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
  [E3] (RISING ACTION) Clara informs the museum director about the theft.
           caused_by: ['E2']
  [E4] (RISING ACTION) The police are called to the museum to investigate the crime scene.
           caused_by: ['E3']
  [E5] (RISING ACTION) Clara remembers that she was the last person to handle the manuscript the previous day.        
           caused_by: ['E4']
  [E6] (RISING ACTION) Clara reveals to the police that the manuscript had hidden notes and codes.
           caused_by: ['E5']
  [E7] (RISING ACTION) The police officer asks Clara to explain the significance of the hidden notes.
           caused_by: ['E6']
  [E8] (RISING ACTION) Clara hesitates to share the full extent of her knowledge about the manuscript.
           caused_by: ['E7']
  [E9] (MIDPOINT) The police officer suspects that Clara might be hiding something.
           caused_by: ['E8']
  [E10] (MIDPOINT) Clara decides to search the museum's archives for any clues about the theft.
           caused_by: ['E9']
  [E11] (MIDPOINT) Clara discovers a cryptic message in an old museum logbook.
           caused_by: ['E10']
  [E12] (MIDPOINT) The cryptic message leads Clara to a hidden room in the museum's basement.
           caused_by: ['E11']
  [E13] (MIDPOINT) In the hidden room, Clara finds a set of old letters and documents related to the manuscript.      
           caused_by: ['E12']
  [E14] (MIDPOINT) The documents reveal a centuries-old conspiracy surrounding the manuscript.
           caused_by: ['E13']
  [E15] (COMPLICATIONS) Clara realizes that she is in danger due to her knowledge about the manuscript.
           caused_by: ['E14']
  [E16] (COMPLICATIONS) Clara decides to confide in the museum director about her findings.
           caused_by: ['E15']
  [E17] (COMPLICATIONS) The museum director reveals that he has been receiving threatening messages about the manuscript.
           caused_by: ['E16']
  [E18] (COMPLICATIONS) Clara and the museum director agree to work together to uncover the truth.
           caused_by: ['E17']
  [E19] (CLIMAX) The police officer returns to the museum with a surprising lead about the thief's identity.
           caused_by: ['E18']
  [E20] (RESOLUTION) Clara, the museum director, and the police officer devise a plan to catch the thief and recover the manuscript.
           caused_by: ['E19']

KnowledgeGraph: KnowledgeGraph(nodes=119, edges=179, by_source={'domain': 70, 'text': 109})

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
The morning sunlight streaming through the museum's grand entrance
highlighted the shattered remains of the display case. Emma, the
archivist, stood frozen, her eyes fixed on the devastation before her.
She had been the first to arrive at the museum that day, and the eerie
silence was only broken by the sound of her own ragged breathing. The
display case had been a sturdy, state-of-the-art model, designed to
protect the priceless artifacts within. Now, it lay in pieces, its
fragments scattered across the floor like a puzzle waiting to be solved.
Emma's mind racing, she wondered what could have caused such
destruction.

As she approached the display case, Emma noticed that the area around it
was undisturbed, with no signs of forced entry or struggle. It was as if
the perpetrator had been someone with access to the museum, someone who
had carefully planned and executed the theft. Emma's thoughts turned to
the manuscript that had been on display, a rare and valuable historical
document. She knew that the manuscript was not only a significant
artifact but also a treasure that could be worth a fortune on the black
market.

The museum's security team was already on its way to assess the
situation, but Emma couldn't shake off the feeling that something was
off. She decided to inform the museum staff and start an investigation
into the theft. Emma's first priority was to secure the area and prevent
any further damage. She carefully made her way around the broken glass
and debris, taking note of any potential clues that might have been left
behind.

As she waited for the security team to arrive, Emma couldn't help but
think about the potential consequences of the theft. The manuscript was
not only a valuable artifact but also a significant part of the museum's
collection. Its loss would be felt by the entire museum community, and
Emma felt a sense of responsibility to ensure that it was recovered.


────────────────────────────────────────────────────────────
--- Plot Point 2: Clara realizes the priceless manuscript is missing. ---
────────────────────────────────────────────────────────────
Clara, the museum's curator, was the first to arrive at the scene,
followed closely by the security team. Emma briefed her on the
situation, and Clara's eyes widened as she took in the extent of the
damage. She rushed to the display case, her heart sinking as she
realized that the manuscript was indeed missing. The manuscript, a rare
and historic document, was one of the museum's most prized possessions.
Clara felt a wave of panic wash over her as she thought about the
implications of the theft.

Clara's mind racing, she began to think about the last time she had seen
the manuscript. She had been working late the previous day, preparing
for an upcoming exhibit, and had stopped by the display case to make
sure everything was in order. The manuscript had been there, safely
nestled in its case, and Clara had locked the display case herself
before leaving for the day. She was certain that she had followed the
standard security protocols, but now the manuscript was gone.

As the security team began to assess the situation, Clara couldn't help
but think about the potential suspects. She knew that the museum had a
number of employees and volunteers who had access to the display case,
but she couldn't imagine any of them being capable of such a crime.
Clara decided to inform the museum director about the theft and start an
investigation into the disappearance of the manuscript.

The museum's security team was well-equipped to handle the situation,
but Clara knew that they would need to involve the police to ensure that
the manuscript was recovered. She made a mental note to contact the
police department and report the theft as soon as possible. Clara's
primary concern was the safe return of the manuscript, and she was
willing to do whatever it took to make that happen.


────────────────────────────────────────────────────────────
--- Plot Point 3: Clara informs the museum director about the theft. ---
────────────────────────────────────────────────────────────
Clara quickly made her way to the museum director's office, her heart
heavy with the news. She found the director, Mr. Jenkins, sitting at his
desk, sipping a cup of coffee. Clara took a deep breath and broke the
news, trying to remain calm and composed. Mr. Jenkins's expression
changed from calm to shocked as Clara explained the situation. He
listened intently, his eyes widening as he realized the significance of
the theft.

Mr. Jenkins immediately sprang into action, calling the museum's
security team to assemble an emergency meeting. He instructed Clara to
inform the police about the theft and to request their assistance in
recovering the manuscript. Clara nodded, relieved that the director was
taking the situation seriously. As she left the director's office, Clara
couldn't help but feel a sense of unease. The theft of the manuscript
was not only a crime but also a personal betrayal.

The museum's staff was in an uproar, with everyone trying to make sense
of the situation. Clara knew that she had to remain focused and work
with the police to recover the manuscript. She decided to start by
reviewing the museum's security footage and interviewing the staff
members who had been on duty the previous day. Clara was determined to
get to the bottom of the theft and to bring the perpetrator to justice.

As the investigation began, Clara couldn't help but think about the
potential consequences of the theft. The manuscript was not only a
valuable artifact but also a significant part of the museum's
collection. Its loss would be felt by the entire museum community, and
Clara felt a sense of responsibility to ensure that it was recovered.
She was determined to work tirelessly to solve the case and to bring the
manuscript back to its rightful home.


────────────────────────────────────────────────────────────
--- Plot Point 4: The police are called to the museum to investigate the crime scene. ---
────────────────────────────────────────────────────────────
The police arrived at the museum, and Clara met with the lead
investigator, Detective James. She explained the situation, and
Detective James listened intently, taking notes and asking questions.
The detective was a seasoned professional, with years of experience in
solving crimes. Clara felt a sense of relief knowing that the police
were involved and that they would do everything in their power to
recover the manuscript.

Detective James began by surveying the crime scene, taking in the
details of the shattered display case and the surrounding area. He asked
Clara and the museum staff questions about the security protocols and
the last time the manuscript had been seen. As the investigation
continued, Clara couldn't help but feel a sense of unease. The theft of
the manuscript was not only a crime but also a personal betrayal.

The police team worked efficiently, collecting evidence and interviewing
witnesses. Clara watched as they carefully examined the display case and
the surrounding area, looking for any clues that might have been left
behind. She knew that the police had a difficult task ahead of them, but
she was confident that they would do everything in their power to solve
the case.

As the investigation continued, Clara decided to start by reviewing the
museum's security footage and interviewing the staff members who had
been on duty the previous day. She worked closely with Detective James,
providing him with any information that might be relevant to the case.
Clara was determined to get to the bottom of the theft and to bring the
perpetrator to justice.


────────────────────────────────────────────────────────────
--- Plot Point 5: Clara remembers that she was the last person to handle the manuscript the previous day. ---
────────────────────────────────────────────────────────────
As Clara worked with Detective James, she suddenly remembered that she
had been the last person to handle the manuscript the previous day. She
had been working late, preparing for an upcoming exhibit, and had
stopped by the display case to make sure everything was in order. Clara
felt a wave of panic wash over her as she realized that she might have
been the last person to see the manuscript before it was stolen.

Clara's mind racing, she tried to remember every detail of her actions
the previous day. She had locked the display case herself, but she
couldn't shake off the feeling that she might have forgotten something.
Detective James noticed Clara's distress and asked her to explain. Clara
took a deep breath and recounted her actions, trying to remember every
detail.

As Clara spoke, Detective James listened intently, his eyes narrowing as
he considered the information. He asked Clara to walk him through her
actions, step by step, and Clara complied, trying to remember every
detail. The detective's questions were thorough, and Clara felt a sense
of relief knowing that he was taking her statement seriously.

Clara's recollection of the previous day's events was crucial to the
investigation. She knew that she had to be careful and accurate, as any
mistake could compromise the case. Detective James's questions were
designed to clarify the events surrounding the theft, and Clara did her
best to provide him with the information he needed.


────────────────────────────────────────────────────────────
--- Plot Point 6: Clara reveals to the police that the manuscript had hidden notes and codes. ---
────────────────────────────────────────────────────────────
As Clara continued to work with Detective James, she revealed that the
manuscript had hidden notes and codes. The manuscript was a rare and
historic document, and Clara had spent countless hours studying it. She
had discovered that the manuscript contained hidden messages and codes,
which were not immediately apparent to the casual observer.

Detective James's eyes lit up with interest as Clara explained the
significance of the hidden notes and codes. He asked her to elaborate,
and Clara spent the next hour explaining the intricate details of the
manuscript. The detective listened intently, his mind racing with the
implications of the hidden messages.

The hidden notes and codes were a significant aspect of the manuscript,
and Clara knew that they could hold the key to solving the case. She
explained that the codes were complex and required a deep understanding
of the manuscript's context. Detective James was fascinated by the
complexity of the codes and asked Clara to provide him with more
information.

As Clara delved deeper into the world of the manuscript, she began to
realize the significance of the hidden notes and codes. The codes were
not only a product of the manuscript's creator but also a window into
the past. Clara's knowledge of the manuscript and its secrets was
crucial to the investigation, and she was determined to use her
expertise to help solve the case.


────────────────────────────────────────────────────────────
--- Plot Point 7: The police officer asks Clara to explain the significance of the hidden notes. ---
────────────────────────────────────────────────────────────
Detective James asked Clara to explain the significance of the hidden
notes and codes. Clara took a deep breath and began to explain the
context of the manuscript and the significance of the codes. She told
Detective James that the manuscript was a rare and historic document,
written by a prominent historian in the 16th century. The historian had
included the hidden notes and codes as a way of conveying secret
information to his contemporaries.

The codes, Clara explained, were a complex system of symbols and ciphers
that required a deep understanding of the manuscript's context. She had
spent countless hours studying the manuscript and had begun to decipher
the codes. Clara's explanation was detailed and thorough, and Detective
James listened intently, his eyes narrowing as he considered the
information.

As Clara spoke, Detective James asked questions, seeking to clarify the
significance of the hidden notes and codes. He was fascinated by the
complexity of the codes and the secrets they held. Clara's knowledge of
the manuscript and its secrets was impressive, and Detective James was
grateful for her expertise.

The conversation between Clara and Detective James was intense and
focused. They were both determined to solve the case, and they knew that
the hidden notes and codes held the key. As they worked together, Clara
felt a sense of relief knowing that she was not alone in her quest to
recover the manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 8: Clara hesitates to share the full extent of her knowledge about the manuscript. ---
────────────────────────────────────────────────────────────
As Clara continued to explain the significance of the hidden notes and
codes, she hesitated to share the full extent of her knowledge. She had
spent years studying the manuscript, and she had uncovered some secrets
that she was not sure she was ready to share. Detective James noticed
Clara's hesitation and asked her to explain.

Clara took a deep breath and explained that she had discovered some
information that could be sensitive. She was not sure if she was ready
to share it with Detective James, and she asked him to assure her that
the information would be kept confidential. Detective James nodded, his
expression serious, and Clara began to explain.

The information Clara shared was significant, and Detective James
listened intently. He asked questions, seeking to clarify the details,
and Clara provided him with the information he needed. As they worked
together, Clara felt a sense of trust growing between them. She knew
that she could rely on Detective James to keep her confidence.

Clara's hesitation to share her knowledge was understandable. She had
spent years studying the manuscript, and she had uncovered secrets that
were not meant to be shared. However, she knew that she had to trust
Detective James if she wanted to recover the manuscript. She took a deep
breath and shared her knowledge, hoping that it would lead to a
breakthrough in the case.


────────────────────────────────────────────────────────────
--- Plot Point 9: The police officer suspects that Clara might be hiding something. ---
────────────────────────────────────────────────────────────
As Clara finished explaining the significance of the hidden notes and
codes, Detective James looked at her with a piercing gaze. He suspected
that Clara might be hiding something, and he asked her to assure him
that she was telling him everything. Clara felt a wave of unease wash
over her as she realized that Detective James did not entirely trust
her.

Detective James's suspicions were understandable. Clara had hesitated to
share her knowledge, and he had noticed that she seemed to be holding
back. He asked her to explain, and Clara took a deep breath, trying to
reassure him. She told him that she was committed to recovering the
manuscript and that she would do everything in her power to help him
solve the case.

The conversation between Clara and Detective James was tense, with an
undercurrent of suspicion. Clara knew that she had to be careful and
transparent if she wanted to regain Detective James's trust. She took a
deep breath and explained that she had been studying the manuscript for
years and that she had uncovered some secrets that she was not sure she
was ready to share.

As they worked together, Clara felt a sense of unease growing between
them. She knew that she had to be careful and transparent if she wanted
to recover the manuscript. Detective James's suspicions were a reminder
that she had to be vigilant and that she could not afford to make any
mistakes.


────────────────────────────────────────────────────────────
--- Plot Point 10: Clara decides to search the museum's archives for any clues about the theft. ---
────────────────────────────────────────────────────────────
Clara decided to search the museum's archives for any clues about the
theft. She knew that the archives were a treasure trove of information,
and she hoped to find something that would lead her to the manuscript.
Detective James agreed, and together they began to search the archives,
looking for any documents or records that might be relevant to the case.

The archives were a vast repository of information, with documents and
records dating back centuries. Clara and Detective James worked
tirelessly, searching through the shelves and boxes, looking for any
clues that might have been left behind. As they worked, Clara explained
the significance of the documents and records, providing Detective James
with context and insight.

The search was painstaking, but Clara was determined to find something.
She knew that the archives held the key to solving the case, and she was
willing to do whatever it took to recover the manuscript. As they
worked, Clara felt a sense of excitement growing. She was getting closer
to solving the case, and she knew that she was on the right track.

The archives were a labyrinth of information, with twists and turns that
led to unexpected discoveries. Clara and Detective James worked
together, following the trail of clues, and slowly but surely, they
began to piece together the puzzle of the theft. Clara's knowledge of
the archives and her expertise in the manuscript were invaluable, and
Detective James relied on her to guide him through the complex web of
information.


────────────────────────────────────────────────────────────
--- Plot Point 11: Clara discovers a cryptic message in an old museum logbook. ---
────────────────────────────────────────────────────────────
As Clara and Detective James searched the archives, Clara stumbled upon
an old museum logbook. She opened it, and as she flipped through the
pages, she noticed a cryptic message scrawled in the margin. The message
was dated several decades ago, and it read: "The truth lies in the
shadows." Clara felt a shiver run down her spine as she realized that
the message might be relevant to the case.

Clara showed the message to Detective James, and he raised an eyebrow.
He asked her to explain the context of the message, and Clara told him
that the logbook belonged to a former museum curator. The curator had
been known for his eccentricities, and Clara suspected that he might
have left behind a trail of clues.

The message was cryptic, but Clara was determined to decipher its
meaning. She spent the next hour poring over the logbook, looking for
any other clues that might be hidden within its pages. As she worked,
Detective James watched her, his eyes narrowed in concentration. He knew
that Clara was close to something, and he was willing to follow her
lead.

The logbook was a treasure trove of information, with notes and
observations that provided a glimpse into the past. Clara's discovery of
the cryptic message was a breakthrough, and she knew that she was on the
right track. She felt a sense of excitement growing, and she was
determined to follow the trail of clues to its conclusion.


────────────────────────────────────────────────────────────
--- Plot Point 12: The cryptic message leads Clara to a hidden room in the museum's basement. ---
────────────────────────────────────────────────────────────
The cryptic message led Clara to a hidden room in the museum's basement.
She and Detective James made their way to the basement, following the
trail of clues that Clara had uncovered. As they descended the stairs,
Clara felt a sense of excitement growing. She knew that she was getting
close to solving the case, and she was determined to see it through.

The hidden room was a small, cramped space that was hidden behind a
false wall. Clara had never known that it existed, and she felt a sense
of wonder as she stepped inside. The room was filled with old artifacts
and documents, and Clara's eyes widened as she took in the treasure
trove of information.

Detective James watched her, his eyes narrowed in concentration. He knew
that Clara was close to something, and he was willing to follow her
lead. As they searched the room, Clara stumbled upon a series of old
letters and documents that seemed to be connected to the manuscript. She
felt a sense of excitement growing, and she knew that she was on the
right track.

The hidden room was a revelation, and Clara felt a sense of awe as she
explored its secrets. She knew that she had uncovered something
significant, and she was determined to follow the trail of clues to its
conclusion. As she worked, Detective James watched her, his eyes
narrowed in concentration. He knew that Clara was close to solving the
case, and he was willing to follow her lead.


────────────────────────────────────────────────────────────
--- Plot Point 13: In the hidden room, Clara finds a set of old letters and documents related to the manuscript. ---  
────────────────────────────────────────────────────────────
In the hidden room, Clara found a set of old letters and documents
related to the manuscript. She spent hours poring over the letters,
reading about the manuscript's history and the people who had handled it
over the years. The letters were a treasure trove of information, and
Clara felt a sense of excitement growing as she delved deeper into the
documents.

As she read, Clara discovered that the manuscript had been the subject
of a centuries-old conspiracy. The letters revealed a web of secrets and
lies that had surrounded the manuscript, and Clara's eyes widened as she
realized the significance of her discovery. She felt a sense of awe as
she realized that she had uncovered a piece of history that had been
hidden for centuries.

The documents were a window into the past, and Clara felt a sense of
wonder as she explored the secrets that they held. She spent hours
reading and studying the documents, and as she did, she began to piece
together the puzzle of the manuscript's history. Detective James watched
her, his eyes narrowed in concentration, as Clara worked to unravel the
mystery of the manuscript.

The letters and documents were a significant discovery, and Clara knew
that she had to share them with Detective James. She felt a sense of
excitement growing as she realized that she was getting close to solving
the case. She was determined to follow the trail of clues to its
conclusion, and she was willing to do whatever it took to recover the
manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 14: The documents reveal a centuries-old conspiracy surrounding the manuscript. ---
────────────────────────────────────────────────────────────
The documents revealed a centuries-old conspiracy surrounding the
manuscript. Clara's eyes widened as she realized the significance of her
discovery. The conspiracy had involved some of the most powerful people
in history, and Clara felt a sense of awe as she realized that she had
uncovered a piece of history that had been hidden for centuries.

The documents told a story of secrets and lies, of people who had been
willing to do whatever it took to possess the manuscript. Clara felt a
sense of wonder as she explored the secrets that the documents held. She
spent hours reading and studying the documents, and as she did, she
began to piece together the puzzle of the manuscript's history.

As Clara delved deeper into the documents, she realized that the
conspiracy was still alive and well. She felt a sense of unease growing
as she realized that she had stumbled into something much bigger than
she had ever imagined. Detective James watched her, his eyes narrowed in
concentration, as Clara worked to unravel the mystery of the manuscript.

The conspiracy was a complex web of secrets and lies, and Clara knew
that she had to be careful. She felt a sense of danger growing, and she
knew that she had to be vigilant. She was determined to follow the trail
of clues to its conclusion, and she was willing to do whatever it took
to recover the manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 15: Clara realizes that she is in danger due to her knowledge about the manuscript. ---
────────────────────────────────────────────────────────────
Clara realized that she was in danger due to her knowledge about the
manuscript. She felt a sense of unease growing as she realized that she
had stumbled into something much bigger than she had ever imagined. The
conspiracy was still alive and well, and Clara knew that she had to be
careful.

As she delved deeper into the documents, Clara began to realize the
significance of her discovery. She had uncovered a piece of history that
had been hidden for centuries, and she knew that there were people who
would stop at nothing to keep it that way. Clara felt a sense of fear
growing, and she knew that she had to be vigilant.

Detective James watched her, his eyes narrowed in concentration, as
Clara worked to unravel the mystery of the manuscript. He knew that
Clara was in danger, and he was determined to protect her. Together,
they began to work on a plan to keep Clara safe and to recover the
manuscript.

The danger was real, and Clara knew that she had to be careful. She felt
a sense of unease growing, and she knew that she had to trust Detective
James to keep her safe. Clara was determined to follow the trail of
clues to its conclusion, and she was willing to do whatever it took to
recover the manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 16: Clara decides to confide in the museum director about her findings. ---
────────────────────────────────────────────────────────────
Clara decided to confide in the museum director about her findings. She
knew that she had to trust someone, and the museum director was the
obvious choice. Clara made her way to the director's office, her heart
pounding in her chest. She took a deep breath and explained everything,
from the cryptic message to the centuries-old conspiracy.

The museum director listened, his eyes widening in surprise. He asked
Clara to explain, and she told him about the documents she had found and
the secrets they held. The director's expression changed from surprise
to concern, and Clara knew that he understood the significance of her
discovery.

The museum director was a man of integrity, and Clara knew that she
could trust him. He listened intently, his eyes narrowed in
concentration, as Clara explained the danger she was in. He promised to
do everything in his power to keep her safe and to help her recover the
manuscript.

As Clara left the director's office, she felt a sense of relief growing.
She knew that she had made the right decision in confiding in the
director. Together, they would work to unravel the mystery of the
manuscript and to bring the perpetrator to justice.


────────────────────────────────────────────────────────────
--- Plot Point 17: The museum director reveals that he has been receiving threatening messages about the manuscript. ---
────────────────────────────────────────────────────────────
The museum director revealed that he had been receiving threatening
messages about the manuscript. Clara's eyes widened in surprise as she
realized that the director had been keeping secrets of his own. The
director explained that he had been receiving messages, warning him to
keep quiet about the manuscript and its secrets.

Clara felt a sense of fear growing as she realized that the conspiracy
was more extensive than she had ever imagined. The director's revelation
added a new layer of complexity to the case, and Clara knew that she had
to be careful. She was determined to follow the trail of clues to its
conclusion, and she was willing to do whatever it took to recover the
manuscript.

The museum director's revelation was a significant development, and
Clara knew that she had to take it seriously. She felt a sense of unease
growing, and she knew that she had to trust the director to keep her
safe. Together, they would work to unravel the mystery of the manuscript
and to bring the perpetrator to justice.

As Clara and the director worked together, they began to piece together
the puzzle of the conspiracy. They knew that they had to be careful, but
they were determined to see justice served. Clara was willing to do
whatever it took to recover the manuscript, and she was grateful to have
the director's support.


────────────────────────────────────────────────────────────
--- Plot Point 18: Clara and the museum director agree to work together to uncover the truth. ---
────────────────────────────────────────────────────────────
Clara and the museum director agreed to work together to uncover the
truth. They knew that they had to be careful, but they were determined
to see justice served. The director promised to provide Clara with any
resources she needed, and Clara promised to keep him informed of any
developments.

Together, they began to work on a plan to recover the manuscript and to
bring the perpetrator to justice. Clara felt a sense of relief growing
as she realized that she was no longer alone. She had the director's
support, and she knew that she could trust him to keep her safe.

As they worked together, Clara and the director began to piece together
the puzzle of the conspiracy. They knew that they had to be careful, but
they were determined to see justice served. Clara was willing to do
whatever it took to recover the manuscript, and she was grateful to have
the director's support.

The partnership between Clara and the director was a significant
development, and Clara knew that it would be crucial to the success of
the investigation. She felt a sense of hope growing as she realized that
she was one step closer to recovering the manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 19: The police officer returns to the museum with a surprising lead about the thief's identity. ---    
────────────────────────────────────────────────────────────
The police officer, Detective James, returned to the museum with a
surprising lead about the thief's identity. Clara and the museum
director were waiting for him, eager to hear any news. Detective James
explained that he had received a tip from an anonymous source, revealing
the identity of the thief.

The revelation was shocking, and Clara's eyes widened in surprise. The
thief was someone she knew, someone who had been close to the museum and
its staff. Clara felt a sense of betrayal growing as she realized that
the thief had been hiding in plain sight.

The museum director's expression was grim, and Clara knew that he was
taking the news seriously. Detective James explained that he had already
begun to investigate the lead, and he was confident that they would be
able to recover the manuscript soon.

As Clara listened to Detective James, she felt a sense of hope growing.
She knew that they were one step closer to recovering the manuscript,
and she was grateful for the detective's hard work. The investigation
was nearing its conclusion, and Clara was eager to see justice served.


────────────────────────────────────────────────────────────
--- Plot Point 20: Clara, the museum director, and the police officer devise a plan to catch the thief and recover the manuscript. ---
────────────────────────────────────────────────────────────
Clara, the museum director, and Detective James devised a plan to catch
the thief and recover the manuscript. They worked together, using all
the information they had gathered to create a strategy that would bring
the perpetrator to justice. The plan was complex, involving a sting
operation and a team of undercover officers.

Clara felt a sense of excitement growing as she realized that they were
finally close to recovering the manuscript. She knew that the plan was
risky, but she was willing to do whatever it took to see justice served.
The museum director and Detective James were equally determined, and
together they put their plan into action.

The sting operation was a success, and the thief was caught in the act.
The manuscript was recovered, and Clara felt a sense of relief wash over
her. She had done it, she had solved the case and recovered the
manuscript. The museum director and Detective James were equally
thrilled, and they all shared a moment of triumph.

As Clara held the manuscript in her hands, she felt a sense of pride and
accomplishment. She had worked tirelessly to recover the manuscript, and
she had succeeded. The case was closed, and justice had been served.
Clara smiled, knowing that she had made a difference, and that the
manuscript was safe once again.

════════════════════════════════════════════════════════════

════════════════════════════════════════════════════════════
RUN SUMMARY
════════════════════════════════════════════════════════════
  Elapsed time  : 24.7 s
  Total events  : 20
  KG stats      : {'nodes': 119, 'edges': 179, 'edges_by_source': {'domain': 70, 'text': 109}}
  Token usage   : TokenUsage(input=1,266, output=7,400, cost=$0.00 [Groq free tier])

## Rambling Rhino Driver
We will have a class/script/notebook with defined methods for the execution of our system.
