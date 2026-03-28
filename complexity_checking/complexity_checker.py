from typing import Optional
import networkx as nx

from quest_parsing.narrative_schema import NodeType, ArcType
from quest_parsing.knowledge_graph import KnowledgeGraph

class ComplexityChecker:
    def __init__(
            self,
            kg: KnowledgeGraph,
            node_reqs : Optional[dict[NodeType, tuple[int, int]]] = None,
            arc_reqs : Optional[dict[ArcType, tuple[int, int]]] = None,
            req_dag : Optional[bool] = True,
            req_conn : Optional[bool] = True,
        ) -> None:
        """
        Args:
            kg: The knowledge graph to check.
            node_reqs: Optional dict mapping NodeType to (min_count, max_count) for that node type. Use max_count=-1 for no upper bound.
            arc_reqs: Optional dict mapping ArcType to (min_count, max_count) for that arc type. Use max_count=-1 for no upper bound.
            req_dag: If True, require that the graph is a directed acyclic graph (no circular events).
            req_conn: If True, require that the graph is weakly connected (no story discontinuity).
        """
        self.kg = kg
        self._node_reqs = node_reqs
        self._arc_reqs = arc_reqs
        self._req_dag = req_dag
        self._req_conn = req_conn

    def __call__(self) -> list[str]:
        """
        Returns:
            A list of feedback messages indicating any complexity requirement violations. An empty list indicates that all requirements are satisfied.
        """
        if self.kg._g.number_of_nodes() == 0:
            return ["Story graph is empty."]

        node_breakdown = self._node_breakdown()
        arc_breakdown = self._arc_breakdown()

        feedback = []

        if self._node_reqs is not None:
            for node_type in self._node_reqs:
                # NOT ENOUGH
                if node_breakdown[node_type.value] < self._node_reqs[node_type][0]:
                    feedback.append(f'Not enough {node_type.value.upper()} nodes.')

                # TOO MANY
                if self._node_reqs[node_type][1] >= 0 and node_breakdown[node_type.value] >= self._node_reqs[node_type][1]:
                    feedback.append(f'Too many {node_type.value.upper()} nodes.')

        if self._arc_reqs is not None:
            for arc_type in self._arc_reqs:
                # NOT ENOUGH
                if arc_breakdown[arc_type.value] < self._arc_reqs[arc_type][0]:
                    feedback.append(f'Not enough {arc_type.value.upper()} arcs.')

                # TOO MANY
                if self._arc_reqs[arc_type][1] >= 0 and arc_breakdown[arc_type.value] >= self._arc_reqs[arc_type][1]:
                    feedback.append(f'Too many {arc_type.value.upper()} arcs.')

        if self._req_dag and not nx.is_directed_acyclic_graph(self.kg._g):
            feedback.append(f'Contains circular events.')

        if self._req_conn and not nx.is_weakly_connected(self.kg._g):
            feedback.append(f'Contains story discontinuity.')

        return feedback

    def _check_complexity(self) -> dict[str, int]:
        num_nodes = self.kg._g.number_of_nodes()
        num_edges = self.kg._g.number_of_edges()
        avg_degree = sum(dict(self.kg._g.degree()).values()) / num_nodes if num_nodes > 0 else 0
        return {
            "num_nodes": num_nodes,
            "num_edges": num_edges,
            "avg_degree": avg_degree
        }

    def _node_breakdown(self) -> dict[NodeType, int]:
        m = {t.value : 0 for t in NodeType}

        for _, node_type in self.kg._g.nodes(data='type'):
            m[node_type] += 1

        return m

    def _arc_breakdown(self) -> dict[ArcType, int]:
        m = {t.value : 0 for t in ArcType}

        for _, _, edge_type in self.kg._g.edges(data='predicate'):
            m[edge_type] += 1

        return m
