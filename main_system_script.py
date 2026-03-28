# main_system_script.py
# Rambling Rhino: Reader-Model-Driven Story Generation Driver

# Uses the Groq API, free, with a limit of ~6000 tokens a min, ~500,000 tokens a day
# Model used: llama-3.3-70b-versatile

# This script is the top-level script that wires together all the system components and runs a full
# Crime Story Events --> Reflection --> Solving Story Events --> Reflection --> Prose pipeline
# to generate a coherent short story using the QUEST reader-model framework

# The architecture of the system is as follows:
# main.py: RamblingRhinoDriver
    # 1. run_crime_story_events() --> LLMClient
    # 2. run_reflection() --> ComplexityChecker, LLMClient (repair)
    # 3. run_solving_story_events() --> LLMClient
    # 4. run_reflection() --> ComplexityChecker, LLMClient (repair)
    # 5. run_prose() --> LLMClient

# llm_api_wrapper.py: LLMClient
    # generate_crime_plot_events()
    # generate_solving_plot_events()
    # reflect_on_quest_gap()
    # generate_prose()

# quest_parsing/knowledge_graph.py: KnowledgeGraph
    # add_triples()
    # get_neighbours()
    # find_path()
    # subgraph()

# quest_parsing/narrative_ingestor.py: NarrativeIngestor
    # from_sentences(), parses event descriptions into KG triples

# complexity_checking/complexity_checker.py: ComplexityChecker
    # find_causal_gaps()
    # find_goal_gaps()

# To run the system:
    # Basic run
        # python main_system_script.py
    # Custom premise and genre:
        # python main_system_script.py --premise "A librarian discovers a coded message hidden in a
        #                       first-edition novel." --genre "mystery thriller"
    # More events, more reflection passes:
        # python main_system_script.py --events 12 --reflection-passes 3
    # Save output to files:
        # python main_system_script.py --output-dir ./output
    # Verbose (print raw LLM responses):
        # python main_system_script.py --verbose

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from llm_api_wrapper import LLMClient, PlotEvent
from quest_parsing.knowledge_graph import KnowledgeGraph, KBSource, Triple

try:
    from quest_parsing.narrative_ingestor import NarrativeIngestor
    _NLP_AVAILABLE = True
except Exception as _nlp_err:
    print(f"[main] NarrativeIngestor unavailable: {_nlp_err}\n"
          "  KnowledgeGraph will not be populated from event text.")
    _NLP_AVAILABLE = False



from complexity_checking.complexity_checker import ComplexityChecker as _KGComplexityChecker
from quest_parsing.narrative_schema import NodeType, ArcType


def _label_plot_point(idx: int, total: int) -> str:
    if idx == 0:
        return "SETUP"
    elif idx == 1:
        return "INCITING INCIDENT"
    elif idx < total * 0.4:
        return "RISING ACTION"
    elif idx < total * 0.7:
        return "MIDPOINT"
    elif idx < total - 2:
        return "COMPLICATIONS"
    elif idx == total - 2:
        return "CLIMAX"
    elif idx == total - 1:
        return "RESOLUTION"
    return "EVENT"

## KnowledgeGraph Population Helper
def _events_to_kg(events: list[PlotEvent], kg: KnowledgeGraph) -> None:
    # Populates the KnowledgeGraph with triples derived from PlotEvents
    nlp = None
    if _NLP_AVAILABLE:
        try:
            nlp = NarrativeIngestor(namespace="story")
        except Exception as exc:
            print(f"[main] NarrativeIngestor init failed: {exc}")

    for ev in events:
        ev_node = f"event:{ev.event_id}"
        # Causal links (C-link in QUEST)
        for cause_id in ev.caused_by:
            if cause_id:
                kg.add_triple(Triple(
                    subject=f"event:{cause_id}",
                    predicate="Causes",
                    obj=ev_node,
                    source=KBSource.DOMAIN,
                    confidence=1.0,
                    provenance=f"plot_event:{ev.event_id}",
                ))
        # Goal links (I-link / O-link in QUEST)
        goal_pred = {
            "initiate": "InitiatesGoal",
            "resolve":  "ResolvesGoal",
            "obstruct": "ObstructsGoal",
        }.get(ev.goal_type or "", "RelatedToGoal")

        for goal in ev.goals:
            if goal:
                kg.add_triple(Triple(
                    subject=ev_node,
                    predicate=goal_pred,
                    obj=f"goal:{goal.lower().replace(' ', '_')}",
                    source=KBSource.DOMAIN,
                    confidence=1.0,
                    provenance=f"plot_event:{ev.event_id}",
                ))
        # Character participation
        for char in ev.characters:
            if char:
                kg.add_triple(Triple(
                    subject=f"char:{char.lower().replace(' ', '_')}",
                    predicate="ParticipatesIn",
                    obj=ev_node,
                    source=KBSource.DOMAIN,
                    confidence=1.0,
                    provenance=f"plot_event:{ev.event_id}",
                ))
        # Tag the event node with a NodeType so ComplexityChecker can count it.
        # goal_type "initiate"/"resolve"/"obstruct" --> goal or action node,
        # everything else is an event node.
        if ev.goal_type in ("initiate", "resolve", "obstruct"):
            node_type_str = "action" if ev.goal_type == "initiate" else "goal"
        else:
            node_type_str = "event"
        if kg._g.has_node(ev_node):
            kg._g.nodes[ev_node]["type"] = node_type_str
        else:
            kg._g.add_node(ev_node, label=ev_node, type=node_type_str, source="domain")
        # NLP-extracted semantic triples from event description
        if nlp and ev.description:
            try:
                text_triples = nlp.from_text(
                    ev.description,
                    kg,
                    provenance=f"event_description:{ev.event_id}",
                )
            except Exception as exc:
                print(f"[main] NLP extraction error for [{ev.event_id}]: {exc}")


class RamblingRhinoDriver:
    # This is where the full crime-story-events --> reflection --> solving-story-events
    # --> reflection --> prose pipeline takes place.
    # In the crime-story phase, LLMClient establishes the criminal act, motive, and fallout.
    # In the solving-story phase, LLMClient drives the investigation and resolution.
    # In KG build, _events_to_kg() populates KnowledgeGraph
    # In reflection, for each reflection pass, ComplexityChecker finds gaps. For each gap, LLMClient reflects on the
    # QUEST gaps, inserts bridging events, rebuilds KG
    # In prose, LLMClient generates prose (the final story text)

    def __init__(
        self,
        premise:            str,
        genre:              str   = "crime mystery",
        events_per_batch:   int   = 20,
        engagement_batches: int   = 1,
        reflection_passes:  int   = 2,
        output_dir:         Optional[str] = None,
        verbose:            bool  = False,
    ) -> None:
        self.premise            = premise
        self.genre              = genre
        self.events_per_batch   = events_per_batch
        self.engagement_batches = engagement_batches
        self.reflection_passes  = reflection_passes
        self.output_dir         = Path(output_dir) if output_dir else None
        self.verbose            = verbose

        self.llm     = LLMClient(verbose=verbose)
        self.kg      = KnowledgeGraph()
        # ComplexityChecker is created after KG is built (it requires a KG instance)
        self._checker = None
        self.crime_story_events: list[PlotEvent] = []
        self.solving_story_events: list[PlotEvent] = []
        self.events: list[PlotEvent] = []

    def _split_stage_event_counts(self) -> tuple[int, int]:
        crime_count = max(1, self.events_per_batch // 2)
        solving_count = max(1, self.events_per_batch - crime_count)
        return crime_count, solving_count

    def _batched_counts(self, total_events: int) -> list[int]:
        batches = max(1, self.engagement_batches)
        base = total_events // batches
        remainder = total_events % batches
        counts = []
        for batch_idx in range(batches):
            counts.append(base + (1 if batch_idx < remainder else 0))
        return [count for count in counts if count > 0]

    def _sync_events(self) -> None:
        self.events = [*self.crime_story_events, *self.solving_story_events]

    ## Phase 1: Crime Story Events
    def run_crime_story_events(self) -> None:
        # Generates the crime-story event sequence using LLM calls. Multiple batches let the
        # crime narrative grow incrementally, with each batch conditioning on prior crime events.
        print("\n" + "═"*60)
        print("PHASE 1: CRIME STORY EVENTS")
        print("═"*60)

        crime_event_count, _ = self._split_stage_event_counts()
        batch_counts = self._batched_counts(crime_event_count)

        for batch_num, batch_size in enumerate(batch_counts, start=1):
            print(f"\n[Crime story batch {batch_num}/{len(batch_counts)}]")
            new_events = self.llm.generate_crime_plot_events(
                premise=         self.premise,
                num_events=      batch_size,
                existing_events= self.crime_story_events if self.crime_story_events else None,
                genre=           self.genre,
            )
            self.crime_story_events.extend(new_events)
            self._sync_events()
            print(f"  Generated {len(new_events)} events "
                  f"(crime story total: {len(self.crime_story_events)})")

        print(f"\nCrime story generation complete: {len(self.crime_story_events)} plot events.")
        self._print_events(self.crime_story_events)

    ## Phase 3: Solving Story Events
    def run_solving_story_events(self) -> None:
        # Continues from the reflected crime-story phase with investigation and resolution events.
        print("\n" + "═"*60)
        print("PHASE 3: SOLVING STORY EVENTS")
        print("═"*60)

        _, solving_event_count = self._split_stage_event_counts()
        batch_counts = self._batched_counts(solving_event_count)

        for batch_num, batch_size in enumerate(batch_counts, start=1):
            print(f"\n[Solving batch {batch_num}/{len(batch_counts)}]")
            new_events = self.llm.generate_solving_plot_events(
                premise=self.premise,
                existing_events=self.events,
                num_events=batch_size,
                genre=self.genre,
            )
            self.solving_story_events.extend(new_events)
            self._sync_events()
            print(f"  Generated {len(new_events)} events "
                  f"(solving story total: {len(self.solving_story_events)})")

        print(f"\nSolving story generation complete: {len(self.solving_story_events)} plot events.")
        self._print_events(self.solving_story_events)

    ## Phase 2: KG Population
    def build_knowledge_graph(self) -> None:
        # Converts the current event list into KnowledgeGraph triples, called after each engagement batch
        # and after each reflection pass.
        self.kg = KnowledgeGraph()   # rebuild from scratch for clean state
        _events_to_kg(self.events, self.kg)
        print(f"\nKnowledgeGraph: {self.kg}")

    ## Phase 3: Reflection
    def run_reflection(self, phase_label: str) -> None:
        # Iterative gap detection and repair loop using the real ComplexityChecker.
        # ComplexityChecker(kg) is called each pass — it returns a list of feedback strings
        # describing which node/arc requirements are violated (e.g. "Not enough EVENT nodes",
        # "Contains story discontinuity"). Each feedback string becomes a gap description
        # passed to the LLM to generate bridging events, which are then appended and the KG rebuilt.
        print("\n" + "═"*60)
        phase_number = 2 if phase_label == "crime story" else 4
        print(f"PHASE {phase_number}: REFLECTION ({phase_label})")
        print("═"*60)

        for pass_num in range(1, self.reflection_passes + 1):
            print(f"\n[Reflection pass {pass_num}/{self.reflection_passes}]")

            # Instantiate ComplexityChecker with the current KG.
            # Node types are set by _events_to_kg based on goal_type.
            # We only check structural properties (DAG + connectivity) here —
            # node/arc count requirements are skipped because the KG predicates
            # (Causes, InitiatesGoal, etc.) don't map to ArcType values.
            total = len(self.events)
            checker = _KGComplexityChecker(
                self.kg,
                node_reqs=None,   # skip — counts are checked via event list length
                arc_reqs=None,    # skip — KG uses domain predicates, not ArcType
                req_dag=True,
                req_conn=False,   # allow disconnected subgraphs (goals, chars, etc.)
            )
            feedback = checker()

            # Also add a simple event-count check on top of structural checks
            if total < 15:
                feedback.append(
                    f"Story has only {total} plot events — aim for at least 15 for a full narrative."
                )

            if not feedback:
                print("  ComplexityChecker: all requirements satisfied — story is QUEST-coherent.")
                break

            print(f"  ComplexityChecker found {len(feedback)} issue(s):")
            for fb in feedback:
                print(f"    - {fb}")

            story_summary = "\n".join(
                f"  [{ev.event_id}] {ev.description}" for ev in self.events
            )

            for fb_msg in feedback:
                gap_description = (
                    f"The QUEST complexity checker reported: '{fb_msg}'. "
                    "Generate 1-2 bridging plot events to address this structural gap."
                )
                print(f"\n  Repairing: {fb_msg}")
                time.sleep(2)   # avoid Groq 429 rate-limit between reflection calls
                bridging = self.llm.reflect_on_quest_gap(
                    gap_description=       gap_description,
                    story_so_far=          story_summary,
                    insert_after_event_id= self.events[-1].event_id if self.events else None,
                )
                if not bridging:
                    print("    [WARNING] LLM returned no bridging events.")
                    continue
                for bridge_ev in bridging:
                    if self.solving_story_events:
                        self.solving_story_events.append(bridge_ev)
                    else:
                        self.crime_story_events.append(bridge_ev)
                    self._sync_events()
                    print(f"    + Added [{bridge_ev.event_id}]: {bridge_ev.description}")

            # Rebuild KG after each reflection pass
            self.build_knowledge_graph()

        print(f"\nReflection complete: {len(self.events)} total events.")

    ## Phase 5: Prose Generation
    def run_prose(self) -> str:
        # Converts the final event list into narrative prose, with each plot
        # point clearly labeled in the output.
        print("\n" + "═"*60)
        print("PHASE 5: STORY GENERATION")
        print("═"*60)
        print(f"  Generating story from {len(self.events)} plot events...")

        prose = self.llm.generate_prose(
            events=self.events,
            genre= self.genre,
        )

        print("\n" + "═"*60)
        print("GENERATED STORY")
        print("═"*60)

        # Print the story preserving plot-point markers (--- Plot Point N: ... ---)
        # but wrap regular prose paragraphs for readability.
        for line in prose.split("\n"):
            stripped = line.strip()
            if stripped.startswith("---") and stripped.endswith("---"):
                print("\n" + "─"*60)
                print(stripped)
                print("─"*60)
            elif stripped == "":
                print()
            else:
                print(textwrap.fill(stripped, width=72))

        print("\n" + "═"*60)
        return prose

    def run(self) -> dict:
        # Executes the full pipeline and returns a results dict.
        # Returns a dict with keys: premise, genre, events, kg_stats, prose, usage
        start_time = time.time()
        self.run_crime_story_events()
        self.build_knowledge_graph()
        self.run_reflection("crime story")
        self.build_knowledge_graph()
        self.run_solving_story_events()
        self.build_knowledge_graph()
        self.run_reflection("solving")
        prose   = self.run_prose()
        elapsed = time.time() - start_time

        print("\n" + "═"*60)
        print("RUN SUMMARY")
        print("═"*60)
        print(f"  Elapsed time  : {elapsed:.1f} s")
        print(f"  Total events  : {len(self.events)}")
        print(f"  KG stats      : {self.kg.stats()}")
        print(f"  Token usage   : {self.llm.usage}")

        result = {
            "premise":  self.premise,
            "genre":    self.genre,
            "crime_story_events": [
                {
                    "event_id":    ev.event_id,
                    "description": ev.description,
                    "characters":  ev.characters,
                    "goals":       ev.goals,
                    "caused_by":   ev.caused_by,
                    "goal_type":   ev.goal_type,
                }
                for ev in self.crime_story_events
            ],
            "solving_story_events": [
                {
                    "event_id":    ev.event_id,
                    "description": ev.description,
                    "characters":  ev.characters,
                    "goals":       ev.goals,
                    "caused_by":   ev.caused_by,
                    "goal_type":   ev.goal_type,
                }
                for ev in self.solving_story_events
            ],
            "events":   [
                {
                    "event_id":    ev.event_id,
                    "description": ev.description,
                    "characters":  ev.characters,
                    "goals":       ev.goals,
                    "caused_by":   ev.caused_by,
                    "goal_type":   ev.goal_type,
                }
                for ev in self.events
            ],
            "kg_stats": self.kg.stats(),
            "prose":    prose,
            "usage":    str(self.llm.usage),
        }
        if self.output_dir:
            self._save_outputs(result)
        return result

    # Helper Functions
    def _print_events(self, events: list[PlotEvent]) -> None:
        print("\nCurrent event list:")
        total = len(events)
        for i, ev in enumerate(events):
            label = _label_plot_point(i, total)
            print(f"  [{ev.event_id}] ({label}) {ev.description}")
            if ev.caused_by:
                print(f"           caused_by: {ev.caused_by}")

    def _save_outputs(self, result: dict) -> None:
        # Saving the events JSON and prose text to output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        crime_story_events_path = self.output_dir / "crime_story_events.json"
        solving_story_events_path = self.output_dir / "solving_story_events.json"
        summary_path = self.output_dir / "run_summary.json"
        prose_path = self.output_dir / "story_prose.txt"
        with open(crime_story_events_path, "w", encoding="utf-8") as f:
            json.dump(result["crime_story_events"], f, indent=2)
        with open(solving_story_events_path, "w", encoding="utf-8") as f:
            json.dump(result["solving_story_events"], f, indent=2)
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        with open(prose_path, "w", encoding="utf-8") as f:
            f.write(result["prose"])
        print(f"\n  Crime story events saved to : {crime_story_events_path}")
        print(f"  Solving story events saved to : {solving_story_events_path}")
        print(f"  Run summary saved to    : {summary_path}")
        print(f"  Prose saved to  : {prose_path}")


## CLI Entry Point
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
        "--events", type=int, default=20, dest="events_per_batch",
        help="Total pre-reflection plot events across story and solving phases (default: 20).",
    )
    parser.add_argument(
        "--batches", type=int, default=1, dest="engagement_batches",
        help="Number of generation batches to use within each event phase (default: 1).",
    )
    parser.add_argument(
        "--reflection-passes", type=int, default=2,
        help="Max reflection / gap-repair passes per reflection stage (default: 2).",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="If set, saves crime_story_events.json, solving_story_events.json, run_summary.json, and story_prose.txt here.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print raw LLM responses for debugging.",
    )
    args = parser.parse_args()

    # Validate API key
    api_key = os.environ.get("GROQ_API_KEY", "API_KEY")
    if not api_key or api_key == "YOUR_GROQ_API_KEY_HERE":
        print(
            "\n[ERROR] No Groq API key found.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\n" + "═"*60)
    print("  RAMBLING RHINO: Story Generation System")
    print("  Team Rambling Rhino | Reader-Model-Driven Generation")
    print("═"*60)
    print(f"  Premise : {textwrap.shorten(args.premise, width=55)}")
    print(f"  Genre   : {args.genre}")
    crime_count = max(1, args.events_per_batch // 2)
    solving_count = max(1, args.events_per_batch - crime_count)
    print(f"  Events  : {args.events_per_batch} total ({crime_count} crime + {solving_count} solving)")
    print(f"  Batches : {args.engagement_batches} per event phase")
    print(f"  Reflect : {args.reflection_passes} pass(es)")

    driver = RamblingRhinoDriver(
        premise=            args.premise,
        genre=              args.genre,
        events_per_batch=   args.events_per_batch,
        engagement_batches= args.engagement_batches,
        reflection_passes=  args.reflection_passes,
        output_dir=         args.output_dir,
        verbose=            args.verbose,
    )
    driver.run()


if __name__ == "__main__":
    main()
