# main_system_script.py
# Rambling Rhino: Reader-Model-Driven Story Generation Driver

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from llm_api_wrapper import LLMClient, PlotEvent
from quest_parsing.knowledge_graph import KnowledgeGraph
from quest_parsing.narrative_ingestor import NarrativeIngestor
from quest_parsing.narrative_schema import ArcType, NodeType
from complexity_checking.complexity_checker import ComplexityChecker


CRIME_NODE_REQUIREMENTS = {
    NodeType.EVENT: (3, -1),
    NodeType.ACTION: (2, -1),
    NodeType.GOAL: (1, -1),
}

CRIME_ARC_REQUIREMENTS = {
    ArcType.CONSEQUENCE: (2, -1),
    ArcType.REASON: (1, -1),
}

SOLVING_NODE_REQUIREMENTS = {
    NodeType.EVENT: (3, -1),
    NodeType.ACTION: (2, -1),
    NodeType.GOAL: (1, -1),
}

SOLVING_ARC_REQUIREMENTS = {
    ArcType.CONSEQUENCE: (2, -1),
    ArcType.REASON: (1, -1),
}


@dataclass
class ThreadState:
    name: str
    events: list[PlotEvent] = field(default_factory=list)
    kg: KnowledgeGraph = field(default_factory=KnowledgeGraph)
    checker: Optional[ComplexityChecker] = None
    feedback_history: list[list[str]] = field(default_factory=list)


class RamblingRhinoDriver:
    def __init__(
        self,
        premise: str,
        genre: str = "crime mystery",
        crime_events_per_batch: int = 6,
        solving_events_per_batch: int = 15,
        engagement_batches: int = 1,
        reflection_passes: int = 2,
        output_dir: Optional[str] = None,
        verbose: bool = False,
    ) -> None:
        self.premise = premise
        self.genre = genre
        self.crime_events_per_batch = crime_events_per_batch
        self.solving_events_per_batch = solving_events_per_batch
        self.engagement_batches = engagement_batches
        self.reflection_passes = reflection_passes
        self.output_dir = Path(output_dir) if output_dir else None
        self.verbose = verbose

        self.llm = LLMClient(verbose=verbose)
        self.ingestor = NarrativeIngestor(include_attr_triples=False)

        self.crime = ThreadState(name="crime")
        self.solving = ThreadState(name="solving")

    def run_crime_thread(self) -> None:
        print("\n" + "═" * 60)
        print("PHASE 1: CRIME THREAD")
        print("═" * 60)
        self._run_thread(
            state=self.crime,
            premise=self.premise,
            hidden_context="",
            events_per_batch=self.crime_events_per_batch,
        )

    def run_solving_thread(self) -> None:
        print("\n" + "═" * 60)
        print("PHASE 2: SOLVING THREAD")
        print("═" * 60)
        self._run_thread(
            state=self.solving,
            premise=self.premise,
            hidden_context=self._crime_context_for_solving(),
            events_per_batch=self.solving_events_per_batch,
        )

    def run_prose(self) -> str:
        print("\n" + "═" * 60)
        print("PHASE 3: PROSE GENERATION")
        print("═" * 60)

        prose = self.llm.generate_prose(
            events=self.solving.events,
            genre=self.genre,
            style_notes=(
                "Write only the visible solving story. Reveal the hidden crime through "
                "investigation and discovery instead of narrating the full crime timeline upfront."
            ),
        )
        print("\n" + "-" * 60)
        print("GENERATED STORY")
        print("-" * 60)
        print(textwrap.fill(prose, width=72))
        return prose

    def run(self) -> dict:
        start_time = time.time()
        self.run_crime_thread()
        self.run_solving_thread()
        prose = self.run_prose()
        elapsed = time.time() - start_time

        print("\n" + "═" * 60)
        print("RUN SUMMARY")
        print("═" * 60)
        print(f"  Elapsed time     : {elapsed:.1f} s")
        print(f"  Crime events     : {len(self.crime.events)}")
        print(f"  Solving events   : {len(self.solving.events)}")
        print(f"  Crime KG stats   : {self.crime.kg.stats()}")
        print(f"  Solving KG stats : {self.solving.kg.stats()}")
        print(f"  Token usage      : {self.llm.usage}")

        result = {
            "premise": self.premise,
            "genre": self.genre,
            "crime_events": self._serialize_events(self.crime.events),
            "crime_kg_stats": self.crime.kg.stats(),
            "crime_feedback_history": self.crime.feedback_history,
            "solving_events": self._serialize_events(self.solving.events),
            "solving_kg_stats": self.solving.kg.stats(),
            "solving_feedback_history": self.solving.feedback_history,
            "prose": prose,
            "usage": str(self.llm.usage),
        }
        if self.output_dir:
            self._save_outputs(result)
        return result

    def _run_thread(
        self,
        state: ThreadState,
        premise: str,
        hidden_context: str,
        events_per_batch: int,
    ) -> None:
        self._run_engagement(state, premise, hidden_context, events_per_batch)
        self._build_knowledge_graph(state)
        self._run_reflection(state)

    def _run_engagement(
        self,
        state: ThreadState,
        premise: str,
        hidden_context: str,
        events_per_batch: int,
    ) -> None:
        for batch_num in range(1, self.engagement_batches + 1):
            print(f"\n[{state.name.title()} engagement batch {batch_num}/{self.engagement_batches}]")
            new_events = self.llm.generate_plot_events(
                premise=premise,
                num_events=events_per_batch,
                existing_events=state.events if state.events else None,
                genre=self.genre,
                mode=state.name,
                hidden_context=hidden_context,
            )
            state.events.extend(new_events)
            print(f"  Generated {len(new_events)} {state.name} events (total: {len(state.events)})")

        print(f"\n{state.name.title()} engagement complete: {len(state.events)} plot events.")
        self._print_events(state)

    def _build_knowledge_graph(self, state: ThreadState) -> None:
        state.kg = KnowledgeGraph()
        event_text = "\n".join(ev.description for ev in state.events if ev.description)
        provenance = f"{state.name}_thread"
        self.ingestor.from_text(event_text, state.kg, provenance=provenance)
        state.checker = self._build_checker(state.name, state.kg)
        print(f"\n{state.name.title()} KnowledgeGraph: {state.kg}")

    def _run_reflection(self, state: ThreadState) -> None:
        print(f"\n{state.name.title()} reflection:")
        for pass_num in range(1, self.reflection_passes + 1):
            print(f"\n[{state.name.title()} reflection pass {pass_num}/{self.reflection_passes}]")
            if state.checker is None:
                self._build_knowledge_graph(state)

            feedback = state.checker() if state.checker is not None else []
            state.feedback_history.append(feedback)

            print(f"  ComplexityChecker feedback: {len(feedback)} issue(s)")
            for msg in feedback:
                print(f"    - {msg}")

            if not feedback:
                print(f"  No gaps found in the {state.name} thread.")
                break

            repairs = self._feedback_to_repairs(feedback, state)
            story_summary = self._events_summary(state.events)
            for repair in repairs:
                print("\n  Repairing graph issue:")
                print(f"    {repair['description']}")
                bridging = self.llm.reflect_on_quest_gap(
                    gap_description=repair["description"],
                    story_so_far=story_summary,
                    insert_after_event_id=repair["insert_after"],
                )
                if not bridging:
                    print("    [WARNING] LLM returned no bridging events.")
                    continue
                self._insert_events(state.events, bridging, repair.get("insert_after"))
                for bridge_ev in bridging:
                    print(f"    + Inserted [{bridge_ev.event_id}]: {bridge_ev.description}")

            self._build_knowledge_graph(state)

        print(f"\n{state.name.title()} reflection complete: {len(state.events)} total events.")

    def _build_checker(self, mode: str, kg: KnowledgeGraph) -> ComplexityChecker:
        node_reqs = CRIME_NODE_REQUIREMENTS if mode == "crime" else SOLVING_NODE_REQUIREMENTS
        arc_reqs = CRIME_ARC_REQUIREMENTS if mode == "crime" else SOLVING_ARC_REQUIREMENTS
        return ComplexityChecker(
            kg,
            node_reqs=node_reqs,
            arc_reqs=arc_reqs,
            req_dag=True,
            req_conn=True,
        )

    def _feedback_to_repairs(
        self,
        feedback: list[str],
        state: ThreadState,
    ) -> list[dict[str, Optional[str]]]:
        return [
            {
                "description": self._build_repair_prompt(message, state.name),
                "insert_after": self._choose_insert_after(message, state.events),
            }
            for message in feedback
        ]

    def _build_repair_prompt(self, message: str, mode: str) -> str:
        if mode == "crime":
            base_rules = (
                "Add 1-2 abstract crime-thread events only. Focus on what truly happened, "
                "why it happened, and how one event caused the next."
            )
            prompt_map = {
                "Not enough EVENT nodes.": "Add concrete crime developments so the hidden timeline contains more distinct happenings.",
                "Not enough ACTION nodes.": "Add intentional actions by the culprit or accomplices that advance the crime or cover-up.",
                "Not enough GOAL nodes.": "Add an event that clearly establishes the culprit's goal or motive.",
                "Not enough CONSEQUENCE arcs.": "Add bridging crime events so the hidden timeline has clearer causal progression.",
                "Not enough REASON arcs.": "Add an event that makes the culprit's reason for acting explicit.",
                "Contains circular events.": "Revise the hidden crime timeline so it moves forward without causal loops.",
                "Contains story discontinuity.": "Add linking crime events that connect isolated parts of the hidden timeline.",
            }
        else:
            base_rules = (
                "Add 1-2 abstract solving-thread events only. Focus on investigation, clues, interviews, deductions, "
                "obstacles, and gradual revelation of the hidden crime."
            )
            prompt_map = {
                "Not enough EVENT nodes.": "Add concrete investigation developments so the solving story advances through more distinct discoveries.",
                "Not enough ACTION nodes.": "Add intentional investigative actions that move the case forward.",
                "Not enough GOAL nodes.": "Add an event that clearly establishes the investigator's goal or motive.",
                "Not enough CONSEQUENCE arcs.": "Add bridging solving events so one clue or discovery clearly leads to the next.",
                "Not enough REASON arcs.": "Add an event that makes a character's investigative motivation explicit.",
                "Contains circular events.": "Revise the investigation so discoveries move forward instead of looping back.",
                "Contains story discontinuity.": "Add linking solving events that connect isolated discoveries into one continuous investigation.",
            }

        repair_instruction = prompt_map.get(
            message,
            "Repair this QUEST graph issue by adding events that improve coherence and explanatory structure.",
        )
        return f"{repair_instruction} {base_rules} Issue to fix: {message}"

    def _choose_insert_after(self, message: str, events: list[PlotEvent]) -> Optional[str]:
        if not events:
            return None
        if message == "Not enough GOAL nodes.":
            return events[0].event_id
        if message == "Contains story discontinuity.":
            return events[max(len(events) // 2 - 1, 0)].event_id
        return events[-1].event_id

    def _crime_context_for_solving(self) -> str:
        if not self.crime.events:
            return ""
        lines = [
            "Hidden crime timeline:",
            *[
                f"- [{event.event_id}] {event.description}"
                for event in self.crime.events
            ],
        ]
        return "\n".join(lines)

    def _insert_events(
        self,
        events: list[PlotEvent],
        new_events: list[PlotEvent],
        insert_after: Optional[str],
    ) -> None:
        insert_idx = len(events)
        if insert_after:
            for i, event in enumerate(events):
                if event.event_id == insert_after:
                    insert_idx = i + 1
                    break
        for offset, event in enumerate(new_events):
            events.insert(insert_idx + offset, event)

    def _events_summary(self, events: list[PlotEvent]) -> str:
        return "\n".join(f"  [{ev.event_id}] {ev.description}" for ev in events)

    def _serialize_events(self, events: list[PlotEvent]) -> list[dict]:
        return [
            {
                "event_id": ev.event_id,
                "description": ev.description,
                "characters": ev.characters,
                "goals": ev.goals,
                "caused_by": ev.caused_by,
                "goal_type": ev.goal_type,
            }
            for ev in events
        ]

    def _print_events(self, state: ThreadState) -> None:
        print(f"\nCurrent {state.name} event list:")
        for ev in state.events:
            print(f"  [{ev.event_id}] {ev.description}")
            if ev.caused_by:
                print(f"           caused_by: {ev.caused_by}")

    def _save_outputs(self, result: dict) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        crime_events_path = self.output_dir / "crime_events.json"
        solving_events_path = self.output_dir / "solving_events.json"
        prose_path = self.output_dir / "solving_story.txt"
        result_path = self.output_dir / "run_summary.json"

        with open(crime_events_path, "w", encoding="utf-8") as f:
            json.dump(result["crime_events"], f, indent=2)
        with open(solving_events_path, "w", encoding="utf-8") as f:
            json.dump(result["solving_events"], f, indent=2)
        with open(prose_path, "w", encoding="utf-8") as f:
            f.write(result["prose"])
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        print(f"\n  Crime events saved to   : {crime_events_path}")
        print(f"  Solving events saved to : {solving_events_path}")
        print(f"  Solving prose saved to  : {prose_path}")
        print(f"  Run summary saved to    : {result_path}")


DEFAULT_PREMISE = (
    "A small-town archivist discovers that a priceless 18th-century manuscript "
    "has been stolen from the local museum the night before its auction. "
    "She is the only one who knows what was truly hidden inside it."
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rambling Rhino: Reader-Model-Driven Story Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Examples:
              python main_system_script.py
              python main_system_script.py --premise "A spy goes rogue in Berlin." --genre "spy thriller"
              python main_system_script.py --events 10 --reflection-passes 3 --output-dir ./output
              python main_system_script.py --verbose
        """),
    )
    parser.add_argument(
        "--premise", type=str, default=DEFAULT_PREMISE,
        help="1-3 sentence story premise (default: archival mystery).",
    )
    parser.add_argument(
        "--genre", type=str, default="crime mystery",
        help="Genre hint for the LLM (default: 'crime mystery').",
    )
    parser.add_argument(
        "--crime-events", type=int, default=6, dest="crime_events_per_batch",
        help="Events to generate per crime-thread batch (default: 6).",
    )
    parser.add_argument(
        "--solving-events", type=int, default=15, dest="solving_events_per_batch",
        help="Events to generate per solving-thread batch (default: 15).",
    )
    parser.add_argument(
        "--batches", type=int, default=1, dest="engagement_batches",
        help="Number of engagement batches per thread (default: 1).",
    )
    parser.add_argument(
        "--reflection-passes", type=int, default=2,
        help="Max reflection / gap-repair passes per thread (default: 2).",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="If set, saves crime events, solving events, prose, and run summary here.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print raw LLM responses for debugging.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GROQ_API_KEY", "API_KEY")
    if not api_key or api_key == "YOUR_GROQ_API_KEY_HERE":
        print("\n[ERROR] No Groq API key found.", file=sys.stderr)
        sys.exit(1)

    print("\n" + "═" * 60)
    print("  RAMBLING RHINO: Story Generation System")
    print("  Team Rambling Rhino | Reader-Model-Driven Generation")
    print("═" * 60)
    print(f"  Premise : {textwrap.shorten(args.premise, width=55)}")
    print(f"  Genre   : {args.genre}")
    print(f"  Crime   : {args.crime_events_per_batch} × {args.engagement_batches} batch(es)")
    print(f"  Solving : {args.solving_events_per_batch} × {args.engagement_batches} batch(es)")
    print(f"  Reflect : {args.reflection_passes} pass(es) per thread")

    driver = RamblingRhinoDriver(
        premise=args.premise,
        genre=args.genre,
        crime_events_per_batch=args.crime_events_per_batch,
        solving_events_per_batch=args.solving_events_per_batch,
        engagement_batches=args.engagement_batches,
        reflection_passes=args.reflection_passes,
        output_dir=args.output_dir,
        verbose=args.verbose,
    )
    driver.run()


if __name__ == "__main__":
    main()
