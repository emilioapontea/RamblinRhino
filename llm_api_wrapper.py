# llm_api_wrapper.py
# LLM wrapper for the Rambling Rhino Reader-Model-Driven Story Generation system
# Uses the Groq API, free, with a limit of ~6000 tokens a min, ~500,000 tokens a day
# Model used: llama-3.3-70b-versatile

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional
import requests

GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "API_KEY_HERE")

_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# There are 2 model options: "llama-3.3-70b-versatile", "llama-3.1-8b-instant"
_MODEL = "llama-3.3-70b-versatile"


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


# Data Structures
@dataclass
class PlotEvent:
    event_id:    str
    description: str
    characters:  list[str]     = field(default_factory=list)
    goals:       list[str]     = field(default_factory=list)
    caused_by:   list[str]     = field(default_factory=list)
    causes:      list[str]     = field(default_factory=list)
    goal_type:   Optional[str] = None
    location:    Optional[str] = None
    preconditions: list[str]   = field(default_factory=list)
    effects:       list[str]   = field(default_factory=list)
    required_objects: list[str] = field(default_factory=list)
    clue:         Optional[str] = None
    is_decision_point: bool = False
    decision_context: str = ""
    hidden_expected_intents: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"[{self.event_id}] {self.description}\n"
            f"  characters : {self.characters}\n"
            f"  goals      : {self.goals}\n"
            f"  caused_by  : {self.caused_by}\n"
            f"  goal_type  : {self.goal_type}\n"
            f"  location   : {self.location}\n"
            f"  preconditions: {self.preconditions}\n"
            f"  effects    : {self.effects}\n"
            f"  required_objects: {self.required_objects}\n"
            f"  clue       : {self.clue}\n"
            f"  decision_point: {self.is_decision_point}"
        )

    @classmethod
    def from_dict(cls, data: dict) -> "PlotEvent":
        return cls(
            event_id=str(data.get("event_id", "")),
            description=str(data.get("description", "")).strip(),
            characters=list(data.get("characters", [])),
            goals=list(data.get("goals", [])),
            caused_by=list(data.get("caused_by", [])),
            causes=list(data.get("causes", [])),
            goal_type=data.get("goal_type"),
            location=data.get("location"),
            preconditions=list(data.get("preconditions", [])),
            effects=list(data.get("effects", [])),
            required_objects=list(data.get("required_objects", [])),
            clue=data.get("clue"),
            is_decision_point=_as_bool(data.get("is_decision_point", False)),
            decision_context=str(data.get("decision_context", "") or ""),
            hidden_expected_intents=list(data.get("hidden_expected_intents", [])),
        )


@dataclass
class TokenUsage:
    input_tokens:  int = 0
    output_tokens: int = 0

    def add(self, inp: int, out: int) -> None:
        self.input_tokens  += inp
        self.output_tokens += out

    def __str__(self) -> str:
        return (
            f"TokenUsage(input={self.input_tokens:,}, "
            f"output={self.output_tokens:,}, "
            f"cost=$0.00 [Groq free tier])"
        )


@dataclass
class InterpretedAction:
    action_type: str
    target: str = ""
    target_location: Optional[str] = None
    target_object: Optional[str] = None
    target_character: Optional[str] = None
    intent_summary: str = ""
    implied_effects: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)


class LLMClient:
    def __init__(
        self,
        api_key:       str   = GROQ_API_KEY,
        model:         str   = _MODEL,
        max_tokens:    int   = 4096,   # increased for longer output
        temperature:   float = 0.85,
        request_delay: float = 0.5,
        verbose:       bool  = False,
    ) -> None:
        if not api_key or api_key == "YOUR_GROQ_API_KEY_HERE":
            raise ValueError("No Groq API key found.")
        self.api_key       = api_key
        self.model         = model
        self.max_tokens    = max_tokens
        self.temperature   = temperature
        self.request_delay = request_delay
        self.verbose       = verbose
        self.usage         = TokenUsage()

        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        })

    ## Engagement Phase
    def generate_crime_plot_events(
        self,
        premise: str,
        num_events: int = 8,
        existing_events: Optional[list[PlotEvent]] = None,
        genre: str = "crime mystery",
    ) -> list[PlotEvent]:
        user_prompt = _build_engagement_prompt(
            premise, num_events, existing_events, genre
        )
        events, raw = self._complete_events_with_repair(
            system=_ENGAGEMENT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            label="crime-story call",
        )
        if self.verbose or len(events) == 0:
            print(f"[LLMClient] parsed {len(events)} events from crime-story call")
            if len(events) == 0:
                print(f"[LLMClient] raw response (first 500 chars):\n{raw[:500]}")
        return events

    def generate_solving_plot_events(
        self,
        premise: str,
        existing_events: list[PlotEvent],
        num_events: int = 8,
        genre: str = "crime mystery",
    ) -> list[PlotEvent]:
        user_prompt = _build_solving_prompt(
            premise=premise,
            num_events=num_events,
            existing_events=existing_events,
            genre=genre,
        )
        events, raw = self._complete_events_with_repair(
            system=_ENGAGEMENT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            label="solving call",
        )
        if self.verbose or len(events) == 0:
            print(f"[LLMClient] parsed {len(events)} events from solving call")
            if len(events) == 0:
                print(f"[LLMClient] raw response (first 500 chars):\n{raw[:500]}")
        return events

    ## Reflection Phase
    def reflect_on_quest_gap(
        self,
        gap_description: str,
        story_so_far: str,
        insert_after_event_id: Optional[str] = None,
    ) -> list[PlotEvent]:
        user_prompt = _build_reflection_prompt(
            gap_description, story_so_far, insert_after_event_id
        )
        events, _ = self._complete_events_with_repair(
            system=_REFLECTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            label="reflection call",
        )
        return events

    def interpret_player_action(
        self,
        command: str,
        world_context: str,
    ) -> InterpretedAction:
        prompt = _build_action_interpretation_prompt(command, world_context)
        raw = self._complete(_ACTION_INTERPRETER_SYSTEM_PROMPT, prompt)
        parsed = _parse_action_interpretation(raw)
        if parsed:
            return parsed
        return _heuristic_interpreted_action(command)

    def accommodate_story_break(
        self,
        exception_action: str,
        world_context: str,
        affected_events: list[PlotEvent],
    ) -> list[PlotEvent]:
        prompt = _build_accommodation_prompt(exception_action, world_context, affected_events)
        events, _ = self._complete_events_with_repair(
            system=_REFLECTION_SYSTEM_PROMPT,
            user_prompt=prompt,
            label="accommodation call",
        )
        return events

    def narrate_interactive_event(
        self,
        event: PlotEvent,
        world_context: str,
    ) -> str:
        prompt = _build_interactive_event_prose_prompt(event, world_context)
        return self._complete(_INTERACTIVE_EVENT_PROSE_SYSTEM_PROMPT, prompt).strip()

    ## Prose Generation, produces a long, plot-point-labeled story
    def generate_prose(
        self,
        events: list[PlotEvent],
        genre: str = "crime mystery",
        style_notes: str = "",
    ) -> str:
        if not events:
            return "[ERROR: No plot events were generated. Check API key and JSON parsing.]"

        # Build a numbered, labeled plot-point list to pass to the LLM
        plot_points = "\n".join(
            f"  Plot Point {i+1} [{e.event_id}]: {e.description}"
            for i, e in enumerate(events)
        )

        # Derive a one-sentence ending summary from the last event for the closing instruction
        last_event = events[-1].description

        system = (
            "You are a skilled literary fiction author. "
            "You write long, detailed, immersive stories with rich prose, "
            "vivid character development, and scene-setting description. "
            "You always write stories that reach a fully resolved, satisfying conclusion."
        )

        prompt = (
            f"Genre: {genre}\n"
            + (f"Style notes: {style_notes}\n" if style_notes else "")
            + f"\nYou have {len(events)} plot points to cover. "
            "Write a LONG, complete short story (aim for 1500-2000 words) "
            "that covers every single plot point below in order.\n\n"
            "CRITICAL RULES:\n"
            "- The story MUST end with a fully resolved, complete conclusion. "
            "Do NOT end mid-sentence, mid-investigation, or on an open note. "
            f"The final paragraph must resolve the story, the last plot point is: \"{last_event}\"\n"
            "- Before writing the prose for each plot point, insert a clearly labeled "
            "marker on its own line in this exact format:\n"
            "  --- Plot Point N: [one-sentence summary] ---\n"
            "- After that marker, write 2-4 paragraphs of rich narrative prose.\n"
            "- Do NOT skip any plot points.\n"
            "- Write in third-person, past tense.\n"
            "- Keep each plot point section to 100-150 words so you have room to finish.\n\n"
            f"Plot points to cover:\n{plot_points}\n\n"
            "Begin the story now, and make sure the final paragraph is a complete, "
            "satisfying ending that wraps up all loose threads:\n"
        )

        # Use a higher token limit for prose generation
        old_max = self.max_tokens
        self.max_tokens = 8192
        prose = self._complete(system, prompt)
        self.max_tokens = old_max

        # Safety check: if the prose appears to be cut off (ends mid-sentence),
        # make a short follow-up call to complete the ending.
        prose_stripped = prose.rstrip()
        last_char = prose_stripped[-1] if prose_stripped else ""
        if last_char not in ".!?\"'":
            print("[LLMClient] Prose appears cut off, requesting a conclusion...")
            conclusion_prompt = (
                f"The following story was cut off mid-sentence. "
                f"Write ONLY the concluding 1-2 paragraphs that finish it with a satisfying, "
                f"complete ending. Do not repeat any earlier content. "
                f"The story so far ends with:\n...{prose_stripped[-300:]}\n\n"
                f"Continue and conclude:"
            )
            self.max_tokens = 512
            conclusion = self._complete(system, conclusion_prompt)
            self.max_tokens = old_max
            prose = prose_stripped + " " + conclusion.strip()

        return prose

    ## Raw API Call
    def _complete(
        self,
        system: str,
        user: str,
        retries: int = 3,
    ) -> str:
        payload = {
            "model":       self.model,
            "max_tokens":  self.max_tokens,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        }

        for attempt in range(1, retries + 1):
            try:
                resp = self._session.post(_API_URL, json=payload, timeout=120)
                if resp.status_code == 429 or resp.status_code >= 500:
                    # Use longer backoff for 429 rate-limit errors
                    if resp.status_code == 429:
                        wait = 15 * attempt   # 15s, 30s, 45s
                        print(f"[LLMClient] Rate limited (429), waiting {wait}s "
                              f"(attempt {attempt}/{retries})")
                    else:
                        wait = self.request_delay * (2 ** attempt)
                        print(f"[LLMClient] HTTP {resp.status_code}, retrying in "
                              f"{wait:.1f}s (attempt {attempt}/{retries})")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                usage = data.get("usage", {})
                self.usage.add(
                    usage.get("prompt_tokens",     0),
                    usage.get("completion_tokens", 0),
                )
                text = data["choices"][0]["message"]["content"]
                if self.verbose:
                    print(f"[LLMClient] response:\n{text}\n{'─'*60}")
                return text
            except requests.RequestException as exc:
                print(f"[LLMClient] Request error (attempt {attempt}): {exc}")
                time.sleep(self.request_delay)
        raise RuntimeError(f"[LLMClient] All {retries} attempts failed.")

    def _complete_events_with_repair(
        self,
        system: str,
        user_prompt: str,
        label: str,
        parse_retries: int = 2,
    ) -> tuple[list[PlotEvent], str]:
        raw = self._complete(system, user_prompt)
        events = _parse_plot_events(raw)
        if events:
            return events, raw

        repair_prompt = (
            user_prompt
            + "\n\nYour previous response was not valid JSON."
            + "\nReturn ONLY a valid JSON array."
            + "\nEvery string value must be wrapped in double quotes."
            + "\nDo not include markdown, comments, or explanation."
            + "\nDo not leave any trailing commas."
        )

        for attempt in range(1, parse_retries + 1):
            print(f"[LLMClient] Retrying {label} with stricter JSON formatting (attempt {attempt}/{parse_retries})")
            raw = self._complete(system, repair_prompt)
            events = _parse_plot_events(raw)
            if events:
                return events, raw

        return [], raw


## Prompt Templates
_ENGAGEMENT_SYSTEM_PROMPT = """\
You are a story planner for a reader-model-driven narrative system (QUEST framework).
Your job is to generate ABSTRACT PLOT EVENTS: not prose, not dialogue.
Each event is a single declarative sentence describing what happens.
You MUST respond with a valid JSON array and absolutely nothing else.
Do not include any explanation, preamble, or markdown formatting.
Start your response with [ and end with ].
"""

_REFLECTION_SYSTEM_PROMPT = """\
You are a narrative coherence editor for a QUEST-based story system.
Your job is to insert bridging plot events that repair logical or causal gaps.
Each event must remain at the abstract plot level: 1 sentence, no prose.
You MUST respond with a valid JSON array and absolutely nothing else.
Do not include any explanation, preamble, or markdown formatting.
Start your response with [ and end with ].
"""

_ACTION_INTERPRETER_SYSTEM_PROMPT = """\
You are an action interpreter for an interactive detective story game.
Convert the player's natural-language command into a single JSON object.
Use one of these action types only:
"move", "inspect", "talk", "take", "use", "damage", "block", "accuse", "wait", "unknown".
Return only valid JSON with double-quoted strings and no markdown.
"""

_INTERACTIVE_EVENT_PROSE_SYSTEM_PROMPT = """\
You are a mystery game narrator.
Turn a structured plot event into short, immersive prose for the player.
Write 2-4 sentences in natural story language.
Do not use bullets, labels, JSON, or meta commentary.
Focus on what the player would perceive, infer, or feel as the event unfolds.
If the event names Clara, write her actions as the player's actions in second person.
"""


def _build_engagement_prompt(
    premise: str,
    num_events: int,
    existing_events: Optional[list[PlotEvent]],
    genre: str,
) -> str:
    context = ""
    if existing_events:
        last_id = existing_events[-1].event_id
        context = f"Crime-story events generated so far (last event_id was {last_id}):\n"
        for ev in existing_events:
            context += f"  [{ev.event_id}] {ev.description}\n"
        context += "\nContinue the crime story from the last event above.\n"

    return f"""\
Genre: {genre}
Premise: {premise}
{context}
Generate exactly {num_events} new CRIME STORY plot events.

The crime story should focus on:
- the crime itself
- How the crime is committed by the perpetrator(s).
- The detail of the act and the method used.
- Clara is the playable protagonist/archivist; do not make Clara the culprit.

Rules:
- One sentence per event, abstract plot level only
- Chronologically ordered and causally plausible
- Prioritize the concealement and the perpetrators motives
- Identify perpetrator characters involved
- Note any story goals this event initiates, resolves, or obstructs
- List which prior event_id(s) causally enable this event
- Include a concrete story location for where the event happens
- Include simple gameplay-friendly preconditions and effects
- For crime backstory, set "is_decision_point" to false unless this event will also be played interactively.

Your response must be ONLY a JSON array. Each element must have exactly these fields:
  "event_id": string (ex. "E1", "E2": if continuing, start from the next number)
  "description": one-sentence abstract event
  "characters": list of character name strings
  "goals": list of short goal-phrase strings
  "caused_by": list of event_id strings that enable this event ([] for the first event)
  "goal_type": "initiate" or "resolve" or "obstruct" or null
  "location": short room/location name string
  "preconditions": list of short state strings needed before the event
  "effects": list of short state strings caused by the event
  "required_objects": list of important object strings used or needed in the event
  "clue": short clue string revealed by this event, or null
  "is_decision_point": boolean
  "decision_context": hidden short description of why this is a meaningful open-ended intervention point, or ""
  "hidden_expected_intents": hidden list of broad action intents that could advance this beat

Example of correct output format, note only the output format and not the actual text in description:
[
  {{
    "event_id": "E1",
    "description": "The archivist arrives at the museum and finds the display case shattered.",
    "characters": ["Clara"],
    "goals": ["discover what happened"],
    "caused_by": [],
    "goal_type": "initiate",
    "location": "Museum Gallery",
    "preconditions": ["museum is open"],
    "effects": ["display case is broken", "theft is discovered"],
    "required_objects": ["display case"],
    "clue": "Shards suggest the case was opened from inside",
    "is_decision_point": false,
    "decision_context": "",
    "hidden_expected_intents": []
  }},
  {{
    "event_id": "E2",
    "description": "Clara realizes the priceless manuscript is missing.",
    "characters": ["Clara"],
    "goals": ["recover the manuscript"],
    "caused_by": ["E1"],
    "goal_type": "initiate",
    "location": "Museum Gallery",
    "preconditions": ["display case is broken"],
    "effects": ["manuscript is confirmed missing"],
    "required_objects": ["manuscript"],
    "clue": "Only staff with access could approach unnoticed",
    "is_decision_point": false,
    "decision_context": "",
    "hidden_expected_intents": []
  }}
]

Now generate exactly {num_events} crime-story events in that format:"""


def _build_reflection_prompt(
    gap_description: str,
    story_so_far: str,
    insert_after_event_id: Optional[str],
) -> str:
    insertion_hint = (
        f"Insert new event(s) immediately after event {insert_after_event_id}."
        if insert_after_event_id
        else "Insert new event(s) at the most logical position."
    )

    return f"""\
Story so far:
{story_so_far}

Narrative gap identified by the QUEST coherence checker:
{gap_description}

{insertion_hint}

Generate 1-2 bridging plot events that repair this gap.
Rules:
- Abstract level only (no dialogue, no prose)
- Each event is 1 sentence

Your response must be ONLY a JSON array using the same schema:
  "event_id" (use "E_b1", "E_b2", etc.), "description", "characters", "goals",
  "caused_by", "goal_type", "location", "preconditions", "effects",
  "required_objects", "clue"

Output only the JSON array, nothing else:"""


def _build_action_interpretation_prompt(command: str, world_context: str) -> str:
    return f"""\
World context:
{world_context}

Player command:
{command}

Interpret the command for the game engine.
Return exactly one JSON object with these fields:
{{
  "action_type": string,
  "target": string,
  "target_location": string or null,
  "target_object": string or null,
  "target_character": string or null,
  "intent_summary": string,
  "implied_effects": [string],
  "risk_flags": [string]
}}

Use null where appropriate. Output only the JSON object.
"""


def _build_accommodation_prompt(
    exception_action: str,
    world_context: str,
    affected_events: list[PlotEvent],
) -> str:
    affected_text = "\n".join(
        f"[{event.event_id}] {event.description} @ {event.location or 'Unknown'}"
        for event in affected_events
    ) or "No explicit affected events were identified."

    return f"""\
World context:
{world_context}

The player performed an exceptional action:
{exception_action}

These events were threatened or invalidated:
{affected_text}

Generate 1-2 replacement plot events that preserve solvability.
Rules:
- Keep the story coherent and playable
- Introduce alternate clues, witnesses, or evidence if needed
- Keep each event at abstract plot level
- Use the same event schema as the rest of the system
- Prefer locations already mentioned in the world context

Output only the JSON array, nothing else.
"""


def _build_interactive_event_prose_prompt(
    event: PlotEvent,
    world_context: str,
) -> str:
    return f"""\
World context:
{world_context}

Structured event:
- Event ID: {event.event_id}
- Description: {event.description}
- Location: {event.location or "Unknown"}
- Characters: {", ".join(event.characters) if event.characters else "None"}
- Goals: {", ".join(event.goals) if event.goals else "None"}
- Effects: {", ".join(event.effects) if event.effects else "None"}
- Clue: {event.clue or "None"}

Write a short prose update that feels like the story is happening right now in the game.
The player is Clara. If Clara appears in the event, address her actions as "you" instead of describing Clara as a separate person.
"""


def _build_solving_prompt(
    premise: str,
    num_events: int,
    existing_events: list[PlotEvent],
    genre: str,
) -> str:
    context = "Crime-story events generated so far:\n"
    for ev in existing_events:
        context += f"  [{ev.event_id}] {ev.description}\n"

    return f"""\
Genre: {genre}
Premise: {premise}
{context}

Generate exactly {num_events} new SOLVING STORY plot events.
These events should continue directly from the existing crime-story events and focus on:
- the investigation
- the intellectual pursuit of justice
- the methodical breakdown of evidence by detectives, investigators, or law enforcement
- deduction, interviews, evidence analysis, confrontation, revelation, and case resolution
- Clara is the player character and should be the central investigator.

Rules:
- One sentence per event, abstract plot level only
- Chronologically ordered and causally plausible
- Continue from the last existing event above
- Prioritize clues, evidence, inference, suspects, procedure, proof, and justice
- Identify characters involved
- Note any story goals this event initiates, resolves, or obstructs
- List which prior event_id(s) causally enable this event
- Include a concrete story location for where the event happens
- Include simple gameplay-friendly preconditions and effects
- Mark only meaningful intervention moments as "is_decision_point": true.
- A decision point is a moment where the player has enough context to make a real open-ended investigative choice.
- Do not create menu options. "hidden_expected_intents" is engine-only metadata and must contain broad intents, not text to show the player.
- Every string value must be enclosed in double quotes
- Output valid JSON only

Your response must be ONLY a JSON array. Each element must have exactly these fields:
  "event_id": string (continue numbering from the existing events)
  "description": one-sentence abstract event
  "characters": list of character name strings
  "goals": list of short goal-phrase strings
  "caused_by": list of event_id strings that enable this event
  "goal_type": "initiate" or "resolve" or "obstruct" or null
  "location": short room/location name string
  "preconditions": list of short state strings needed before the event
  "effects": list of short state strings caused by the event
  "required_objects": list of important object strings used or needed in the event
  "clue": short clue string revealed by this event, or null
  "is_decision_point": boolean
  "decision_context": hidden short description of why this is a meaningful open-ended intervention point, or ""
  "hidden_expected_intents": hidden list of broad action intents that could advance this beat

Example:
[
  {{
    "event_id": "E11",
    "description": "Detective Mora compares the museum security logs with witness timelines and identifies a gap matching the theft window.",
    "characters": ["Detective Mora", "Clara"],
    "goals": ["identify the thief's entry route"],
    "caused_by": ["E10"],
    "goal_type": "initiate",
    "location": "Security Office",
    "preconditions": ["security logs are available"],
    "effects": ["entry window is narrowed"],
    "required_objects": ["security logs", "witness timelines"],
    "clue": "A disabled camera marks the likely route",
    "is_decision_point": true,
    "decision_context": "The player can decide how to pursue the first evidence lead.",
    "hidden_expected_intents": ["inspect_footage", "question_security", "visit_gallery"]
  }},
  {{
    "event_id": "E12",
    "description": "Clara shows Detective Mora the manuscript's hidden-compartment notes, giving the investigation a motive tied to the map's secret.",
    "characters": ["Clara", "Detective Mora"],
    "goals": ["explain the theft motive"],
    "caused_by": ["E11"],
    "goal_type": "initiate",
    "location": "Archive Office",
    "preconditions": ["entry window is narrowed"],
    "effects": ["theft motive is clarified"],
    "required_objects": ["hidden-compartment notes"],
    "clue": "The thief wanted what was inside the manuscript, not the manuscript itself",
    "is_decision_point": false,
    "decision_context": "",
    "hidden_expected_intents": []
  }}
]

Now generate exactly {num_events} solving-phase events in that format:"""


## The JSON Parser
def _parse_plot_events(raw: str) -> list[PlotEvent]:
    if not raw or not raw.strip():
        print("[_parse_plot_events] WARNING: empty response")
        return []
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
    start = cleaned.find("[")
    end   = cleaned.rfind("]") + 1

    if (start == -1 or end == 0):
        print(f"[_parse_plot_events] WARNING: no JSON array found. Raw (first 300):\n{raw[:300]}")
        return []
    json_str = cleaned[start:end]

    try:
        records = json.loads(json_str)
    except json.JSONDecodeError as exc:
        try:
            json_str_fixed = re.sub(r",\s*([}\]])", r"\1", json_str)
            records = json.loads(json_str_fixed)
        except json.JSONDecodeError:
            print(f"[_parse_plot_events] JSON error: {exc}")
            print(f"[_parse_plot_events] Fragment (first 500):\n{json_str[:500]}")
            return []

    if not isinstance(records, list):
        print(f"[_parse_plot_events] WARNING: parsed JSON is not a list: {type(records)}")
        return []

    events: list[PlotEvent] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        event_id = str(rec.get("event_id", f"E{len(events)+1}"))
        description = str(rec.get("description", "")).strip()
        if not description:
            continue
        events.append(PlotEvent(
            event_id=    event_id,
            description= description,
            characters=  list(rec.get("characters", [])),
            goals=       list(rec.get("goals",      [])),
            caused_by=   list(rec.get("caused_by",  [])),
            goal_type=   rec.get("goal_type"),
            location=    rec.get("location"),
            preconditions=list(rec.get("preconditions", [])),
            effects=       list(rec.get("effects", [])),
            required_objects=list(rec.get("required_objects", [])),
            clue=         rec.get("clue"),
            is_decision_point=_as_bool(rec.get("is_decision_point", False)),
            decision_context=str(rec.get("decision_context", "") or ""),
            hidden_expected_intents=list(rec.get("hidden_expected_intents", [])),
        ))

    return events


def _heuristic_interpreted_action(command: str) -> InterpretedAction:
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
        target = command[3:].strip()
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


def _parse_action_interpretation(raw: str) -> Optional[InterpretedAction]:
    if not raw or not raw.strip():
        return None
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    json_str = cleaned[start:end]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        try:
            fixed = re.sub(r",\s*([}\]])", r"\1", json_str)
            data = json.loads(fixed)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return InterpretedAction(
        action_type=str(data.get("action_type", "unknown")),
        target=str(data.get("target", "")),
        target_location=data.get("target_location"),
        target_object=data.get("target_object"),
        target_character=data.get("target_character"),
        intent_summary=str(data.get("intent_summary", "")),
        implied_effects=list(data.get("implied_effects", [])),
        risk_flags=list(data.get("risk_flags", [])),
    )
