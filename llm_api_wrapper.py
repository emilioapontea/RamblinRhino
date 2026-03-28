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
    def generate_plot_events(
        self,
        premise: str,
        num_events: int = 8,
        existing_events: Optional[list[PlotEvent]] = None,
        genre: str = "crime mystery",
    ) -> list[PlotEvent]:
        user_prompt = _build_engagement_prompt(
            premise, num_events, existing_events, genre
        )
        raw = self._complete(_ENGAGEMENT_SYSTEM_PROMPT, user_prompt)
        events = _parse_plot_events(raw)
        if self.verbose or len(events) == 0:
            print(f"[LLMClient] parsed {len(events)} events from engagement call")
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
        raw = self._complete(_REFLECTION_SYSTEM_PROMPT, user_prompt)
        return _parse_plot_events(raw)

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
            for i, e in enumerate(events))

        system = (
            "You are a skilled literary fiction author. "
            "You write long, detailed, immersive stories with rich prose, "
            "vivid character development, and scene-setting description.")

        prompt = (
            f"Genre: {genre}\n"
            + (f"Style notes: {style_notes}\n" if style_notes else "")
            + f"\nYou have {len(events)} plot points to cover. "
            "Write a LONG, complete short story (aim for 1500-2000 words minimum) "
            "that covers every single plot point below in order.\n\n"
            "IMPORTANT FORMATTING RULES:\n"
            "- Before writing the prose for each plot point, insert a clearly labeled "
            "marker on its own line in this exact format:\n"
            "  --- Plot Point N: [one-sentence summary] ---\n"
            "- After that marker, write 2-4 paragraphs of rich narrative prose for that plot point.\n"
            "- Do NOT skip any plot points.\n"
            "- Write in third-person, past tense.\n"
            "- Each plot point section should be substantial: at least 150 words of prose.\n\n"
            f"Plot points to cover:\n{plot_points}\n\n"
            "Begin the story now:\n")

        # Use a higher token limit for prose generation
        old_max = self.max_tokens
        self.max_tokens = 8192
        prose = self._complete(system, prompt)
        self.max_tokens = old_max
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
                        print(f"[LLMClient] Rate limited (429): waiting {wait}s "
                              f"(attempt {attempt}/{retries})")
                    else:
                        wait = self.request_delay * (2 ** attempt)
                        print(f"[LLMClient] HTTP {resp.status_code}: retrying in "
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
        context = f"Events generated so far (last event_id was {last_id}):\n"
        for ev in existing_events:
            context += f"  [{ev.event_id}] {ev.description}\n"
        context += "\nContinue the story from the last event above.\n"

    return f"""\
Genre: {genre}
Premise: {premise}
{context}
Generate exactly {num_events} new plot events.

Rules:
- One sentence per event, abstract plot level only
- Chronologically ordered and causally plausible
- Identify characters involved
- Note any story goals this event initiates, resolves, or obstructs
- List which prior event_id(s) causally enable this event

Your response must be ONLY a JSON array. Each element must have exactly these fields:
  "event_id": string (ex. "E1", "E2": if continuing, start from the next number)
  "description": one-sentence abstract event
  "characters": list of character name strings
  "goals": list of short goal-phrase strings
  "caused_by": list of event_id strings that enable this event ([] for the first event)
  "goal_type": "initiate" or "resolve" or "obstruct" or null

Example of correct output format:
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

Now generate exactly {num_events} events in that format:"""


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
        # Try to fix common issues: trailing commas, single quotes
        try:
            json_str_fixed = re.sub(r",\s*([}\]])", r"\1", json_str)  # trailing commas
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
            continue  # skip empty events
        events.append(PlotEvent(
            event_id=    event_id,
            description= description,
            characters=  list(rec.get("characters", [])),
            goals=       list(rec.get("goals",      [])),
            caused_by=   list(rec.get("caused_by",  [])),
            goal_type=   rec.get("goal_type"),
        ))

    return events
