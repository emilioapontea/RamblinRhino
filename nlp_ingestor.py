"""
nlp_ingestor.py
Ingestor that extracts triples from plain text using spaCy.

Pipeline
--------
1. Coreference resolution  – replace pronouns with their antecedents so
   relations survive across sentence boundaries.
2. Named entity recognition – ground mention strings to canonical node ids.
3. SVO extraction           – subject-verb-object from the dependency tree.
4. Semantic role labelling  – richer predicate-argument structure via
   spaCy's built-in dependency heuristics or an optional SRL model.
5. Causal/temporal patterns – regex + dependency rules for "X causes Y",
   "X leads to Y", "after X, Y", etc.

Requirements
------------
    pip install spacy
    python -m spacy download en_core_web_sm      # small model
    # For better accuracy:
    # python -m spacy download en_core_web_trf   # transformer model

Optional coreference (improves quality significantly):
    pip install coreferee
    python -m spacy download en_core_web_lg
    python -m coreferee install en

Usage
-----
    from nlp_ingestor import NLPIngestor
    from knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph()
    ingestor = NLPIngestor()
    triples = ingestor.from_text(
        "The mitochondria produces ATP.  It is found in eukaryotic cells.",
        provenance="biology_textbook.pdf:p12"
    )
    kg.add_triples(triples)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import spacy
from spacy.language import Language
from spacy.tokens import Doc, Span, Token

from knowledge_graph import KBSource, Triple


# ---------------------------------------------------------------------------
# Verb → QUEST predicate mapping
# A lightweight lexicon; extend as needed for your domain.
# ---------------------------------------------------------------------------

VERB_PREDICATE_MAP: dict[str, str] = {
    # Causality
    "cause":      "Causes",
    "produce":    "Causes",
    "generate":   "Causes",
    "lead":       "Causes",
    "result":     "Causes",
    "trigger":    "Causes",
    "induce":     "Causes",
    "create":     "CreatedBy",   # passive form handled below
    # Properties / attributes
    "be":         "HasProperty",
    "have":       "HasA",
    "contain":    "HasA",
    "consist":    "HasA",
    # Location
    "locate":     "AtLocation",
    "find":       "AtLocation",
    "reside":     "AtLocation",
    "occur":      "AtLocation",
    # Classification
    "classify":   "IsA",
    "define":     "DefinedAs",
    "call":       "DefinedAs",
    "refer":      "DefinedAs",
    # Purpose
    "use":        "UsedFor",
    "serve":      "UsedFor",
    "function":   "UsedFor",
    # Prerequisites
    "require":    "HasPrerequisite",
    "need":       "HasPrerequisite",
    "depend":     "HasPrerequisite",
    # Similarity
    "resemble":   "SimilarTo",
    "like":       "SimilarTo",
}

# Causal surface patterns (applied before spaCy parsing for speed)
_CAUSAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(.+?)\s+causes?\s+(.+)", re.I),         "Causes"),
    (re.compile(r"(.+?)\s+leads?\s+to\s+(.+)", re.I),     "Causes"),
    (re.compile(r"(.+?)\s+results?\s+in\s+(.+)", re.I),   "Causes"),
    (re.compile(r"(.+?)\s+triggers?\s+(.+)", re.I),       "Causes"),
    (re.compile(r"(.+?)\s+is\s+caused\s+by\s+(.+)", re.I), "CausedBy"),
    (re.compile(r"because\s+of\s+(.+?),\s+(.+)", re.I),   "CausedBy"),
]

# Definitional surface patterns
_DEF_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(.+?)\s+is\s+(?:a|an|the)\s+(.+)", re.I),  "IsA"),
    (re.compile(r"(.+?)\s+is\s+defined\s+as\s+(.+)", re.I),  "DefinedAs"),
    (re.compile(r"(.+?),\s+(?:a|an)\s+(.+),", re.I),         "IsA"),
]


# ---------------------------------------------------------------------------
# NLPIngestor
# ---------------------------------------------------------------------------

class NLPIngestor:
    """
    Extracts triples from free text using spaCy.

    Parameters
    ----------
    model : str
        spaCy model name (default "en_core_web_sm").
    namespace : str
        Prefix for text-derived node ids (default "text").
    min_confidence : float
        Triples below this threshold are discarded.
    use_coreference : bool
        Attempt to load coreferee for coreference resolution.
        Gracefully degrades if coreferee is not installed.
    """

    def __init__(
        self,
        model: str = "en_core_web_sm",
        namespace: str = "text",
        min_confidence: float = 0.3,
        use_coreference: bool = True,
    ) -> None:
        self.namespace = namespace
        self.min_confidence = min_confidence

        self.nlp: Language = spacy.load(model)

        self._coref_available = False
        if use_coreference:
            try:
                import coreferee  # noqa: F401
                self.nlp.add_pipe("coreferee")
                self._coref_available = True
            except (ImportError, Exception):
                pass  # coref is optional; degrade silently

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def from_text(
        self,
        text: str,
        provenance: str = "",
        source: KBSource = KBSource.TEXT,
    ) -> list[Triple]:
        """
        Extract triples from a single text string.

        Steps:
          1. Pattern-based extraction (fast, high-precision for known forms)
          2. Dependency-based SVO extraction (broad coverage)
          3. NER grounding (standardise entity mention strings)
          4. Deduplication and confidence scoring
        """
        doc = self.nlp(text)
        triples: list[Triple] = []

        # 1. Surface pattern extraction
        for sent in doc.sents:
            triples.extend(self._pattern_extract(sent.text, provenance + ":pattern", source))

        # 2. Dependency SVO extraction
        for sent in doc.sents:
            triples.extend(self._dep_extract(sent, provenance + ":dep", source))

        # 3. NER-based typing (add type triples: entity → InstanceOf → NE-type)
        triples.extend(self._ner_triples(doc, provenance + ":ner", source))

        # 4. Coreference: re-extract over coref-resolved text
        if self._coref_available:
            resolved = self._resolve_coref(doc)
            if resolved != text:
                doc2 = self.nlp(resolved)
                for sent in doc2.sents:
                    triples.extend(self._dep_extract(sent, provenance + ":coref", source))

        # 5. Filter and deduplicate
        triples = self._deduplicate(triples)
        triples = [t for t in triples if t.confidence >= self.min_confidence]
        return triples

    def from_file(
        self,
        path: str | Path,
        encoding: str = "utf-8",
        chunk_size: int = 10_000,
    ) -> list[Triple]:
        """
        Ingest a plain-text file, processing in chunks to avoid spaCy's
        max-length limit.
        """
        path = Path(path)
        text = path.read_text(encoding=encoding)
        provenance = f"file:{path.name}"

        triples: list[Triple] = []
        for start in range(0, len(text), chunk_size):
            chunk = text[start: start + chunk_size]
            triples.extend(self.from_text(chunk, provenance=provenance))

        return self._deduplicate(triples)

    def from_sentences(
        self,
        sentences: list[str],
        provenance: str = "",
        source: KBSource = KBSource.TEXT,
    ) -> list[Triple]:
        """Convenience: ingest a pre-tokenised list of sentence strings."""
        triples: list[Triple] = []
        for sent in sentences:
            triples.extend(self.from_text(sent, provenance=provenance, source=source))
        return self._deduplicate(triples)

    # ------------------------------------------------------------------
    # Extraction strategies
    # ------------------------------------------------------------------

    def _pattern_extract(
        self,
        text: str,
        provenance: str,
        source: KBSource,
    ) -> list[Triple]:
        """Apply regex surface patterns for causality and definitions."""
        triples: list[Triple] = []

        for pattern, predicate in _CAUSAL_PATTERNS + _DEF_PATTERNS:
            m = pattern.match(text.strip())
            if m:
                subj_text = m.group(1).strip()
                obj_text  = m.group(2).strip().rstrip(".")
                if subj_text and obj_text:
                    triples.append(Triple(
                        subject=self._make_id(subj_text),
                        predicate=predicate,
                        obj=self._make_id(obj_text),
                        source=source,
                        confidence=0.75,   # pattern match is reliable but not perfect
                        provenance=provenance,
                    ))

        return triples

    def _dep_extract(
        self,
        sent: Span,
        provenance: str,
        source: KBSource,
    ) -> list[Triple]:
        """
        Extract SVO triples from the dependency parse of a single sentence.

        Handles:
          - Simple SVO:  "Bees produce honey."
          - Passive:     "ATP is produced by mitochondria."
          - Existential: "There are three types of X."
          - Compound objects via conjuncts.
        """
        triples: list[Triple] = []

        for token in sent:
            if token.pos_ not in ("VERB", "AUX") or token.dep_ == "aux":
                continue

            subj_spans = self._find_subj(token)
            obj_spans  = self._find_obj(token)

            if not subj_spans or not obj_spans:
                continue

            lemma     = token.lemma_.lower()
            predicate = VERB_PREDICATE_MAP.get(lemma, self._verb_to_predicate(token))
            confidence = self._edge_confidence(token, sent)

            # Check for negation
            if any(c.dep_ == "neg" for c in token.children):
                predicate = f"Not_{predicate}"
                confidence *= 0.6

            for subj in subj_spans:
                for obj in obj_spans:
                    subj_text = self._span_head_text(subj)
                    obj_text  = self._span_head_text(obj)
                    if not subj_text or not obj_text:
                        continue
                    if subj_text.lower() in ("it", "this", "that", "they"):
                        continue   # unresolved pronoun — skip unless coref ran

                    triples.append(Triple(
                        subject=self._make_id(subj_text),
                        predicate=predicate,
                        obj=self._make_id(obj_text),
                        source=source,
                        confidence=confidence,
                        provenance=provenance,
                    ))

        return triples

    def _ner_triples(
        self,
        doc: Doc,
        provenance: str,
        source: KBSource,
    ) -> list[Triple]:
        """
        For each named entity, emit (entity) -[InstanceOf]-> (NE-type).
        e.g. "London" → ("text:london", "InstanceOf", "text:GPE")
        """
        triples: list[Triple] = []
        seen: set[tuple] = set()

        for ent in doc.ents:
            ent_id  = self._make_id(ent.text)
            type_id = self._make_id(ent.label_)
            key     = (ent_id, "InstanceOf", type_id)
            if key in seen:
                continue
            seen.add(key)
            triples.append(Triple(
                subject=ent_id,
                predicate="InstanceOf",
                obj=type_id,
                source=source,
                confidence=0.95,
                provenance=provenance,
            ))

        return triples

    # ------------------------------------------------------------------
    # Coreference resolution helper
    # ------------------------------------------------------------------

    def _resolve_coref(self, doc: Doc) -> str:
        """
        Return a version of doc.text with coreferring pronouns replaced by
        their most specific antecedent head noun.  Requires coreferee.
        """
        if not self._coref_available or not doc._.has("coref_chains"):
            return doc.text

        tokens = [t.text_with_ws for t in doc]

        for chain in doc._.coref_chains:
            # chain[0] is the antecedent mention (best label)
            if not chain:
                continue
            head_mention = chain[0]
            head_span = doc[head_mention.root_index]
            replacement = head_span.text

            for mention in chain[1:]:
                span = doc[mention.root_index]
                if span.pos_ == "PRON":
                    tokens[span.i] = replacement + span.whitespace_

        return "".join(tokens)

    # ------------------------------------------------------------------
    # Dependency helpers
    # ------------------------------------------------------------------

    def _find_subj(self, verb: Token) -> list[Span]:
        """Collect all subject spans (including conjoined subjects)."""
        subjects: list[Token] = []
        for child in verb.children:
            if child.dep_ in ("nsubj", "nsubjpass", "csubj", "expl"):
                subjects.extend(self._expand_conjuncts(child))
        # Walk up for xcomp / relcl subjects
        if not subjects and verb.dep_ in ("xcomp", "relcl"):
            for child in verb.head.children:
                if child.dep_ in ("nsubj", "nsubjpass"):
                    subjects.extend(self._expand_conjuncts(child))
        return [t.doc[t.left_edge.i: t.right_edge.i + 1] for t in subjects]

    def _find_obj(self, verb: Token) -> list[Span]:
        """Collect all object spans (direct obj, prep-obj, attr)."""
        objects: list[Token] = []
        for child in verb.children:
            if child.dep_ in ("dobj", "attr", "oprd"):
                objects.extend(self._expand_conjuncts(child))
            elif child.dep_ == "prep":
                for gc in child.children:
                    if gc.dep_ == "pobj":
                        objects.extend(self._expand_conjuncts(gc))
        return [t.doc[t.left_edge.i: t.right_edge.i + 1] for t in objects]

    def _expand_conjuncts(self, token: Token) -> list[Token]:
        """Return token plus any tokens joined by 'conj' dependency."""
        result = [token]
        for child in token.children:
            if child.dep_ == "conj":
                result.extend(self._expand_conjuncts(child))
        return result

    def _span_head_text(self, span: Span) -> str:
        """Return the head token's text with any compound modifiers."""
        head = span.root
        compounds = [c.text for c in head.children if c.dep_ == "compound"]
        parts = compounds + [head.text]
        return " ".join(parts).strip()

    def _verb_to_predicate(self, token: Token) -> str:
        """
        Fallback: convert a verb lemma to a CamelCase predicate.
        "produce" → "Produces"
        """
        lemma = token.lemma_.lower()
        return lemma.capitalize()

    def _edge_confidence(self, verb: Token, sent: Span) -> float:
        """
        Heuristic confidence for a dependency-extracted edge.
        Reduced by hedging language; boosted by short sentences (less ambiguity).
        """
        confidence = 0.65   # base confidence for dep extraction

        hedges = {"may", "might", "could", "can", "possibly", "perhaps",
                  "seem", "appear", "suggest", "indicate"}
        sent_tokens = {t.lemma_.lower() for t in sent}
        if sent_tokens & hedges:
            confidence *= 0.7

        # Shorter sentences have less syntactic ambiguity
        if len(list(sent.doc.sents)) == 1 and len(sent) < 15:
            confidence = min(confidence * 1.2, 1.0)

        return round(confidence, 3)

    # ------------------------------------------------------------------
    # Node id helpers
    # ------------------------------------------------------------------

    def _make_id(self, text: str) -> str:
        """Produce a stable, namespaced node id from a text span."""
        slug = re.sub(r"\s+", "_", text.lower().strip())
        slug = re.sub(r"[^\w_-]", "", slug)
        return f"{self.namespace}:{slug}"

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _deduplicate(self, triples: list[Triple]) -> list[Triple]:
        """
        Merge duplicate (subject, predicate, object) triples by keeping
        the one with the highest confidence.
        """
        best: dict[tuple, Triple] = {}
        for t in triples:
            key = (t.subject, t.predicate, t.obj)
            if key not in best or t.confidence > best[key].confidence:
                best[key] = t
        return list(best.values())
