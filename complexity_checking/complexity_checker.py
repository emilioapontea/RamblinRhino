# complexity_checking/complexity_checker.py
from __future__ import annotations

from typing import Optional
import networkx as nx

from quest_parsing.narrative_schema import NodeType, ArcType
from quest_parsing.knowledge_graph import KnowledgeGraph

_VALID_NODE_TYPES = {t.value for t in NodeType}
_VALID_ARC_TYPES  = {t.value for t in ArcType}

class ComplexityChecker:
    def __init__(
            self,
            kg,
            node_reqs=None,
            arc_reqs=None,
            req_dag=True,
            req_conn=True,
    ) -> None:
        self.kg         = kg
        self._node_reqs = node_reqs
        self._arc_reqs  = arc_reqs
        self._req_dag   = req_dag
        self._req_conn  = req_conn

    def __call__(self) -> list:
        node_breakdown = self._node_breakdown()
        arc_breakdown  = self._arc_breakdown()
        feedback = []

        if self._node_reqs is not None:
            for node_type, (min_c, max_c) in self._node_reqs.items():
                count = node_breakdown.get(node_type.value, 0)
                if count < min_c:
                    feedback.append(
                        f'Not enough {node_type.value.upper()} nodes '
                        f'(found {count}, need at least {min_c}).')
                if max_c >= 0 and count > max_c:
                    feedback.append(
                        f'Too many {node_type.value.upper()} nodes '
                        f'(found {count}, max is {max_c}).')

        if self._arc_reqs is not None:
            for arc_type, (min_c, max_c) in self._arc_reqs.items():
                count = arc_breakdown.get(arc_type.value, 0)
                if count < min_c:
                    feedback.append(
                        f'Not enough {arc_type.value.upper()} arcs '
                        f'(found {count}, need at least {min_c}).')
                if max_c >= 0 and count > max_c:
                    feedback.append(
                        f'Too many {arc_type.value.upper()} arcs '
                        f'(found {count}, max is {max_c}).')

        if self._req_dag and self.kg._g.number_of_nodes() > 0:
            if not nx.is_directed_acyclic_graph(self.kg._g):
                feedback.append('Contains circular events.')

        if self._req_conn and self.kg._g.number_of_nodes() > 0:
            if not nx.is_weakly_connected(self.kg._g):
                feedback.append('Contains story discontinuity.')
        return feedback

    def _node_breakdown(self) -> dict:
        m = {t.value: 0 for t in NodeType}
        for _, node_type in self.kg._g.nodes(data='type'):
            if node_type in _VALID_NODE_TYPES:
                m[node_type] += 1
        return m

    def _arc_breakdown(self) -> dict:
        m = {t.value: 0 for t in ArcType}
        for _, _, edge_type in self.kg._g.edges(data='predicate'):
            if edge_type in _VALID_ARC_TYPES:
                m[edge_type] += 1
        return m