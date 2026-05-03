from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from collections import deque
from difflib import get_close_matches
import re

from llm_api_wrapper import InterpretedAction, LLMClient, PlotEvent


DEFAULT_ROOM_ORDER = [
    "Museum Entrance",
    "Museum Gallery",
    "Archive Office",
    "Security Office",
    "Staff Hallway",
    "Storage Room",
    "Parking Lot",
    "Warehouse",
]

NON_SUSPECT_TOKENS = {
    "clara",
    "detective",
    "police",
    "officer",
    "security team",
    "museum staff",
}

MAX_COMMAND_WORDS = 12
MAX_AUTONARRATED_EVENTS = 3


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _match_name(target: str, candidates: list[str]) -> Optional[str]:
    norm_target = _normalize(target)
    for candidate in candidates:
        norm_candidate = _normalize(candidate)
        if norm_target and (norm_target in norm_candidate or norm_candidate in norm_target):
            return candidate
    if not norm_target:
        return None
    candidate_map = {
        _normalize(candidate): candidate
        for candidate in candidates
        if _normalize(candidate)
    }
    close_matches = get_close_matches(norm_target, candidate_map.keys(), n=1, cutoff=0.72)
    if close_matches:
        return candidate_map[close_matches[0]]
    target_tokens = set(norm_target.split())
    for candidate in candidates:
        candidate_tokens = set(_normalize(candidate).split())
        if target_tokens and any(
            target_token in candidate_token or candidate_token in target_token
            for target_token in target_tokens
            for candidate_token in candidate_tokens
            if len(target_token) >= 4 and len(candidate_token) >= 4
        ):
            return candidate
    return None


def _token_overlap_score(target: str, candidate: str) -> int:
    target_tokens = set(_normalize(target).split())
    candidate_tokens = set(_normalize(candidate).split())
    return len(target_tokens & candidate_tokens)


def infer_location_from_text(description: str) -> str:
    text = description.lower()
    if "warehouse" in text:
        return "Warehouse"
    if "security" in text or "footage" in text or "camera" in text:
        return "Security Office"
    if "office" in text:
        return "Archive Office"
    if "staff" in text or "hallway" in text:
        return "Staff Hallway"
    if "parking" in text or "car" in text or "outside" in text:
        return "Parking Lot"
    if "storage" in text or "back room" in text:
        return "Storage Room"
    if "display case" in text or "museum" in text or "gallery" in text:
        return "Museum Gallery"
    return "Archive Office"


@dataclass
class Room:
    name: str
    description: str
    exits: dict[str, str] = field(default_factory=dict)
    objects: list[str] = field(default_factory=list)
    npcs: list[str] = field(default_factory=list)
    clues: list[str] = field(default_factory=list)


@dataclass
class StoryEventState:
    event: PlotEvent
    triggered: bool = False
    invalidated: bool = False
    invalid_reason: str = ""


@dataclass
class WorldState:
    premise: str
    rooms: dict[str, Room]
    player_location: str
    inventory: list[str] = field(default_factory=list)
    known_clues: list[str] = field(default_factory=list)
    objectives: list[str] = field(default_factory=list)
    event_states: list[StoryEventState] = field(default_factory=list)
    turn_count: int = 0
    active_facts: list[str] = field(default_factory=list)
    story_status: str = "active"
    ending_reason: str = ""
    player_name: str = "Clara"
    last_classification: str = ""
    last_intervention: str = ""
    offtrack_turns: int = 0
    exceptional_actions: int = 0
    suspect_name: Optional[str] = None
    last_action_signature: str = ""
    repeated_action_count: int = 0
    last_inspected_target: str = ""
    last_guidance_signature: str = ""

    def current_room(self) -> Room:
        return self.rooms[self.player_location]

    def move_player(self, destination: str) -> bool:
        room = self.current_room()
        if destination in room.exits:
            self.player_location = room.exits[destination]
            return True
        if destination in self.rooms and destination in room.exits.values():
            self.player_location = destination
            return True
        return False

    def resolve_room_name(self, target: str) -> Optional[str]:
        direct = _match_name(target, list(self.rooms.keys()))
        if direct:
            return direct
        normalized_rooms = {_normalize(room_name): room_name for room_name in self.rooms}
        normalized_target = _normalize(target)
        close = get_close_matches(normalized_target, list(normalized_rooms.keys()), n=1, cutoff=0.6)
        if close:
            return normalized_rooms[close[0]]
        best_match = None
        best_score = 0
        for room_name in self.rooms:
            score = _token_overlap_score(target, room_name)
            if score > best_score:
                best_match = room_name
                best_score = score
        return best_match if best_score > 0 else None

    def path_to_room(self, destination: str) -> Optional[list[str]]:
        if destination not in self.rooms:
            return None
        if destination == self.player_location:
            return [destination]

        queue: deque[tuple[str, list[str]]] = deque([(self.player_location, [self.player_location])])
        visited = {self.player_location}

        while queue:
            current, path = queue.popleft()
            for next_room in self.rooms[current].exits.values():
                if next_room in visited:
                    continue
                next_path = [*path, next_room]
                if next_room == destination:
                    return next_path
                visited.add(next_room)
                queue.append((next_room, next_path))
        return None

    def travel_player(self, destination: str) -> Optional[list[str]]:
        path = self.path_to_room(destination)
        if not path:
            return None
        self.player_location = destination
        return path

    def describe_current_room(self) -> str:
        room = self.current_room()
        lines = [
            f"Location: {room.name}",
            room.description,
        ]
        if room.exits:
            lines.append("Exits: " + ", ".join(f"{k} -> {v}" for k, v in room.exits.items()))
        if room.objects:
            lines.append("Objects: " + ", ".join(room.objects))
        if room.npcs:
            lines.append("People here: " + ", ".join(room.npcs))
        if room.clues:
            lines.append("Possible clues: " + ", ".join(room.clues))
        return "\n".join(lines)

    def add_fact(self, fact: str) -> None:
        if fact and fact not in self.active_facts:
            self.active_facts.append(fact)

    def add_clue(self, clue: str) -> None:
        if clue and clue not in self.known_clues:
            self.known_clues.append(clue)

    def next_story_event(self) -> Optional[StoryEventState]:
        for event_state in self.event_states:
            if not event_state.triggered and not event_state.invalidated:
                return event_state
        return None

    def remaining_story_events(self) -> list[StoryEventState]:
        return [
            event_state for event_state in self.event_states
            if not event_state.triggered and not event_state.invalidated
        ]


def _room_description(name: str) -> str:
    descriptions = {
        "Museum Entrance": "The public entrance connects the museum to the outside world and staff traffic.",
        "Museum Gallery": "Display cases, polished floors, and the crime scene itself dominate the gallery.",
        "Archive Office": "Research notes, catalogs, and preservation tools are scattered around the office.",
        "Security Office": "Monitors, recordings, and access logs make this room the center of surveillance.",
        "Staff Hallway": "A narrow corridor links work areas used by staff and security.",
        "Storage Room": "Shelves and sealed crates create plenty of places to hide evidence.",
        "Parking Lot": "Vehicles and delivery routes connect the museum to the city beyond.",
        "Warehouse": "A remote, risky meeting point well outside the museum's controlled spaces.",
    }
    return descriptions.get(name, f"{name} is an important story location.")


def _connect_rooms(rooms: dict[str, Room]) -> None:
    # ordered = [name for name in DEFAULT_ROOM_ORDER if name in rooms]
    ordered = list(rooms.keys())
    for idx, name in enumerate(ordered):
        room = rooms[name]
        if idx > 0:
            room.exits["back"] = ordered[idx - 1]
        if idx < len(ordered) - 1:
            room.exits["forward"] = ordered[idx + 1]


def _infer_primary_suspect(events: list[PlotEvent]) -> Optional[str]:
    counts: dict[str, int] = {}
    for event in events:
        for character in event.characters:
            norm = _normalize(character)
            if not norm or norm in NON_SUSPECT_TOKENS:
                continue
            counts[character] = counts.get(character, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def build_world_from_events(
    events: list[PlotEvent],
    premise: str,
    playable_events: Optional[list[PlotEvent]] = None,
    player_name: str = "Clara",
) -> WorldState:
    active_events = playable_events if playable_events is not None else events
    rooms: dict[str, Room] = {}
    event_states: list[StoryEventState] = []
    objectives: list[str] = []
    active_facts: list[str] = []

    for event in events:
        location = event.location or infer_location_from_text(event.description)
        event.location = location

        if location not in rooms:
            rooms[location] = Room(name=location, description=_room_description(location))

        room = rooms[location]
        room.npcs.extend(
            char for char in event.characters
            if char and char not in room.npcs and _normalize(char) != _normalize(player_name)
        )
        room.objects.extend(obj for obj in event.required_objects if obj and obj not in room.objects)

        if event.clue and event.clue not in room.clues:
            room.clues.append(event.clue)

        for goal in event.goals:
            if goal and goal not in objectives:
                objectives.append(goal)

        for character in event.characters:
            active_facts.append(f"{character} is available")
        for obj in event.required_objects:
            active_facts.append(f"{obj} is intact")
        active_facts.append(f"{location} is accessible")

    for event in active_events:
        event_states.append(StoryEventState(event=event))

    if not rooms:
        rooms["Archive Office"] = Room(
            name="Archive Office",
            description=_room_description("Archive Office"),
        )

    _connect_rooms(rooms)
    deduped_facts = list(dict.fromkeys(active_facts))
    first_playable_location = None
    if active_events:
        first_playable_location = active_events[0].location or infer_location_from_text(active_events[0].description)
    start_room = (
        first_playable_location
        if first_playable_location in rooms
        else ("Museum Entrance" if "Museum Entrance" in rooms else next(iter(rooms)))
    )
    return WorldState(
        premise=premise,
        rooms=rooms,
        player_location=start_room,
        player_name=player_name,
        known_clues=[],
        objectives=objectives[:5],
        event_states=event_states,
        active_facts=deduped_facts,
        suspect_name=_infer_primary_suspect(events),
    )


class InteractiveStoryGame:
    def __init__(self, world: WorldState, llm: Optional[LLMClient] = None) -> None:
        self.world = world
        self.llm = llm

    def _build_context_summary(self) -> str:
        room = self.world.current_room()
        next_event = self.world.next_story_event()
        next_summary = "None"
        if next_event:
            next_summary = (
                f"{next_event.event.event_id}: {next_event.event.description} "
                f"at {next_event.event.location}"
            )
        return "\n".join([
            f"Player character: {self.world.player_name}",
            f"Current location: {room.name}",
            f"Visible objects: {', '.join(room.objects) if room.objects else 'none'}",
            f"Visible people: {', '.join(room.npcs) if room.npcs else 'none'}",
            f"Visible clues: {', '.join(room.clues) if room.clues else 'none'}",
            f"Inventory: {', '.join(self.world.inventory) if self.world.inventory else 'empty'}",
            f"Known clues: {', '.join(self.world.known_clues) if self.world.known_clues else 'none'}",
            f"Objectives: {', '.join(self.world.objectives) if self.world.objectives else 'investigate the case'}",
            f"Next story event: {next_summary}",
            f"Active facts: {', '.join(self.world.active_facts[:20])}",
        ])

    def _player_is_character(self, character: str) -> bool:
        return _normalize(character) == _normalize(self.world.player_name)

    def _player_relative_text(self, text: str) -> str:
        name = re.escape(self.world.player_name)
        verb_replacements = {
            "analyzes": "analyze",
            "compares": "compare",
            "confronts": "confront",
            "decides": "decide",
            "decodes": "decode",
            "discovers": "discover",
            "finds": "find",
            "identifies": "identify",
            "inspects": "inspect",
            "interviews": "interview",
            "learns": "learn",
            "notices": "notice",
            "obtains": "obtain",
            "questions": "question",
            "realizes": "realize",
            "reviews": "review",
            "shows": "show",
            "suspects": "suspect",
        }
        for third_person, second_person in verb_replacements.items():
            text = re.sub(
                rf"\b{name}\s+{third_person}\b",
                f"you {second_person}",
                text,
                flags=re.IGNORECASE,
            )
            text = re.sub(
                rf"\band\s+{third_person}\b",
                f"and {second_person}",
                text,
                flags=re.IGNORECASE,
            )
            text = re.sub(
                rf"\byou\s+{third_person}\b",
                f"you {second_person}",
                text,
                flags=re.IGNORECASE,
            )
        text = re.sub(rf"\b{name}'s\b", "your", text, flags=re.IGNORECASE)
        text = re.sub(rf"\b{name}\b", "you", text, flags=re.IGNORECASE)
        text = re.sub(r"\bshe\b", "you", text, flags=re.IGNORECASE)
        text = re.sub(r"\bher\b", "your", text, flags=re.IGNORECASE)
        return text[:1].upper() + text[1:] if text else text

    def _fallback_event_prose(self, event: PlotEvent) -> str:
        room_phrase = f"In the {event.location.lower()}, " if event.location else ""
        description_text = event.description.strip()
        if any(self._player_is_character(character) for character in event.characters):
            description_text = self._player_relative_text(description_text)
        people_phrase = ""
        non_player_characters = [
            character for character in event.characters
            if not self._player_is_character(character)
        ]
        if non_player_characters and not any(self._player_is_character(character) for character in event.characters):
            if len(non_player_characters) == 1:
                people_phrase = f"{non_player_characters[0]} "
            elif len(non_player_characters) == 2:
                people_phrase = f"{non_player_characters[0]} and {non_player_characters[1]} "
            else:
                people_phrase = f"{', '.join(non_player_characters[:-1])}, and {non_player_characters[-1]} "
        if non_player_characters and description_text:
            first_character = non_player_characters[0].lower()
            if description_text.lower().startswith(first_character):
                people_phrase = ""

        lines = [
            f"{room_phrase}{people_phrase}{description_text[0].lower() + description_text[1:] if description_text else ''}".strip(),
        ]
        if event.clue:
            lines.append(f"The moment leaves behind a telling detail: {event.clue.rstrip('.')}.")
        elif event.effects:
            lines.append(f"The development changes the investigation in a concrete way: {', '.join(event.effects)}.")
        return " ".join(line for line in lines if line).strip()

    def _render_event_prose(self, event: PlotEvent) -> str:
        if self.llm:
            try:
                prose = self.llm.narrate_interactive_event(
                    event=event,
                    world_context=self._build_context_summary(),
                )
                if prose:
                    return prose
            except Exception:
                pass
        return self._fallback_event_prose(event)

    def _heuristic_action(self, command: str) -> InterpretedAction:
        corrected_command = command
        typo_replacements = {
            r"\bconfonrt\b": "confront",
            r"\bhte\b": "the",
            r"\bteh\b": "the",
            r"\binterragate\b": "interrogate",
            r"\bth eknown\b": "the known",
        }
        for pattern, replacement in typo_replacements.items():
            corrected_command = re.sub(pattern, replacement, corrected_command, flags=re.IGNORECASE)

        lower = corrected_command.lower().strip()
        route_intent_terms = (
            "where",
            "came from",
            "come from",
            "entered",
            "entry",
            "route",
            "path",
            "follow",
            "trace",
            "locate",
            "track",
            "investigate",
            "figure out",
        )
        if any(term in lower for term in route_intent_terms) and any(
            person in lower for person in ("thief", "culprit", "perpetrator", "killer")
        ):
            next_event = self.world.next_story_event()
            target = command.strip()
            if next_event and next_event.event.location:
                return InterpretedAction(
                    action_type="move",
                    target=next_event.event.location,
                    target_location=next_event.event.location,
                    intent_summary=f"pursue route lead: {target}",
                )
            return InterpretedAction(
                action_type="inspect",
                target=target,
                target_object=target,
                intent_summary=f"investigate route lead: {target}",
            )
        if any(word in lower for word in ("perpetrator", "culprit", "thief", "killer")) and any(
            word in lower for word in ("caught", "catch", "identify", "it's", " is ")
        ):
            return InterpretedAction(
                action_type="accuse",
                target=command.strip(),
                target_character=command.strip(),
            )
        if lower.startswith("confront "):
            target = re.sub(r"^confront\s+(the\s+)?", "", corrected_command, count=1, flags=re.IGNORECASE).strip()
            return InterpretedAction(action_type="talk", target=target, target_character=target)
        if lower.startswith("go "):
            target = re.sub(r"^(go|walk|move|head)\s+(to\s+)?", "", lower, count=1).strip()
            return InterpretedAction(action_type="move", target=target, target_location=target)
        if any(lower.startswith(prefix) for prefix in ("walk ", "move ", "head ")):
            target = re.sub(r"^(go|walk|move|head)\s+(to\s+)?", "", lower, count=1).strip()
            return InterpretedAction(action_type="move", target=target, target_location=target)
        if lower.startswith((
            "look ",
            "inspect ",
            "examine ",
            "search ",
            "study ",
            "analyze ",
            "analyse ",
            "investigate ",
            "check ",
            "review ",
            "read ",
        )):
            target = re.sub(
                r"^(look|inspect|examine|search|study|analyze|analyse|investigate|check|review|read)\s+",
                "",
                corrected_command,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            target = re.sub(
                r"^(further|farther|closer|more|carefully|closely)\s+",
                "",
                target,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            target = re.sub(
                r"^(at|into|for|around|over|the|a|an)\s+",
                "",
                target,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            target = re.sub(
                r"^(further|farther|closer|more|carefully|closely)\s+",
                "",
                target,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            target = re.sub(r"^(at|the|a|an)\s+", "", target, count=1, flags=re.IGNORECASE).strip()
            target = re.sub(r"^what\s+is\s+on\s+(the\s+)?", "", target, count=1, flags=re.IGNORECASE).strip()
            if target:
                return InterpretedAction(action_type="inspect", target=target, target_object=target)
        if lower.startswith("inspect "):
            target = command[8:].strip()
            return InterpretedAction(action_type="inspect", target=target, target_object=target)
        if lower.startswith("talk "):
            target = re.sub(r"^to\s+", "", command[5:].strip(), flags=re.IGNORECASE)
            return InterpretedAction(action_type="talk", target=target, target_character=target)
        if lower.startswith(("ask ", "question ", "interrogate ", "interragate ")):
            target = re.sub(
                r"^(ask|question|interrogate|interragate)\s+(the\s+)?",
                "",
                corrected_command,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            target = re.split(r"\s+(about|who|what|why|where|when|how)\b", target, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            return InterpretedAction(action_type="talk", target=target, target_character=target)
        if lower.startswith(("contact ", "find ", "track down ", "locate ")):
            target = re.sub(
                r"^(contact|find|track down|locate)\s+(the\s+)?(known\s+)?",
                "",
                corrected_command,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            next_event = self.world.next_story_event()
            if next_event and (
                _normalize(target) in _normalize(next_event.event.description)
                or any(_normalize(target) in _normalize(char) for char in next_event.event.characters)
                or any(_normalize(target) in _normalize(goal) for goal in next_event.event.goals)
            ):
                return InterpretedAction(
                    action_type="move",
                    target=next_event.event.location or target,
                    target_location=next_event.event.location or target,
                    intent_summary=f"pursue {target}",
                )
            return InterpretedAction(action_type="talk", target=target, target_character=target)
        if lower.startswith("take "):
            target = command[5:].strip()
            return InterpretedAction(action_type="take", target=target, target_object=target)
        if "steal" in lower:
            target = re.sub(r".*steal(?:s|ing)?\s+", "", command, flags=re.IGNORECASE).strip()
            target = target or "something valuable"
            return InterpretedAction(action_type="take", target=target, target_object=target)
        if lower.startswith("use "):
            target = command[4:].strip()
            return InterpretedAction(action_type="use", target=target, target_object=target)
        if any(word in lower for word in ("break ", "destroy ", "smash ", "burn ", "tear ")):
            target = command.split(" ", 1)[1] if " " in command else command
            return InterpretedAction(action_type="damage", target=target, target_object=target)
        if any(word in lower for word in ("block ", "jam ", "lock ")):
            target = command.split(" ", 1)[1] if " " in command else command
            return InterpretedAction(action_type="block", target=target, target_object=target)
        if lower.startswith("accuse "):
            target = command[7:].strip()
            return InterpretedAction(action_type="accuse", target=target, target_character=target)
        if lower in {"wait", "pass"}:
            return InterpretedAction(action_type="wait", target="wait")
        return InterpretedAction(action_type="unknown", target=command)

    def _interpret_action(self, command: str) -> InterpretedAction:
        lower = command.lower().strip()
        local_action = self._heuristic_action(command)
        if local_action.action_type in {"damage", "block", "move"}:
            return local_action
        if any(phrase in lower for phrase in ("go there", "go to this location", "go to that location", "go to the lead")):
            next_event = self.world.next_story_event()
            if next_event and next_event.event.location:
                return InterpretedAction(
                    action_type="move",
                    target=next_event.event.location,
                    target_location=next_event.event.location,
                    intent_summary=f"go to {next_event.event.location}",
                )
        if not self.llm:
            return local_action
        try:
            action = self.llm.interpret_player_action(
                command=command,
                world_context=self._build_context_summary(),
            )
            if action.action_type == "accuse":
                if local_action.action_type in {"move", "inspect"}:
                    return local_action
            if action.action_type == "unknown":
                if local_action.action_type != "unknown":
                    return local_action
            return action
        except Exception:
            return local_action

    def _current_targets(self) -> tuple[list[str], list[str]]:
        room = self.world.current_room()
        objects = list(dict.fromkeys([*room.objects, *self.world.inventory]))
        people = list(dict.fromkeys(room.npcs))
        return objects, people

    def _action_signature(self, action: InterpretedAction) -> str:
        target = (
            action.target_location
            or action.target_object
            or action.target_character
            or action.target
        )
        return f"{action.action_type}:{_normalize(target or '')}"

    def _track_action_repetition(self, action: InterpretedAction) -> int:
        signature = self._action_signature(action)
        if signature and signature == self.world.last_action_signature:
            self.world.repeated_action_count += 1
        else:
            self.world.last_action_signature = signature
            self.world.repeated_action_count = 0
        return self.world.repeated_action_count

    def _next_lead_guidance(self) -> Optional[str]:
        next_event = self.world.next_story_event()
        if not next_event:
            return None

        event = next_event.event
        if event.location == self.world.player_location:
            parts = [f"No new story beat opens yet. The next lead is here in {event.location}."]
        else:
            parts = [f"No new story beat opens here. The next lead is tied to {event.location}."]

        path = self.world.path_to_room(event.location or "")
        if path and len(path) > 1:
            parts.append(f"Route: {' -> '.join(path)}.")

        required = [obj for obj in event.required_objects if obj]
        people = [char for char in event.characters if char]
        if required:
            parts.append(f"Something relevant here: {', '.join(required[:2])}.")
        elif people:
            parts.append(f"Someone relevant here: {', '.join(people[:2])}.")

        return " ".join(parts)

    def _clue_followup_guidance(self, clue: str) -> Optional[str]:
        next_event = self.world.next_story_event()
        if not next_event:
            return None

        event = next_event.event
        signature = f"{_normalize(clue)}->{event.event_id}"
        if signature == self.world.last_guidance_signature:
            return "That clue is already recorded; try acting on the current lead instead."
        self.world.last_guidance_signature = signature

        details: list[str] = []
        if event.required_objects:
            details.append(f"look for {', '.join(event.required_objects[:2])}")
        elif event.characters:
            details.append(f"question {', '.join(event.characters[:2])}")
        elif event.goals:
            details.append(event.goals[0])

        if event.location == self.world.player_location:
            lead = "Studying it keeps your attention on this room"
        else:
            lead = f"Studying it points you toward {event.location}"
        if details:
            lead += f" to {details[0]}"
        lead += "."

        path = self.world.path_to_room(event.location or "")
        if path and len(path) > 1:
            lead += f" Route: {' -> '.join(path)}."
        return lead

    def _visual_evidence_answer(self) -> Optional[str]:
        room = self.world.current_room()
        inspected = _normalize(self.world.last_inspected_target)
        if not any(term in inspected for term in ("footage", "camera", "video", "still")):
            return None

        visual_clues = [
            clue for clue in [*room.clues, *self.world.known_clues]
            if any(term in _normalize(clue) for term in (
                "camera",
                "footage",
                "seen",
                "visible",
                "tattoo",
                "person",
                "thief",
                "angle",
                "entering",
            ))
        ]
        visual_clues = list(dict.fromkeys(visual_clues))

        lines = [f"In the {self.world.last_inspected_target}, you do not get a clean face."]
        if visual_clues:
            lines.append("What you can make out:")
            lines.extend(f"- {clue.rstrip('.')}" for clue in visual_clues[:4])
        else:
            lines.append("The image is unclear, but it confirms someone moved through this part of the case.")

        next_event = self.world.next_story_event()
        if next_event and next_event.event.location:
            lines.append(f"The useful follow-up is {next_event.event.location}.")
        return "\n".join(lines)

    def _readable_evidence_answer(self, target: str = "") -> Optional[str]:
        room = self.world.current_room()
        inspected = _normalize(target or self.world.last_inspected_target)
        readable_terms = ("document", "note", "email", "message", "record", "file", "folder", "accounts", "transaction")
        if not any(term in inspected for term in readable_terms):
            return None

        clues = list(dict.fromkeys([*room.clues, *self.world.known_clues]))
        matched_clue = _match_name(target or self.world.last_inspected_target, clues)
        if not matched_clue:
            documentish_clues = [
                clue for clue in clues
                if any(term in _normalize(clue) for term in (
                    "note",
                    "message",
                    "email",
                    "document",
                    "meeting",
                    "alibi",
                    "value",
                    "transaction",
                    "attachment",
                    "cryptic",
                    "motive",
                ))
            ]
            matched_clue = documentish_clues[0] if documentish_clues else None

        label = target or self.world.last_inspected_target or "it"
        if matched_clue:
            return f"The {label} says: {matched_clue.rstrip('.')}."
        return f"The {label} looks important, but you cannot make out a specific detail yet."

    def _person_lead_guidance(self, target: str) -> Optional[str]:
        lead = self._person_lead(target)
        if not lead:
            return None

        matched, location = lead
        parts = [f"{matched} is part of the next lead, but they are not here."]
        if location:
            parts.append(f"Look in {location}.")
            path = self.world.path_to_room(location)
            if path and len(path) > 1:
                parts.append(f"Route: {' -> '.join(path)}.")
        return " ".join(parts)

    def _person_lead(self, target: str) -> Optional[tuple[str, str]]:
        for event_state in self.world.remaining_story_events():
            matched = _match_name(target, event_state.event.characters)
            if not matched or self._player_is_character(matched):
                continue

            location = event_state.event.location or infer_location_from_text(event_state.event.description)
            return matched, location
        return None

    def _inspectable_lead(self, target: str) -> Optional[tuple[str, str, str]]:
        resolved_room = self.world.resolve_room_name(target)
        if resolved_room:
            return resolved_room, resolved_room, "location"

        for event_state in self.world.remaining_story_events():
            event = event_state.event
            event_location = event.location or infer_location_from_text(event.description)
            if event_location and _match_name(target, [event_location]):
                return event_location, event_location, "location"
            matched_required = _match_name(target, event.required_objects)
            if matched_required:
                return matched_required, event_location, "object"
            if event.clue and _match_name(target, [event.clue]):
                return event.clue, event_location, "clue"

        for room_name, room in self.world.rooms.items():
            matched_object = _match_name(target, room.objects)
            if matched_object:
                return matched_object, room_name, "object"
            matched_clue = _match_name(target, room.clues)
            if matched_clue:
                return matched_clue, room_name, "clue"

        return None

    def _validate_action(self, action: InterpretedAction) -> tuple[bool, str]:
        room = self.world.current_room()
        objects, people = self._current_targets()

        if action.action_type == "move":
            target = action.target_location or action.target
            if not target:
                return False, "You need to specify where to go."
            resolved_room = self.world.resolve_room_name(target)
            if not resolved_room:
                return False, f"There is no known location matching '{target}'."
            if resolved_room == self.world.player_location:
                return True, ""
            path = self.world.path_to_room(resolved_room)
            if path:
                return True, ""
            return False, f"You cannot reach '{resolved_room}' from here."

        if action.action_type in {"inspect", "take", "use", "damage", "block"}:
            target = action.target_object or action.target
            if not target:
                return False, "That action needs a target."
            matched = _match_name(target, objects + room.clues + list(room.exits.keys()))
            if matched:
                return True, ""
            if action.action_type == "inspect" and self._inspectable_lead(target):
                return True, ""
            return False, f"You do not have access to '{target}' here."

        if action.action_type in {"talk", "accuse"}:
            target = action.target_character or action.target
            if not target:
                return False, "That action needs a person."
            if action.action_type == "talk" and self._player_is_character(target):
                return False, f"You are {self.world.player_name}; choose someone else to question or inspect a lead."
            if action.action_type == "talk" and _normalize(target) in {"suspect", "the suspect"} and people:
                return True, ""
            matched = _match_name(target, people)
            if matched or action.action_type == "accuse":
                return True, ""
            if self._person_lead(target):
                return True, ""
            return False, f"No one here matches '{target}'."

        if action.action_type in {"wait", "unknown"}:
            return True, ""

        return True, ""

    def _remaining_required_objects(self) -> list[str]:
        required: list[str] = []
        for event_state in self.world.remaining_story_events():
            required.extend(event_state.event.required_objects)
        return list(dict.fromkeys(obj for obj in required if obj))

    def _remaining_required_characters(self) -> list[str]:
        required: list[str] = []
        for event_state in self.world.remaining_story_events():
            required.extend(event_state.event.characters)
        return list(dict.fromkeys(char for char in required if char))

    def _find_affected_events(self, action: InterpretedAction) -> list[StoryEventState]:
        target = _normalize(action.target_object or action.target_character or action.target)
        affected: list[StoryEventState] = []
        for event_state in self.world.remaining_story_events():
            event_targets = [
                _normalize(obj) for obj in event_state.event.required_objects
            ]
            event_targets.extend(_normalize(char) for char in event_state.event.characters)
            event_targets.append(_normalize(event_state.event.location or ""))
            if event_state.event.clue:
                event_targets.append(_normalize(event_state.event.clue))
            if target and any(target in candidate or candidate in target for candidate in event_targets if candidate):
                affected.append(event_state)
        return affected

    def _destructive_action_hits_evidence(self, action: InterpretedAction) -> bool:
        target = action.target_object or action.target
        if action.action_type == "block":
            return bool(self.world.current_room().exits)
        if not target:
            return False

        room = self.world.current_room()
        evidence_pool = [
            *room.objects,
            *room.clues,
            *self.world.inventory,
            *self.world.known_clues,
            *self._remaining_required_objects(),
        ]
        return _match_name(target, evidence_pool) is not None

    def _exception_anchor_events(self, action: InterpretedAction) -> list[StoryEventState]:
        affected_events = self._find_affected_events(action)
        if affected_events:
            return affected_events

        next_event = self.world.next_story_event()
        if next_event:
            return [next_event]

        remaining = self.world.remaining_story_events()
        return remaining[:1]

    def _classify_action(self, action: InterpretedAction) -> tuple[str, list[StoryEventState]]:
        next_event = self.world.next_story_event()
        affected_events = self._find_affected_events(action)

        if action.action_type in {"damage", "block"}:
            if affected_events:
                return "exceptional", affected_events
            if self._destructive_action_hits_evidence(action):
                return "exceptional", []

        if action.action_type == "accuse":
            if self.world.suspect_name and _match_name(action.target_character or action.target, [self.world.suspect_name]):
                return "constituent", affected_events
            return "exceptional", self._exception_anchor_events(action)

        if next_event:
            target_pool = [
                next_event.event.location or "",
                *(next_event.event.required_objects or []),
                *(next_event.event.characters or []),
                *(next_event.event.goals or []),
                *(next_event.event.hidden_expected_intents or []),
            ]
            if next_event.event.clue:
                target_pool.append(next_event.event.clue)
            target = action.target or ""
            intent = action.intent_summary or ""
            if action.action_type == "inspect":
                inspection_target = action.target_object or action.target
                room = self.world.current_room()
                if _match_name(inspection_target, room.clues + self.world.known_clues):
                    return "constituent", affected_events
            if self.world.player_location == next_event.event.location:
                if action.action_type in {"inspect", "talk", "take", "use"}:
                    return "constituent", affected_events
                if action.action_type == "move" and action.target_location == next_event.event.location:
                    return "constituent", affected_events
            normalized_target = _normalize(target)
            normalized_intent = _normalize(intent)
            if any(
                (normalized_target and normalized_target in _normalize(item))
                or (normalized_intent and normalized_intent in _normalize(item))
                for item in target_pool
                if item
            ):
                return "constituent", affected_events

        if action.action_type in {"move", "inspect", "talk", "take", "use", "wait"}:
            return "consistent", affected_events

        return "consistent", affected_events

    def _apply_action(self, action: InterpretedAction) -> str:
        room = self.world.current_room()

        if action.action_type == "move":
            target = action.target_location or action.target
            resolved_room = self.world.resolve_room_name(target) or target
            path = self.world.travel_player(resolved_room)
            self.world.add_fact(f"player visited {self.world.player_location}")
            if path and len(path) > 1:
                route = " -> ".join(path)
                return f"Route taken: {route}\n{self.world.describe_current_room()}"
            return self.world.describe_current_room()

        if action.action_type == "inspect":
            target = action.target_object or action.target
            matched_visual_object = None
            if any(term in _normalize(target) for term in ("footage", "camera", "video", "still")):
                matched_visual_object = _match_name(target, room.objects + self.world.inventory)
            if matched_visual_object:
                self.world.last_inspected_target = matched_visual_object
                self.world.add_fact(f"inspected {matched_visual_object}")
                answer = self._visual_evidence_answer()
                if answer:
                    return f"You review the {matched_visual_object}.\n{answer}"

            location_lead = self._inspectable_lead(target)
            if location_lead and location_lead[2] == "location":
                matched_target, location, _ = location_lead
                path = self.world.travel_player(location)
                room = self.world.current_room()
                self.world.add_fact(f"player followed lead to {location}")
                route = f"Route taken: {' -> '.join(path)}\n" if path and len(path) > 1 else ""
                self.world.last_inspected_target = matched_target
                self.world.add_fact(f"inspected {location}")
                event_text = self._trigger_story_segment()
                if event_text:
                    return f"{route}{event_text}"
                return f"{route}{self.world.describe_current_room()}\nYou inspect {location} for the next lead."

            matched_clue = _match_name(target, room.clues)
            if matched_clue:
                self.world.last_inspected_target = target or matched_clue
                self.world.add_clue(matched_clue)
                self.world.add_fact(f"inspected {matched_clue}")
                followup = self._clue_followup_guidance(matched_clue)
                if followup:
                    return f"You inspect the {target}. {matched_clue.rstrip('.')}. {followup}"
                return f"You inspect {matched_clue} and notice: {matched_clue}"
            matched_known_clue = _match_name(target, self.world.known_clues)
            if matched_known_clue:
                self.world.last_inspected_target = target or matched_known_clue
                self.world.add_fact(f"reexamined {matched_known_clue}")
                followup = self._clue_followup_guidance(matched_known_clue)
                if followup:
                    return f"You reexamine {matched_known_clue}. {followup}"
                return f"You reexamine {matched_known_clue}, but it does not reveal a new lead yet."
            matched_object = _match_name(target, room.objects + self.world.inventory)
            if matched_object:
                self.world.last_inspected_target = matched_object
                self.world.add_fact(f"inspected {matched_object}")
                if any(term in _normalize(matched_object) for term in ("footage", "camera", "video", "still")):
                    answer = self._visual_evidence_answer()
                    if answer:
                        return f"You review the {matched_object}.\n{answer}"
                readable_answer = self._readable_evidence_answer(matched_object)
                if readable_answer:
                    return f"You read the {matched_object}.\n{readable_answer}"
                return f"You inspect the {matched_object}. It seems relevant to the case."

            lead = self._inspectable_lead(target)
            if lead:
                matched_target, location, lead_kind = lead
                path = self.world.travel_player(location)
                room = self.world.current_room()
                self.world.add_fact(f"player followed lead to {location}")
                route = f"Route taken: {' -> '.join(path)}\n" if path and len(path) > 1 else ""

                if lead_kind == "location":
                    self.world.last_inspected_target = location
                    self.world.add_fact(f"inspected {location}")
                    event_text = self._trigger_story_segment()
                    if event_text:
                        return f"{route}{event_text}"
                    return f"{route}{self.world.describe_current_room()}\nYou inspect {location} for the next lead."

                if lead_kind == "clue":
                    room_clue = _match_name(matched_target, room.clues)
                    clue = room_clue or matched_target
                    self.world.last_inspected_target = clue
                    self.world.add_clue(clue)
                    self.world.add_fact(f"inspected {clue}")
                    return f"{route}You follow the lead to {location} and inspect {clue}."

                room_object = _match_name(matched_target, room.objects + self.world.inventory)
                obj = room_object or matched_target
                self.world.last_inspected_target = obj
                self.world.add_fact(f"inspected {obj}")
                event_text = self._trigger_story_segment()
                if event_text:
                    return f"{route}You follow the lead to {location} and inspect the {obj}.\n\n{event_text}"
                return f"{route}You follow the lead to {location} and inspect the {obj}."
            return f"You do not see anything matching '{target}' here."

        if action.action_type == "talk":
            target = _match_name(action.target_character or action.target, room.npcs)
            if not target and _normalize(action.target_character or action.target) in {"suspect", "the suspect"} and room.npcs:
                target = (
                    _match_name("staff member", room.npcs)
                    or _match_name("suspect", room.npcs)
                    or room.npcs[0]
                )
            if target:
                fact = f"talked to {target}"
                already_talked = fact in self.world.active_facts
                self.world.add_fact(fact)
                for clue in room.clues:
                    self.world.add_clue(clue)
                if already_talked:
                    return f"You have already talked to {target}; they do not add anything new."
                return f"You talk to {target}. They share what they know about this location."

            lead = self._person_lead(action.target_character or action.target)
            if lead:
                lead_name, location = lead
                path = self.world.travel_player(location)
                room = self.world.current_room()
                if lead_name not in room.npcs:
                    room.npcs.append(lead_name)
                self.world.add_fact(f"approached {lead_name}")
                route = f"Route taken: {' -> '.join(path)}\n" if path and len(path) > 1 else ""
                return f"{route}You follow the lead to {location} and approach {lead_name}."

            return f"No one here matches '{action.target}'."

        if action.action_type == "take":
            target = _match_name(action.target_object or action.target, room.objects)
            if target:
                if target not in self.world.inventory:
                    self.world.inventory.append(target)
                room.objects.remove(target)
                self.world.add_fact(f"{target} is in inventory")
                return f"You take the {target}."
            return f"You cannot take '{action.target}' here."

        if action.action_type == "use":
            target = _match_name(action.target_object or action.target, room.objects + self.world.inventory)
            if target:
                self.world.add_fact(f"used {target}")
                return f"You use the {target} and test whether it reveals anything useful."
            return f"You cannot use '{action.target}' here."

        if action.action_type == "damage":
            target = _match_name(action.target_object or action.target, room.objects + self.world.inventory + room.clues)
            if target:
                if target in room.objects:
                    room.objects.remove(target)
                if target in self.world.inventory:
                    self.world.inventory.remove(target)
                if target in room.clues:
                    room.clues.remove(target)
                self.world.add_fact(f"{target} is destroyed")
                return f"You damage the {target}, changing the case in a serious way."
            return f"You cannot damage '{action.target}' here."

        if action.action_type == "block":
            if room.exits:
                direction = next(iter(room.exits))
                blocked_room = room.exits.pop(direction)
                self.world.add_fact(f"path to {blocked_room} is blocked")
                return f"You block the route leading {direction} toward {blocked_room}."
            return "There is nothing obvious to block here."

        if action.action_type == "wait":
            self.world.add_fact("player waited")
            return "You pause and let the scene breathe for a moment."

        if action.action_type == "accuse":
            accused = action.target_character or action.target
            if self.world.suspect_name and _match_name(accused, [self.world.suspect_name]):
                if len(self.world.known_clues) >= 3:
                    self.world.story_status = "solved"
                    clue_summary = "\n  - ".join(self.world.known_clues)
                    self.world.ending_reason = (
                        f"\n{'='*60}\n"
                        f"CASE CLOSED\n"
                        f"{'='*60}\n"
                        f"You confront {self.world.suspect_name} with the full weight of your evidence.\n\n"
                        f"The clues you uncovered:\n  - {clue_summary}\n\n"
                        f"Faced with the proof, {self.world.suspect_name} has no way out. "
                        f"The authorities are called and an arrest is made. "
                        f"The stolen manuscript — and the secrets it contained — are finally recovered. "
                        f"Your instincts as an investigator solved the case.\n\n"
                        f"Turns taken: {self.world.turn_count} | "
                        f"Clues gathered: {len(self.world.known_clues)} | "
                        f"Disruptions: {self.world.exceptional_actions}\n"
                        f"{'='*60}"
                    )
                    return self.world.ending_reason
                return (
                    f"You accuse {self.world.suspect_name}, but you need more evidence first.\n"
                    f"Clues found so far: {len(self.world.known_clues)}/3 needed.\n"
                    f"Known clues: {', '.join(self.world.known_clues) if self.world.known_clues else 'none yet'}"
                )
            self.world.add_fact(f"wrong accusation against {accused}")
            self.world.last_intervention = (
                f"The accusation against {accused} rattles the investigation and forces the case to shift."
            )
            return (
                f"You accuse {accused}, but the claim does not hold. "
                "The investigation is thrown off balance and needs a new lead."
            )

        self.world.add_fact(f"attempted action: {action.target}")
        if action.action_type == "unknown":
            return (
                "I could not map that command to a clear game action. "
                "Try phrasing it as movement, inspection, conversation, taking something, using something, or an accusation."
            )
        return (
            "The project could not confidently execute that action. "
            "Try movement, inspection, conversation, taking objects, or waiting."
        )

    def _event_is_ready(self, event_state: StoryEventState) -> bool:
        event = event_state.event
        if event.location != self.world.player_location:
            return False
        if event.required_objects:
            available = self.world.current_room().objects + self.world.inventory + self.world.known_clues
            if not any(_match_name(obj, available) for obj in event.required_objects):
                return False
        return True

    def _is_decision_event(self, event_state: StoryEventState) -> bool:
        event = event_state.event
        if event.goal_type == "resolve":
            return False
        if event.is_decision_point:
            return True

        try:
            event_index = self.world.event_states.index(event_state)
        except ValueError:
            event_index = 0

        description = event.description.lower()
        decision_terms = (
            "confront",
            "interview",
            "question",
            "suspect",
            "alibi",
            "choose",
            "decide",
            "lead",
            "trail",
        )
        if event.goal_type == "obstruct":
            return True
        if any(term in description for term in decision_terms):
            return True
        if event.clue and event_index % 3 == 0:
            return True
        return event_index == 0

    def _open_decision_prompt(self, event_state: StoryEventState) -> str:
        return "What do you do?"

    def _is_case_resolution_event(self, event: PlotEvent) -> bool:
        resolution_text = " ".join([
            event.description,
            " ".join(event.goals),
            " ".join(event.effects),
            event.clue or "",
            " ".join(event.hidden_expected_intents),
        ]).lower()
        case_resolution_terms = (
            "accuse culprit",
            "culprit confessed",
            "confesses to the crime",
            "confessed to the crime",
            "case closed",
            "case resolved",
            "under arrest",
            "arrest is made",
            "solved the case",
        )
        return any(term in resolution_text for term in case_resolution_terms)

    def _trigger_ready_event(self) -> Optional[str]:
        next_event = self.world.next_story_event()
        if not next_event or not self._event_is_ready(next_event):
            return None

        next_event.triggered = True
        self.world.offtrack_turns = 0
        event = next_event.event

        for effect in event.effects:
            self.world.add_fact(effect)
        if event.clue:
            self.world.add_clue(event.clue)

        if event.goal_type == "resolve" and self._is_case_resolution_event(event):
            self.world.story_status = "solved"
            self.world.ending_reason = f"Case resolved: {event.description}"

        return self._render_event_prose(event)

    def _trigger_story_segment(self) -> Optional[str]:
        response_parts: list[str] = []

        for _ in range(MAX_AUTONARRATED_EVENTS):
            next_event = self.world.next_story_event()
            if not next_event or not self._event_is_ready(next_event):
                break

            should_pause_after = self._is_decision_event(next_event)
            event_text = self._trigger_ready_event()
            if event_text:
                response_parts.append(event_text)

            if self.world.story_status in {"solved", "failed", "unsolvable"}:
                break
            if should_pause_after:
                response_parts.append(self._open_decision_prompt(next_event))
                break

        return "\n\n".join(response_parts) if response_parts else None

    def _fallback_accommodation(
        self,
        affected_events: list[StoryEventState],
        action: Optional[InterpretedAction] = None,
    ) -> list[PlotEvent]:
        anchor_event_state = affected_events[0] if affected_events else self.world.next_story_event()
        if not anchor_event_state:
            return []
        anchor = anchor_event_state.event
        repair_location = "Security Office" if "Security Office" in self.world.rooms else self.world.player_location
        if action and action.action_type == "accuse":
            repair_description = "A witness challenges the premature accusation and provides a fresh lead."
            repair_clue = "The failed accusation exposes a contradiction that points back to the real chain of evidence."
            repair_objects = ["witness statement"]
            repair_effects = ["new witness statement is available", "investigation regains direction"]
        else:
            lost_target = _normalize((action.target_object or action.target) if action else "")
            if "fabric" in lost_target:
                repair_description = (
                    "Clara finds a backup security still from the gallery camera showing a dark sleeve "
                    "snagging on the display case."
                )
                repair_clue = "A still image shows the thief's dark sleeve catching near the display case."
                repair_objects = ["backup security still"]
            elif "footage" in lost_target or "camera" in lost_target:
                repair_description = (
                    "Clara finds an archived access log that recorded the side door opening during the theft."
                )
                repair_clue = "The access log shows the side door opened during the theft window."
                repair_objects = ["archived access log"]
            elif "email" in lost_target:
                repair_description = (
                    "Clara finds a synced copy of the curator's message in the mail server archive."
                )
                repair_clue = "The archived email links the curator to Alex before the theft."
                repair_objects = ["archived email"]
            else:
                repair_description = "Clara uncovers a secondary witness note that restores the investigation's direction."
                repair_clue = "The witness note points back to the next lead in the evidence chain."
                repair_objects = ["witness note"]
            repair_effects = ["alternate lead is available"]
        return [
            PlotEvent(
                event_id=f"R_{anchor.event_id}",
                description=repair_description,
                characters=["Clara"],
                goals=anchor.goals[:1],
                caused_by=[anchor.event_id],
                goal_type="initiate",
                location=repair_location,
                preconditions=[],
                effects=repair_effects,
                required_objects=repair_objects,
                clue=repair_clue,
            )
        ]

    def _accommodate_exception(
        self,
        action: InterpretedAction,
        affected_events: list[StoryEventState],
    ) -> str:
        for event_state in affected_events:
            event_state.invalidated = True
            event_state.invalid_reason = f"Player action made {event_state.event.event_id} unreliable."

        anchor_events = affected_events[:]
        if not anchor_events:
            next_event = self.world.next_story_event()
            if next_event:
                anchor_events = [next_event]

        repairs: list[PlotEvent] = []
        if self.llm and anchor_events:
            try:
                repairs = self.llm.accommodate_story_break(
                    exception_action=action.target or action.action_type,
                    world_context=self._build_context_summary(),
                    affected_events=[event_state.event for event_state in anchor_events],
                )
            except Exception:
                repairs = []

        if not repairs:
            repairs = self._fallback_accommodation(anchor_events, action=action)

        if repairs:
            if anchor_events:
                anchor_index = max(
                    self.world.event_states.index(anchor_events[0]),
                    0,
                )
            else:
                anchor_index = 0
            for offset, repair in enumerate(repairs, start=1):
                repair.event_id = repair.event_id or f"R_{anchor_events[0].event.event_id}_{offset}" if anchor_events else f"R_{offset}"
                if not repair.event_id.startswith("R_"):
                    repair.event_id = f"R_{repair.event_id}"
                repair.location = repair.location or self.world.player_location
                if repair.location not in self.world.rooms:
                    self.world.rooms[repair.location] = Room(
                        name=repair.location,
                        description=_room_description(repair.location),
                    )
                    _connect_rooms(self.world.rooms)
                repair_room = self.world.rooms[repair.location]
                for obj in repair.required_objects:
                    if obj and obj not in repair_room.objects:
                        repair_room.objects.append(obj)
                if repair.clue and repair.clue not in repair_room.clues:
                    repair_room.clues.append(repair.clue)
                if affected_events:
                    insertion_index = anchor_index + offset
                else:
                    insertion_index = anchor_index + offset - 1
                self.world.event_states.insert(insertion_index, StoryEventState(event=repair))

            if action.action_type == "accuse":
                self.world.last_intervention = (
                    "Drama manager intervention: the accusation redirected suspicion, and a new lead was introduced."
                )
            else:
                self.world.last_intervention = (
                    "Drama manager intervention: the original plan was repaired with an alternate lead."
                )

            next_repair = self.world.next_story_event()
            repair_guidance = None
            if next_repair and next_repair.event.event_id.startswith("R_"):
                repair = next_repair.event
                parts = [
                    f"New lead: {repair.description}",
                    f"Location: {repair.location}.",
                ]
                if repair.required_objects:
                    parts.append(f"Look for: {', '.join(repair.required_objects[:2])}.")
                if repair.clue:
                    parts.append(f"Possible clue: {repair.clue}")
                path = self.world.path_to_room(repair.location or "")
                if path and len(path) > 1:
                    parts.append(f"Route: {' -> '.join(path)}.")
                repair_guidance = " ".join(parts)

            ready_text = self._trigger_story_segment()
            response_parts = [self.world.last_intervention]
            if ready_text:
                response_parts.append(ready_text)
                if "What do you do?" not in ready_text:
                    response_parts.append("What do you do?")
            elif repair_guidance:
                response_parts.append(repair_guidance)
                response_parts.append("What do you do?")
            return "\n\n".join(response_parts)

        self.world.story_status = "unsolvable"
        self.world.ending_reason = (
            "The case can no longer be repaired after the damage to critical story elements."
        )
        return self.world.ending_reason

    def _soft_hint(self) -> Optional[str]:
        if self.world.offtrack_turns < 3:
            return None
        next_event = self.world.next_story_event()
        if not next_event:
            return None
        hint_path = self.world.path_to_room(next_event.event.location or "")
        path_text = ""
        if hint_path and len(hint_path) > 1:
            path_text = f" Follow this route: {' -> '.join(hint_path)}."
        self.world.last_intervention = (
            f"Hint: the next useful lead is likely in {next_event.event.location}.{path_text}"
        )
        self.world.offtrack_turns = 0
        return self.world.last_intervention

    def _final_status_check(self) -> Optional[str]:
        if self.world.story_status in {"solved", "failed", "unsolvable"}:
            return self.world.ending_reason

        if not self.world.remaining_story_events():
            self.world.story_status = "solved"
            clue_summary = "\n  - ".join(self.world.known_clues) if self.world.known_clues else "none recorded"
            self.world.ending_reason = (
                f"\n{'='*60}\n"
                f"INVESTIGATION COMPLETE\n"
                f"{'='*60}\n"
                f"Every thread of the investigation has been followed to its conclusion.\n\n"
                f"Evidence gathered:\n  - {clue_summary}\n\n"
                f"The case is closed. Justice has been served.\n\n"
                f"Turns taken: {self.world.turn_count} | "
                f"Clues gathered: {len(self.world.known_clues)} | "
                f"Disruptions: {self.world.exceptional_actions}\n"
                f"{'='*60}"
            )
            return self.world.ending_reason

        if self.world.exceptional_actions >= 3 and not any(
            event.goal_type == "resolve" and not event.invalidated
            for event in self.world.remaining_story_events()
        ):
            self.world.story_status = "unsolvable"
            self.world.ending_reason = (
                "Too many critical disruptions have removed every clear route to solve the case."
            )
            return self.world.ending_reason

        return None

    def handle_command(self, command: str) -> str:
        raw = command.strip()
        if not raw:
            return "Type a natural-language action like 'go to the security office' or 'inspect the display case'."
        if len(raw.split()) > MAX_COMMAND_WORDS:
            return f"Keep actions short: {MAX_COMMAND_WORDS} words or fewer."

        lower = raw.lower()
        if lower in {"help", "?"}:
            return (
                "Commands still supported directly: look, status, map, inventory, quit.\n"
                "You can also type open-ended actions like 'go to the gallery', 'inspect the case', "
                "'question Sarah', 'take the notes', 'break the footage', or 'accuse Sarah'."
            )

        if lower == "look":
            return self.world.describe_current_room()

        if lower == "status":
            triggered = sum(1 for event in self.world.event_states if event.triggered)
            valid_total = sum(1 for event in self.world.event_states if not event.invalidated)
            return (
                f"Story status: {self.world.story_status}\n"
                f"Last action type: {self.world.last_classification or 'none yet'}\n"
                f"Objective focus: {', '.join(self.world.objectives) if self.world.objectives else 'investigate the case'}\n"
                f"Known clues: {', '.join(self.world.known_clues) if self.world.known_clues else 'none yet'}\n"
                f"Progress: {triggered}/{valid_total} active story events completed\n"
                f"Last intervention: {self.world.last_intervention or 'none'}"
            )

        if lower == "map":
            lines = []
            for room_name, room in self.world.rooms.items():
                exits = ", ".join(f"{k}->{v}" for k, v in room.exits.items()) or "no exits"
                lines.append(f"{room_name}: {exits}")
            return "\n".join(lines)

        if lower == "inventory":
            return "Inventory: " + (", ".join(self.world.inventory) if self.world.inventory else "empty")

        if lower == "quit":
            return "quit"

        if lower.startswith(("who ", "why ", "what ")):
            if lower.startswith("who ") and any(word in lower for word in ("see", "seen", "visible", "footage", "camera")):
                visual_answer = self._visual_evidence_answer()
                if visual_answer:
                    return visual_answer
            if any(word in lower for word in ("document", "note", "email", "message", "record", "file", "folder", "transaction")):
                target = re.sub(
                    r"^(what|why|who)\s+(is|was|do|does|did)?\s*(on|in|inside|about)?\s*(the\s+)?",
                    "",
                    raw,
                    count=1,
                    flags=re.IGNORECASE,
                ).strip()
                readable_answer = self._readable_evidence_answer(target)
                if readable_answer:
                    return readable_answer
            room = self.world.current_room()
            next_event = self.world.next_story_event()
            lines = [self.world.describe_current_room()]
            if next_event:
                lines.append(
                    f"Current lead: {next_event.event.description} "
                    f"({next_event.event.location})."
                )
            if room.npcs:
                lines.append("People present: " + ", ".join(room.npcs))
            return "\n".join(lines)

        self.world.turn_count += 1
        action = self._interpret_action(raw)
        repeat_count = self._track_action_repetition(action)
        valid, reason = self._validate_action(action)
        if not valid:
            self.world.offtrack_turns += 1
            hint = self._soft_hint()
            if action.action_type == "move":
                target = action.target_location or action.target
                resolved_room = self.world.resolve_room_name(target) if target else None
                if resolved_room:
                    path = self.world.path_to_room(resolved_room)
                    if path and len(path) > 1:
                        reason = (
                            f"You cannot jump straight there from here, but you can travel to {resolved_room}. "
                            f"Use this route: {' -> '.join(path)}."
                        )
            return reason if not hint else reason + "\n" + hint

        classification, affected_events = self._classify_action(action)
        self.world.last_classification = classification

        result = self._apply_action(action)

        response_parts = [
            f"Action classification: {classification}",
            result,
        ]

        if action.action_type == "unknown":
            guidance = self._next_lead_guidance()
            if guidance:
                response_parts.append(guidance)
            hint = self._soft_hint()
            if hint:
                response_parts.append(hint)
            return "\n\n".join(part for part in response_parts if part)

        if classification == "exceptional":
            self.world.exceptional_actions += 1
            intervention = self._accommodate_exception(action, affected_events)
            response_parts.append(intervention)
            self.world.offtrack_turns = 0
        else:
            if classification == "consistent":
                self.world.offtrack_turns += 1
            else:
                self.world.offtrack_turns = 0

            event_text = self._trigger_story_segment()
            if event_text:
                response_parts.append(event_text)
            elif classification in {"consistent", "constituent"}:
                guidance = self._next_lead_guidance()
                if guidance:
                    response_parts.append(guidance)

            hint = self._soft_hint()
            if hint:
                response_parts.append(hint)

        final_status = self._final_status_check()
        if final_status:
            response_parts.append(f"Ending: {final_status}")

        return "\n\n".join(part for part in response_parts if part)

    def run(self) -> None:
        print("\n" + "=" * 60)
        print("RAMBLING RHINO: INTERACTIVE STORY MODE")
        print("=" * 60)
        print(self.world.premise)
        print()
        print(self.world.describe_current_room())
        print("\nType 'help' for commands. Type 'quit' to stop.\n")

        opening_event = self._trigger_story_segment()
        if opening_event:
            print(opening_event)
            print()

        while True:
            try:
                command = input("> ")
            except EOFError:
                print("\nExiting interactive mode.")
                return

            result = self.handle_command(command)
            if result == "quit":
                print("Exiting interactive mode.")
                return

            print(result)
            print()

            if self.world.story_status in {"solved", "failed", "unsolvable"}:
                if self.world.story_status == "solved":
                    print(f"\nFinal story status: SOLVED")
                elif self.world.story_status == "unsolvable":
                    print(f"\nFinal story status: UNSOLVABLE — too many critical disruptions.")
                else:
                    print(f"\nFinal story status: {self.world.story_status.upper()}")
                return


def action_target(required_objects: list[str]) -> str:
    return required_objects[0] if required_objects else "a key clue"
