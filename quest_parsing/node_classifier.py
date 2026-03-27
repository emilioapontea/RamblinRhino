"""
node_classifier.py
Classifies a parsed spaCy clause (sentence or subordinate clause) into
one of four narrative node types: Event, Action, Goal, or State.

Classification is a priority-ordered cascade:

  Priority 1 - Goal cues (strongest signal; goal clauses have
                distinctive syntactic markers that rarely appear otherwise)
  Priority 2 - Action cues (intentional, agentive, goal-directed verbs)
  Priority 3 - State cues  (stative verbs, copular clauses)
  Priority 4 - Event       (default for all remaining dynamic clauses)

Each classifier returns a (NodeType, confidence, fields_dict) triple so
the NarrativeIngestor can build the right NarrativeNode subclass.
"""

from __future__ import annotations

import re
import hashlib
import time
from typing import Optional

import spacy
from spacy.tokens import Span, Token

from quest_parsing.narrative_schema import (
    NodeType,
    EventNode,
    ActionNode,
    GoalNode,
    StateNode,
    NarrativeNode,
)


# ---------------------------------------------------------------------------
# Lexicons
# ---------------------------------------------------------------------------

# Verbs whose lemma strongly indicates a goal-directed (intentional) action
ACTION_VERB_LEMMAS: frozenset[str] = frozenset({
    "attempt", "try", "seek", "plan", "decide", "choose", "intend",
    "manage", "succeed", "fail", "strive", "aim", "pursue", "achieve",
    "accomplish", "execute", "perform", "carry", "undertake",
    "attack", "defend", "escape", "flee", "hide", "steal", "help",
    "rescue", "destroy", "build", "create", "write", "send", "give",
    "take", "bring", "move", "travel", "go", "come", "leave", "enter",
    "open", "close", "push", "pull", "lift", "throw", "catch",
})

# Verbs that signal a goal / desire state
GOAL_VERB_LEMMAS: frozenset[str] = frozenset({
    "want", "wish", "desire", "hope", "need", "require", "expect",
    "intend", "plan", "decide", "choose", "prefer", "long", "yearn",
    "aspire", "aim", "seek",
})

# Stative verbs → StateNode
STATIVE_VERB_LEMMAS: frozenset[str] = frozenset({
    "be", "have", "contain", "consist", "include", "involve",
    "remain", "stay", "keep", "seem", "appear", "look", "feel",
    "sound", "smell", "taste", "weigh", "measure", "cost", "equal",
    "resemble", "lack", "own", "possess", "know", "understand",
    "believe", "think", "suppose", "realise", "recognize",
    "remember", "forget", "love", "hate", "like", "dislike",
    "belong", "stand", "sit", "lie",
})

# Discourse markers that introduce a goal / purpose clause
GOAL_DISCOURSE_MARKERS: tuple[re.Pattern, ...] = (
    re.compile(r"\bin\s+order\s+to\b", re.I),
    re.compile(r"\bso\s+(?:as\s+)?to\b", re.I),
    re.compile(r"\bso\s+that\b", re.I),
    re.compile(r"\bin\s+hopes?\s+(?:of|to)\b", re.I),
    re.compile(r"\bwith\s+the\s+(?:goal|aim|intention|purpose)\s+of\b", re.I),
    re.compile(r"\bfor\s+the\s+purpose\s+of\b", re.I),
)

# Manner markers (signal ActionNode used as instrument of another action)
MANNER_MARKERS: tuple[re.Pattern, ...] = (
    re.compile(r"\bby\s+\w+ing\b", re.I),
    re.compile(r"\bthrough\s+\w+ing\b", re.I),
    re.compile(r"\busing\b", re.I),
    re.compile(r"\bvia\b", re.I),
    re.compile(r"\bwith\s+the\s+help\s+of\b", re.I),
)

# Named entity types considered animate (for agent detection)
ANIMATE_NE_TYPES: frozenset[str] = frozenset({
    "PERSON", "ORG", "GPE", "NORP",
})


# ---------------------------------------------------------------------------
# NodeClassifier
# ---------------------------------------------------------------------------

class NodeClassifier:
    """
    Classifies a spaCy Span (sentence or clause) into a NarrativeNode.

    Parameters
    ----------
    namespace : str
        Prefix for generated node IDs.
    """

    def __init__(self, namespace: str = "text") -> None:
        self.namespace = namespace

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(
        self,
        span: Span,
        provenance: str = "",
        sent_index: int = 0,
    ) -> Optional[NarrativeNode]:
        """
        Classify a spaCy Span and return the appropriate NarrativeNode.
        Returns None if the span contains no classifiable predicate.
        """
        root = self._find_root_verb(span)
        if root is None:
            return None

        text   = span.text.strip()
        node_id = self._make_id(text, sent_index)

        # Priority cascade
        node_type, confidence, fields = self._classify_cascade(root, span, text)

        # Build the right subclass
        base = dict(
            id=node_id,
            text=text,
            agent=fields.get("agent"),
            source=provenance,
            confidence=confidence,
        )

        if node_type == NodeType.GOAL:
            return GoalNode(
                **base,
                goal_state=fields.get("goal_state"),
                motivation=fields.get("motivation"),
            )
        elif node_type == NodeType.ACTION:
            return ActionNode(
                **base,
                action=fields.get("action"),
                patient=fields.get("patient"),
                instrument=fields.get("instrument"),
            )
        elif node_type == NodeType.STATE:
            return StateNode(
                **base,
                attribute=fields.get("attribute"),
                value=fields.get("value"),
            )
        else:  # EVENT (default)
            return EventNode(
                **base,
                action=fields.get("action"),
                patient=fields.get("patient"),
                time_ref=fields.get("time_ref"),
            )

    # ------------------------------------------------------------------
    # Classification cascade
    # ------------------------------------------------------------------

    def _classify_cascade(
        self,
        root: Token,
        span: Span,
        text: str,
    ) -> tuple[NodeType, float, dict]:
        """
        Returns (NodeType, confidence, extracted_fields).
        """

        # ── Priority 1: Goal ─────────────────────────────────────────
        goal_result = self._try_goal(root, span, text)
        if goal_result:
            return goal_result

        # ── Priority 2: Action ───────────────────────────────────────
        action_result = self._try_action(root, span)
        if action_result:
            return action_result

        # ── Priority 3: State ────────────────────────────────────────
        state_result = self._try_state(root, span)
        if state_result:
            return state_result

        # ── Priority 4: Default Event ────────────────────────────────
        return self._extract_event(root, span)

    # ------------------------------------------------------------------
    # Per-type classifiers
    # ------------------------------------------------------------------

    def _try_goal(
        self,
        root: Token,
        span: Span,
        text: str,
    ) -> Optional[tuple[NodeType, float, dict]]:
        """Detect goal / desire clauses."""
        confidence = 0.0
        fields: dict = {}

        # Signal 1: goal verb lemma ("want", "hope", …)
        if root.lemma_.lower() in GOAL_VERB_LEMMAS:
            confidence = max(confidence, 0.85)

        # Signal 2: discourse marker in the span text
        for pat in GOAL_DISCOURSE_MARKERS:
            if pat.search(text):
                confidence = max(confidence, 0.90)
                break

        # Signal 3: infinitival xcomp ("wanted [to leave]")
        for child in root.children:
            if child.dep_ == "xcomp" and child.pos_ == "VERB":
                confidence = max(confidence, 0.80)
                fields["goal_state"] = child.lemma_
                break

        # Signal 4: purpose advcl ("so that she could escape")
        for child in root.children:
            if child.dep_ == "advcl":
                marker_texts = {t.lower_ for t in child.subtree if t.dep_ == "mark"}
                if marker_texts & {"that", "as"}:
                    confidence = max(confidence, 0.75)

        if confidence < 0.60:
            return None

        fields["agent"]      = self._extract_agent(root)
        fields["motivation"] = self._find_motivation(root)
        return NodeType.GOAL, confidence, fields

    def _try_action(
        self,
        root: Token,
        span: Span,
    ) -> Optional[tuple[NodeType, float, dict]]:
        """Detect intentional action clauses."""
        confidence = 0.0
        fields: dict = {}

        # Signal 1: action verb lemma
        if root.lemma_.lower() in ACTION_VERB_LEMMAS:
            confidence = max(confidence, 0.80)

        # Signal 2: animate agent (person / org performing a dynamic verb)
        agent = self._extract_agent(root)
        if agent and root.lemma_.lower() not in STATIVE_VERB_LEMMAS:
            subj_tok = self._find_subj_token(root)
            if subj_tok and subj_tok.ent_type_ in ANIMATE_NE_TYPES:
                confidence = max(confidence, 0.75)
            elif subj_tok and subj_tok.pos_ in ("NOUN", "PROPN"):
                confidence = max(confidence, 0.65)

        # Signal 3: manner marker in subtree ("by climbing…")
        subtree_text = " ".join(t.text for t in root.subtree)
        for pat in MANNER_MARKERS:
            if pat.search(subtree_text):
                fields["instrument"] = pat.search(subtree_text).group(0)
                confidence = max(confidence, 0.70)
                break

        if confidence < 0.60:
            return None

        fields["agent"]   = agent
        fields["action"]  = root.lemma_
        fields["patient"] = self._extract_patient(root)
        return NodeType.ACTION, confidence, fields

    def _try_state(
        self,
        root: Token,
        span: Span,
    ) -> Optional[tuple[NodeType, float, dict]]:
        """Detect stative / copular clauses."""
        confidence = 0.0
        fields: dict = {}

        # Signal 1: stative verb lemma
        if root.lemma_.lower() in STATIVE_VERB_LEMMAS:
            confidence = max(confidence, 0.80)

        # Signal 2: copula ("is", "was") with attribute complement
        if root.lemma_ == "be":
            for child in root.children:
                if child.dep_ in ("attr", "acomp", "nsubj"):
                    confidence = max(confidence, 0.85)
                    if child.dep_ in ("attr", "acomp"):
                        fields["attribute"] = child.lemma_

        # Signal 3: passive voice without goal verb → resultant state
        if root.dep_ in ("auxpass",) or any(
            c.dep_ == "auxpass" for c in root.children
        ):
            confidence = max(confidence, 0.70)

        if confidence < 0.60:
            return None

        fields["agent"] = self._extract_agent(root)
        fields["value"] = self._extract_patient(root)
        return NodeType.STATE, confidence, fields

    def _extract_event(
        self,
        root: Token,
        span: Span,
    ) -> tuple[NodeType, float, dict]:
        """Default: dynamic verb clause → EventNode."""
        return NodeType.EVENT, 0.60, {
            "agent":    self._extract_agent(root),
            "action":   root.lemma_,
            "patient":  self._extract_patient(root),
            "time_ref": self._extract_time_ref(span),
        }

    # ------------------------------------------------------------------
    # Field extraction helpers
    # ------------------------------------------------------------------

    def _find_root_verb(self, span: Span) -> Optional[Token]:
        """Return the syntactic root if it's a verb, else None."""
        root = span.root
        if root.pos_ in ("VERB", "AUX"):
            return root
        # Fallback: walk children for a verbal head
        for token in span:
            if token.dep_ == "ROOT" and token.pos_ in ("VERB", "AUX"):
                return token
        return None

    def _find_subj_token(self, verb: Token) -> Optional[Token]:
        """Return the head token of the subject NP."""
        for child in verb.children:
            if child.dep_ in ("nsubj", "nsubjpass", "csubj"):
                return child
        # Check parent for xcomp subjects
        if verb.dep_ == "xcomp":
            for sibling in verb.head.children:
                if sibling.dep_ in ("nsubj", "nsubjpass"):
                    return sibling
        return None

    def _extract_agent(self, verb: Token) -> Optional[str]:
        """Return the canonical agent string (subject NP head text)."""
        subj = self._find_subj_token(verb)
        if subj is None:
            return None
        # Prefer the full NP for short spans (≤ 3 tokens); else head only
        span_tokens = list(subj.subtree)
        if len(span_tokens) <= 4:
            return " ".join(t.text for t in span_tokens).strip()
        return subj.text

    def _extract_patient(self, verb: Token) -> Optional[str]:
        """Return the direct object or attribute head text."""
        for child in verb.children:
            if child.dep_ in ("dobj", "attr", "oprd", "nsubjpass"):
                return child.text
        # Prepositional object
        for child in verb.children:
            if child.dep_ == "prep":
                for gc in child.children:
                    if gc.dep_ == "pobj":
                        return gc.text
        return None

    def _extract_time_ref(self, span: Span) -> Optional[str]:
        """Return the text of a TIME or DATE entity in the span."""
        for ent in span.ents:
            if ent.label_ in ("TIME", "DATE"):
                return ent.text
        return None

    def _find_motivation(self, goal_verb: Token) -> Optional[str]:
        """
        Look for a causal adverbial clause that explains the goal.
        e.g. "She wanted to leave because she was scared."
        """
        for child in goal_verb.children:
            if child.dep_ == "advcl":
                markers = {t.lower_ for t in child.subtree if t.dep_ == "mark"}
                if markers & {"because", "since", "as"}:
                    return " ".join(t.text for t in child.subtree)
        return None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, text: str, index: int) -> str:
        """
        Generate a stable node ID.  Short texts get a slug; longer texts
        get a hash suffix to avoid collisions.
        """
        import re as _re
        slug = _re.sub(r"\s+", "_", text[:40].lower().strip())
        slug = _re.sub(r"[^\w_]", "", slug)
        h    = hashlib.md5(text.encode()).hexdigest()[:6]
        return f"{self.namespace}:{slug}_{h}"
