"""
arc_classifier.py
Assigns QUEST arc types between pairs of NarrativeNodes.

Classification runs a four-level cascade:

  Level 1 - Intra-sentence discourse connectives
             (strongest signal; nearly unambiguous)
  Level 2 - Inter-sentence discourse markers
             (sentence-initial connectives like "Therefore", "As a result")
  Level 3 - Shared-agent / agentive-overlap heuristics
             (distinguishes Manner from Consequence)
  Level 4 - Default arc from the node-type pair table in narrative_schema.py

Each level can override the one below it.  The cascade stops at the first
level that produces a confidence ≥ the acceptance threshold (default 0.70).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from spacy.tokens import Span

from quest_parsing.narrative_schema import (
    ArcType,
    DEFAULT_ARC,
    NarrativeArc,
    NarrativeNode,
    NodeType,
    arc_is_valid,
)


# ---------------------------------------------------------------------------
# Discourse cue tables
# ---------------------------------------------------------------------------

# Intra-sentence connectives → (ArcType, confidence)
# Keys are compiled regex patterns applied to the *full sentence text*.
INTRA_SENTENCE_CUES: list[tuple[re.Pattern, ArcType, float]] = [
    # Manner
    (re.compile(r"\bby\s+\w+ing\b",              re.I), ArcType.MANNER,      0.90),
    (re.compile(r"\bthrough\s+\w+ing\b",         re.I), ArcType.MANNER,      0.85),
    (re.compile(r"\busing\b",                    re.I), ArcType.MANNER,      0.75),
    (re.compile(r"\bvia\b",                      re.I), ArcType.MANNER,      0.75),
    # Reason / Goal
    (re.compile(r"\bin\s+order\s+to\b",          re.I), ArcType.REASON,      0.95),
    (re.compile(r"\bso\s+(?:as\s+)?to\b",        re.I), ArcType.REASON,      0.90),
    (re.compile(r"\bso\s+that\b",                re.I), ArcType.REASON,      0.90),
    (re.compile(r"\bfor\s+the\s+purpose\s+of\b", re.I), ArcType.REASON,      0.90),
    (re.compile(r"\bin\s+hopes?\s+(?:of|to)\b",  re.I), ArcType.REASON,      0.85),
    # Consequence / Causal
    (re.compile(r"\bcausing\b",                  re.I), ArcType.CONSEQUENCE, 0.90),
    (re.compile(r"\bleading\s+to\b",             re.I), ArcType.CONSEQUENCE, 0.88),
    (re.compile(r"\bresulting\s+in\b",           re.I), ArcType.CONSEQUENCE, 0.88),
    (re.compile(r"\btriggering\b",               re.I), ArcType.CONSEQUENCE, 0.85),
    (re.compile(r"\bmaking\s+\w+",               re.I), ArcType.CONSEQUENCE, 0.70),
    # Outcome
    (re.compile(r"\bwhich\s+(?:left|made|rendered)\b", re.I), ArcType.OUTCOME, 0.85),
    # Initiate
    (re.compile(r"\bprompting\b",                re.I), ArcType.INITIATE,    0.85),
    (re.compile(r"\binspiring\b",                re.I), ArcType.INITIATE,    0.82),
    (re.compile(r"\bmotivating\b",               re.I), ArcType.INITIATE,    0.82),
    # Implies
    (re.compile(r"\bimplying\b",                 re.I), ArcType.IMPLIES,     0.85),
    (re.compile(r"\bmeaning\s+that\b",           re.I), ArcType.IMPLIES,     0.85),
    (re.compile(r"\bsuggest(?:ing)?\s+that\b",   re.I), ArcType.IMPLIES,     0.75),
]

# Inter-sentence markers (applied to the *start* of the second sentence)
INTER_SENTENCE_CUES: list[tuple[re.Pattern, ArcType, float]] = [
    # Consequence
    (re.compile(r"^(?:Therefore|Thus|Hence|Consequently|As\s+a\s+result)",
                re.I), ArcType.CONSEQUENCE, 0.90),
    (re.compile(r"^(?:This\s+(?:caused|led|resulted|triggered))",
                re.I), ArcType.CONSEQUENCE, 0.88),
    (re.compile(r"^(?:So\b)",                      re.I), ArcType.CONSEQUENCE, 0.75),
    # Reason
    (re.compile(r"^(?:Because|Since|As\b)",        re.I), ArcType.REASON,      0.82),
    (re.compile(r"^(?:In\s+order\s+to)",           re.I), ArcType.REASON,      0.90),
    # Outcome
    (re.compile(r"^(?:As\s+a\s+(?:result|consequence))", re.I), ArcType.OUTCOME, 0.88),
    (re.compile(r"^(?:Afterwards?|Subsequently)",  re.I), ArcType.OUTCOME,     0.80),
    # Initiate
    (re.compile(r"^(?:This\s+(?:prompted|motivated|inspired|encouraged))",
                re.I), ArcType.INITIATE,    0.88),
    # Implies
    (re.compile(r"^(?:This\s+(?:means?|implies?|suggests?))",
                re.I), ArcType.IMPLIES,     0.85),
    (re.compile(r"^(?:If\b)",                      re.I), ArcType.IMPLIES,     0.78),
    # Manner
    (re.compile(r"^(?:By\s+doing\s+this|In\s+this\s+way)",
                re.I), ArcType.MANNER,      0.85),
]


# ---------------------------------------------------------------------------
# ArcClassifier
# ---------------------------------------------------------------------------

class ArcClassifier:
    """
    Assigns a QUEST arc type to an ordered pair of NarrativeNodes.

    Parameters
    ----------
    confidence_threshold : float
        Minimum confidence required to accept a cue-based arc.
        Falls back to default arc table when no cue clears this threshold.
    """

    def __init__(self, confidence_threshold: float = 0.70) -> None:
        self.threshold = confidence_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(
        self,
        src: NarrativeNode,
        dst: NarrativeNode,
        src_span: Optional[Span] = None,
        dst_span: Optional[Span] = None,
        provenance: str = "",
    ) -> Optional[NarrativeArc]:
        """
        Classify the arc between *src* and *dst*.

        Parameters
        ----------
        src, dst : NarrativeNode
            The two nodes (ordered: src → dst).
        src_span, dst_span : spacy Span | None
            The original parsed spans; used for richer cue extraction.
        provenance : str
            Propagated to the resulting NarrativeArc.

        Returns
        -------
        NarrativeArc | None
            None if no valid arc can be assigned.
        """
        # Level 1 - intra-sentence cues (both nodes from the same sentence)
        if src_span is not None and dst_span is not None:
            if src_span.sent == dst_span.sent:
                result = self._intra_sentence(src, dst, src_span, provenance)
                if result:
                    return result

        # Level 2 - inter-sentence cues (look at the start of dst_span's sent)
        if dst_span is not None:
            result = self._inter_sentence(src, dst, dst_span, provenance)
            if result:
                return result

        # Level 3 - shared-agent heuristic (Manner vs Consequence)
        if src_span is not None and dst_span is not None:
            result = self._shared_agent_heuristic(src, dst, provenance)
            if result:
                return result

        # Level 4 - default from node-type pair table
        return self._default_arc(src, dst, provenance)

    def classify_sequence(
        self,
        nodes: list[NarrativeNode],
        spans: Optional[list[Span]] = None,
        provenance: str = "",
        window: int = 2,
    ) -> list[NarrativeArc]:
        """
        Classify arcs across a sequence of nodes using a sliding window.

        Parameters
        ----------
        nodes : list[NarrativeNode]
            Ordered list of nodes (sentence order).
        spans : list[Span] | None
            Corresponding spaCy spans (same length as nodes).
        window : int
            How many steps ahead to consider for arc assignment (default 2).
            Window > 1 catches long-distance arcs like goal→action separated
            by an intervening state description.

        Returns
        -------
        list[NarrativeArc]
        """
        arcs: list[NarrativeArc] = []

        for i, src in enumerate(nodes):
            for j in range(i + 1, min(i + 1 + window, len(nodes))):
                dst = nodes[j]

                src_span = spans[i] if spans else None
                dst_span = spans[j] if spans else None

                arc = self.classify(src, dst, src_span, dst_span, provenance)
                if arc:
                    arcs.append(arc)

                # Don't skip over a goal node — it must participate
                # in a Reason arc before the chain continues
                if (
                    j == i + 1
                    and dst.node_type == NodeType.GOAL
                    and window > 1
                ):
                    break   # force the next iteration to start from the goal

        return arcs

    # ------------------------------------------------------------------
    # Cascade levels
    # ------------------------------------------------------------------

    def _intra_sentence(
        self,
        src: NarrativeNode,
        dst: NarrativeNode,
        span: Span,
        provenance: str,
    ) -> Optional[NarrativeArc]:
        """Check intra-sentence discourse cues."""
        text = span.text

        best_arc:  Optional[ArcType] = None
        best_conf: float             = 0.0
        best_cue:  str               = ""

        for pattern, arc_type, conf in INTRA_SENTENCE_CUES:
            if conf <= best_conf:
                continue
            m = pattern.search(text)
            if m and arc_is_valid(arc_type, src, dst):
                best_arc  = arc_type
                best_conf = conf
                best_cue  = m.group(0)

        if best_arc and best_conf >= self.threshold:
            return NarrativeArc(
                src_id=src.id,
                dst_id=dst.id,
                arc_type=best_arc,
                confidence=best_conf,
                cue=best_cue,
                provenance=provenance,
            )
        return None

    def _inter_sentence(
        self,
        src: NarrativeNode,
        dst: NarrativeNode,
        dst_span: Span,
        provenance: str,
    ) -> Optional[NarrativeArc]:
        """Check the beginning of the destination sentence for discourse markers."""
        sent_text = dst_span.sent.text.strip()

        best_arc:  Optional[ArcType] = None
        best_conf: float             = 0.0
        best_cue:  str               = ""

        for pattern, arc_type, conf in INTER_SENTENCE_CUES:
            if conf <= best_conf:
                continue
            m = pattern.match(sent_text)
            if m and arc_is_valid(arc_type, src, dst):
                best_arc  = arc_type
                best_conf = conf
                best_cue  = m.group(0)

        if best_arc and best_conf >= self.threshold:
            return NarrativeArc(
                src_id=src.id,
                dst_id=dst.id,
                arc_type=best_arc,
                confidence=best_conf,
                cue=best_cue,
                provenance=provenance,
            )
        return None

    def _shared_agent_heuristic(
        self,
        src: NarrativeNode,
        dst: NarrativeNode,
        provenance: str,
    ) -> Optional[NarrativeArc]:
        """
        Distinguish Manner from Consequence using agent overlap.

        Manner requires the same agent performing both events.
        If agents match and both nodes are Action/Event, prefer Manner
        over the default Consequence — but only at moderate confidence
        since this heuristic can misfire on narrative re-mention.
        """
        if src.node_type not in (NodeType.ACTION, NodeType.EVENT):
            return None
        if dst.node_type not in (NodeType.ACTION, NodeType.EVENT):
            return None
        if not src.agent or not dst.agent:
            return None

        # Normalise agent strings for comparison
        def norm(s: str) -> str:
            return s.lower().strip().split()[0]   # head word comparison

        if norm(src.agent) == norm(dst.agent):
            # Same agent: lean toward Manner (one action as method of another)
            if arc_is_valid(ArcType.MANNER, src, dst):
                return NarrativeArc(
                    src_id=src.id,
                    dst_id=dst.id,
                    arc_type=ArcType.MANNER,
                    confidence=0.68,
                    cue="shared-agent heuristic",
                    provenance=provenance,
                )

        return None

    def _default_arc(
        self,
        src: NarrativeNode,
        dst: NarrativeNode,
        provenance: str,
    ) -> Optional[NarrativeArc]:
        """Fall back to the DEFAULT_ARC table from narrative_schema.py."""
        key = (src.node_type, dst.node_type)
        arc_type = DEFAULT_ARC.get(key)
        if arc_type is None:
            return None

        return NarrativeArc(
            src_id=src.id,
            dst_id=dst.id,
            arc_type=arc_type,
            confidence=0.55,   # low confidence: no cue evidence
            cue="default",
            provenance=provenance,
        )
