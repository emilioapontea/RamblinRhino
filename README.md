# Reading Model Driven Story Generation
> **System Name:** Rambling Rhino Story Engine

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
main_system_script.py (the top-level driver)
llm_api_wrapper.py (Groq API warpper, engagement + reflection + prose)
environment.yml
Graesser-Question-answering.pdf
complexity_checking/

> complexity_checker.py (QUEST coherence checker, node/arc requirements)

quest_parsing/

> arc_classifier.py (classifies arc types between narrative nodes)

> knowledge_graph.py

> narrative_ingestor.py (end-to-end text --> KG pipeline)

> narrative_schema.py (node and arc data structures (ex. EventNode, GoalNode))

> node_classifier.py (classifies clauses into Event/Action/Goal/State nodes)

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
A class with defined methods to evaluate the complexity of the quest graph in order to determine the system's control flow. The `ComplexityChecker` class allows you to initialize a `ComplexityChecker` object with the following parameters, and then call the object to check against the defined complexity parameters.

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

## Example Output
> genre: crime mystery (default)

> 8 events (default)

> 2 reflection passes (default)

> Premise: "A small-town archivist discovers that a priceless 18th-century manuscript has been stolen from the local museum the night before its auction. She is the only one who knows what was truly hidden inside it."

Output:
════════════════════════════════════════════════════════════
  RAMBLING RHINO: Story Generation System
  Team Rambling Rhino | Reader-Model-Driven Generation
════════════════════════════════════════════════════════════
  Premise : A small-town archivist discovers that a priceless [...]
  Genre   : crime mystery
  Events  : 8 × 1 batch(es)
  Reflect : 2 pass(es)

════════════════════════════════════════════════════════════
PHASE 1: ENGAGEMENT
════════════════════════════════════════════════════════════

[Engagement batch 1/1]
  Generated 8 events (total: 8)

Engagement complete: 8 plot events.

Current event list:
  [E1] The small-town archivist, Emily, arrives at the local museum to prepare for the auction of the 18th-century manuscript.
  [E2] Emily discovers that the manuscript has been stolen from the museum, prompting her to investigate the theft.
           caused_by: ['E1']
  [E3] Emily recalls that she is the only one who knows about the hidden notes and codes within the manuscript, making her a key player in the investigation.   
           caused_by: ['E2']
  [E4] Emily decides to secretly investigate the theft, without informing the authorities, to avoid drawing attention to the manuscript's true value.
           caused_by: ['E3']
  [E5] Emily begins by reviewing the museum's security footage to identify potential suspects and clues.
           caused_by: ['E4']
  [E6] The museum's director, Mr. Johnson, announces the theft to the public, offering a reward for information leading to the recovery of the manuscript.      
           caused_by: ['E2']
  [E7] Emily's investigation is obstructed by the arrival of a detective, James, who has been assigned to the case and is unaware of the manuscript's true significance.
           caused_by: ['E6']
  [E8] James asks Emily to assist him in the investigation, unaware of her secret knowledge, and Emily must decide how much to reveal to him.
           caused_by: ['E7']

KnowledgeGraph: KnowledgeGraph(nodes=40, edges=46, by_source={'domain': 28, 'text': 18})

════════════════════════════════════════════════════════════
PHASE 3: REFLECTION
════════════════════════════════════════════════════════════

[Reflection pass 1/2]
  ComplexityChecker: 0 causal gap(s), 1 goal gap(s)

  Repairing goal gap:
    Event [E7] resolves/obstructs goal "protect knowledge of hidden notes", but no earlier event initiates this goal. An event that establishes the goal is needed.
    + Inserted [E_b1]: Emily realizes the significance of keeping the hidden notes and codes secret to prevent them from falling into the wrong hands
    + Inserted [E_b2]: Emily understands that her secret investigation must also focus on protecting the knowledge of the manuscript's hidden content

KnowledgeGraph: KnowledgeGraph(nodes=43, edges=55, by_source={'domain': 36, 'text': 19})

[Reflection pass 2/2]
  ComplexityChecker: 0 causal gap(s), 0 goal gap(s)
  No gaps found, story is QUEST-coherent.

Reflection complete: 10 total events.

════════════════════════════════════════════════════════════
PHASE 3: PROSE GENERATION
════════════════════════════════════════════════════════════

------------------------------------------------------------
GENERATED STORY
------------------------------------------------------------
As Emily arrived at the local museum, the early morning sunlight casting
a golden glow over the historic building, she felt a sense of excitement
and trepidation. The auction of the 18th-century manuscript was just
days away, and she had spent countless hours preparing the delicate
pages for display. But as she entered the vault where the manuscript was
kept, her heart sank. The glass case lay empty, the manuscript nowhere
to be found. Emily's mind racing, she realized that the manuscript had
been stolen from the museum, prompting her to investigate the theft.  As
she stood there, trying to process the news, Emily recalled that she was
the only one who knew about the hidden notes and codes within the
manuscript. She had spent years studying the intricate script,
unraveling the secrets that lay hidden within the yellowed pages. This
knowledge made her a key player in the investigation, and she knew that
she had to tread carefully. Emily decided to secretly investigate the
theft, without informing the authorities, to avoid drawing attention to
the manuscript's true value. She couldn't risk the wrong people finding
out about the hidden content, and the potential consequences that could
follow.  Emily began her investigation by reviewing the museum's
security footage, scanning the grainy images for any sign of the thief.
She spent hours poring over the footage, her eyes scanning the corridors
and galleries for any suspicious activity. As she worked, the museum's
director, Mr. Johnson, announced the theft to the public, offering a
reward for information leading to the recovery of the manuscript. Emily
watched as the news spread like wildfire, the public's interest in the
manuscript growing by the minute. But she knew that she had to keep the
true significance of the manuscript hidden, even from the authorities.
The realization hit her like a ton of bricks: the hidden notes and codes
were not just valuable, but also potentially dangerous if they fell into
the wrong hands. Emily understood that her secret investigation must
also focus on protecting the knowledge of the manuscript's hidden
content, and she felt the weight of that responsibility settling on her
shoulders.  As she delved deeper into the investigation, Emily's resolve
was put to the test. She had to navigate the complex web of secrets and
lies, all while keeping her true intentions hidden. The arrival of
Detective James, assigned to the case, only added to the complexity. He
was a seasoned investigator, with a keen mind and a sharp instinct, but
he was also unaware of the manuscript's true significance. James asked
Emily to assist him in the investigation, unaware of her secret
knowledge, and Emily was faced with a difficult decision. How much could
she reveal to him, without putting the manuscript's secrets at risk? She
knew that she had to tread carefully, balancing her desire to recover
the manuscript with the need to protect its hidden content. As she
looked at James, his eyes expectant and trusting, Emily knew that she
had to make a choice. Would she confide in him, or keep her secrets
hidden, even from those who might be able to help her? The fate of the
manuscript, and the secrets it held, hung in the balance.

════════════════════════════════════════════════════════════
RUN SUMMARY
════════════════════════════════════════════════════════════
  Elapsed time  : 5.9 s
  Total events  : 10
  KG stats      : {'nodes': 43, 'edges': 55, 'edges_by_source': {'domain': 36, 'text': 19}}
  Token usage   : TokenUsage(input=1,287, output=1,440, cost=$0.00 [Groq free tier])

## Rambling Rhino Driver
We will have a class/script/notebook with defined methods for the execution of our system.
