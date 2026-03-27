"""
narrative_ingestor.py
Orchestrates the full narrative extraction pipeline and writes the
resulting nodes and arcs into a KnowledgeGraph.

Pipeline
--------
  1. Preprocessing   - spaCy parse, coreference resolution
  2. Clause splitting - sentence segmentation + sub-clause extraction
  3. Node classification - NodeClassifier → EventNode | GoalNode | …
  4. Arc classification  - ArcClassifier  → NarrativeArc
  5. Graph construction  - nodes and arcs written to KnowledgeGraph as Triples

Node → Triple mapping
---------------------
  NarrativeNode attrs  → separate triples from the node id:
    (node_id, "hasAgent",   agent_id)
    (node_id, "hasAction",  action_id)   # events / actions only
    (node_id, "hasPatient", patient_id)  # events / actions only
    (node_id, "hasGoalState", state_id)  # goals only
    (node_id, "nodeType",   type_literal)

  NarrativeArc → one triple:
    (src_id, arc_type.value, dst_id)

Usage
-----
    from narrative_ingestor import NarrativeIngestor
    from knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph()
    ingestor = NarrativeIngestor()

    ingestor.ingest_text(
        "Mary wanted to escape. She climbed the fence, causing the alarm to sound.",
        kg,
        provenance="example"
    )
    print(kg)
    # → KnowledgeGraph(nodes=..., edges=..., by_source={'text': ...})

    # Inspect extracted arcs
    for t in kg.iter_triples():
        if t.predicate in ("Consequence", "Reason", "Manner", "Initiate",
                           "Outcome", "Implies"):
            print(f"  {t.subject} --[{t.predicate}]--> {t.obj}  conf={t.confidence:.2f}")
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import spacy
from spacy.language import Language
from spacy.tokens import Doc, Span

from quest_parsing.arc_classifier import ArcClassifier
from quest_parsing.knowledge_graph import KBSource, KnowledgeGraph, Triple
from quest_parsing.narrative_schema import (
    ArcType,
    NarrativeArc,
    NarrativeNode,
    NodeType,
)
from quest_parsing.node_classifier import NodeClassifier


# ---------------------------------------------------------------------------
# NarrativeIngestor
# ---------------------------------------------------------------------------

class NarrativeIngestor:
    """
    End-to-end pipeline from raw text to a typed narrative KnowledgeGraph.

    Parameters
    ----------
    spacy_model : str
        spaCy model to load (default "en_core_web_sm").
        Recommended: "en_core_web_lg" or "en_core_web_trf" for better
        dependency accuracy, especially on complex sentences.
    namespace : str
        Prefix for generated node IDs.
    arc_window : int
        How many consecutive sentences to consider for arc assignment.
        Default 2: each node is linked to the next node and the one after.
        Increase to 3 for texts with long-distance goal→action separations.
    min_node_confidence : float
        Nodes classified below this threshold are dropped.
    min_arc_confidence : float
        Arcs below this threshold are not written to the graph.
    use_coreference : bool
        Attempt to load coreferee. Degrades gracefully if not installed.
    include_attr_triples : bool
        If True, write auxiliary triples (hasAgent, hasAction, etc.) in
        addition to the arc triples.  Useful for downstream QA retrieval.
    """

    def __init__(
        self,
        spacy_model:          str   = "en_core_web_sm",
        namespace:            str   = "text",
        arc_window:           int   = 2,
        min_node_confidence:  float = 0.50,
        min_arc_confidence:   float = 0.55,
        use_coreference:      bool  = True,
        include_attr_triples: bool  = True,
    ) -> None:
        self.namespace           = namespace
        self.arc_window          = arc_window
        self.min_node_conf       = min_node_confidence
        self.min_arc_conf        = min_arc_confidence
        self.include_attr_triples = include_attr_triples

        self.nlp: Language = spacy.load(spacy_model)

        self._coref_available = False
        if use_coreference:
            try:
                import coreferee  # noqa: F401
                self.nlp.add_pipe("coreferee")
                self._coref_available = True
            except (ImportError, Exception):
                pass

        self._node_clf = NodeClassifier(namespace=namespace)
        self._arc_clf  = ArcClassifier()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def from_text(
        self,
        text: str,
        kg: KnowledgeGraph,
        provenance: str = "",
    ) -> tuple[list[NarrativeNode], list[NarrativeArc]]:
        """
        Extract narrative nodes and arcs from *text* and write them to *kg*.

        Returns the raw (nodes, arcs) lists for inspection or testing.
        """
        doc = self.nlp(text)

        if self._coref_available:
            text = self._resolve_coref(doc)
            doc  = self.nlp(text)

        nodes, spans = self._extract_nodes(doc, provenance)
        arcs         = self._extract_arcs(nodes, spans, provenance)

        self._write_to_graph(nodes, arcs, kg, provenance)
        return nodes, arcs

    def from_file(
        self,
        path: str | Path,
        kg: KnowledgeGraph,
        encoding: str = "utf-8",
        chunk_chars: int = 8_000,
    ) -> tuple[list[NarrativeNode], list[NarrativeArc]]:
        """
        Ingest a plain-text file in chunks.  Returns all nodes and arcs.
        """
        path  = Path(path)
        text  = path.read_text(encoding=encoding)
        prov  = f"file:{path.name}"

        all_nodes: list[NarrativeNode] = []
        all_arcs:  list[NarrativeArc]  = []

        for start in range(0, len(text), chunk_chars):
            chunk = text[start: start + chunk_chars]
            nodes, arcs = self.from_text(chunk, kg, provenance=prov)
            all_nodes.extend(nodes)
            all_arcs.extend(arcs)

        return all_nodes, all_arcs

    def from_sentences(
        self,
        sentences: list[str],
        kg: KnowledgeGraph,
        provenance: str = "",
    ) -> tuple[list[NarrativeNode], list[NarrativeArc]]:
        """Convenience: ingest a pre-split list of sentence strings."""
        return self.from_text(" ".join(sentences), kg, provenance)

    # ------------------------------------------------------------------
    # Stage 1: Node extraction
    # ------------------------------------------------------------------

    def _extract_nodes(
        self,
        doc: Doc,
        provenance: str,
    ) -> tuple[list[NarrativeNode], list[Span]]:
        """
        Classify each sentence (and significant sub-clauses) into nodes.

        Sub-clause splitting: for sentences containing purpose adverbials
        ("in order to …") or concessive clauses we split and classify
        the sub-clause separately so it can receive its own node type.
        """
        nodes: list[NarrativeNode] = []
        spans: list[Span]          = []

        for sent_i, sent in enumerate(doc.sents):
            prov_i = f"{provenance}:s{sent_i}"

            # Attempt sub-clause split first
            sub_spans = self._split_clauses(sent)

            if sub_spans:
                for sub in sub_spans:
                    node = self._node_clf.classify(sub, prov_i, sent_i)
                    if node and node.confidence >= self.min_node_conf:
                        nodes.append(node)
                        spans.append(sub)
            else:
                node = self._node_clf.classify(sent, prov_i, sent_i)
                if node and node.confidence >= self.min_node_conf:
                    nodes.append(node)
                    spans.append(sent)

        return nodes, spans

    def _split_clauses(self, sent: Span) -> list[Span]:
        """
        Detect sentences containing a purpose advcl or xcomp and split
        them into [main clause span, subordinate clause span].

        Returns an empty list if no split is warranted.
        """
        root = sent.root
        split_deps = {"advcl", "xcomp", "ccomp", "relcl"}

        sub_roots = [
            child for child in root.children
            if child.dep_ in split_deps and child.pos_ == "VERB"
        ]
        if not sub_roots:
            return []

        sub_root  = sub_roots[0]
        sub_start = min(t.i for t in sub_root.subtree)
        sub_end   = max(t.i for t in sub_root.subtree) + 1

        # Main clause: everything in sent NOT in the sub-clause subtree
        main_tokens = [
            t for t in sent
            if t.i < sub_start or t.i >= sub_end
        ]
        if not main_tokens:
            return []

        main_span = sent.doc[main_tokens[0].i: main_tokens[-1].i + 1]
        sub_span  = sent.doc[sub_start: sub_end]

        return [main_span, sub_span]

    # ------------------------------------------------------------------
    # Stage 2: Arc extraction
    # ------------------------------------------------------------------

    def _extract_arcs(
        self,
        nodes: list[NarrativeNode],
        spans: list[Span],
        provenance: str,
    ) -> list[NarrativeArc]:
        """Classify arcs across the node sequence."""
        arcs = self._arc_clf.classify_sequence(
            nodes,
            spans=spans,
            provenance=provenance,
            window=self.arc_window,
        )
        return [a for a in arcs if a.confidence >= self.min_arc_conf]

    # ------------------------------------------------------------------
    # Stage 3: Graph construction
    # ------------------------------------------------------------------

    def _write_to_graph(
        self,
        nodes: list[NarrativeNode],
        arcs:  list[NarrativeArc],
        kg:    KnowledgeGraph,
        provenance: str,
    ) -> None:
        """
        Write all nodes and arcs to the KnowledgeGraph as normalised Triples.
        """
        # ── Node type triples ─────────────────────────────────────────
        for node in nodes:
            # Register the node itself
            if not kg.has_node(node.id):
                kg._g.add_node(
                    node.id,
                    label=node.text[:80],
                    type=node.node_type.value,
                    source=KBSource.TEXT.value,
                )
            else:
                kg.set_node_attr(node.id, type=node.node_type.value)

            if not self.include_attr_triples:
                continue

            # nodeType triple
            kg.add_triple(Triple(
                subject=node.id,
                predicate="nodeType",
                obj=f"{self.namespace}:{node.node_type.value}",
                source=KBSource.TEXT,
                confidence=node.confidence,
                provenance=provenance,
            ))

            # hasAgent
            if node.agent:
                kg.add_triple(Triple(
                    subject=node.id,
                    predicate="hasAgent",
                    obj=self._make_literal_id(node.agent),
                    source=KBSource.TEXT,
                    confidence=node.confidence,
                    provenance=provenance,
                ))

            # hasAction / hasGoalState / hasAttribute
            self._write_node_specific_triples(node, kg, provenance)

        # ── Arc triples ───────────────────────────────────────────────
        for arc in arcs:
            kg.add_triple(Triple(
                subject=arc.src_id,
                predicate=arc.arc_type.value,
                obj=arc.dst_id,
                source=KBSource.TEXT,
                confidence=arc.confidence,
                provenance=arc.provenance or provenance,
            ))

    def _write_node_specific_triples(
        self,
        node: NarrativeNode,
        kg:   KnowledgeGraph,
        provenance: str,
    ) -> None:
        """Write type-specific attribute triples for a node."""
        # Import here to avoid circular issues in type-checking
        from quest_parsing.narrative_schema import EventNode, ActionNode, GoalNode, StateNode

        conf = node.confidence

        if isinstance(node, (EventNode, ActionNode)):
            if node.action:
                kg.add_triple(Triple(
                    subject=node.id, predicate="hasAction",
                    obj=self._make_literal_id(node.action),
                    source=KBSource.TEXT, confidence=conf,
                    provenance=provenance,
                ))
            if node.patient:
                kg.add_triple(Triple(
                    subject=node.id, predicate="hasPatient",
                    obj=self._make_literal_id(node.patient),
                    source=KBSource.TEXT, confidence=conf,
                    provenance=provenance,
                ))
            if isinstance(node, ActionNode) and node.instrument:
                kg.add_triple(Triple(
                    subject=node.id, predicate="hasInstrument",
                    obj=self._make_literal_id(node.instrument),
                    source=KBSource.TEXT, confidence=conf,
                    provenance=provenance,
                ))
            if isinstance(node, EventNode) and node.time_ref:
                kg.add_triple(Triple(
                    subject=node.id, predicate="hasTimeRef",
                    obj=self._make_literal_id(node.time_ref),
                    source=KBSource.TEXT, confidence=conf,
                    provenance=provenance,
                ))

        elif isinstance(node, GoalNode):
            if node.goal_state:
                kg.add_triple(Triple(
                    subject=node.id, predicate="hasGoalState",
                    obj=self._make_literal_id(node.goal_state),
                    source=KBSource.TEXT, confidence=conf,
                    provenance=provenance,
                ))
            if node.motivation:
                kg.add_triple(Triple(
                    subject=node.id, predicate="hasMotivation",
                    obj=self._make_literal_id(node.motivation),
                    source=KBSource.TEXT, confidence=conf,
                    provenance=provenance,
                ))

        elif isinstance(node, StateNode):
            if node.attribute:
                kg.add_triple(Triple(
                    subject=node.id, predicate="hasAttribute",
                    obj=self._make_literal_id(node.attribute),
                    source=KBSource.TEXT, confidence=conf,
                    provenance=provenance,
                ))

    # ------------------------------------------------------------------
    # Coreference resolution
    # ------------------------------------------------------------------

    def _resolve_coref(self, doc: Doc) -> str:
        """Replace pronouns with their antecedent head noun."""
        if not self._coref_available or not doc._.has("coref_chains"):
            return doc.text

        tokens = [t.text_with_ws for t in doc]
        for chain in doc._.coref_chains:
            if not chain:
                continue
            head_tok    = doc[chain[0].root_index]
            replacement = head_tok.text
            for mention in chain[1:]:
                span = doc[mention.root_index]
                if span.pos_ == "PRON":
                    tokens[span.i] = replacement + span.whitespace_
        return "".join(tokens)

    # ------------------------------------------------------------------
    # ID helpers
    # ------------------------------------------------------------------

    def _make_literal_id(self, text: str) -> str:
        """Stable node id for a literal value (agent name, verb lemma, etc.)."""
        import re, hashlib
        slug = re.sub(r"\s+", "_", text[:40].lower().strip())
        slug = re.sub(r"[^\w_]", "", slug)
        return f"{self.namespace}:{slug}"
