"""
knowledge_graph.py
Unified knowledge graph for QUEST.

Every fact from every source is stored as a labelled, directed edge:
    (subject_id) --[predicate]--> (object_id | literal)

Node attributes : id, label, type, source
Edge attributes : predicate, weight, confidence, source, timestamp, provenance
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Optional

import networkx as nx


# ---------------------------------------------------------------------------
# Source taxonomy
# ---------------------------------------------------------------------------

class KBSource(str, Enum):
    WORLD  = "world"
    DOMAIN = "domain"
    TEXT   = "text"


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

@dataclass
class Triple:
    """Normalised 5-tuple shared by all ingestors."""
    subject:    str          # canonical node id
    predicate:  str          # relation label
    obj:        str          # canonical node id or literal string
    source:     KBSource
    confidence: float = 1.0
    provenance: str   = ""   # URL, filename, sentence span, …
    timestamp:  float = field(default_factory=time.time)

    def validate(self) -> None:
        if not self.subject:
            raise ValueError("Triple.subject must be non-empty")
        if not self.predicate:
            raise ValueError("Triple.predicate must be non-empty")
        if not self.obj:
            raise ValueError("Triple.obj must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1]; got {self.confidence}")


@dataclass
class Node:
    id:     str
    label:  str
    type:   str   = "concept"   # concept | entity | literal | event
    source: str   = ""


# ---------------------------------------------------------------------------
# KnowledgeGraph
# ---------------------------------------------------------------------------

class KnowledgeGraph:
    """
    Thin wrapper around a NetworkX MultiDiGraph that enforces the triple
    schema and exposes the three query primitives used by the answer generator.

    Serialisation
    -------------
    save(path)  - writes GraphML (human-readable, lossless for str attrs)
    load(path)  - class-method, returns a new KnowledgeGraph

    Alternative backends
    --------------------
    Swap self._g for a py2neo.Graph, rdflib.Graph, or any object that
    supports add_node / add_edge without changing the public interface.
    """

    def __init__(self) -> None:
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_triple(self, triple: Triple) -> None:
        """
        Insert a normalised triple.  Duplicate edges are allowed (MultiDiGraph)
        so that the same fact from two sources is preserved with both weights.
        """
        triple.validate()

        for node_id in (triple.subject, triple.obj):
            if not self._g.has_node(node_id):
                self._g.add_node(
                    node_id,
                    label=node_id,
                    type="concept",
                    source=triple.source.value,
                )

        self._g.add_edge(
            triple.subject,
            triple.obj,
            predicate=triple.predicate,
            weight=triple.confidence,
            confidence=triple.confidence,
            source=triple.source.value,
            provenance=triple.provenance,
            timestamp=triple.timestamp,
        )

    def add_triples(self, triples: list[Triple]) -> int:
        """Bulk insert; returns count of triples added."""
        added = 0
        for t in triples:
            try:
                self.add_triple(t)
                added += 1
            except ValueError as exc:
                print(f"[KnowledgeGraph] skipping invalid triple: {exc}")
        return added

    def set_node_attr(self, node_id: str, **attrs: Any) -> None:
        """Update metadata on an existing node (label, type, …)."""
        if self._g.has_node(node_id):
            self._g.nodes[node_id].update(attrs)

    # ------------------------------------------------------------------
    # Query primitives
    # ------------------------------------------------------------------

    def get_neighbours(
        self,
        node_id: str,
        predicate: Optional[str] = None,
        source: Optional[KBSource] = None,
        direction: str = "out",          # "out" | "in" | "both"
        min_confidence: float = 0.0,
    ) -> list[dict]:
        """
        Return adjacent nodes + edge data, optionally filtered.

        Each result dict: {node_id, label, predicate, confidence, source, provenance}
        """
        if not self._g.has_node(node_id):
            return []

        results: list[dict] = []

        def _collect(src: str, dst: str) -> None:
            edge_data_dict = self._g.get_edge_data(src, dst) or {}
            for _, edata in edge_data_dict.items():
                if predicate and edata.get("predicate") != predicate:
                    continue
                if source and edata.get("source") != source.value:
                    continue
                if edata.get("confidence", 1.0) < min_confidence:
                    continue
                neighbour_id = dst if src == node_id else src
                results.append({
                    "node_id":    neighbour_id,
                    "label":      self._g.nodes[neighbour_id].get("label", neighbour_id),
                    "predicate":  edata.get("predicate"),
                    "confidence": edata.get("confidence", 1.0),
                    "source":     edata.get("source"),
                    "provenance": edata.get("provenance", ""),
                })

        if direction in ("out", "both"):
            for dst in self._g.successors(node_id):
                _collect(node_id, dst)
        if direction in ("in", "both"):
            for src in self._g.predecessors(node_id):
                _collect(src, node_id)

        results.sort(key=lambda r: r["confidence"], reverse=True)
        return results

    def find_path(
        self,
        src_id: str,
        dst_id: str,
        max_hops: int = 4,
        predicate_filter: Optional[set[str]] = None,
    ) -> list[list[str]] | None:
        """
        Find one or more shortest paths between two nodes.

        Returns a list of node-id sequences, or None if no path exists.
        Uses an unweighted BFS view (edge weight treated as uniform) because
        we want hop-count minimisation, not weight minimisation.
        """
        if not (self._g.has_node(src_id) and self._g.has_node(dst_id)):
            return None

        view = self._g
        if predicate_filter:
            edges_to_keep = [
                (u, v, k)
                for u, v, k, d in self._g.edges(keys=True, data=True)
                if d.get("predicate") in predicate_filter
            ]
            view = self._g.edge_subgraph(edges_to_keep)

        try:
            paths = list(nx.all_shortest_paths(view, src_id, dst_id))
            paths = [p for p in paths if len(p) - 1 <= max_hops]
            return paths if paths else None
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def subgraph(
        self,
        node_ids: list[str],
        hops: int = 1,
    ) -> "KnowledgeGraph":
        """
        Return a new KnowledgeGraph containing the given nodes plus all
        nodes reachable within *hops* steps.  Useful for pulling the
        local context around a set of entities before answer generation.
        """
        expanded: set[str] = set(node_ids)
        frontier = set(node_ids)

        for _ in range(hops):
            next_frontier: set[str] = set()
            for n in frontier:
                if self._g.has_node(n):
                    next_frontier.update(self._g.successors(n))
                    next_frontier.update(self._g.predecessors(n))
            next_frontier -= expanded
            expanded.update(next_frontier)
            frontier = next_frontier

        sub = self._g.subgraph(expanded).copy()
        kg = KnowledgeGraph()
        kg._g = sub
        return kg

    # ------------------------------------------------------------------
    # Convenience look-ups
    # ------------------------------------------------------------------

    def has_node(self, node_id: str) -> bool:
        return self._g.has_node(node_id)

    def node_attr(self, node_id: str) -> dict:
        return dict(self._g.nodes.get(node_id, {}))

    def edges_between(self, src: str, dst: str) -> list[dict]:
        """All edges (any predicate) from src to dst."""
        data = self._g.get_edge_data(src, dst)
        if data is None:
            return []
        return [dict(v) for v in data.values()]

    def iter_triples(
        self,
        source: Optional[KBSource] = None,
    ) -> Iterator[Triple]:
        """Iterate over all stored triples, optionally filtered by source."""
        for u, v, data in self._g.edges(data=True):
            if source and data.get("source") != source.value:
                continue
            yield Triple(
                subject=u,
                predicate=data.get("predicate", ""),
                obj=v,
                source=KBSource(data.get("source", KBSource.WORLD)),
                confidence=data.get("confidence", 1.0),
                provenance=data.get("provenance", ""),
                timestamp=data.get("timestamp", 0.0),
            )

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        source_counts: dict[str, int] = {}
        for _, _, data in self._g.edges(data=True):
            s = data.get("source", "unknown")
            source_counts[s] = source_counts.get(s, 0) + 1

        return {
            "nodes":          self._g.number_of_nodes(),
            "edges":          self._g.number_of_edges(),
            "edges_by_source": source_counts,
        }

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Persist to GraphML.  Node/edge attributes must be str/int/float."""
        nx.write_graphml(self._g, str(path))

    @classmethod
    def load(cls, path: str | Path) -> "KnowledgeGraph":
        kg = cls()
        kg._g = nx.read_graphml(str(path))
        return kg

    def to_json(self) -> dict:
        return nx.node_link_data(self._g)

    @classmethod
    def from_json(cls, data: dict) -> "KnowledgeGraph":
        kg = cls()
        kg._g = nx.node_link_graph(data)
        return kg

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return self._g.number_of_edges()

    def __repr__(self) -> str:
        s = self.stats()
        return (
            f"KnowledgeGraph(nodes={s['nodes']}, edges={s['edges']}, "
            f"by_source={s['edges_by_source']})"
        )
