# Rambling Rhino Story Engine
> **System Name:** Rambling Rhino Story Engine

> **Project Template:** Intervention and Accommodation

> Team Rambling Rhino

Rambling Rhino generates a crime mystery, separates the crime backstory from the playable investigation, and lets the user play through the solving story as an interactive text game. The system uses LLM-generated plot events, QUEST-style causal structure, a lightweight world model, and dynamic repair when the player derails the investigation.

This repository now reflects our **Phase 2** project: an interactive mystery system built around intervention and accommodation.

## Current Project Behavior
- The crime story is treated as backstory and world context.
- The solving story is treated as the playable investigation sequence.
- The default run targets at least 15 solving-story plot events.
- Interactive mode accepts open-ended text input.
- Player actions are interpreted as constituent, consistent, or exceptional.
- Exceptional actions can trigger accommodation, which repairs the investigation with alternate leads.
- `story_prose.txt` is generated from the solving story, not the full crime timeline.

## Setup
Create and activate the project environment:

```bash
conda env create -f environment.yml
conda activate rhino
```

Install spaCy and the English model:

```bash
pip install spacy
python -m spacy download en_core_web_sm
```

If `networkx` is missing in your current Python, install it in the same environment you use to run the project:

```bash
python -m pip install networkx
```

## Cerebras API Key
The project uses the Cerebras Inference API for:
- story generation
- reflection / repair generation
- interactive action interpretation
- interactive event narration
- full prose generation

Set your key in the terminal before running:

```
$env:CEREBRAS_API_KEY="YOUR_API_KEY_GOES_HERE"
```

To get a Cerebras Inference API key:
- Go to https://cloud.cerebras.ai/platform/org_4jprj3hmkmyfnhcwvy66yrr8/get-started?onboarding=true
- Log in, copy an API key

You only need a Cerebras API key when generating a new story or using the LLM-backed interactive features. If you load a previously saved story, the project can still run with local fallbacks.

## How to Run
Generate a new story:

```bash
python main_system_script.py
```

Generate a new story with custom premise and genre:

```bash
python main_system_script.py --premise "Your premise goes here" --genre "crime mystery"
```

Generate a new story and save outputs:

```bash
python main_system_script.py --output-dir ./output
```

Run the interactive investigation:

```bash
python main_system_script.py --interactive
```

Load a previously saved story and skip regeneration:

```bash
python main_system_script.py --load-story ./output/run_summary.json --interactive
```

Generate with more events or reflection passes:

```bash
python main_system_script.py --events 30 --reflection-passes 3
```

Verbose mode:

```bash
python main_system_script.py --verbose
```

## Saved Outputs
When you run with `--output-dir`, the project writes:
- `crime_story_events.json`: structured crime backstory events
- `solving_story_events.json`: structured playable solving events
- `run_summary.json`: premise, events, world summary, and prose metadata
- `story_prose.txt`: prose generated from the solving story

By default, the system generates `30` total pre-reflection events, which splits into `15` crime-story events and `15` solving-story events before reflection adds any repairs or bridge events.

## Repository Structure
- `main_system_script.py`: top-level driver for story generation, reflection, saving, loading, and interactive mode
- `llm_api_wrapper.py`: Cerebras client, event generation, reflection, action interpretation, accommodation prompts, and prose generation
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
- reflection / bridging events
- interactive action interpretation
- accommodation event generation
- event narration
- full solving-story prose generation

### KnowledgeGraph
A graph structure used to store story relationships and support reflection/coherence checks. The project uses `NarrativeIngestor` and the QUEST-related parsing modules to derive additional structure from event text.

### InteractiveStoryGame
Builds the playable investigation world and manages:
- room traversal
- clue discovery
- inventory
- open-ended player commands
- classification of actions
- dynamic repair of broken story paths

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

## Phase 2 Notes
This repository is organized around the **Phase 2** version of the project.

What that means in practice:
- the crime story is generated as backstory and case context
- the solving story is the playable investigation
- the default target is at least 15 solving-story plot points
- `story_prose.txt` is written from the solving story, not the crime backstory
- interactive play supports open-ended commands, action classification, and dynamic repair

## Example Usage
Generate and save a Phase 2 story package:

```bash
python main_system_script.py --output-dir ./output
```

Run the interactive investigation using a saved story:

```bash
python main_system_script.py --load-story ./output/run_summary.json --interactive
```

Generate a larger story if you want more than the default:

```bash
python main_system_script.py --events 36 --reflection-passes 3 --output-dir ./output
```
manuscript and the leather-bound book into a specially designed bag,
taking care not to damage either artifact. As they sealed the bag, The
Fox felt a sense of pride and accomplishment, knowing that they had
pulled off the impossible.


────────────────────────────────────────────────────────────
--- Plot Point 4: A small, valuable item is found hidden within the manuscript, which was the true target of the theft. ---
────────────────────────────────────────────────────────────
The leather-bound book was the true target of the theft, a rare and
valuable artifact that The Fox had been hired to steal. The manuscript,
while valuable in its own right, was merely a distraction, a way to
throw the museum's security team off The Fox's trail. As The Fox held
the book, they felt a sense of satisfaction, knowing that they had
completed their mission.

The book was small, but its significance was immense. It was said to
contain secrets and knowledge that had been lost for centuries, and The
Fox knew that it would fetch a handsome price on the black market. With
the book safely in hand, The Fox made their way back through the museum,
avoiding the security cameras and alarms with ease.

As they reached the exit, The Fox felt a sense of relief wash over them.
The heist had been a success, and they had escaped undetected. But The
Fox knew that the real challenge lay ahead, selling the book on the
black market without getting caught.


────────────────────────────────────────────────────────────
--- Plot Point 5: The thief escapes the museum without triggering any alarms, using a pre-planned route. ---
────────────────────────────────────────────────────────────
The Fox made their way back through the museum, using a pre-planned
route to avoid the security cameras and alarms. They moved swiftly and
silently, their senses on high alert as they navigated the dark and
deserted halls. The Fox had spent months studying the museum's layout,
planning the perfect escape route, and now they put that knowledge to
use.

As they reached the exit, The Fox felt a sense of relief wash over them.
They had pulled off the impossible, stealing the manuscript and the
valuable item without triggering a single alarm. The Fox slipped out
into the night, disappearing into the shadows as they made their way
back to their safe house.

The city was alive and bustling, but The Fox moved through it unnoticed,
a ghostly figure in the darkness. They knew that the museum's security
team would be on high alert, searching for any sign of the thief, but
The Fox was confident that they had covered their tracks. With the
manuscript and the valuable item safely in hand, The Fox disappeared
into the night, ready to sell their prize on the black market.


────────────────────────────────────────────────────────────
--- Plot Point 6: The archivist, Clara, arrives at the museum the next morning to prepare for the auction and discovers the theft. ---
────────────────────────────────────────────────────────────
Clara arrived at the museum the next morning, eager to begin preparing
for the auction. As she made her way to the display case, she noticed
that something was off. The case was open, and the manuscript was gone.
Clara's heart sank as she realized that the museum had been robbed.

She quickly called the security team, reporting the theft and asking
them to review the security footage. As she waited for the team to
arrive, Clara couldn't help but feel a sense of responsibility for the
theft. She had been in charge of preparing the manuscript for the
auction, and now it was gone.

The security team arrived, and together they reviewed the footage,
searching for any sign of the thief. But The Fox had been careful,
avoiding the cameras and alarms with ease. Clara knew that she had a
long day ahead of her, working to track down the thief and recover the
stolen manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 7: Clara realizes that the thief must have had inside help to bypass the museum's security system. ---
────────────────────────────────────────────────────────────
As Clara reviewed the security footage, she realized that the thief must
have had inside help to bypass the museum's security system. The Fox had
moved with ease, avoiding the cameras and alarms as if they had a
detailed knowledge of the museum's layout. Clara's eyes narrowed as she
thought about the possibilities.

She knew that the museum's security system was state-of-the-art, and it
would have been impossible for The Fox to breach it without help. Clara
began to think about the museum's staff, wondering if anyone could have
been involved in the theft. She made a mental note to interview the
staff members, looking for anyone who might have been acting
suspiciously.

The more Clara thought about it, the more she became convinced that The
Fox had had inside help. The question was, who had helped them, and how
had they managed to keep it a secret? Clara was determined to find out,
and she began to make a list of suspects, starting with the museum's
staff members.


────────────────────────────────────────────────────────────
--- Plot Point 8: Clara begins to investigate the museum staff, looking for anyone who may have been involved in the theft. ---
────────────────────────────────────────────────────────────
Clara began to investigate the museum staff, looking for anyone who may
have been involved in the theft. She started by interviewing the staff
members, asking them about their whereabouts the night before. As she
spoke to each person, Clara watched their body language, looking for any
sign of nervousness or deception.

The staff members seemed shaken by the theft, but Clara noticed that one
of them, a quiet and reserved woman named Sarah, seemed particularly
nervous. Clara made a mental note to speak to Sarah again, to ask her
more questions about her whereabouts the night before.

As the day wore on, Clara continued to investigate, searching for any
clues that might lead her to The Fox. She reviewed the security footage
again, looking for any sign of the thief or their accomplice. Clara was
determined to solve the case, and she was willing to do whatever it took
to recover the stolen manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 9: The thief, now in possession of the valuable item, contacts a potential buyer on the black market. ---
────────────────────────────────────────────────────────────
The Fox, now in possession of the valuable item, contacted a potential
buyer on the black market. The buyer, a wealthy collector, was known for
his love of rare and valuable artifacts, and The Fox knew that he would
be interested in the leather-bound book. The Fox sent the collector a
message, describing the book and its contents, and asking for a meeting
to discuss the sale.

The collector was intrigued, and he agreed to meet with The Fox. They
arranged to meet at a secure location, a warehouse on the outskirts of
the city. The Fox was cautious, knowing that the collector could be a
trap, but they were also confident in their ability to negotiate a good
price.

As The Fox waited for the meeting, they couldn't help but feel a sense
of excitement. They had pulled off the impossible, stealing the
manuscript and the valuable item, and now they were about to sell it to
the highest bidder. The Fox knew that they would have to be careful, but
they were confident in their ability to get away with the sale.


────────────────────────────────────────────────────────────
--- Plot Point 10: Clara discovers a cryptic message at the crime scene, which may lead her to the thief's identity and the location of the stolen manuscript. ---
────────────────────────────────────────────────────────────
Clara discovered a cryptic message at the crime scene, a small piece of
paper with a code written on it. The code was complex, but Clara was
determined to crack it, knowing that it could lead her to The Fox's
identity and the location of the stolen manuscript. She took the paper
to the museum's cryptologist, who began to work on deciphering the code.

As they worked, Clara couldn't help but feel a sense of excitement. She
had been searching for a lead, and now she had one. The code was the key
to unlocking the mystery of the theft, and Clara was determined to solve
it.

The cryptologist worked tirelessly, using their knowledge of codes and
ciphers to decipher the message. Finally, after hours of work, they
cracked the code, revealing a message that read: "Look to the shadows
for the truth." Clara's eyes narrowed as she thought about the message,
wondering what it could mean.


────────────────────────────────────────────────────────────
--- Plot Point 11: Clara decodes the cryptic message, revealing a possible lead on the thief's accomplice within the museum staff. ---
────────────────────────────────────────────────────────────
Clara decoded the cryptic message, revealing a possible lead on The
Fox's accomplice within the museum staff. The message had been a riddle,
leading Clara to a specific staff member who had been acting
suspiciously. Clara's eyes widened as she realized that the staff member
was none other than Sarah, the quiet and reserved woman she had
interviewed earlier.

Clara felt a sense of excitement and trepidation as she realized that
she had been on the right track all along. She had suspected that Sarah
might be involved, and now she had proof. Clara decided to bring Sarah
in for further questioning, to see if she could get to the bottom of the
mystery.

As Clara prepared to confront Sarah, she couldn't help but feel a sense
of unease. She had been working with Sarah for months, and she had
always thought of her as a friend. But now, Clara wasn't so sure. She
wondered if Sarah had been playing her all along, using their friendship
to further her own goals.


────────────────────────────────────────────────────────────
--- Plot Point 12: Clara interviews museum staff members, gathering information about potential suspects and their alibis for the night of the theft. ---
────────────────────────────────────────────────────────────
Clara interviewed the museum staff members, gathering information about
potential suspects and their alibis for the night of the theft. She
started with Sarah, asking her about her whereabouts the night before.
Sarah seemed nervous, but she provided a solid alibi, saying that she
had been at home, alone.

Clara wasn't convinced, and she decided to investigate further. She
spoke to the other staff members, asking them if they had seen or heard
anything suspicious. One of the staff members mentioned that they had
seen Sarah arguing with one of the security guards earlier that day.
Clara's ears perked up as she heard this, wondering if there might be a
connection between the argument and the theft.

As Clara continued to investigate, she began to piece together a
timeline of the events surrounding the theft. She discovered that Sarah
had been in the museum late the night before, supposedly working on a
project. But Clara wasn't sure if she believed this, and she decided to
look deeper into Sarah's alibi.


────────────────────────────────────────────────────────────
--- Plot Point 13: Clara identifies a discrepancy in the staff member's alibi. ---
────────────────────────────────────────────────────────────
Clara identified a discrepancy in Sarah's alibi, a small inconsistency
that suggested she might not have been telling the truth. Sarah had said
that she was at home alone the night before, but Clara had discovered
that Sarah's neighbor had seen her leaving her apartment around 10 pm.
Clara's eyes narrowed as she thought about this, wondering what Sarah
might have been doing.

Clara decided to confront Sarah about the discrepancy, to see if she
could get to the bottom of the mystery. She called Sarah into her
office, asking her to explain the inconsistency in her alibi. Sarah
seemed taken aback, but she tried to explain, saying that she had gone
out for a walk to clear her head.

Clara wasn't convinced, and she decided to press Sarah further. She
asked her about the argument with the security guard, wondering if there
might be a connection between the argument and the theft. Sarah seemed
hesitant, but she eventually opened up, telling Clara about the argument
and how it had been about a misunderstanding.


────────────────────────────────────────────────────────────
--- Plot Point 14: Clara obtains security footage of the staff member's suspicious activity. ---
────────────────────────────────────────────────────────────
Clara obtained security footage of Sarah's suspicious activity, a video
that showed her entering the museum late the night before. The footage
was grainy, but it clearly showed Sarah slipping into the museum,
avoiding the security cameras. Clara's eyes widened as she watched the
footage, realizing that she had finally found the proof she needed.

The footage showed Sarah making her way to the display case, where she
seemed to be waiting for someone. Clara's heart racing with excitement,
she realized that Sarah must have been working with The Fox, helping
them to steal the manuscript. Clara decided to confront Sarah about the
footage, to see if she could get her to confess.

As Clara prepared to confront Sarah, she couldn't help but feel a sense
of satisfaction. She had been working on the case for days, and finally,
she had found the break she needed. Clara was determined to solve the
case, and she was willing to do whatever it took to recover the stolen
manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 15: Clara analyzes the security footage and discovers a staff member's suspicious activity near the display case on the night of the theft. ---
────────────────────────────────────────────────────────────
Clara analyzed the security footage, discovering a staff member's
suspicious activity near the display case on the night of the theft. The
footage showed Sarah lingering around the case, glancing nervously at
her watch. Clara's eyes narrowed as she thought about this, wondering
what Sarah might have been waiting for.

As Clara continued to analyze the footage, she noticed that Sarah seemed
to be communicating with someone, using a series of subtle hand
gestures. Clara's heart racing with excitement, she realized that Sarah
must have been working with The Fox, helping them to steal the
manuscript. Clara decided to enhance the footage, to see if she could
get a better look at Sarah's accomplice.

The enhanced footage revealed a shocking truth: Sarah had been working
with one of the museum's security guards. Clara's eyes widened as she
realized the extent of the betrayal, wondering how the guard could have
been involved in the theft. Clara decided to bring the guard in for
questioning, to see if she could get to the bottom of the mystery.


────────────────────────────────────────────────────────────
--- Plot Point 16: Clara interviews the staff member, who provides an alibi that Clara suspects is false. ---
────────────────────────────────────────────────────────────
Clara interviewed the staff member, who provided an alibi that Clara
suspected was false. The staff member, a quiet and reserved woman,
seemed nervous and fidgety, avoiding eye contact. Clara's ears perked up
as she listened to the alibi, wondering if the staff member was hiding
something.

The staff member said that she had been at home, watching TV, at the
time of the theft. But Clara noticed that the staff member seemed
hesitant, and she decided to press her further. Clara asked the staff
member about her whereabouts earlier that day, wondering if she might
have been seen near the display case.

The staff member seemed taken aback, but she tried to explain, saying
that she had been on a break. Clara wasn't convinced, and she decided to
investigate further. She asked the staff member about her relationship
with the security guard, wondering if there might be a connection
between them.


────────────────────────────────────────────────────────────
--- Plot Point 17: Clara discovers a discrepancy in the staff member's alibi and confronts them about the inconsistency. ---
────────────────────────────────────────────────────────────
Clara discovered a discrepancy in the staff member's alibi and
confronted them about the inconsistency. The staff member seemed taken
aback, but they tried to explain, saying that they had forgotten to
mention a trip to the store. Clara's eyes narrowed as she thought about
this, wondering if the staff member was telling the truth.

Clara decided to press the staff member further, to see if she could get
to the bottom of the mystery. She asked the staff member about their
relationship with the security guard, wondering if there might be a
connection between them. The staff member seemed hesitant, but they
eventually opened up, telling Clara about their friendship.

Clara's ears perked up as she listened to the staff member's story,
wondering if she might be getting close to the truth. She decided to
investigate further, to see if she could find any evidence of a
connection between the staff member and the security guard. Clara's
heart racing with excitement, she realized that she might be on the
verge of solving the case.


────────────────────────────────────────────────────────────
--- Plot Point 18: The staff member cracks under pressure and reveals their involvement in the theft, but claims they were coerced by the true mastermind. ---
────────────────────────────────────────────────────────────
The staff member cracked under pressure and revealed their involvement
in the theft, but claimed they were coerced by the true mastermind.
Clara's eyes widened as she listened to the staff member's confession,
realizing that she had finally found a break in the case.

The staff member said that they had been approached by the security
guard, who had offered them a large sum of money to help with the theft.
The staff member claimed that they had been hesitant at first, but the
guard had convinced them that it would be easy and that they would never
get caught. Clara's ears perked up as she listened to the staff member's
story, wondering if they might be telling the truth.

Clara decided to investigate further, to see if she could find any
evidence of the security guard's involvement. She asked the staff member
about the guard's identity, wondering if she might be able to track them
down. The staff member provided a name, and Clara's heart racing with
excitement, she realized that she might be on the verge of solving the
case.


────────────────────────────────────────────────────────────
--- Plot Point 19: Clara obtains a list of the staff member's contacts and discovers a connection to a known black market dealer. ---
────────────────────────────────────────────────────────────
Clara obtained a list of the staff member's contacts and discovered a
connection to a known black market dealer. The dealer, a notorious
figure in the art world, was known for his ability to sell stolen goods
to the highest bidder. Clara's eyes widened as she realized the extent
of the dealer's involvement, wondering if she might be able to track him
down.

Clara decided to investigate further, to see if she could find any
evidence of the dealer's involvement in the theft. She asked the staff
member about their relationship with the dealer, wondering if they might
have been in contact with him recently. The staff member seemed
hesitant, but they eventually opened up, telling Clara about their
dealings with the dealer.

Clara's ears perked up as she listened to the staff member's story,
realizing that she might be getting close to the truth. She decided to
track down the dealer, to see if she could recover the stolen
manuscript. Clara's heart racing with excitement, she realized that she
might be on the verge of solving the case.


────────────────────────────────────────────────────────────
--- Plot Point 20: Clara and the police set up a sting operation to catch the black market dealer and recover the stolen manuscript. ---
────────────────────────────────────────────────────────────
Clara and the police set up a sting operation to catch the black market
dealer and recover the stolen manuscript. The operation was complex,
involving multiple officers and a series of undercover agents. Clara's
heart racing with excitement, she realized that she might be on the
verge of solving the case.

The police had tracked the dealer to a warehouse on the outskirts of the
city, where they suspected he was hiding the manuscript. Clara and the
officers set up a sting, posing as buyers interested in purchasing the
manuscript. The dealer, confident in his ability to sell the manuscript,
agreed to meet with them.

As the meeting approached, Clara's nerves began to fray. She knew that
the operation was risky, and that anything could go wrong. But she was
determined to see it through, to recover the stolen manuscript and bring
the dealer to justice. Clara's eyes locked onto the dealer, and she
smiled, knowing that she had him right where she wanted him.


────────────────────────────────────────────────────────────
--- Plot Point 21: The sting operation is successful, and the black market dealer is arrested, but the manuscript is not found on their person. ---
────────────────────────────────────────────────────────────
The sting operation was successful, and the black market dealer was
arrested, but the manuscript was not found on their person. Clara's
heart sank as she realized that the dealer must have hidden the
manuscript elsewhere. But she was determined to find it, and she began
to question the dealer, trying to get him to reveal the manuscript's
location.

The dealer, however, was not cooperative. He refused to say anything,
and Clara was forced to use her skills of persuasion to try and get him
to talk. After hours of questioning, the dealer finally cracked,
revealing that he had sold the manuscript to a private collector.

Clara's eyes widened as she listened to the dealer's confession,
realizing that she had been one step behind the thief all along. But she
was determined to recover the manuscript, and she set her sights on the
private collector. Clara's heart racing with excitement, she realized
that she might be on the verge of solving the case.


────────────────────────────────────────────────────────────
--- Plot Point 22: The black market dealer reveals that the manuscript was sold to a private collector, who is willing to return it in exchange for immunity. ---
────────────────────────────────────────────────────────────
The black market dealer revealed that the manuscript was sold to a
private collector, who was willing to return it in exchange for
immunity. Clara's ears perked up as she listened to the dealer's
confession, realizing that she might be able to recover the manuscript
after all.

The private collector, a wealthy and influential figure, had been known
to collect rare and valuable artifacts. Clara suspected that the
collector might have been aware of the manuscript's stolen status, but
she was willing to offer them immunity in exchange for the manuscript's
return.

Clara's heart racing with excitement, she realized that she might be on
the verge of solving the case. She contacted the private collector,
offering them a deal: in exchange for the manuscript's return, the
collector would receive immunity from prosecution. The collector agreed,
and Clara arranged to meet with them to recover the manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 23: Clara and the police negotiate with the private collector, and a deal is made to return the manuscript in exchange for immunity. ---
────────────────────────────────────────────────────────────
Clara and the police negotiated with the private collector, and a deal
was made to return the manuscript in exchange for immunity. The
collector, a middle-aged man with a passion for rare artifacts, seemed
reluctant to give up the manuscript, but he eventually agreed to the
terms.

Clara's eyes locked onto the manuscript as it was handed over, feeling a
sense of relief and satisfaction. She had solved the case, and the
manuscript was finally back where it belonged. The collector, in turn,
received immunity from prosecution, and Clara was willing to let him off
with a warning.

As the deal was finalized, Clara couldn't help but feel a sense of pride
and accomplishment. She had worked tirelessly to solve the case, and it
had finally paid off. The manuscript was back, and the thief had been
brought to justice. Clara's heart racing with excitement, she realized
that she had done it – she had solved the case of the stolen manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 24: The manuscript is returned, and Clara is hailed as a hero for solving the case and recovering the valuable artifact. ---
────────────────────────────────────────────────────────────
The manuscript was returned, and Clara was hailed as a hero for solving
the case and recovering the valuable artifact. The museum's staff and
patrons were overjoyed, and Clara was praised for her dedication and
expertise. The manuscript was put back on display, and Clara was invited
to give a lecture on its history and significance.

As Clara stood in front of the crowd, she felt a sense of pride and
satisfaction. She had solved the case, and the manuscript was finally
back where it belonged. The crowd applauded, and Clara smiled, knowing
that she had done something truly special. She had recovered a valuable
piece of history, and she had brought a thief to justice.

The museum's director approached Clara, shaking her hand and
congratulating her on a job well done. "You are a true hero, Clara," the
director said, smiling. "Your dedication and expertise have recovered a
priceless artifact, and we are forever grateful." Clara blushed, feeling
a sense of pride and humility. She had done what she loved, and she had
made a difference. The case of the stolen manuscript was closed, and
Clara had emerged victorious.

════════════════════════════════════════════════════════════

════════════════════════════════════════════════════════════
RUN SUMMARY
════════════════════════════════════════════════════════════
  Elapsed time  : 27.4 s
  Total events  : 24
  KG stats      : {'nodes': 137, 'edges': 202, 'edges_by_source': {'domain': 93, 'text': 109}}
  Token usage   : TokenUsage(input=3,690, output=7,470, cost=$0.00 [Groq free tier])

  Crime story events saved to : output/crime_story_events.json
  Solving story events saved to : output/solving_story_events.json
  Run summary saved to    : output/run_summary.json
  Prose saved to  : output/story_prose.txt
## Rambling Rhino Driver
This is main_system_script.py in the main directory.
