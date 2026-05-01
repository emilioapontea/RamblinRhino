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


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _match_name(target: str, candidates: list[str]) -> Optional[str]:
    norm_target = _normalize(target)
    for candidate in candidates:
        norm_candidate = _normalize(candidate)
        if norm_target and (norm_target in norm_candidate or norm_candidate in norm_target):
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
    last_classification: str = ""
    last_intervention: str = ""
    offtrack_turns: int = 0
    exceptional_actions: int = 0
    suspect_name: Optional[str] = None

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
    ordered = [name for name in DEFAULT_ROOM_ORDER if name in rooms]
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
        room.npcs.extend(char for char in event.characters if char and char not in room.npcs)
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
        self._current_option_map: dict = {}

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

    def _fallback_event_prose(self, event: PlotEvent) -> str:
        room_phrase = f"In the {event.location.lower()}, " if event.location else ""
        description_text = event.description.strip()
        people_phrase = ""
        if event.characters:
            if len(event.characters) == 1:
                people_phrase = f"{event.characters[0]} "
            elif len(event.characters) == 2:
                people_phrase = f"{event.characters[0]} and {event.characters[1]} "
            else:
                people_phrase = f"{', '.join(event.characters[:-1])}, and {event.characters[-1]} "
        if event.characters and description_text:
            first_character = event.characters[0].lower()
            if description_text.lower().startswith(first_character):
                people_phrase = ""

        lines = [
            f"{room_phrase}{people_phrase}{description_text[0].lower() + description_text[1:] if description_text else ''}".strip(),
        ]
        if event.clue:
            lines.append(f"The moment leaves behind a telling detail: {event.clue}.")
        elif event.effects:
            lines.append(f"The development changes the investigation in a concrete way: {', '.join(event.effects)}.")
        if event.goals:
            lines.append(f"For now, the focus shifts toward {', '.join(event.goals)}.")
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
        lower = command.lower().strip()
        if any(word in lower for word in ("perpetrator", "culprit", "thief", "killer")) and any(
            word in lower for word in ("find", "caught", "catch", "identify", "it's", "is ")
        ):
            return InterpretedAction(
                action_type="accuse",
                target=command.strip(),
                target_character=command.strip(),
            )
        if lower.startswith("go "):
            target = re.sub(r"^(go|walk|move|head)\s+(to\s+)?", "", lower, count=1).strip()
            return InterpretedAction(action_type="move", target=target, target_location=target)
        if any(lower.startswith(prefix) for prefix in ("walk ", "move ", "head ")):
            target = re.sub(r"^(go|walk|move|head)\s+(to\s+)?", "", lower, count=1).strip()
            return InterpretedAction(action_type="move", target=target, target_location=target)
        if lower.startswith("inspect "):
            target = command[8:].strip()
            return InterpretedAction(action_type="inspect", target=target, target_object=target)
        if lower.startswith("talk "):
            target = command[5:].strip()
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
        if not self.llm:
            return self._heuristic_action(command)
        try:
            return self.llm.interpret_player_action(
                command=command,
                world_context=self._build_context_summary(),
            )
        except Exception:
            return self._heuristic_action(command)

    def _current_targets(self) -> tuple[list[str], list[str]]:
        room = self.world.current_room()
        objects = list(dict.fromkeys([*room.objects, *self.world.inventory]))
        people = list(dict.fromkeys(room.npcs))
        return objects, people

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
            return False, f"You do not have access to '{target}' here."

        if action.action_type in {"talk", "accuse"}:
            target = action.target_character or action.target
            if not target:
                return False, "That action needs a person."
            matched = _match_name(target, people)
            if matched or action.action_type == "accuse":
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
            if target and any(target in candidate or candidate in target for candidate in event_targets if candidate):
                affected.append(event_state)
        return affected

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

        if action.action_type in {"damage", "block"} and affected_events:
            return "exceptional", affected_events

        if action.action_type == "accuse":
            if self.world.suspect_name and _match_name(action.target_character or action.target, [self.world.suspect_name]):
                return "constituent", affected_events
            return "exceptional", self._exception_anchor_events(action)

        if next_event:
            target_pool = [
                next_event.event.location or "",
                *(next_event.event.required_objects or []),
                *(next_event.event.characters or []),
            ]
            target = action.target or ""
            if self.world.player_location == next_event.event.location:
                if action.action_type in {"inspect", "talk", "take", "use"}:
                    return "constituent", affected_events
                if action.action_type == "move" and action.target_location == next_event.event.location:
                    return "constituent", affected_events
            if any(_normalize(target) in _normalize(item) for item in target_pool if item and target):
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
            matched_clue = _match_name(target, room.clues)
            if matched_clue:
                self.world.add_clue(matched_clue)
                self.world.add_fact(f"inspected {matched_clue}")
                return f"You inspect {matched_clue} and notice: {matched_clue}"
            matched_object = _match_name(target, room.objects + self.world.inventory)
            if matched_object:
                self.world.add_fact(f"inspected {matched_object}")
                return f"You inspect the {matched_object}. It seems relevant to the case."
            return f"You do not see anything matching '{target}' here."

        if action.action_type == "talk":
            target = _match_name(action.target_character or action.target, room.npcs)
            if target:
                self.world.add_fact(f"talked to {target}")
                for clue in room.clues:
                    self.world.add_clue(clue)
                return f"You talk to {target}. They share what they know about this location."
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
                    self.world.ending_reason = f"You accuse {self.world.suspect_name} and the evidence holds."
                    return self.world.ending_reason
                return f"You accuse {self.world.suspect_name}, but you do not have enough evidence yet."
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

        if event.goal_type == "resolve":
            self.world.story_status = "solved"
            self.world.ending_reason = f"Case resolved: {event.description}"

        return self._render_event_prose(event)

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
            repair_description = "An alternate lead emerges, giving the investigation a new way forward."
            repair_clue = (
                f"A backup record preserves the lead after the loss of {action_target(anchor.required_objects)}."
                if anchor.required_objects else
                "A secondary witness account restores the investigation's direction."
            )
            repair_objects = ["backup record"]
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

        repairs: list[PlotEvent] = []
        if self.llm and affected_events:
            try:
                repairs = self.llm.accommodate_story_break(
                    exception_action=action.target or action.action_type,
                    world_context=self._build_context_summary(),
                    affected_events=[event_state.event for event_state in affected_events],
                )
            except Exception:
                repairs = []

        if not repairs:
            repairs = self._fallback_accommodation(affected_events, action=action)

        if repairs:
            insertion_index = max(
                self.world.event_states.index(affected_events[0]),
                0,
            )
            for offset, repair in enumerate(repairs, start=1):
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
                self.world.event_states.insert(
                    insertion_index + offset,
                    StoryEventState(event=repair),
                )

            if action.action_type == "accuse":
                self.world.last_intervention = (
                    "Drama manager intervention: the accusation redirected suspicion, and a new lead was introduced."
                )
            else:
                self.world.last_intervention = (
                    "Drama manager intervention: the original plan was repaired with an alternate lead."
                )
            return self.world.last_intervention

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

    def _generate_available_options(self) -> dict:
        """Generate clear, structured options for the player based on current game state."""
        room = self.world.current_room()
        next_event = self.world.next_story_event()
        options = {
            "movement": [],
            "interaction": [],
            "investigation": [],
            "decisions": [],
        }

        # Movement options: nearby rooms
        if room.exits:
            for direction, destination in room.exits.items():
                options["movement"].append({
                    "action": f"go {direction.lower()}",
                    "display": f"Go {direction.lower()} to {destination}",
                    "target": destination,
                })

        # Interaction options: NPCs in this room
        for npc in room.npcs:
            options["interaction"].append({
                "action": f"talk to {npc.lower()}",
                "display": f"Talk to {npc}",
                "target": npc,
            })

        # Investigation options: objects and clues in room
        for obj in room.objects:
            options["investigation"].append({
                "action": f"inspect {obj.lower()}",
                "display": f"Inspect {obj}",
                "target": obj,
            })
        for clue in room.clues:
            options["investigation"].append({
                "action": f"inspect {clue.lower()}",
                "display": f"Examine {clue}",
                "target": clue,
            })

        # Take objects
        for obj in room.objects:
            if obj not in self.world.inventory:
                options["investigation"].append({
                    "action": f"take {obj.lower()}",
                    "display": f"Take {obj}",
                    "target": obj,
                })

        # Use inventory items
        for item in self.world.inventory:
            options["interaction"].append({
                "action": f"use {item.lower()}",
                "display": f"Use {item}",
                "target": item,
            })

        # Decision-based options
        if next_event and next_event.event.characters:
            suspect_name = _match_name(self.world.suspect_name or "", next_event.event.characters)
            if suspect_name:
                options["decisions"].append({
                    "action": f"accuse {suspect_name.lower()}",
                    "display": f"Accuse {suspect_name}",
                    "target": suspect_name,
                })

        # Wait option
        options["decisions"].append({
            "action": "wait",
            "display": "Wait for more information",
            "target": "wait",
        })

        return options

    def _format_options_display(self) -> str:
        """Format available options for display to player."""
        room = self.world.current_room()
        next_event = self.world.next_story_event()
        objectives_str = ", ".join(self.world.objectives) if self.world.objectives else "investigate the case"
        known_clues_str = f" ({len(self.world.known_clues)} clues found)" if self.world.known_clues else " (no clues yet)"

        lines = []
        lines.append("\n" + "─" * 60)
        lines.append(f"OBJECTIVE: {objectives_str}{known_clues_str}")
        lines.append("─" * 60)
        
        # Current situation
        next_event_display = ""
        if next_event:
            next_event_display = f"\nNext story beat: {next_event.event.description}"
            lines.append(next_event_display)

        lines.append("")
        options = self._generate_available_options()

        # Display options grouped by category
        option_num = 1
        option_map = {}

        if options["movement"]:
            lines.append("📍 WHERE YOU CAN GO:")
            for opt in options["movement"]:
                lines.append(f"  [{option_num}] {opt['display']}")
                option_map[option_num] = opt
                option_num += 1

        if options["interaction"]:
            lines.append("\n🗣️  WHO/WHAT YOU CAN INTERACT WITH:")
            for opt in options["interaction"]:
                lines.append(f"  [{option_num}] {opt['display']}")
                option_map[option_num] = opt
                option_num += 1

        if options["investigation"]:
            lines.append("\n🔍 WHAT YOU CAN INVESTIGATE:")
            for opt in options["investigation"]:
                lines.append(f"  [{option_num}] {opt['display']}")
                option_map[option_num] = opt
                option_num += 1

        if options["decisions"]:
            lines.append("\n⚖️  MAJOR DECISIONS:")
            for opt in options["decisions"]:
                lines.append(f"  [{option_num}] {opt['display']}")
                option_map[option_num] = opt
                option_num += 1

        lines.append("\n" + "─" * 60)
        lines.append("Enter an option number, or describe your action in natural language.")
        lines.append("Type 'status' for case progress, 'inventory' for items, 'map' for locations.")
        lines.append("─" * 60)

        self._current_option_map = option_map
        return "\n".join(lines)

    def _final_status_check(self) -> Optional[str]:
        if self.world.story_status in {"solved", "failed", "unsolvable"}:
            return self.world.ending_reason

        if not self.world.remaining_story_events():
            self.world.story_status = "solved"
            self.world.ending_reason = "Every remaining story beat has been completed."
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

        lower = raw.lower()
        
        # Check if user entered a numbered option
        if lower.isdigit():
            option_num = int(lower)
            if option_num in self._current_option_map:
                selected_opt = self._current_option_map[option_num]
                # Recursively handle the selected action
                return self.handle_command(selected_opt["action"])
            else:
                return f"Invalid option number. Please choose from the available options [1-{len(self._current_option_map)}]."
        
        if lower in {"help", "?"}:
            return (
                "Commands still supported directly: look, status, map, inventory, quit.\n"
                "You can also type open-ended actions like 'go to the gallery', 'inspect the case', "
                "'talk to Clara', 'take the notes', 'break the footage', or 'accuse Sarah'.\n"
                "Or select one of the numbered options displayed before each prompt."
            )

        if lower == "look":
            return self.world.describe_current_room()

        if lower == "status":
            triggered = sum(1 for event in self.world.event_states if event.triggered)
            valid_total = sum(1 for event in self.world.event_states if not event.invalidated)
            objectives_str = ", ".join(self.world.objectives) if self.world.objectives else "investigate the case"
            return (
                f"🎯 Objectives: {objectives_str}\n"
                f"📋 Story status: {self.world.story_status}\n"
                f"📍 Current location: {self.world.player_location}\n"
                f"🔍 Known clues: {', '.join(self.world.known_clues) if self.world.known_clues else 'none yet'}\n"
                f"📦 Inventory: {', '.join(self.world.inventory) if self.world.inventory else 'empty'}\n"
                f"✅ Progress: {triggered}/{valid_total} active story beats completed\n"
                f"💬 Last update: {self.world.last_intervention or 'investigation ongoing'}"
            )

        if lower == "map":
            lines = []
            for room_name, room in self.world.rooms.items():
                exits = ", ".join(f"{k}->{v}" for k, v in room.exits.items()) or "no exits"
                lines.append(f"{room_name}: {exits}")
            return "\n".join(lines)

        if lower == "inventory":
            return "📦 Inventory: " + (", ".join(self.world.inventory) if self.world.inventory else "empty")

        if lower == "quit":
            return "quit"

        self.world.turn_count += 1
        action = self._interpret_action(raw)
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
            result,
        ]

        if classification == "exceptional":
            self.world.exceptional_actions += 1
            intervention = self._accommodate_exception(action, affected_events)
            response_parts.append(f"⚠️  {intervention}")
            self.world.offtrack_turns = 0
        else:
            if classification == "consistent":
                self.world.offtrack_turns += 1
            else:
                self.world.offtrack_turns = 0

            event_text = self._trigger_ready_event()
            if event_text:
                response_parts.append(f"📖 {event_text}")

            hint = self._soft_hint()
            if hint:
                response_parts.append(f"💡 {hint}")

        final_status = self._final_status_check()
        if final_status:
            response_parts.append(f"\n🎬 ENDING: {final_status}")

        return "\n\n".join(part for part in response_parts if part)

    def run(self) -> None:
        print("\n" + "=" * 60)
        print("RAMBLING RHINO: INTERACTIVE STORY MODE")
        print("=" * 60)
        print(f"\n🎭 {self.world.premise}\n")
        print(self.world.describe_current_room())
        print("\nType 'help' for commands. Type 'quit' to stop.\n")

        opening_event = self._trigger_ready_event()
        if opening_event:
            print(f"📖 {opening_event}\n")

        while True:
            # Display available options before prompting
            print(self._format_options_display())
            
            try:
                command = input("\n> ")
            except EOFError:
                print("\nExiting interactive mode.")
                return

            result = self.handle_command(command)
            if result == "quit":
                print("Exiting interactive mode.")
                return

            print(f"\n{result}")

            if self.world.story_status in {"solved", "failed", "unsolvable"}:
                print(f"\n🎬 Final story status: {self.world.story_status}")
                return


def action_target(required_objects: list[str]) -> str:
    return required_objects[0] if required_objects else "a key clue"
