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

> 20 events (default)

> 5 reflection passes (default)

> Premise: "A small-town archivist discovers that a priceless 18th-century manuscript has been stolen from the local museum the night before its auction. She is the only one who knows what was truly hidden inside it."

════════════════════════════════════════════════════════════
  RAMBLING RHINO: Story Generation System
  Team Rambling Rhino | Reader-Model-Driven Generation
════════════════════════════════════════════════════════════
  Premise : A small-town archivist discovers that a priceless [...]
  Genre   : crime mystery
  Events  : 20 × 1 batch(es)
  Reflect : 2 pass(es)

════════════════════════════════════════════════════════════
PHASE 1: ENGAGEMENT
════════════════════════════════════════════════════════════

[Engagement batch 1/1]
  Generated 20 events (total: 20)

Engagement complete: 20 plot events.

Current event list:
  [E1] (SETUP) The archivist arrives at the museum and finds the display case shattered.
  [E2] (INCITING INCIDENT) Clara realizes the priceless manuscript is missing.
           caused_by: ['E1']
  [E3] (RISING ACTION) Clara remembers that she is the only one who knows the manuscript's true value and hidden contents.
           caused_by: ['E2']
  [E4] (RISING ACTION) Clara decides to investigate the theft without involving the police.
           caused_by: ['E3']
  [E5] (RISING ACTION) Clara reviews the museum's security footage and finds a suspicious figure.
           caused_by: ['E4']
  [E6] (RISING ACTION) The figure is partially obscured, but Clara notices a distinctive tattoo on their hand.        
           caused_by: ['E5']
  [E7] (RISING ACTION) Clara decides to ask the museum staff if they recognize the tattoo.
           caused_by: ['E6']
  [E8] (RISING ACTION) One of the staff members recognizes the tattoo as belonging to a local antique dealer.
           caused_by: ['E7']
  [E9] (MIDPOINT) Clara visits the antique dealer's shop and pretends to be a customer.
           caused_by: ['E8']
  [E10] (MIDPOINT) The antique dealer seems nervous and avoids eye contact with Clara.
           caused_by: ['E9']
  [E11] (MIDPOINT) Clara confronts the antique dealer, who denies any involvement in the theft.
           caused_by: ['E10']
  [E12] (MIDPOINT) Clara searches the antique dealer's shop and finds a hidden room.
           caused_by: ['E11']
  [E13] (MIDPOINT) Inside the room, Clara finds a cryptic message that hints at the manuscript's location.
           caused_by: ['E12']
  [E14] (MIDPOINT) Clara decodes the message and discovers that the manuscript is hidden in an old warehouse on the outskirts of town.
           caused_by: ['E13']
  [E15] (COMPLICATIONS) Clara goes to the warehouse and finds the manuscript, but it's booby-trapped.
           caused_by: ['E14']
  [E16] (COMPLICATIONS) Clara carefully disables the trap and retrieves the manuscript.
           caused_by: ['E15']
  [E17] (COMPLICATIONS) As Clara exits the warehouse, she's confronted by the antique dealer and his accomplices.     
           caused_by: ['E16']
  [E18] (COMPLICATIONS) Clara fights off the accomplices, but the antique dealer escapes with a valuable page from the manuscript.
           caused_by: ['E17']
  [E19] (CLIMAX) Clara reports the incident to the police and finally involves them in the investigation.
           caused_by: ['E18']
  [E20] (RESOLUTION) The police launch a manhunt for the antique dealer, and Clara finally feels that the case is nearing its resolution.
           caused_by: ['E19']

KnowledgeGraph: KnowledgeGraph(nodes=103, edges=164, by_source={'domain': 77, 'text': 87})

════════════════════════════════════════════════════════════
PHASE 2: REFLECTION
════════════════════════════════════════════════════════════

[Reflection pass 1/2]
  ComplexityChecker: all requirements satisfied — story is QUEST-coherent.

Reflection complete: 20 total events.

════════════════════════════════════════════════════════════
PHASE 3: PROSE GENERATION
════════════════════════════════════════════════════════════
  Generating story from 20 plot events...

════════════════════════════════════════════════════════════
GENERATED STORY
════════════════════════════════════════════════════════════

────────────────────────────────────────────────────────────
--- Plot Point 1: The archivist arrives at the museum and finds the display case shattered. ---
────────────────────────────────────────────────────────────
The archivist, Clara, pushed open the heavy wooden doors of the museum,
her eyes scanning the dimly lit hallway. She had worked at the museum
for over a decade, and the familiar scent of old books and dust was
comforting. As she made her way to the exhibit hall, she noticed a sense
of unease in the air. The security guards were huddled near the
entrance, their faces grave. Clara's heart sank as she approached the
display case that held the museum's most prized possession: a priceless
manuscript from the 14th century. The case was shattered, the glass
scattered across the floor like a thousand tiny diamonds.

The museum's director, Dr. Lee, rushed towards Clara, his face pale.
"Clara, we've been robbed," he exclaimed, his voice shaking. Clara's
eyes widened as she took in the scene. The display case had been broken,
and the manuscript was gone. She felt a wave of nausea wash over her.
The manuscript was more than just a valuable artifact; it was a piece of
history, a window into the past.

Clara's mind began to racing as she surveyed the damage. She knew that
the museum's security system was state-of-the-art, and it was unlikely
that the thief had simply smashed the case and grabbed the manuscript.
There had to be more to it. She knelt down to examine the broken glass,
her eyes searching for any clues. As she stood up, she noticed a small
piece of paper on the floor, partially hidden under the exhibit case. It
was a note, scribbled in haste: "You'll never find it."


────────────────────────────────────────────────────────────
--- Plot Point 2: Clara realizes the priceless manuscript is missing. ---
────────────────────────────────────────────────────────────
Clara's heart sank as she realized the true extent of the theft. The
manuscript was gone, and with it, a piece of history that could never be
replaced. She felt a wave of anger and frustration wash over her. Who
could have done this? And why? The manuscript was not only valuable but
also extremely rare. It was a treasure that belonged to the museum, and
now it was gone.

As she stood there, trying to process the situation, Clara's mind began
to racing with questions. Who could have pulled off such a daring heist?
And what did they plan to do with the manuscript? She knew that the
manuscript was not only valuable but also extremely fragile. It required
special care and handling, and she feared that it might be damaged or
even destroyed.

Clara's eyes scanned the room, searching for any clues. She noticed that
the security cameras had been disabled, and the alarm system had not
gone off. It was as if the thief had inside help or had somehow managed
to bypass the security system. She made a mental note to review the
security footage and interview the staff members.


────────────────────────────────────────────────────────────
--- Plot Point 3: Clara remembers that she is the only one who knows the manuscript's true value and hidden contents. ---
────────────────────────────────────────────────────────────
As Clara stood there, trying to make sense of the situation, she
remembered that she was the only one who knew the manuscript's true
value and hidden contents. The manuscript was not just a valuable
artifact; it was also a treasure trove of hidden knowledge and secrets.
Clara had spent years studying the manuscript, and she had discovered
that it contained hidden codes and messages that revealed a much larger
story.

Clara's mind began to racing with the implications. She knew that the
thief might not be aware of the manuscript's true value, and she feared
that they might try to sell it or destroy it. She also knew that she had
to keep the manuscript's secrets safe, not just for the museum's sake
but also for the sake of history. Clara made a mental note to keep her
knowledge of the manuscript's contents to herself, at least for the time
being.

As she stood there, lost in thought, Clara noticed that the museum's
staff was gathering around her. They were all talking and speculating
about the theft, but Clara remained silent. She knew that she had to
keep her knowledge to herself, at least until she had a better
understanding of the situation.


────────────────────────────────────────────────────────────
--- Plot Point 4: Clara decides to investigate the theft without involving the police. ---
────────────────────────────────────────────────────────────
Clara decided to investigate the theft without involving the police, at
least not yet. She knew that the police would have to be involved
eventually, but she wanted to do some digging on her own first. She had
a feeling that the thief might have left some clues behind, and she
wanted to follow them before the police got involved.

Clara began to review the security footage, looking for any signs of the
thief. She spent hours poring over the tapes, searching for any clues.
She also started to interview the staff members, asking them if they had
seen or heard anything suspicious. As she investigated, Clara began to
piece together a timeline of the theft. She discovered that the security
cameras had been disabled, and the alarm system had not gone off.

Clara's mind began to racing with theories and suspects. She knew that
the theft had been carefully planned, and she suspected that the thief
might have had inside help. She made a mental note to investigate the
staff members further, looking for any potential suspects.


────────────────────────────────────────────────────────────
--- Plot Point 5: Clara reviews the museum's security footage and finds a suspicious figure. ---
────────────────────────────────────────────────────────────
As Clara reviewed the security footage, she noticed a suspicious figure
lurking around the exhibit hall. The figure was partially obscured by a
pillar, but Clara could see that they were wearing a black hoodie and
gloves. She couldn't make out their face, but she noticed that they
seemed to be trying to avoid the cameras.

Clara's heart skipped a beat as she realized that she might have found a
lead. She rewound the tape and watched it again, this time paying closer
attention to the figure's movements. She noticed that they seemed to be
carrying a small bag, and they kept glancing over their shoulder as if
they were nervous.

Clara's eyes were glued to the screen as she watched the figure move
around the exhibit hall. She noticed that they seemed to be heading
towards the display case, and she felt a wave of excitement. She was
getting close to catching the thief.


────────────────────────────────────────────────────────────
--- Plot Point 6: The figure is partially obscured, but Clara notices a distinctive tattoo on their hand. ---
────────────────────────────────────────────────────────────
As Clara continued to watch the footage, she noticed that the figure's
hand was visible for a brief moment. She saw a distinctive tattoo on
their hand, a snake coiled around their wrist. Clara's eyes widened as
she realized that the tattoo might be a crucial clue. She made a mental
note to look for anyone with a similar tattoo.

Clara's mind began to racing with possibilities. She wondered if the
tattoo might be a signature or a symbol of some kind. She also wondered
if the thief might be part of a larger organization or gang. The tattoo
seemed to be a deliberate attempt to leave a mark, and Clara was
determined to follow the trail.

As she continued to watch the footage, Clara noticed that the figure
seemed to be moving with a sense of confidence. They didn't seem to be
in a hurry, and they didn't seem to be worried about being caught.
Clara's instincts told her that the thief might be someone who was
familiar with the museum, someone who knew the layout and the security
system.


────────────────────────────────────────────────────────────
--- Plot Point 7: Clara decides to ask the museum staff if they recognize the tattoo. ---
────────────────────────────────────────────────────────────
Clara decided to ask the museum staff if they recognized the tattoo. She
showed them the footage and asked if anyone had seen the tattoo before.
The staff members gathered around her, watching the footage and shaking
their heads. None of them recognized the tattoo, but one of the staff
members mentioned that they had seen a similar tattoo on a local antique
dealer.

Clara's ears perked up as she heard the staff member's comment. She
asked them to describe the antique dealer and the tattoo in more detail.
The staff member told her that the antique dealer was a tall, thin man
with a scruffy beard and a snake tattoo on his hand. Clara's eyes
widened as she realized that the description matched the figure in the
footage.

Clara's mind began to racing with possibilities. She wondered if the
antique dealer might be the thief, or if they might be involved in some
way. She made a mental note to visit the antique dealer's shop and ask
them some questions.


────────────────────────────────────────────────────────────
--- Plot Point 8: One of the staff members recognizes the tattoo as belonging to a local antique dealer. ---
────────────────────────────────────────────────────────────
One of the staff members, a quiet and reserved woman named Sarah, spoke
up. "I think I've seen that tattoo before," she said, her voice barely
above a whisper. "It belongs to a local antique dealer. I've seen him
around town, and I've noticed that he has a snake tattoo on his hand."

Clara's eyes locked onto Sarah's face, her attention riveted. "Do you
know the antique dealer's name?" she asked, her voice gentle but urgent.
Sarah nodded, her eyes cast downward. "I think his name is Marcus. He
owns an antique shop on Main Street."

Clara's mind began to racing with possibilities. She wondered if Marcus
might be the thief, or if he might be involved in some way. She made a
mental note to visit Marcus's shop and ask him some questions.


────────────────────────────────────────────────────────────
--- Plot Point 9: Clara visits the antique dealer's shop and pretends to be a customer. ---
────────────────────────────────────────────────────────────
Clara visited the antique dealer's shop, pretending to be a customer.
She browsed the shelves, looking for any signs of the manuscript or any
clues that might lead her to the thief. The shop was dimly lit, and the
air was thick with the scent of old books and dust. Clara's eyes
adjusted slowly to the light, and she began to take in the surroundings.

As she browsed the shelves, Clara noticed that the shop was filled with
a wide range of artifacts, from ancient coins to rare books. She saw a
few items that caught her eye, and she asked the antique dealer about
them. The antique dealer, Marcus, seemed nervous and fidgety, avoiding
eye contact with Clara.

Clara's instincts told her that Marcus might be hiding something. She
continued to browse the shelves, looking for any signs of the manuscript
or any clues that might lead her to the thief.


────────────────────────────────────────────────────────────
--- Plot Point 10: The antique dealer seems nervous and avoids eye contact with Clara. ---
────────────────────────────────────────────────────────────
As Clara browsed the shelves, she noticed that Marcus seemed nervous and
avoidant. He wouldn't meet her eye, and he fidgeted with his hands as he
spoke. Clara's instincts told her that Marcus might be hiding something,
and she made a mental note to press him for more information.

Clara approached Marcus, a friendly smile on her face. "Excuse me," she
said, her voice gentle. "I'm looking for a rare book. Do you have
anything that might interest me?" Marcus hesitated, his eyes darting
back and forth. "Uh, yeah. I think I might have something. Let me
check."

As Marcus rummaged through the shelves, Clara noticed that he seemed to
be stalling. She wondered if he might be trying to hide something, and
she made a mental note to investigate further.


────────────────────────────────────────────────────────────
--- Plot Point 11: Clara confronts the antique dealer, who denies any involvement in the theft. ---
────────────────────────────────────────────────────────────
Clara confronted Marcus, her eyes locked onto his face. "I think you
know why I'm here," she said, her voice firm but gentle. "I'm looking
for a stolen manuscript. Do you know anything about it?" Marcus's eyes
widened, and he shook his head. "No, I don't know anything about a
stolen manuscript."

Clara's instincts told her that Marcus might be lying. She pressed him
for more information, her voice firm but controlled. "I think you do
know something, Marcus. I think you might be involved in the theft."
Marcus's face went white, and he took a step back. "I don't know what
you're talking about," he said, his voice shaking.

Clara's eyes narrowed as she watched Marcus's reaction. She knew that he
might be hiding something, and she made a mental note to investigate
further.


────────────────────────────────────────────────────────────
--- Plot Point 12: Clara searches the antique dealer's shop and finds a hidden room. ---
────────────────────────────────────────────────────────────
Clara searched the antique dealer's shop, looking for any signs of the
manuscript or any clues that might lead her to the thief. As she browsed
the shelves, she noticed that one of the bookcases seemed to be slightly
ajar. She pushed it open, and a hidden room was revealed.

The room was small and dimly lit, with a single chair and a small table
in the center. Clara's eyes adjusted slowly to the light, and she began
to take in the surroundings. She noticed that the room was filled with a
variety of artifacts, from ancient coins to rare books. She saw a few
items that caught her eye, and she began to examine them more closely.

As she searched the room, Clara found a small piece of paper with a
cryptic message. The message read: "Look to the past for the key to the
future." Clara's mind began to racing with possibilities. She wondered
what the message might mean, and she made a mental note to investigate
further.


────────────────────────────────────────────────────────────
--- Plot Point 13: Inside the room, Clara finds a cryptic message that hints at the manuscript's location. ---        
────────────────────────────────────────────────────────────
As Clara examined the message, she realized that it might be a clue to
the manuscript's location. She wondered if the message might be a
riddle, and she began to think about possible solutions. The message
read: "Look to the past for the key to the future." Clara's mind began
to racing with possibilities.

She thought about the manuscript's history, and the various owners it
had had over the years. She wondered if one of the owners might have
left a clue or a hidden message that would lead her to the manuscript.
As she thought about the message, Clara began to piece together a
theory. She realized that the message might be pointing to an old
warehouse on the outskirts of town.

Clara's eyes lit up with excitement as she realized the possibility. She
made a mental note to investigate the warehouse and see if she could
find any signs of the manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 14: Clara decodes the message and discovers that the manuscript is hidden in an old warehouse on the outskirts of town. ---
────────────────────────────────────────────────────────────
Clara decoded the message, and she discovered that the manuscript was
hidden in an old warehouse on the outskirts of town. She felt a wave of
excitement and relief wash over her. She had been searching for the
manuscript for days, and she had finally found a lead.

As she made her way to the warehouse, Clara's mind began to racing with
possibilities. She wondered what she would find at the warehouse, and
she wondered if she would finally recover the stolen manuscript. She
arrived at the warehouse, and she saw that it was an old, abandoned
building with a faded sign that read "Warehouse 12".

Clara's heart skipped a beat as she approached the warehouse. She
wondered if she would find the manuscript inside, and she wondered if
she would be able to recover it safely.


────────────────────────────────────────────────────────────
--- Plot Point 15: Clara goes to the warehouse and finds the manuscript, but it's booby-trapped. ---
────────────────────────────────────────────────────────────
Clara went to the warehouse and found the manuscript, but it was booby-
trapped. She saw that the manuscript was sitting on a pedestal in the
center of the room, surrounded by wires and alarms. Clara's eyes widened
as she realized the danger. She knew that she had to be careful, or she
might trigger the trap.

Clara's mind began to racing with possibilities. She wondered how she
could disable the trap and recover the manuscript safely. She examined
the wires and alarms, looking for any clues. As she worked, Clara's
hands moved slowly and carefully, her eyes fixed on the manuscript.

After a few tense moments, Clara finally disabled the trap and recovered
the manuscript. She felt a wave of relief wash over her, and she knew
that she had finally solved the case.


────────────────────────────────────────────────────────────
--- Plot Point 16: Clara carefully disables the trap and retrieves the manuscript. ---
────────────────────────────────────────────────────────────
Clara carefully disabled the trap and retrieved the manuscript. She held
it in her hands, feeling a sense of pride and accomplishment. She had
solved the case, and she had recovered the stolen manuscript.

As she held the manuscript, Clara noticed that it was slightly damaged.
The pages were torn, and the cover was scratched. But despite the
damage, the manuscript was still intact, and Clara knew that it was
still valuable.

Clara's mind began to racing with possibilities. She wondered what she
would do next, and she wondered how she would return the manuscript to
the museum. As she stood there, thinking about her next move, Clara
heard a noise behind her.


────────────────────────────────────────────────────────────
--- Plot Point 17: As Clara exits the warehouse, she's confronted by the antique dealer and his accomplices. ---      
────────────────────────────────────────────────────────────
As Clara exited the warehouse, she was confronted by the antique dealer
and his accomplices. They were standing in the doorway, blocking her
path. Clara's eyes widened as she realized the danger. She knew that she
had to be careful, or she might be hurt.

The antique dealer, Marcus, sneered at Clara. "You're a clever girl," he
said, his voice dripping with malice. "But you're not clever enough.
You'll never leave this place alive." Clara's heart skipped a beat as
she realized the threat. She knew that she had to act fast, or she might
be in grave danger.

Clara's eyes scanned the area, looking for any escape routes. She saw a
small window on the side of the warehouse, and she knew that she might
be able to escape through it. But as she turned to make a run for the
window, Clara was confronted by Marcus's accomplices.


────────────────────────────────────────────────────────────
--- Plot Point 18: Clara fights off the accomplices, but the antique dealer escapes with a valuable page from the manuscript. ---
────────────────────────────────────────────────────────────
Clara fought off the accomplices, using all her strength and cunning to
defend herself. But despite her best efforts, the antique dealer escaped
with a valuable page from the manuscript. Clara's heart sank as she
realized the loss. She had recovered the manuscript, but she had lost a
valuable page.

As Clara stood there, panting and exhausted, she realized that she had
to report the incident to the police. She knew that she couldn't handle
the situation alone, and she needed the police's help to catch the
antique dealer and recover the stolen page.

Clara's mind began to racing with possibilities. She wondered what she
would do next, and she wondered how she would catch the antique dealer.
As she stood there, thinking about her next move, Clara heard the sound
of sirens in the distance.


────────────────────────────────────────────────────────────
--- Plot Point 19: Clara reports the incident to the police and finally involves them in the investigation. ---       
────────────────────────────────────────────────────────────
Clara reported the incident to the police and finally involved them in
the investigation. She told them everything, from the theft of the
manuscript to the confrontation with the antique dealer. The police
listened intently, their faces grave with concern.

As Clara finished her story, the police officer in charge nodded. "We'll
do everything we can to catch the antique dealer and recover the stolen
page," he said, his voice firm and reassuring. Clara felt a wave of
relief wash over her. She knew that she had finally done the right
thing, and she knew that the police would help her solve the case.

The police began to investigate, following up on leads and gathering
evidence. Clara worked closely with them, providing any information she
could. As the investigation continued, Clara felt a sense of hope and
optimism. She knew that she would finally see justice, and she knew that
the manuscript would be safe.


────────────────────────────────────────────────────────────
--- Plot Point 20: The police launch a manhunt for the antique dealer, and Clara finally feels that the case is nearing its resolution. ---
────────────────────────────────────────────────────────────
The police launched a manhunt for the antique dealer, and Clara finally
felt that the case was nearing its resolution. She had worked tirelessly
with the police, providing any information she could, and she knew that
they were getting close to catching the culprit. As she watched the
police cars speed away, sirens blaring, Clara felt a sense of
satisfaction and relief. She had solved the case, and she had recovered
the stolen manuscript.

The police finally apprehended the antique dealer, and he was charged
with theft and conspiracy. Clara attended the trial, watching as the
antique dealer was sentenced to prison. She felt a sense of closure and
justice, knowing that the thief had been brought to justice. The
manuscript was safely back in the museum, and Clara's reputation as a
skilled archivist had been cemented. She had proven herself to be
resourceful and determined, and she knew that she would always be ready
for whatever challenges came her way. With the case finally closed,
Clara smiled, feeling a sense of pride and accomplishment. She had
solved the mystery, and she had brought the perpetrator to justice.

════════════════════════════════════════════════════════════

════════════════════════════════════════════════════════════
RUN SUMMARY
════════════════════════════════════════════════════════════
  Elapsed time  : 18.0 s
  Total events  : 20
  KG stats      : {'nodes': 103, 'edges': 164, 'edges_by_source': {'domain': 77, 'text': 87}}
  Token usage   : TokenUsage(input=1,291, output=5,792, cost=$0.00 [Groq free tier])

## Rambling Rhino Driver
This is main_system_script.py in the main directory.
