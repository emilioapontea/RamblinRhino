# Reading Model Driven Story Generation
> ***System Name:** Rambling Rhino Story Engine
> **Project Template:** Reader Model Driven Story Generation
> Team Rambling Rhino

To install our conda environment (`rhino`) with necessary dependencies:
```bash
conda env create -file environment.yml
conda activate rhino
```

Then install spaCy and download the language model:
```bash
pip install spacy
python -m spacy download en_core_web_sm
```

If you have pip dependencies to add (be sure you are in the `rhino` environment):
```bash
conda install <package> pip
conda env export > environment.yml
```

## API Key Setup
Our system uses the free tier of the Groq API. To get a Groq API key:
1. Go to [https://console.groq.com/keys](https://console.groq.com/keys)
2. Log in with your Google account
3. Click "Create API Key," create an API key, and copy it.
4. In llm_api_wrapper.py, replace API_KEY_HERE with your API key, so that it reads:
> python GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "gsk_YOUR_KEY_HERE

## How to Run the System
Run 'python main_system_script.py' in the terminal.
### With a custom premise and genre:
Run 'python main_system_script.py --premise "Your premise goes here" --genre "Your genre goes here"'
### With more events or reflection passes
Run ''python main_system_script.py --events m --reflection-passes n', replacing m and n with numbers
### Saving output to files
Run 'python main_system_script.py --output-dir ./output', which saves 2 files to the output directory: story_events.json (all plot events with QUEST metadata), and story_prose.txt (the final generated story)
### Verbose mode (which prints the raw LLM responses)
Run 'python main_system_script.py --verbose'

## Repository Structure
├── main_system_script.py                 # The top-level driver
├── llm_api_wrapper.py                    # Groq API wrapper (Engagement + Reflection + Prose)
├── environment.yml
├── Graesser-Question-answering.pdf
├── complexity_checking/
│   └── complexity_checker.py             # QUEST coherence checker (node/arc requirements)
└── quest_parsing/
    ├── arc_classifier.py                 # Classifies arc types between narrative nodes
    ├── knowledge_graph.py
    ├── narrative_ingestor.py             # End-to-end text -> KG pipeline
    ├── narrative_schema.py               # Node and arc data structures (ex. EventNode, GoalNode)
    └── node_classifier.py                # This classifies clauses into Event/Action/Goal/State nodes

## Engagement Modules
### ContextPrompter
A class that manages feedback from the `ComplexityChecker` and generates an engineered prompt to pass on to the LLM.
### LLM
A wrapper class to handle API requests to our chosen LLM and receive output in the form of QUEST events, goals, etc. to be parsed into the QUEST `KnowledgeGraph`.

## Reflection Modules
### KnowledgeGraph
A class (`quest_parsing.KnowledgeGraph`) to support `(subject --predicate--> object)` relationships in our QUEST graph. We will primarily be using the `NarrativeIngestor` (`quest_parsing.narrative_ingestor`) class which uses `spaCy`'s [`en_core_web_sm`](https://spacy.io/models/en#en_core_web_sm) (12 MB) CPU pipeline for tokenization, part of speech tagging, named entity recognition, etc., to build up the knowledge graph from our LLM's text responses.

> Example usage
```python
from quest_parsing.narrative_ingestor import NarrativeIngestor
from quest_parsing.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph()
ingestor = NarrativeIngestor(include_attr_triples=False)

ingestor.from_file('testing/claude_lighthouse.txt', kg) # replace with .txt file containing LLM generated story points.

# List KnowledgeGraph nodes
list(kg._g.nodes(data=True))

# List KnowledgeGraph edges
list(kg._g.edges(data=True))

# Use plt to plot KnowledgeGraph with node and edge labels.
import matplotlib.pyplot as plt
import networkx as nx

G = kg._g
pos = nx.spring_layout(G)
# subax1 = plt.subplot(121)
nx.draw(
    G,
    pos=pos,
    font_weight='bold',
    labels={n : f'{d['type']} : {d['label'][:10]}...' for n, d in G.nodes(data=True)},
    node_size=100,
    font_size=5,
    horizontalalignment='left',
)
nx.draw_networkx_edge_labels(
    G,
    pos=pos,
    edge_labels={(u,v) : f'{d['predicate']} ({d['weight']})' for u, v, d in G.edges(data=True)},
    font_size=2
)

plt.show()
```

### ComplexityChecker
A class with defined methods to evaluate the complexity of the quest graph in order to determine the system's control flow. Teh `ComplexityChecker` class allows you to initialize a `ComplexityChecker` object with the following parameters, and then call the object to check against the defined complexity parameters.

```python
"""
Args:
    kg: The knowledge graph to check.
    node_reqs: Optional dict mapping NodeType to (min_count, max_count) for that node type. Use max_count=-1 for no upper bound.
    arc_reqs: Optional dict mapping ArcType to (min_count, max_count) for that arc type. Use max_count=-1 for no upper bound.
    req_dag: If True, require that the graph is a directed acyclic graph (no circular events).
    req_conn: If True, require that the graph is weakly connected (no story discontinuity).


Returns:
    A list of feedback messages indicating any complexity requirement violations. An empty list indicates that all requirements are satisfied.
"""
```

> Example usage
```python
from quest_parsing.narrative_ingestor import NarrativeIngestor
from quest_parsing.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph()
ingestor = NarrativeIngestor(include_attr_triples=False)

ingestor.from_file('testing/claude_lighthouse.txt', kg) # replace with .txt file containing LLM generated story points.


from quest_parsing.narrative_schema import NodeType, ArcType
from complexity_checking.complexity_checker import ComplexityChecker

# Define ComplexityChecker with simple requirement: minimum 10 EVENT nodes and no max
c = ComplexityChecker(kg, node_reqs={NodeType.EVENT : (10, -1)})

# Call the ComplexityChecker to get feedback (list of strings)
c()
```

## Rambling Rhino Driver
We will have a class/script/notebook with defined methods for the execution of our system.
