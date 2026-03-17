"""
api_ingestor.py
Ingestor for the ConceptNet REST API.

Pulls edges for one or more concept terms and converts them to the
normalised Triple schema understood by KnowledgeGraph.

ConceptNet edge structure (abbreviated):
{
  "@id":   "/a/[/r/Causes/,/c/en/fire/,/c/en/smoke/]",
  "rel":   {"@id": "/r/Causes",   "label": "Causes"},
  "start": {"@id": "/c/en/fire",  "label": "fire",  "language": "en"},
  "end":   {"@id": "/c/en/smoke", "label": "smoke", "language": "en"},
  "weight": 4.47,
  "surfaceText": "Fire causes smoke."
}

Usage
-----
    from api_ingestor import ConceptNetIngestor
    from knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph()
    ingestor = ConceptNetIngestor(language="en")
    triples = ingestor.fetch("fire", limit=50)
    kg.add_triples(triples)
    print(kg)
"""

from __future__ import annotations

import time
from typing import Optional
from urllib.parse import quote

import requests

from knowledge_graph import KBSource, Triple


# ---------------------------------------------------------------------------
# Relation mapping:  ConceptNet relation  →  QUEST question-category hint
# (stored as predicate so the answer generator can filter efficiently)
# ---------------------------------------------------------------------------

CONCEPTNET_PREDICATE_MAP: dict[str, str] = {
    "/r/IsA":              "IsA",
    "/r/PartOf":           "PartOf",
    "/r/HasA":             "HasA",
    "/r/UsedFor":          "UsedFor",
    "/r/CapableOf":        "CapableOf",
    "/r/AtLocation":       "AtLocation",
    "/r/Causes":           "Causes",
    "/r/HasProperty":      "HasProperty",
    "/r/MotivatedByGoal":  "MotivatedByGoal",
    "/r/ObstructedBy":     "ObstructedBy",
    "/r/Desires":          "Desires",
    "/r/CreatedBy":        "CreatedBy",
    "/r/DefinedAs":        "DefinedAs",
    "/r/SymbolOf":         "SymbolOf",
    "/r/HasContext":       "HasContext",
    "/r/SimilarTo":        "SimilarTo",
    "/r/RelatedTo":        "RelatedTo",
    "/r/Antonym":          "Antonym",
    "/r/DistinctFrom":     "DistinctFrom",
    "/r/HasFirstSubevent": "HasFirstSubevent",
    "/r/HasLastSubevent":  "HasLastSubevent",
    "/r/HasPrerequisite":  "HasPrerequisite",
    "/r/HasSubevent":      "HasSubevent",
    "/r/CausesDesire":     "CausesDesire",
    "/r/MadeOf":           "MadeOf",
    "/r/ReceivesAction":   "ReceivesAction",
    "/r/Synonym":          "Synonym",
    "/r/ExternalURL":      "ExternalURL",
    "/r/FormOf":           "FormOf",
    "/r/DerivedFrom":      "DerivedFrom",
}

# Maximum weight ConceptNet returns; used to normalise to [0, 1].
_MAX_CN_WEIGHT = 10.0
_BASE_URL = "https://api.conceptnet.io"


class ConceptNetIngestor:
    """
    Fetches edges from the ConceptNet REST API for one or more concepts and
    converts them into normalised Triples.

    Parameters
    ----------
    language : str
        BCP-47 language tag (default "en").
    min_weight : float
        ConceptNet edges below this raw weight are discarded (default 1.0).
    request_delay : float
        Seconds to sleep between paginated requests to avoid rate-limiting.
    session : requests.Session | None
        Inject a custom session (useful for testing with a mock).
    """

    def __init__(
        self,
        language: str = "en",
        min_weight: float = 1.0,
        request_delay: float = 0.25,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.language = language
        self.min_weight = min_weight
        self.request_delay = request_delay
        self._session = session or requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(
        self,
        term: str,
        limit: int = 100,
        relation: Optional[str] = None,
    ) -> list[Triple]:
        """
        Fetch edges for *term* from ConceptNet and return normalised triples.

        Parameters
        ----------
        term : str
            A plain English word or phrase (spaces replaced with underscores
            internally).
        limit : int
            Maximum edges to retrieve (paginated in pages of 20).
        relation : str | None
            If given, restrict to a specific ConceptNet relation, e.g.
            "/r/Causes" or "Causes".

        Returns
        -------
        list[Triple]
        """
        triples: list[Triple] = []
        node_uri = self._term_to_uri(term)
        url = f"{_BASE_URL}/c/{self.language}/{node_uri}"

        params: dict = {"limit": min(limit, 1000)}
        if relation:
            if not relation.startswith("/r/"):
                relation = f"/r/{relation}"
            params["rel"] = relation

        fetched = 0
        while url and fetched < limit:
            params["offset"] = fetched
            data = self._get(url, params)
            if data is None:
                break

            edges = data.get("edges", [])
            if not edges:
                break

            for edge in edges:
                t = self._edge_to_triple(edge, term)
                if t is not None:
                    triples.append(t)

            fetched += len(edges)
            url = data.get("view", {}).get("nextPage")
            if url:
                url = _BASE_URL + url
                params = {}      # nextPage URL already contains all params
            time.sleep(self.request_delay)

        return triples

    def fetch_many(
        self,
        terms: list[str],
        limit_per_term: int = 50,
    ) -> list[Triple]:
        """Fetch edges for multiple terms and merge into a single list."""
        all_triples: list[Triple] = []
        seen: set[tuple] = set()

        for term in terms:
            for t in self.fetch(term, limit=limit_per_term):
                key = (t.subject, t.predicate, t.obj)
                if key not in seen:
                    seen.add(key)
                    all_triples.append(t)

        return all_triples

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: dict) -> Optional[dict]:
        try:
            resp = self._session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            print(f"[ConceptNetIngestor] HTTP error for {url}: {exc}")
            return None

    def _term_to_uri(self, term: str) -> str:
        """'ice cream' → 'ice_cream', then percent-encode."""
        return quote(term.lower().replace(" ", "_"))

    def _node_id(self, cn_node: dict) -> str:
        """
        Produce a stable, namespaced node id from a ConceptNet node dict.
        e.g. "/c/en/fire/n" → "world:fire"
        We strip the language and POS suffix; the label retains them.
        """
        raw_id: str = cn_node.get("@id", "")
        parts = raw_id.strip("/").split("/")
        # parts: ["c", lang, term, (optional pos)]
        term = parts[2] if len(parts) >= 3 else raw_id
        return f"world:{term}"

    def _normalise_weight(self, weight: float) -> float:
        """Map ConceptNet weight [0, ~10] → confidence [0, 1]."""
        return min(max(weight / _MAX_CN_WEIGHT, 0.0), 1.0)

    def _edge_to_triple(self, edge: dict, query_term: str) -> Optional[Triple]:
        """Convert one ConceptNet edge dict to a Triple, or None to skip."""
        weight = edge.get("weight", 0.0)
        if weight < self.min_weight:
            return None

        start_node = edge.get("start", {})
        end_node   = edge.get("end", {})
        rel_id     = edge.get("rel", {}).get("@id", "")

        # Only keep edges where at least one side is in our language
        start_lang = start_node.get("language", "")
        end_lang   = end_node.get("language", "")
        if start_lang != self.language and end_lang != self.language:
            return None

        predicate  = CONCEPTNET_PREDICATE_MAP.get(rel_id, rel_id.split("/")[-1])
        subject_id = self._node_id(start_node)
        object_id  = self._node_id(end_node)
        confidence = self._normalise_weight(weight)
        provenance = f"conceptnet:{edge.get('@id', '')}"

        return Triple(
            subject=subject_id,
            predicate=predicate,
            obj=object_id,
            source=KBSource.WORLD,
            confidence=confidence,
            provenance=provenance,
        )


# ---------------------------------------------------------------------------
# Convenience wrapper for node metadata enrichment
# ---------------------------------------------------------------------------

def enrich_node_labels(
    kg,              # KnowledgeGraph instance
    ingestor: ConceptNetIngestor,
) -> None:
    """
    For every world-sourced node in *kg*, fetch its ConceptNet label and
    update the node's 'label' attribute.  Call after bulk ingestion.
    """
    for node_id in list(kg._g.nodes):
        if not node_id.startswith("world:"):
            continue
        attrs = kg.node_attr(node_id)
        if attrs.get("label", node_id) != node_id:
            continue   # already has a real label

        term = node_id.replace("world:", "")
        uri  = f"{_BASE_URL}/c/{ingestor.language}/{ingestor._term_to_uri(term)}"
        data = ingestor._get(uri, {})
        if data:
            label = data.get("label", term)
            kg.set_node_attr(node_id, label=label, type="concept")
        time.sleep(ingestor.request_delay)
