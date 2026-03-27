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

# GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE")
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "API_KEY_HERE")

_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# There are 2 model options: "llama-3.3-70b-versatile", "llama-3.1-8b-instant"
_MODEL = "llama-3.3-70b-versatile"


# Data Structures
@dataclass
class PlotEvent:
    # This is a single narrative event in the QUEST format.
    # description is a 1-sentence plot summary, characters are character names involved in that event, goals are 
    # goals initiated, resolved, or obstructed by the event, caused_by are event_id's that cause this event,
    # causes are event_id's that this event causes, and goal_type is either initiate, resolve, obstruct, or None.
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
    # this accumulates API token counts across all calls that are made by an LLMClient instance (keeping in mind we're still
    # using the free tier)
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
    # Wrapper around the Groq Chat Completions API (OpenAI-compatible)
        # generate_plot_events() --> Engagement phase (forward plot generation)
        # reflect_on_quest_gap() --> Reflection phase (causal/goal gap repair)
        # generate_prose() --> final step, converts events into a readable story
    def __init__(
        self,
        api_key:       str   = GROQ_API_KEY,
        model:         str   = _MODEL,
        max_tokens:    int   = 1024,
        temperature:   float = 0.85,
        request_delay: float = 0.5,
        verbose:       bool  = False,
    ) -> None:
        if not api_key or api_key == "YOUR_GROQ_API_KEY_HERE":
            raise ValueError(
                "No Groq API key found."
            )
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
        # the Engagement phase, where we generate a sequence of abstract plot events
        # The model gets prompted, and each element becomes a PlotEvent which has characters,
        # goals, and causal links.
        user_prompt = _build_engagement_prompt(
            premise, num_events, existing_events, genre
        )
        raw = self._complete(_ENGAGEMENT_SYSTEM_PROMPT, user_prompt)
        return _parse_plot_events(raw)

    
    ## Reflection Phase
    def reflect_on_quest_gap(
        self,
        gap_description: str,
        story_so_far: str,
        insert_after_event_id: Optional[str] = None,
    ) -> list[PlotEvent]:
        # the Reflection phase, where we generate bridging events to repair any QUEST gaps
        # It's called by the ComplexityChecker whenever it finds a missing causal relationship (no C-link), or a
        # goal with no initiating event (no I-link)
        user_prompt = _build_reflection_prompt(
            gap_description, story_so_far, insert_after_event_id
        )
        raw = self._complete(_REFLECTION_SYSTEM_PROMPT, user_prompt)
        return _parse_plot_events(raw)


    ## Prose Generation
    def generate_prose(
        self,
        events: list[PlotEvent],
        genre: str = "crime mystery",
        style_notes: str = "",
    ) -> str:
        # This converts a list of PlotEvents into flowing narrative prose. It's called once after all the
        # Engagement and Reflection cycles are done.
        bullet_list = "\n".join(
            f"- [{e.event_id}] {e.description}" for e in events
        )
        system = "You are a skilled fiction author writing in a literary style."
        prompt = (
            f"Genre: {genre}\n"
            + (f"Style notes: {style_notes}\n" if style_notes else "")
            + "Write a complete short story based ONLY on the following plot events, "
            "in the order listed. Do not introduce major plot points not shown here. "
            "Write in third-person, past tense. Aim for 400-600 words.\n\n"
            f"Plot events:\n{bullet_list}\n\nStory:\n"
        )
        return self._complete(system, prompt)


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
                resp = self._session.post(_API_URL, json=payload, timeout=60)
                if resp.status_code == 429 or resp.status_code >= 500:
                    wait = self.request_delay * (2 ** attempt)
                    print(f"[LLMClient] HTTP {resp.status_code} — retrying in "
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
                if (self.verbose):
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
Always respond with valid JSON only: no extra text, no markdown fences.
"""

_REFLECTION_SYSTEM_PROMPT = """\
You are a narrative coherence editor for a QUEST-based story system.
Your job is to insert bridging plot events that repair logical or causal gaps.
Each event must remain at the abstract plot level: 1 sentence, no prose.
Always respond with valid JSON only: no extra text, no markdown fences.
"""


def _build_engagement_prompt(
    premise: str,
    num_events: int,
    existing_events: Optional[list[PlotEvent]],
    genre: str,
) -> str:
    context = ""
    if existing_events:
        context = "Events generated so far:\n"
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

Respond ONLY with a JSON array. Each element must have:
  "event_id": a string (e.g. "E1", "E2" — continue numbering if events exist)
  "description": a 1-sentence abstract event
  "characters": a list of character name strings
  "goals": a list of short goal-phrase strings
  "caused_by": a list of event_id strings that enable this event ([] for the first event)
  "goal_type": "initiate" | "resolve" | "obstruct" | null

Example element:
{{
  "event_id": "E3",
  "description": "The detective discovers a hidden compartment in the victim's desk.",
  "characters": ["Detective Mills"],
  "goals": ["find evidence of the theft"],
  "caused_by": ["E2"],
  "goal_type": "initiate"
}}
"""


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
- New events must logically connect the gap

Respond ONLY with a JSON array using the same schema as engagement:
  "event_id" (use "E_b1", "E_b2", …), "description", "characters", "goals",
  "caused_by", "goal_type"
"""



## The JSON Parser
def _parse_plot_events(raw: str) -> list[PlotEvent]:
    # Parses a JSON array of plot-event dicts from the LLM's raw text output
    # It handles the case where the model wraps its response in markdown code fences
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
    start = cleaned.find("[")
    end   = cleaned.rfind("]") + 1
    if (start == -1 or end == 0):
        print(f"[_parse_plot_events] WARNING: no JSON array found.\nRaw:\n{raw[:400]}")
        return []
    try:
        records = json.loads(cleaned[start:end])
    except json.JSONDecodeError as exc:
        print(f"[_parse_plot_events] JSON error: {exc}\nFragment:\n{cleaned[start:end][:500]}")
        return []
    events: list[PlotEvent] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        events.append(PlotEvent(
            event_id=    str(rec.get("event_id",    f"E{len(events)+1}")),
            description= str(rec.get("description", "")),
            characters=  list(rec.get("characters", [])),
            goals=       list(rec.get("goals",      [])),
            caused_by=   list(rec.get("caused_by",  [])),
            goal_type=   rec.get("goal_type"),
        ))
    return events