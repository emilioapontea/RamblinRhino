# Rambling Rhino Story Engine

> **System Name:** Rambling Rhino Story Engine  
> **Project Template:** Intervention and Accommodation  
> Team Rambling Rhino: Emilio Aponte, Neja Atapattu, Nandini Ramakrishnan

Rambling Rhino generates a crime mystery, separates the crime backstory from the playable investigation, and lets the user play through the solving story as an interactive text game. The system uses LLM-generated plot events, QUEST-style causal structure, a lightweight world model, and dynamic repair when the player derails the investigation.

This repository reflects the Phase 2 version of the project: an interactive mystery system built around intervention and accommodation.

An example run through is listed in (`demo_command_trace.md`)
## To run the reproducible demo

The interactive system is able to bypass the initial story generation stage by loading a previously generated story structure. For demo purposes and to reduce the amount of API requests, we recommend using our generated story (`./output/solving_story_events`). This way the interactive element will be as close as possible to our own testing runs.
> The interactive Drama Manager still makes API requests to write the story and to make adjustments as the user feedback loop executes, so the exact output may differ between runs.

To run the interactive system:

1. Create and activate our `conda` environment (see [Setup](#setup) section)
2. Generate a [Cerebras](https://cloud.cerebras.ai/) API key (free tier should be sufficient) and set the environment variable (see [API Key](#api-key) section)
3. Run our main system script with the `--interactive` and `--load-story` flags.
```bash
python main_system_script.py --load-story ./output/run_summary.json --interactive
```

See [How to Run](#how-to-run) for more run configurations and read the remaining document for additional information about our system.

## Current Behavior

- The crime story is treated as backstory and world context.
- The solving story is treated as the playable investigation sequence.
- Interactive mode accepts open-ended text input.
- Player actions are classified as `constituent`, `consistent`, or `exceptional`.
- Exceptional actions can trigger accommodation and introduce alternate leads.
- LLM-backed interactive mode interprets user actions, narrates events, and supports repair generation.
- `story_prose.txt` is generated from the solving story, not the full crime timeline.

## Setup

Create and activate the project environment:

```bash
conda env create -f environment.yml
conda activate rhino
```

Install spaCy and the English model:

```bash
python -m pip install spacy
python -m spacy download en_core_web_sm
```

If `networkx` is missing:

```bash
python -m pip install networkx
```

If spaCy is not installed, the project can still run, but the `NarrativeIngestor` warning will appear and the knowledge graph will not include NLP-derived triples.

## API Key

The current LLM wrapper uses the Cerebras chat-completions API:

```bash
export CEREBRAS_API_KEY="YOUR_CEREBRAS_API_KEY"
```

Some older project checks still refer to Groq. If you see an API-key warning from the driver, also set:

```bash
export GROQ_API_KEY="YOUR_CEREBRAS_API_KEY"
```

The key is used for:

- story generation
- reflection and repair generation
- interactive action interpretation
- interactive event narration
- full prose generation

If the API key is missing or invalid, interactive mode falls back to local command parsing where possible. A `401 Unauthorized` error means the Cerebras key is missing, invalid, expired, or not authorized for the endpoint.

## How to Run

Generate a new story:

```bash
python main_system_script.py
```

Generate and save outputs:

```bash
python main_system_script.py --output-dir ./output
```

Run a fresh interactive investigation:

```bash
python main_system_script.py --interactive
```

Load a saved story and play interactively:

```bash
python main_system_script.py --load-story ./output/run_summary.json --interactive
```

Generate with a custom premise and genre:

```bash
python main_system_script.py --premise "Your premise goes here" --genre "crime mystery"
```

Generate with more events or reflection passes:

```bash
python main_system_script.py --events 36 --reflection-passes 3 --output-dir ./output
```

Verbose mode:

```bash
python main_system_script.py --verbose
```

## Interactive Commands

Interactive mode accepts natural-language commands such as:

```text
inspect fabric
look at side door
inspect the cufflink
look at alex's phone
review the security footage
question the staff member
go to curator's computer
read the email
inspect computer
look at transaction
go to storage room
open the safe
confront curator about email
```

The game also supports disruptive actions for the accommodation demo:

```text
burn the fabric
destroy the security footage
delete the suspicious email
accuse alex immediately
```

These should be classified as `exceptional` when they damage evidence or derail the investigation.

## Demo Transcript Files

Two transcript files are included for presenting the interactive run:

- `demo_command_trace.md`: Markdown transcript with player commands bolded.
- `demo_command_trace.html`: HTML transcript with player commands highlighted in color.

Use the Markdown file for reports or GitHub. Use the HTML file when you want colored command highlighting in a browser.

## Saved Outputs

When you run with `--output-dir`, the project writes:

- `crime_story_events.json`: structured crime backstory events
- `solving_story_events.json`: structured playable solving events
- `run_summary.json`: premise, events, world summary, and prose metadata
- `story_prose.txt`: prose generated from the solving story

By default, the system generates `30` total pre-reflection events, split into crime-story and solving-story events before reflection adds repairs or bridge events.

## Repository Structure

- `main_system_script.py`: top-level driver for story generation, reflection, saving, loading, and interactive mode
- `llm_api_wrapper.py`: Cerebras API wrapper, event generation, reflection, action interpretation, accommodation prompts, and prose generation
- `interactive_story_world.py`: world model, room graph, interactive loop, action validation, classification, dynamic repair, and event prose rendering
- `environment.yml`: environment definition
- `complexity_checking/complexity_checker.py`: QUEST coherence checks
- `quest_parsing/knowledge_graph.py`: graph representation used by the system
- `quest_parsing/narrative_ingestor.py`: text-to-graph ingestion
- `quest_parsing/narrative_schema.py`: node and arc schema
- `quest_parsing/arc_classifier.py`: narrative arc classification
- `quest_parsing/node_classifier.py`: narrative node classification

## Core Modules

### LLMClient

Handles:

- crime story event generation
- solving story event generation
- reflection and bridging events
- interactive action interpretation
- accommodation event generation
- event narration
- full solving-story prose generation

### InteractiveStoryGame

Builds the playable investigation world and manages:

- room traversal
- clue discovery
- inventory
- open-ended player commands
- action classification
- dynamic repair of broken story paths

### KnowledgeGraph

Stores story relationships and supports reflection/coherence checks. When spaCy is available, `NarrativeIngestor` can derive additional structure from event text.

### ComplexityChecker

Evaluates structural properties of the quest graph, such as connectivity, DAG constraints, and node/arc requirements.

## Notes

- `story_prose.txt` is a polished linear version of the solving story. Interactive mode does not directly play through that prose; it builds a playable world from the structured JSON events.
- The interactive world may expose rooms and objects derived from future events. The next-lead guidance tells the player which location/object currently matters.
- Restart the script after code changes so Python reloads the updated files.
