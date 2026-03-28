# main_system_script.py
# Rambling Rhino: Reader-Model-Driven Story Generation Driver

# Uses the Groq API, free, with a limit of ~6000 tokens a min, ~500,000 tokens a day
# Model used: llama-3.3-70b-versatile

# This script is the top-level script that wires together all the system components and runs a full
# Engagement --> Reflection --> Prose pipeline to generate a coherent short story using the QUEST reader-model framework

# The architecture of the system is as follows:
# main.py: RamblingRhinoDriver
    # 1. run_engagement() --> LLMClient
    # 2. run_reflection() --> ComplexityChecker, LLMClient (repair)
    # 3. run_prose() --> LLMClient

# llm_api_wrapper.py: LLMClient
    # generate_plot_events()
    # reflect_on_quest_gap()
    # generate_prose()

# knowledge_graph.py: KnowledgeGraph
    # add_triples()
    # get_neighbours()
    # find_path()
    # subgraph()

# nlp_ingestor.py: NLPIngestor
    # from_sentences(), parses event descriptions into KG triples

# complexity_checker.py
    # find_causal_gaps()
    # find_goal_gaps()

# To run the system:
    # Basic run
        # python main_system_script.py
    # Customer premise and genre:
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


from llm_api_wrapper import LLMClient, PlotEvent
from knowledge_graph import KnowledgeGraph, KBSource, Triple

try:
    from nlp_ingestor import NLPIngestor
    _NLP_AVAILABLE = True
except Exception as _nlp_err:
    print(f"[main] NLPIngestor unavailable: {_nlp_err}\n"
          "  KnowledgeGraph will not be populated from event text.")
    _NLP_AVAILABLE = False


## Complexity Checker
class ComplexityChecker:
    # The ComplexityChecker inspects a list of PlotEvents and identifies QUEST coherence gaps
    # Looks for 2 types of gaps: causal gaps (C-link missing), goal gaps (I-link)
    # Causal gaps are where an event lists event_id X in its caused_by field, but X does not exist in the current
    # event list
    # Goal gaps are where an event has goal_type == "resolve" or "obstruct" but no earlier event initiates the same
    # goal string
    # The reflection loop calls find_gaps() iteratively until either no gaps remain or the maximum number of passes is reached


    def find_gaps(self, events: list[PlotEvent]) -> list[dict]:
        # Returns a list of gap descriptors (dicts with type: causal/goal, description, insert_after)
        gaps: list[dict] = []
        event_ids   = {ev.event_id for ev in events}
        goal_inits  = {
            goal
            for ev in events
            if ev.goal_type == "initiate"
            for goal in ev.goals
        }
        for ev in events:
            # Causal gaps
            for cid in ev.caused_by:
                if cid and cid not in event_ids:
                    gaps.append({
                        "type": "causal",
                        "description": (
                            f"Event [{ev.event_id}] states it was caused by "
                            f"[{cid}], but that event does not exist in the story. "
                            "A bridging event is needed to establish this causal link."
                        ),
                        "insert_after": self._find_predecessor(ev, events),
                    })
            # Goal gaps
            if ev.goal_type in ("resolve", "obstruct"):
                for goal in ev.goals:
                    if goal and goal not in goal_inits:
                        gaps.append({
                            "type": "goal",
                            "description": (
                                f"Event [{ev.event_id}] resolves/obstructs goal "
                                f'"{goal}", but no earlier event initiates this goal. '
                                "An event that establishes the goal is needed."
                            ),
                            "insert_after": self._find_predecessor(ev, events),
                        })
        return gaps

    def _find_predecessor(
        self,
        event: PlotEvent,
        all_events: list[PlotEvent],
    ) -> Optional[str]:
        """Return the event_id of the event immediately before *event*, if any."""
        ids = [ev.event_id for ev in all_events]
        idx = ids.index(event.event_id) if event.event_id in ids else -1
        return ids[idx - 1] if idx > 0 else None

    def summary(self, events: list[PlotEvent]) -> str:
        """One-line summary of gap counts."""
        gaps = self.find_gaps(events)
        causal = sum(1 for g in gaps if g["type"] == "causal")
        goal   = sum(1 for g in gaps if g["type"] == "goal")
        return f"ComplexityChecker: {causal} causal gap(s), {goal} goal gap(s)"


def _label_plot_point(self, idx: int, total: int) -> str:
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
    # (event_id) --Causes-->          (caused_event_id)   [C-link]
    # (event_id) --InitiatesGoal-->   (goal_string)       [I-link]
    # (event_id) --ResolvesGoal-->    (goal_string)       [O-link]
    # (event_id) --ObstructsGoal-->   (goal_string)       [O-link variant]
    # (character) --ParticipatesIn--> (event_id)
    nlp: Optional[NLPIngestor] = None
    if _NLP_AVAILABLE:
        try:
            nlp = NLPIngestor(namespace="story")
        except Exception as exc:
            print(f"[main] NLPIngestor init failed: {exc}")

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
        # NLP-extracted semantic triples from event description
        if nlp and ev.description:
            try:
                text_triples = nlp.from_text(
                    ev.description,
                    provenance=f"event_description:{ev.event_id}",
                )
                kg.add_triples(text_triples)
            except Exception as exc:
                print(f"[main] NLP extraction error for [{ev.event_id}]: {exc}")




class RamblingRhinoDriver:
    # This is where the full engagement --> reflection --> promse pipeline takes place
    # In engagement, LLMClient generates plot events
    # In KG build, _events_to_kg() populates KnowledgeGraph
    # In reflection, for each reflection pass, ComplexityChecker finds gaps. For each gap, LLMClient reflects on the
    # QUEST gaps, inserts bridging events, rebuilds KG
    # In prose, LLMClient generated prose (the final story text)

    def __init__(
        self,
        premise:            str,
        genre:              str   = "crime mystery",
        events_per_batch:   int   = 20,
        engagement_batches: int   = 4,
        reflection_passes:  int   = 5,
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
        self.checker = ComplexityChecker()
        self.kg      = KnowledgeGraph()
        self.events: list[PlotEvent] = []

    
    ## Phase 1: Engagement
    def run_engagement(self) -> None:
        # Generated the initial event sequence using LLM calls. Multiple batches let the story grow incrementally, with
        # each batch conditioning on all previosuly-generated events.
        print("\n" + "═"*60)
        print("PHASE 1: ENGAGEMENT")
        print("═"*60)

        for batch_num in range(1, self.engagement_batches + 1):
            print(f"\n[Engagement batch {batch_num}/{self.engagement_batches}]")
            new_events = self.llm.generate_plot_events(
                premise=         self.premise,
                num_events=      self.events_per_batch,
                existing_events= self.events if self.events else None,
                genre=           self.genre,
            )
            self.events.extend(new_events)
            print(f"  Generated {len(new_events)} events "
                  f"(total: {len(self.events)})")

        print(f"\nEngagement complete: {len(self.events)} plot events.")
        self._print_events()

    
    ## Phase 2: KG Population
    def build_knowledge_graph(self) -> None:
        # Converts the current event list into KnowledgeGraph tripes, called after each engagement batch and after each
        # reflection pass.
        self.kg = KnowledgeGraph()   # rebuild from scratch for clean state
        _events_to_kg(self.events, self.kg)
        print(f"\nKnowledgeGraph: {self.kg}")

    
    ## Phase 3: Reflection
    def run_reflection(self) -> None:
        # Iterative gap detection and repair loop
        # During each pass, ComplexityChecker scans the event list for QUEST gaps. For each gap, the LLM generates a bridging
        # event. The bridging event is inserted at the correct position, and the KG is rebuilt. The loop stops when there's
        # no gaps, or we've reached the max number of passes.
        print("\n" + "═"*60)
        print("PHASE 3: REFLECTION")
        print("═"*60)

        for pass_num in range(1, self.reflection_passes + 1):
            print(f"\n[Reflection pass {pass_num}/{self.reflection_passes}]")
            gaps = self.checker.find_gaps(self.events)
            print(f"  {self.checker.summary(self.events)}")
            if (not gaps):
                print("  No gaps found, story is QUEST-coherent.")
                break
            story_summary = "\n".join(
                f"  [{ev.event_id}] {ev.description}" for ev in self.events
            )
            for gap in gaps:
                print(f"\n  Repairing {gap['type']} gap:")
                print(f"    {gap['description']}")
                bridging = self.llm.reflect_on_quest_gap(
                    gap_description=       gap["description"],
                    story_so_far=          story_summary,
                    insert_after_event_id= gap["insert_after"],
                )
                if (not bridging):
                    print("    [WARNING] LLM returned no bridging events.")
                    continue
                # Insert bridging events after the specified position
                insert_after = gap.get("insert_after")
                insert_idx   = len(self.events)
                if insert_after:
                    for i, ev in enumerate(self.events):
                        if ev.event_id == insert_after:
                            insert_idx = i + 1
                            break
                for j, bridge_ev in enumerate(bridging):
                    self.events.insert(insert_idx + j, bridge_ev)
                    print(f"    + Inserted [{bridge_ev.event_id}]: {bridge_ev.description}")
            # Rebuild KG after each reflection pass
            self.build_knowledge_graph()
        print(f"\nReflection complete: {len(self.events)} total events.")

    
    ## Phase 4: Prose Generation
    def run_prose(self) -> str:
        # Converts the final event list into narrative prose
        print("\n" + "═"*60)
        print("PHASE 3: PROSE GENERATION")
        print("═"*60)

        prose = self.llm.generate_prose(
            events=      self.events,
            genre=       self.genre,
        )
        print("\n" + "-"*60)
        print("GENERATED STORY")
        print("-"*60)
        print(textwrap.fill(prose, width=72))
        return prose



    def run(self) -> dict:
        # This executes the full pipeline and returns a results dict.
        # Returns a dict with keys: premise, genre, events , kg_stats (KnowledgeGraph statistics dict), prose (final
        # story string), usage (token usage string)
        start_time = time.time()
        # 1. Engagement
        self.run_engagement()
        # 2. Initial KG build
        self.build_knowledge_graph()
        # 3. Reflection loop
        self.run_reflection()
        # 4. Prose
        prose = self.run_prose()
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
    def _print_events(self) -> None:
        print("\nCurrent event list:")
        total = len(self.events)
        for i, ev in enumerate(self.events):
            label = self._label_plot_point(i, total)
            print(f"  [{ev.event_id}] ({label}) {ev.description}")
            if ev.caused_by:
                print(f"           caused_by: {ev.caused_by}")

    def _save_outputs(self, result: dict) -> None:
        # Saving the events JSON and prose text to output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        json_path  = self.output_dir / "story_events.json"
        prose_path = self.output_dir / "story_prose.txt"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        with open(prose_path, "w", encoding="utf-8") as f:
            f.write(result["prose"])
        print(f"\n  Events saved to : {json_path}")
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
              python main.py
              python main.py --premise "A spy goes rogue in Berlin." --genre "spy thriller"
              python main.py --events 10 --reflection-passes 3 --output-dir ./output
              python main.py --verbose
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
        "--events", type=int, default=8, dest="events_per_batch",
        help="Events to generate per engagement batch (default: 8).",
    )
    parser.add_argument(
        "--batches", type=int, default=1, dest="engagement_batches",
        help="Number of engagement batches (default: 1).",
    )
    parser.add_argument(
        "--reflection-passes", type=int, default=2,
        help="Max reflection / gap-repair passes (default: 2).",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="If set, saves story_events.json and story_prose.txt here.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print raw LLM responses for debugging.",
    )
    args = parser.parse_args()

    # Validate API key
    # api_key = os.environ.get("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE")
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
    print(f"  Events  : {args.events_per_batch} × {args.engagement_batches} batch(es)")
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