"""
schema_ingestor.py
Ingestor for structured domain knowledge sources.

Supports four formats:
  - CSV  : rows become entity nodes; column pairs become edges
  - JSON : flat records, JSON-LD, or arbitrary nested objects
  - SQL  : any SQLAlchemy-compatible DB (SQLite, PostgreSQL, …)
  - OWL  : OWL/RDF ontologies via rdflib

All results are converted to the normalised Triple schema so the
KnowledgeGraph receives a uniform representation regardless of source.

Usage
-----
    from schema_ingestor import SchemaIngestor
    from knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph()
    ingestor = SchemaIngestor(namespace="bio")

    # CSV: treat 'name' column as subject id, 'function' as literal object
    triples = ingestor.from_csv(
        "organelles.csv",
        subject_col="name",
        triples_spec=[("function", "HasFunction"), ("location", "AtLocation")],
    )
    kg.add_triples(triples)
"""

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from knowledge_graph import KBSource, Triple


# ---------------------------------------------------------------------------
# SchemaIngestor
# ---------------------------------------------------------------------------

class SchemaIngestor:
    """
    Converts structured domain data into normalised Triples.

    Parameters
    ----------
    namespace : str
        Short prefix used to disambiguate entity IDs, e.g. "bio" gives
        nodes like "bio:mitochondria".
    default_confidence : float
        Confidence assigned to all schema-derived triples (default 0.9 —
        structured data is considered reliable but lower than 1.0 to allow
        world KB facts to override when confidence is compared).
    """

    def __init__(
        self,
        namespace: str = "domain",
        default_confidence: float = 0.9,
    ) -> None:
        self.namespace = namespace
        self.default_confidence = default_confidence

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    def from_csv(
        self,
        path: str | Path,
        subject_col: str,
        triples_spec: list[tuple[str, str]],
        delimiter: str = ",",
        skip_empty: bool = True,
        provenance: str = "",
    ) -> list[Triple]:
        """
        Ingest a CSV file.

        Parameters
        ----------
        path : str | Path
            Path to the CSV file.
        subject_col : str
            Name of the column whose value becomes the subject node id.
        triples_spec : list of (column_name, predicate) pairs
            Each pair maps one CSV column to an edge predicate.
            e.g. [("function", "HasFunction"), ("location", "AtLocation")]
        delimiter : str
            CSV field delimiter (default ",").
        skip_empty : bool
            Skip rows where the object cell is empty.
        provenance : str
            Optional provenance string stored on each triple.

        Returns
        -------
        list[Triple]
        """
        path = Path(path)
        provenance = provenance or f"file:{path.name}"
        triples: list[Triple] = []

        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            for row in reader:
                subject_val = row.get(subject_col, "").strip()
                if not subject_val:
                    continue

                subject_id = self._make_id(subject_val)
                for col_name, predicate in triples_spec:
                    obj_val = row.get(col_name, "").strip()
                    if skip_empty and not obj_val:
                        continue

                    obj_id = self._make_id(obj_val)
                    triples.append(Triple(
                        subject=subject_id,
                        predicate=predicate,
                        obj=obj_id,
                        source=KBSource.DOMAIN,
                        confidence=self.default_confidence,
                        provenance=provenance,
                    ))

        return triples

    def from_csv_hierarchy(
        self,
        path: str | Path,
        child_col: str,
        parent_col: str,
        predicate: str = "IsA",
        delimiter: str = ",",
        provenance: str = "",
    ) -> list[Triple]:
        """
        Convenience method: ingest a CSV with a parent→child taxonomy column.
        Every row emits a single (child) -[IsA]-> (parent) edge.
        """
        path = Path(path)
        provenance = provenance or f"file:{path.name}"
        triples: list[Triple] = []

        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            for row in reader:
                child  = row.get(child_col, "").strip()
                parent = row.get(parent_col, "").strip()
                if not child or not parent:
                    continue
                triples.append(Triple(
                    subject=self._make_id(child),
                    predicate=predicate,
                    obj=self._make_id(parent),
                    source=KBSource.DOMAIN,
                    confidence=self.default_confidence,
                    provenance=provenance,
                ))

        return triples

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def from_json(
        self,
        path: str | Path,
        subject_key: str,
        triples_spec: list[tuple[str, str]],
        records_key: Optional[str] = None,
        provenance: str = "",
    ) -> list[Triple]:
        """
        Ingest a JSON file containing a list of objects.

        Parameters
        ----------
        path : str | Path
        subject_key : str
            Key whose value becomes the subject node.
        triples_spec : list of (key, predicate) pairs
        records_key : str | None
            If the JSON root is an object, the key whose value is the list
            of records.  If None, the root itself must be a list.
        provenance : str
        """
        path = Path(path)
        provenance = provenance or f"file:{path.name}"

        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh)

        records = raw[records_key] if records_key else raw
        if not isinstance(records, list):
            raise ValueError(
                f"Expected a list of records; got {type(records).__name__}. "
                "Pass records_key if the list is nested."
            )

        triples: list[Triple] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            subject_val = record.get(subject_key, "")
            if not subject_val:
                continue

            subject_id = self._make_id(str(subject_val))
            for key, predicate in triples_spec:
                obj_val = record.get(key)
                if obj_val is None:
                    continue

                # Scalar or list value
                values = obj_val if isinstance(obj_val, list) else [obj_val]
                for v in values:
                    obj_id = self._make_id(str(v))
                    triples.append(Triple(
                        subject=subject_id,
                        predicate=predicate,
                        obj=obj_id,
                        source=KBSource.DOMAIN,
                        confidence=self.default_confidence,
                        provenance=provenance,
                    ))

        return triples

    def from_json_ld(
        self,
        path: str | Path,
        provenance: str = "",
    ) -> list[Triple]:
        """
        Lightweight JSON-LD ingestor.
        Handles @graph arrays and simple @type / property dicts.
        Does NOT implement the full JSON-LD processing algorithm — use
        rdflib for that; this covers the common case of hand-authored files.
        """
        path = Path(path)
        provenance = provenance or f"file:{path.name}"

        with path.open(encoding="utf-8") as fh:
            doc = json.load(fh)

        nodes = doc.get("@graph", [doc])
        triples: list[Triple] = []

        for node in nodes:
            if "@id" not in node:
                continue
            subject_id = self._iri_to_id(node["@id"])

            for key, value in node.items():
                if key.startswith("@"):
                    continue
                predicate = self._iri_to_predicate(key)
                values = value if isinstance(value, list) else [value]
                for v in values:
                    if isinstance(v, dict):
                        obj_id = self._iri_to_id(v.get("@id", str(v)))
                    else:
                        obj_id = self._make_id(str(v))
                    triples.append(Triple(
                        subject=subject_id,
                        predicate=predicate,
                        obj=obj_id,
                        source=KBSource.DOMAIN,
                        confidence=self.default_confidence,
                        provenance=provenance,
                    ))

        return triples

    # ------------------------------------------------------------------
    # SQL  (requires sqlalchemy)
    # ------------------------------------------------------------------

    def from_sql(
        self,
        connection_string: str,
        query: str,
        subject_col: str,
        triples_spec: list[tuple[str, str]],
        provenance: str = "",
    ) -> list[Triple]:
        """
        Execute *query* against any SQLAlchemy-compatible database and
        ingest the result set as triples.

        Parameters
        ----------
        connection_string : str
            SQLAlchemy URL, e.g. "sqlite:///facts.db" or
            "postgresql://user:pass@host/db".
        query : str
            Raw SQL SELECT statement.
        subject_col, triples_spec : same semantics as from_csv.
        """
        try:
            import sqlalchemy as sa
        except ImportError as exc:
            raise ImportError(
                "sqlalchemy is required for SQL ingestion. "
                "Install it with: pip install sqlalchemy"
            ) from exc

        provenance = provenance or f"sql:{connection_string.split('//')[0]}"
        engine = sa.create_engine(connection_string)
        triples: list[Triple] = []

        with engine.connect() as conn:
            result = conn.execute(sa.text(query))
            columns = list(result.keys())
            for row in result:
                row_dict = dict(zip(columns, row))
                subject_val = str(row_dict.get(subject_col, "")).strip()
                if not subject_val:
                    continue

                subject_id = self._make_id(subject_val)
                for col_name, predicate in triples_spec:
                    obj_val = row_dict.get(col_name)
                    if obj_val is None:
                        continue
                    obj_id = self._make_id(str(obj_val).strip())
                    triples.append(Triple(
                        subject=subject_id,
                        predicate=predicate,
                        obj=obj_id,
                        source=KBSource.DOMAIN,
                        confidence=self.default_confidence,
                        provenance=provenance,
                    ))

        return triples

    # ------------------------------------------------------------------
    # OWL / RDF  (requires rdflib)
    # ------------------------------------------------------------------

    def from_owl(
        self,
        path: str | Path,
        format: str = "xml",
        provenance: str = "",
        include_annotation_properties: bool = False,
    ) -> list[Triple]:
        """
        Ingest an OWL ontology using rdflib.

        Extracts:
          - rdfs:subClassOf  → "IsA"
          - rdfs:subPropertyOf → "IsA"
          - owl:equivalentClass → "SimilarTo"
          - rdf:type        → "InstanceOf"
          - All object properties → predicate label
          - All data properties  → predicate label (if include_annotation_properties)

        Parameters
        ----------
        path : str | Path
        format : str
            rdflib format string: "xml" (OWL/RDF-XML), "turtle", "n3",
            "nt", "json-ld", etc.
        """
        try:
            import rdflib
            from rdflib import RDF, RDFS, OWL, namespace as rdfns
        except ImportError as exc:
            raise ImportError(
                "rdflib is required for OWL ingestion. "
                "Install it with: pip install rdflib"
            ) from exc

        path = Path(path)
        provenance = provenance or f"file:{path.name}"
        g = rdflib.Graph()
        g.parse(str(path), format=format)

        triples: list[Triple] = []

        PREDICATE_LABEL_MAP = {
            str(RDFS.subClassOf):       "IsA",
            str(RDFS.subPropertyOf):    "IsA",
            str(OWL.equivalentClass):   "SimilarTo",
            str(RDF.type):              "InstanceOf",
            str(OWL.disjointWith):      "DisjointWith",
            str(OWL.sameAs):            "SameAs",
        }

        for subj, pred, obj in g:
            pred_str = str(pred)
            mapped   = PREDICATE_LABEL_MAP.get(pred_str)

            # Skip annotation/data properties unless explicitly requested
            if mapped is None and not include_annotation_properties:
                continue

            predicate = mapped or self._iri_to_predicate(pred_str)
            subject_id = self._iri_to_id(str(subj))
            obj_id     = self._iri_to_id(str(obj))

            # Skip blank nodes and non-URI objects
            if subject_id.startswith("_:") or obj_id.startswith("_:"):
                continue

            triples.append(Triple(
                subject=subject_id,
                predicate=predicate,
                obj=obj_id,
                source=KBSource.DOMAIN,
                confidence=self.default_confidence,
                provenance=provenance,
            ))

        return triples

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_id(self, value: str) -> str:
        """Produce a stable, namespaced node id from a string value."""
        slug = re.sub(r"\s+", "_", value.lower().strip())
        slug = re.sub(r"[^\w_-]", "", slug)
        return f"{self.namespace}:{slug}"

    def _iri_to_id(self, iri: str) -> str:
        """
        Convert an IRI to a namespaced id.
        "http://purl.obolibrary.org/obo/GO_0005739" → "domain:GO_0005739"
        """
        fragment = iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        return f"{self.namespace}:{fragment}"

    def _iri_to_predicate(self, iri: str) -> str:
        """Extract a human-readable predicate label from an IRI."""
        fragment = iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        # CamelCase → keep as-is for QUEST category matching
        return fragment
