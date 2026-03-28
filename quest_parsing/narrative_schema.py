"""
narrative_schema.py
Data structures for QUEST narrative graph extraction.

Every clause in a text maps to one of four node types:
    EventNode  - a dynamic occurrence with an agent and (optional) patient
    GoalNode   - a desired state held by an agent; motivates actions
    ActionNode - an intentional event; sub-type of EventNode, goal-directed
    StateNode  - a static property or resulting condition

Every edge between nodes is one of six QUEST arc types:
    Consequence - event/action causally or temporally leads to another event
    Implies     - state/condition entails another state (defeasible)
    Manner      - event A is the method by which event B is accomplished
    Initiate    - event triggers a goal becoming active in an agent
    Reason      - goal motivates / explains an action
    Outcome     - action produces a resulting state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


# ---------------------------------------------------------------------------
# Node types
# ---------------------------------------------------------------------------

class NodeType(str, Enum):
    EVENT  = "event"
    GOAL   = "goal"
    ACTION = "action"
    STATE  = "state"


@dataclass
class NarrativeNode:
    """Base class for all narrative graph nodes."""
    id:          str
    text:        str             # the surface clause text
    node_type:   NodeType
    agent:       Optional[str]   # canonical agent string
    source:      str = ""        # provenance (file, sentence index, char span)
    confidence:  float = 1.0
    timestamp:   float = field(default_factory=time.time)

    def to_triple_subject(self) -> str:
        return self.id

    def label(self) -> str:
        return f"[{self.node_type.value}] {self.text[:60]}"


@dataclass
class EventNode(NarrativeNode):
    """
    A dynamic occurrence.
    e.g. "the fire spread to the east wing"
    """
    node_type: NodeType = field(default=NodeType.EVENT, init=False)
    action:    Optional[str] = None   # verb lemma
    patient:   Optional[str] = None   # object NP
    time_ref:  Optional[str] = None   # temporal expression if present


@dataclass
class ActionNode(NarrativeNode):
    """
    An intentional, goal-directed event.
    e.g. "Mary climbed the fence"  (to escape — goal is external)
    """
    node_type:   NodeType = field(default=NodeType.ACTION, init=False)
    action:      Optional[str] = None
    patient:     Optional[str] = None
    instrument:  Optional[str] = None   # "by means of" NP


@dataclass
class GoalNode(NarrativeNode):
    """
    A desired state held by an agent.
    e.g. "Mary wanted to escape"
    """
    node_type:    NodeType = field(default=NodeType.GOAL, init=False)
    goal_state:   Optional[str] = None   # the desired condition
    motivation:   Optional[str] = None   # why the agent holds this goal


@dataclass
class StateNode(NarrativeNode):
    """
    A static property or resulting condition.
    e.g. "the door was locked", "the room was empty"
    """
    node_type: NodeType = field(default=NodeType.STATE, init=False)
    attribute: Optional[str] = None   # the property being predicated
    value:     Optional[str] = None   # value or complement


# ---------------------------------------------------------------------------
# Arc types
# ---------------------------------------------------------------------------

class ArcType(str, Enum):
    CONSEQUENCE = "Consequence"   # event/action → event/action (causal/temporal)
    IMPLIES     = "Implies"       # state → state  (logical entailment)
    MANNER      = "Manner"        # event A is the method for event B
    INITIATE    = "Initiate"      # event → goal   (event activates a goal)
    REASON      = "Reason"        # goal  → action (goal motivates action)
    OUTCOME     = "Outcome"       # action → state (action produces state)


# Valid (source_type, target_type) pairs per arc
ARC_TYPE_CONSTRAINTS: dict[ArcType, list[tuple[NodeType, NodeType]]] = {
    ArcType.CONSEQUENCE: [
        (NodeType.EVENT,  NodeType.EVENT),
        (NodeType.EVENT,  NodeType.ACTION),
        (NodeType.ACTION, NodeType.EVENT),
        (NodeType.ACTION, NodeType.ACTION),
    ],
    ArcType.IMPLIES: [
        (NodeType.STATE, NodeType.STATE),
        (NodeType.STATE, NodeType.EVENT),   # states can enable events
    ],
    ArcType.MANNER: [
        (NodeType.ACTION, NodeType.ACTION),
        (NodeType.EVENT,  NodeType.ACTION),
    ],
    ArcType.INITIATE: [
        (NodeType.EVENT,  NodeType.GOAL),
        (NodeType.ACTION, NodeType.GOAL),
        (NodeType.STATE,  NodeType.GOAL),
    ],
    ArcType.REASON: [
        (NodeType.GOAL, NodeType.ACTION),
        (NodeType.GOAL, NodeType.EVENT),
    ],
    ArcType.OUTCOME: [
        (NodeType.ACTION, NodeType.STATE),
        (NodeType.EVENT,  NodeType.STATE),
    ],
}


def arc_is_valid(arc: ArcType, src: NarrativeNode, dst: NarrativeNode) -> bool:
    """Check whether the arc type is permitted for the given node type pair."""
    allowed = ARC_TYPE_CONSTRAINTS.get(arc, [])
    return (src.node_type, dst.node_type) in allowed


# Default arc when node types are known but no discourse cue is present
DEFAULT_ARC: dict[tuple[NodeType, NodeType], ArcType] = {
    (NodeType.EVENT,  NodeType.EVENT):  ArcType.CONSEQUENCE,
    (NodeType.EVENT,  NodeType.ACTION): ArcType.CONSEQUENCE,
    (NodeType.ACTION, NodeType.EVENT):  ArcType.CONSEQUENCE,
    (NodeType.ACTION, NodeType.ACTION): ArcType.CONSEQUENCE,
    (NodeType.STATE,  NodeType.STATE):  ArcType.IMPLIES,
    (NodeType.STATE,  NodeType.EVENT):  ArcType.IMPLIES,
    (NodeType.EVENT,  NodeType.GOAL):   ArcType.INITIATE,
    (NodeType.ACTION, NodeType.GOAL):   ArcType.INITIATE,
    (NodeType.STATE,  NodeType.GOAL):   ArcType.INITIATE,
    (NodeType.GOAL,   NodeType.ACTION): ArcType.REASON,
    (NodeType.GOAL,   NodeType.EVENT):  ArcType.REASON,
    (NodeType.ACTION, NodeType.STATE):  ArcType.OUTCOME,
    (NodeType.EVENT,  NodeType.STATE):  ArcType.OUTCOME,
}


@dataclass
class NarrativeArc:
    """A typed, directed edge in the narrative graph."""
    src_id:     str
    dst_id:     str
    arc_type:   ArcType
    confidence: float = 1.0
    cue:        str   = ""   # the discourse cue that triggered this arc
    provenance: str   = ""
    timestamp:  float = field(default_factory=time.time)
