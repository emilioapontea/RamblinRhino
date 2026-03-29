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

    def __str__(self) -> str:
        return (
            f"[{self.event_id}] {self.description}\n"
            f"  characters : {self.characters}\n"
            f"  goals      : {self.goals}\n"
            f"  caused_by  : {self.caused_by}\n"
            f"  goal_type  : {self.goal_type}"
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

Rules:
- One sentence per event, abstract plot level only
- Chronologically ordered and causally plausible
- Prioritize the concealement and the perpetrators motives
- Identify perpetrator characters involved
- Note any story goals this event initiates, resolves, or obstructs
- List which prior event_id(s) causally enable this event

Your response must be ONLY a JSON array. Each element must have exactly these fields:
  "event_id": string (ex. "E1", "E2": if continuing, start from the next number)
  "description": one-sentence abstract event
  "characters": list of character name strings
  "goals": list of short goal-phrase strings
  "caused_by": list of event_id strings that enable this event ([] for the first event)
  "goal_type": "initiate" or "resolve" or "obstruct" or null

Example of correct output format, note only the output format and not the actual text in description:
[
  {{
    "event_id": "E1",
    "description": "The archivist arrives at the museum and finds the display case shattered.",
    "characters": ["Clara"],
    "goals": ["discover what happened"],
    "caused_by": [],
    "goal_type": "initiate"
  }},
  {{
    "event_id": "E2",
    "description": "Clara realizes the priceless manuscript is missing.",
    "characters": ["Clara"],
    "goals": ["recover the manuscript"],
    "caused_by": ["E1"],
    "goal_type": "initiate"
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
  "caused_by", "goal_type"

Output only the JSON array, nothing else:"""


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

Rules:
- One sentence per event, abstract plot level only
- Chronologically ordered and causally plausible
- Continue from the last existing event above
- Prioritize clues, evidence, inference, suspects, procedure, proof, and justice
- Identify characters involved
- Note any story goals this event initiates, resolves, or obstructs
- List which prior event_id(s) causally enable this event
- Every string value must be enclosed in double quotes
- Output valid JSON only

Your response must be ONLY a JSON array. Each element must have exactly these fields:
  "event_id": string (continue numbering from the existing events)
  "description": one-sentence abstract event
  "characters": list of character name strings
  "goals": list of short goal-phrase strings
  "caused_by": list of event_id strings that enable this event
  "goal_type": "initiate" or "resolve" or "obstruct" or null

Example:
[
  {{
    "event_id": "E11",
    "description": "Detective Mora compares the museum security logs with witness timelines and identifies a gap matching the theft window.",
    "characters": ["Detective Mora", "Clara"],
    "goals": ["identify the thief's entry route"],
    "caused_by": ["E10"],
    "goal_type": "initiate"
  }},
  {{
    "event_id": "E12",
    "description": "Clara shows Detective Mora the manuscript's hidden-compartment notes, giving the investigation a motive tied to the map's secret.",
    "characters": ["Clara", "Detective Mora"],
    "goals": ["explain the theft motive"],
    "caused_by": ["E11"],
    "goal_type": "initiate"
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
        ))

    return events
