# Reading Model Driven Story Generation
> Team Rambling Rhino

This repo contains a two-thread QUEST-based story generation pipeline for mystery narratives:

- a hidden `crime` thread representing what really happened
- a visible `solving` thread representing what the investigator discovers
- a QUEST parser that converts event descriptions into narrative graphs
- a graph-based complexity checker used to trigger reflection and repair
- a final prose generator that writes only the solving story

## Setup

Create and activate the environment:

```bash
conda env create -f environment.yml
conda activate rhino
```

Install the spaCy English model required by `NarrativeIngestor`:

```bash
python -m spacy download en_core_web_sm
```

Set your Groq API key in the current shell:

```bash
export GROQ_API_KEY="your-real-groq-api-key"
```

## Current Architecture

### LLM Wrapper

- [`llm_api_wrapper.py`](/Users/nejaatapattu/Downloads/Spring2026/RamblinRhino/llm_api_wrapper.py)
  Contains `LLMClient`, which can:
  - generate hidden crime-thread events
  - generate visible solving-thread events
  - generate reflection/repair events
  - generate final prose from the solving thread

### QUEST Parsing

- [`quest_parsing/narrative_ingestor.py`](/Users/nejaatapattu/Downloads/Spring2026/RamblinRhino/quest_parsing/narrative_ingestor.py)
  Parses text into QUEST-style nodes and arcs.

- [`quest_parsing/knowledge_graph.py`](/Users/nejaatapattu/Downloads/Spring2026/RamblinRhino/quest_parsing/knowledge_graph.py)
  Stores the resulting narrative graph.

### Reflection

- [`complexity_checking/complexity_checker.py`](/Users/nejaatapattu/Downloads/Spring2026/RamblinRhino/complexity_checking/complexity_checker.py)
  Checks the graph against structural requirements such as:
  - minimum node counts
  - minimum arc counts
  - DAG requirement
  - connectivity requirement

### Driver

- [`main_system_script.py`](/Users/nejaatapattu/Downloads/Spring2026/RamblinRhino/main_system_script.py)
  Runs the full two-thread pipeline:
  1. generate the hidden crime thread
  2. parse crime events into a QUEST graph
  3. reflect/repair the crime thread using graph feedback
  4. generate the solving thread using the crime thread as hidden context
  5. parse solving events into a QUEST graph
  6. reflect/repair the solving thread using graph feedback
  7. generate final prose from the solving thread only

## Story Model

The system treats mystery generation as two connected narrative threads:

- `crime thread`
  The hidden ground-truth timeline. This includes motive, actions, concealment, and causal structure behind the crime.

- `solving thread`
  The reader-visible investigation timeline. This includes clues, interviews, obstacles, deductions, and staged revelation of the hidden crime.

Only the solving thread is turned into final prose.

## Running The System

Basic run:

```bash
python3 main_system_script.py
```

Example run:

```bash
python3 main_system_script.py \
  --premise "A museum archivist discovers that the theft of a manuscript is tied to a decades-old murder." \
  --genre "crime mystery" \
  --events 6 \
  --reflection-passes 2 \
  --output-dir ./output \
  --verbose
```

Useful flags:

- `--premise`: 1-3 sentence story premise
- `--genre`: genre hint for the LLM
- `--events`: number of events to generate per thread batch
- `--batches`: number of engagement batches per thread
- `--reflection-passes`: maximum repair passes per thread
- `--output-dir`: save thread outputs and prose
- `--verbose`: print raw LLM responses

## Output

When `--output-dir` is provided, the driver saves:

- `crime_events.json`: hidden crime-thread events
- `solving_events.json`: visible solving-thread events
- `solving_story.txt`: final prose generated only from the solving thread
- `run_summary.json`: combined run metadata, graph stats, and feedback history

## Example ComplexityChecker Usage

```python
from quest_parsing.narrative_ingestor import NarrativeIngestor
from quest_parsing.knowledge_graph import KnowledgeGraph
from quest_parsing.narrative_schema import ArcType, NodeType
from complexity_checking.complexity_checker import ComplexityChecker

kg = KnowledgeGraph()
ingestor = NarrativeIngestor(include_attr_triples=False)

text = (
    "The archivist notices that the manuscript is missing. "
    "She decides to investigate the curator. "
    "She wants to discover who stole the manuscript."
)

ingestor.from_text(text, kg, provenance="example")

checker = ComplexityChecker(
    kg,
    node_reqs={
        NodeType.EVENT: (2, -1),
        NodeType.GOAL: (1, -1),
    },
    arc_reqs={
        ArcType.CONSEQUENCE: (1, -1),
    },
    req_dag=True,
    req_conn=True,
)

feedback = checker()
print(feedback)
```

## Notes

- The current driver translates checker feedback into targeted repair prompts inside [`main_system_script.py`](/Users/nejaatapattu/Downloads/Spring2026/RamblinRhino/main_system_script.py).
- The crime thread is used as hidden context for the solving thread, not as final prose input.
- There is not currently a separate `ContextPrompter` class in the repo.
- The reflection rubrics for the crime and solving threads are intentionally simple and can be tuned as you test more stories.
