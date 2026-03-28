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
  [E1] (SETUP) The archivist, Clara, arrives at the museum and finds the display case shattered.
  [E2] (INCITING INCIDENT) Clara realizes the priceless 18th-century manuscript is missing.
           caused_by: ['E1']
  [E3] (RISING ACTION) Clara remembers that she was the last person to see the manuscript the night before.
           caused_by: ['E2']
  [E4] (RISING ACTION) Clara decides to review the security footage to identify potential suspects.
           caused_by: ['E2']
  [E5] (RISING ACTION) The security guard, Jack, is called to assist Clara in reviewing the footage.
           caused_by: ['E4']
  [E6] (RISING ACTION) The footage reveals a suspicious person entering the museum after hours.
           caused_by: ['E5']
  [E7] (RISING ACTION) Clara recognizes the suspicious person as a former museum employee, Alex.
           caused_by: ['E6']
  [E8] (RISING ACTION) Clara and Jack decide to pay a visit to Alex's residence to ask questions.
           caused_by: ['E7']
  [E9] (MIDPOINT) Alex is found to be absent from his residence, and his landlord reports that he left in a hurry.    
           caused_by: ['E8']
  [E10] (MIDPOINT) Clara discovers a hidden note in the manuscript's display case with a cryptic message.
           caused_by: ['E2']
  [E11] (MIDPOINT) The cryptic message is believed to be a clue left by the thief, leading Clara to a potential location.
           caused_by: ['E10']
  [E12] (MIDPOINT) Clara decides to follow the clue and visit the old warehouse on the outskirts of town.
           caused_by: ['E11']
  [E13] (MIDPOINT) At the warehouse, Clara finds evidence of a secret meeting between Alex and an unknown individual. 
           caused_by: ['E12']
  [E14] (MIDPOINT) Clara discovers a hidden room in the warehouse containing rare books and artifacts.
           caused_by: ['E13']
  [E15] (COMPLICATIONS) Among the artifacts, Clara finds a rare book with a note referencing the stolen manuscript.   
           caused_by: ['E14']
  [E16] (COMPLICATIONS) The note reveals that the manuscript holds a secret that could change the course of historical events.
           caused_by: ['E15']
  [E17] (COMPLICATIONS) Clara realizes that she is not the only one searching for the manuscript and its secrets.     
           caused_by: ['E16']
  [E18] (COMPLICATIONS) Clara receives a warning from an anonymous source, telling her to drop the investigation.     
           caused_by: ['E17']
  [E19] (CLIMAX) Clara decides to confide in Jack about the warning and the true significance of the manuscript.      
           caused_by: ['E18']
  [E20] (RESOLUTION) Together, Clara and Jack devise a plan to recover the manuscript and protect its secrets from falling into the wrong hands.
           caused_by: ['E19']

KnowledgeGraph: KnowledgeGraph(nodes=115, edges=179, by_source={'domain': 72, 'text': 107})

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
--- Plot Point 1: The archivist, Clara, arrives at the museum and finds the display case shattered. ---
────────────────────────────────────────────────────────────
Clara's eyes widened as she stepped into the grand foyer of the museum,
the soft glow of the morning sunlight casting an eerie light on the
scene before her. The usually immaculate display case, which had once
proudly showcased the museum's prized 18th-century manuscript, now lay
in shattered fragments on the floor. The sound of crunching glass
beneath her feet echoed through the silence, a stark contrast to the
gentle hum of activity that typically filled the museum. As she
approached the wreckage, Clara's mind began to reel with the
implications of what she was seeing. The manuscript, a priceless
artifact that had been the centerpiece of the museum's collection for
decades, was nowhere to be seen. The air was thick with an unsettling
sense of unease, and Clara couldn't shake the feeling that something was
terribly amiss.

As she surveyed the damage, Clara's gaze fell upon the fragments of the
display case, the shards of glass glinting like tiny knives in the
morning light. The case had been specially designed to protect the
manuscript from the elements and potential thieves, and the fact that it
had been shattered with such ease sent a chill down Clara's spine. She
knew that the museum's security team took the safety of the artifacts
very seriously, and the idea that someone had managed to breach the
display case without triggering any alarms was a disturbing one. Clara's
thoughts turned to the night before, and she wondered if anyone had
reported anything unusual.

The museum's staff began to stir, drawn by the commotion, and soon the
foyer was filled with the sound of murmured conversations and the
rustling of footsteps. Clara's colleagues, a mix of curators,
conservators, and security personnel, converged on the scene, their
faces etched with concern and curiosity. As they surveyed the damage,
the atmosphere grew increasingly tense, and Clara knew that she had to
take charge of the situation. She took a deep breath, her mind racing
with the implications of the shattered display case, and began to assess
the situation, her trained eye scanning the area for any clues that
might lead her to the missing manuscript.

As she stood amidst the chaos, Clara's thoughts turned to the museum's
director, who would undoubtedly be called to the scene soon. She knew
that she would have to provide a thorough explanation of the events, and
that the director would expect her to have a plan in place to recover
the stolen manuscript. Clara's stomach twisted into knots as she
contemplated the daunting task ahead of her. She had always been
meticulous in her work, and the thought of failing to protect the
manuscript was unbearable. With a sense of determination, Clara steeled
herself for the challenge, knowing that she would have to draw on all
her expertise and experience to unravel the mystery of the stolen
manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 2: Clara realizes the priceless 18th-century manuscript is missing. ---
────────────────────────────────────────────────────────────
As Clara continued to survey the wreckage, her worst fears were
confirmed: the manuscript was indeed missing. The display case had been
emptied, and the pedestal where the manuscript had once rested was now
bare. Clara felt a wave of panic wash over her, her heart racing with
the implications of the theft. The manuscript, a rare and invaluable
artifact, was not only a prized possession of the museum but also a
significant cultural treasure. Its loss would be felt throughout the
academic community, and Clara knew that she would have to act swiftly to
recover it. She took a deep breath, trying to calm her racing thoughts,
and began to think clearly about the next steps she needed to take.

The museum's security team sprang into action, reviewing the security
footage and interviewing staff members who had been on duty the night
before. Clara, meanwhile, began to methodically search the area,
scouring every inch of the foyer and adjacent rooms for any sign of the
missing manuscript. She knew that time was of the essence, and that
every minute counted in the recovery of the stolen artifact. As she
searched, Clara's mind turned to the manuscript's significance, and the
potential consequences of its loss. The manuscript was not only a
valuable historical artifact but also a window into the past, providing
insights into the lives and experiences of people who had lived
centuries ago.

Clara's thoughts were interrupted by the sound of footsteps, as the
museum's director, Dr. Lee, arrived on the scene. His face was etched
with concern, and his eyes scanned the area, taking in the shattered
display case and the sense of unease that hung in the air. Clara knew
that she would have to provide a thorough explanation of the events, and
that the director would expect her to have a plan in place to recover
the stolen manuscript. She took a deep breath, steeling herself for the
conversation ahead, and began to brief the director on the situation.

As they spoke, Clara's mind turned to the task ahead, and the challenges
she would face in recovering the manuscript. She knew that she would
have to work closely with the security team, as well as other experts,
to track down the thief and recover the stolen artifact. The thought of
the challenge ahead was daunting, but Clara was determined to succeed.
She was a skilled archivist, with years of experience in handling rare
and valuable artifacts, and she was confident that she could recover the
manuscript and bring it back to its rightful home.


────────────────────────────────────────────────────────────
--- Plot Point 3: Clara remembers that she was the last person to see the manuscript the night before. ---
────────────────────────────────────────────────────────────
As Clara continued to discuss the situation with Dr. Lee, she couldn't
shake the feeling that she was somehow responsible for the manuscript's
disappearance. She remembered that she had been the last person to see
the manuscript the night before, and a pang of guilt washed over her.
Clara had been working late, preparing for an upcoming exhibition, and
she had stopped by the display case to check on the manuscript before
leaving for the night. She had locked the case, as she always did, and
had set the alarm system, but somehow, the thief had still managed to
breach the display case and steal the manuscript.

Clara's mind turned to the events of the previous evening, and she tried
to recall every detail. She had been alone in the museum, the only sound
the soft hum of the security systems and the creaking of the old
building. She had checked the display case, making sure that everything
was in order, and had then headed to her office to gather her things
before leaving for the night. As she walked out of the museum, Clara had
felt a sense of satisfaction, knowing that she had completed all her
tasks for the day. But now, in the cold light of morning, she wondered
if she had missed something, if she had somehow overlooked a crucial
detail that could have prevented the theft.

The memory of the previous evening's events played in Clara's mind like
a video recording, and she tried to analyze every detail. She had locked
the display case, and she had set the alarm system, but had she checked
the case one last time before leaving? Clara's eyes narrowed as she
tried to recall the exact sequence of events. She had been distracted by
her thoughts, preoccupied with the upcoming exhibition, and she might
have missed something. The thought sent a shiver down her spine, and
Clara knew that she would have to review the security footage to see if
it could provide any clues.

As she stood in the foyer, surrounded by the remnants of the shattered
display case, Clara felt a sense of determination wash over her. She was
going to get to the bottom of the mystery, and she was going to recover
the stolen manuscript. She would leave no stone unturned, and she would
work tirelessly to uncover the truth. The memory of the previous
evening's events would haunt her, but Clara was determined to use it as
a catalyst for her investigation. She would learn from her mistakes, and
she would use her knowledge and expertise to track down the thief and
recover the manuscript.


────────────────────────────────────────────────────────────
--- Plot Point 4: Clara decides to review the security footage to identify potential suspects. ---
────────────────────────────────────────────────────────────
Clara's decision to review the security footage was driven by a desire
to understand the events of the previous evening. She knew that the
footage would provide a crucial window into the theft, and she was
determined to analyze every frame. The museum's security team had
already begun to review the footage, but Clara wanted to see it for
herself, to get a sense of what had happened and who might have been
involved. She made her way to the security room, a small, cramped space
filled with banks of monitors and rows of recording equipment.

As she sat down in front of the monitors, Clara felt a sense of
trepidation. She was about to witness the theft, to see the manuscript
being taken from its display case, and she wasn't sure if she was ready
for it. The security team had already fast-forwarded through the
footage, highlighting the relevant sections, and Clara took a deep
breath as she began to watch. The footage showed the museum's empty
corridors, the only sound the soft hum of the security systems. And
then, suddenly, a figure appeared, moving swiftly and silently through
the corridors.

Clara's eyes were glued to the monitor as she watched the figure
approach the display case. The thief was careful, methodical, and seemed
to know exactly what they were doing. Clara's mind was racing as she
tried to analyze the footage, to identify any clues that might lead her
to the thief. She watched as the thief breached the display case, as
they carefully lifted the manuscript out of its pedestal, and as they
disappeared into the night. The footage was grainy, but Clara could make
out the thief's general build and height. She couldn't see their face,
but she was determined to find out who they were and how they had
managed to pull off the theft.

As she finished watching the footage, Clara felt a sense of
determination wash over her. She was going to catch the thief, and she
was going to recover the manuscript. She would work tirelessly to
analyze the footage, to identify any clues that might lead her to the
perpetrator. And she would not rest until the manuscript was back in its
rightful place, safe and secure in the museum's display case. Clara's
eyes narrowed as she thought about the challenge ahead, and she knew
that she would have to be meticulous, to follow every lead, no matter
how small.


────────────────────────────────────────────────────────────
--- Plot Point 5: The security guard, Jack, is called to assist Clara in reviewing the footage. ---
────────────────────────────────────────────────────────────
As Clara continued to analyze the security footage, she was joined by
Jack, the museum's head of security. Jack was a tall, imposing figure,
with a no-nonsense attitude and a wealth of experience in dealing with
security breaches. Clara had worked with him before, and she valued his
expertise and insight. Together, they sat down in front of the monitors,
and Clara began to show him the footage. Jack's eyes scanned the
screens, his expression growing increasingly serious as he watched the
thief in action.

As they watched the footage, Jack pointed out several details that Clara
had missed. He noted the thief's height and build, their clothing and
shoes, and the way they moved with a confident, practiced air. Clara was
impressed by Jack's attention to detail, and she realized that she had
been so focused on the manuscript that she had overlooked some of the
more obvious clues. Jack's expertise was invaluable, and Clara was
grateful to have him by her side as they analyzed the footage. Together,
they began to piece together the events of the previous evening, using
the footage to reconstruct the thief's movements and actions.

As they worked, Clara and Jack developed a rapport, their conversation
flowing easily as they discussed the case. Clara was struck by Jack's
knowledge and experience, and she found herself relying on him more and
more as they analyzed the footage. Jack, in turn, was impressed by
Clara's expertise and her passion for the manuscript. He had worked with
her before, but he had never seen her so focused, so driven by a desire
to recover a stolen artifact. Together, they made a formidable team, and
Clara knew that she could rely on Jack to help her track down the thief
and recover the manuscript.

As they finished reviewing the footage, Jack turned to Clara and said,
"We need to take a closer look at the thief's movements. I think I saw
something that might be a clue." Clara's eyes locked onto his, and she
felt a surge of excitement. She knew that they were onto something, and
she was eager to see where the investigation would lead. Together, they
began to analyze the footage frame by frame, searching for any detail
that might lead them to the thief.


────────────────────────────────────────────────────────────
--- Plot Point 6: The footage reveals a suspicious person entering the museum after hours. ---
────────────────────────────────────────────────────────────
As Clara and Jack continued to analyze the footage, they noticed a
suspicious person entering the museum after hours. The figure was
difficult to make out, but they seemed to be moving with a purpose,
their actions swift and deliberate. Clara's eyes narrowed as she watched
the figure, her mind racing with possibilities. Who was this person, and
what were they doing in the museum after hours? The figure seemed to
know exactly where they were going, and they moved with a confidence
that was unsettling.

As they watched, the figure disappeared from view, and Clara felt a
sense of frustration. She had been so focused on the thief, and now it
seemed that there was another player in the game. Jack, however, was
undeterred, his expression calm and focused. "Let's keep watching," he
said, his voice low and even. "I think we might be able to learn more
about this person." Clara nodded, her eyes locked onto the screen as
they continued to analyze the footage.

The figure reappeared a few minutes later, this time in a different part
of the museum. Clara and Jack watched as they moved swiftly and
silently, their actions seemingly choreographed. The figure seemed to
know the museum's layout intimately, and they moved with a ease that was
unnerving. Clara's mind was racing with questions, and she couldn't help
but wonder what this person's role was in the theft. Were they an
accomplice, or were they working alone?

As they continued to watch, Clara and Jack began to piece together the
events of the previous evening. The suspicious person had entered the
museum after hours, and they had moved swiftly and silently to the
display case. The thief had then appeared, and the two of them had
seemed to work together, their actions coordinated and deliberate.
Clara's eyes locked onto Jack's, and she felt a sense of excitement.
They were getting close to the truth, and she could sense that they were
on the verge of a breakthrough.


────────────────────────────────────────────────────────────
--- Plot Point 7: Clara recognizes the suspicious person as a former museum employee, Alex. ---
────────────────────────────────────────────────────────────
As Clara and Jack continued to analyze the footage, Clara's eyes widened
in shock. The suspicious person, the one who had entered the museum
after hours, was someone she knew. It was Alex, a former museum employee
who had left the museum several months ago. Clara's mind was racing with
memories of Alex, and she couldn't believe what she was seeing. Alex had
been a quiet, unassuming person, always keeping to himself. Clara had
never suspected that he might be involved in something like this.

As she watched the footage, Clara's thoughts turned to her interactions
with Alex. She had worked with him on several projects, and she had
always found him to be competent and efficient. But she had also found
him to be somewhat distant, always keeping to himself. Clara had never
really gotten to know him, and now she wondered if she had misjudged him
entirely. The Alex she was seeing on the screen was a different person,
someone who seemed confident and calculating.

Clara turned to Jack, her eyes locked onto his. "I know this person,"
she said, her voice barely above a whisper. "It's Alex, a former museum
employee." Jack's expression was serious, and he nodded slowly. "Let's
take a closer look at his movements," he said, his voice low and even.
Together, they began to analyze the footage, searching for any clue that
might lead them to Alex.

As they watched, Clara felt a sense of unease. She had worked with Alex,
and she had considered him a colleague. But now, she wasn't so sure. The
Alex she was seeing on the screen was a stranger, someone who seemed
capable of theft and deception. Clara's mind was racing with questions,
and she couldn't help but wonder what had driven Alex to this point. Had
he been struggling financially, or was there something more complex at
play?


────────────────────────────────────────────────────────────
--- Plot Point 8: Clara and Jack decide to pay a visit to Alex's residence to ask questions. ---
────────────────────────────────────────────────────────────
As Clara and Jack finished analyzing the footage, they decided to pay a
visit to Alex's residence. They wanted to ask him questions, to see if
he had any alibi for the time the manuscript was stolen. Clara was
nervous, unsure of what they would find. She had worked with Alex, and
she had considered him a colleague. But now, she wasn't so sure. The
Alex she had seen on the screen was a different person, someone who
seemed capable of theft and deception.

As they arrived at Alex's residence, Clara felt a sense of trepidation.
She had never been to his home before, and she wasn't sure what to
expect. The building was a small, unassuming apartment complex, and
Alex's apartment was on the second floor. Clara and Jack walked up the
stairs, their footsteps echoing in the silence. As they reached the
door, Clara took a deep breath, steeling herself for what was to come.

Jack knocked on the door, his expression serious. There was no answer,
and Clara felt a sense of unease. Where was Alex? Was he avoiding them,
or was he simply not home? Jack knocked again, this time louder, and
Clara could feel her heart pounding in her chest. Suddenly, the door
opened, and a woman stood before them. She was older, with a kind face
and a look of concern.

"Can I help you?" she asked, her voice hesitant. Clara explained their
presence, and the woman nodded slowly. "I'm Alex's landlord," she said.
"He's not here right now. He left in a hurry this morning, saying he had
to go out of town." Clara's eyes locked onto Jack's, and she felt a
sense of frustration. They had missed Alex, and now they had to start
searching for him all over again.


────────────────────────────────────────────────────────────
--- Plot Point 9: Alex is found to be absent from his residence, and his landlord reports that he left in a hurry. ---
────────────────────────────────────────────────────────────
As Clara and Jack spoke with Alex's landlord, they learned that he had
left his residence in a hurry. The landlord, a kind-faced woman, seemed
concerned, and Clara could sense that she was telling the truth. "He
came down to the office this morning, saying he had to leave town
immediately," she said. "He didn't say where he was going, but he
seemed...nervous." Clara's eyes locked onto Jack's, and she felt a sense
of excitement. They were getting close to the truth, and she could sense
that they were on the verge of a breakthrough.

The landlord's words painted a picture of a man in a hurry, someone who
was desperate to escape. Clara's mind was racing with possibilities, and
she couldn't help but wonder what Alex was running from. Was he afraid
of being caught, or was there something more complex at play? As they
finished speaking with the landlord, Clara and Jack decided to search
Alex's apartment, to see if they could find any clues that might lead
them to the manuscript.

As they entered the apartment, Clara felt a sense of unease. The space
was small and cluttered, with books and papers scattered everywhere.
Clara's eyes scanned the room, searching for any sign of the manuscript.
But there was nothing, just a sense of disarray and chaos. Jack,
however, seemed to be searching for something specific, his eyes
scanning the room with a keen intensity. Suddenly, he stopped, his
expression serious.

"Look at this," he said, his voice low. Clara followed his gaze, and her
eyes widened in surprise. On the kitchen counter, there was a small
note, scribbled in haste. It was a cryptic message, but it seemed to
point to a specific location. Clara's heart was racing as she realized
the significance of the note. They were one step closer to finding the
manuscript, and she could sense that they were on the verge of a major
breakthrough.


────────────────────────────────────────────────────────────
--- Plot Point 10: Clara discovers a hidden note in the manuscript's display case with a cryptic message. ---
────────────────────────────────────────────────────────────
As Clara and Jack continued to investigate, they decided to take a
closer look at the manuscript's display case. Clara had already searched
the area, but she had missed something. As she peered into the case, she
noticed a small piece of paper, tucked away in a corner. It was a note,
scribbled in haste, and it seemed to be a cryptic message. Clara's eyes
widened as she read the words, her mind racing with possibilities.

The note was brief, just a few words, but it seemed to point to a
specific location. Clara's heart was racing as she realized the
significance of the note. It was a clue, left by the thief, and it might
lead them to the manuscript. Jack's eyes locked onto hers, and he nodded
slowly. "This is it," he said, his voice low. "This is the break we've
been waiting for." Clara felt a sense of excitement, mixed with a sense
of trepidation. They were getting close to the truth, and she could
sense that they were on the verge of a major breakthrough.

As they analyzed the note, Clara realized that it was more than just a
simple message. It was a puzzle, a cryptic code that required decoding.
The words seemed to dance on the page, taunting her with their secrets.
But Clara was determined to crack the code, to uncover the truth behind
the note. She and Jack worked tirelessly, pouring over the note,
searching for any clue that might lead them to the manuscript.

As they worked, Clara felt a sense of fascination with the note. It was
a clever puzzle, one that required patience and persistence. But she was
driven by a desire to uncover the truth, to recover the manuscript and
bring it back to its rightful home. The note was a challenge, a test of
her skills and her determination. And Clara was ready to rise to the
challenge, to follow the clue and see where it would lead.


────────────────────────────────────────────────────────────
--- Plot Point 11: The cryptic message is believed to be a clue left by the thief, leading Clara to a potential location. ---
────────────────────────────────────────────────────────────
As Clara and Jack continued to analyze the note, they became
increasingly convinced that it was a clue left by the thief. The message
was cryptic, but it seemed to point to a specific location, a place
where the manuscript might be hidden. Clara's eyes locked onto Jack's,
and she felt a sense of excitement. They were getting close to the
truth, and she could sense that they were on the verge of a major
breakthrough.

The note was a puzzle, a complex web of words and symbols that required
decoding. But Clara was determined to crack the code, to uncover the
truth behind the message. She and Jack worked tirelessly, pouring over
the note, searching for any clue that might lead them to the manuscript.
As they worked, Clara felt a sense of fascination with the note. It was
a clever puzzle, one that required patience and persistence.

But Clara was driven by a desire to uncover the truth, to recover the
manuscript and bring it back to its rightful home. The note was a
challenge, a test of her skills and her determination. And Clara was
ready to rise to the challenge, to follow the clue and see where it
would lead. As they finally cracked the code, Clara felt a sense of
triumph. The note was a clue, a message that pointed to a specific
location. And Clara was ready to follow the clue, to see where it would
lead.

The location was an old warehouse on the outskirts of town, a place that
seemed abandoned and forgotten. But Clara was not deterred, her heart
racing with anticipation. She and Jack made their way to the warehouse,
their footsteps echoing in the silence. As they approached the building,
Clara felt a sense of trepidation. What would they find inside? Was the
manuscript hidden here, or was it just a wild goose chase?


────────────────────────────────────────────────────────────
--- Plot Point 12: Clara decides to follow the clue and visit the old warehouse on the outskirts of town. ---
────────────────────────────────────────────────────────────
As Clara and Jack approached the warehouse, they could feel a sense of
unease in the air. The building loomed before them, its walls towering
and imposing. Clara's heart was racing with anticipation, and she could
sense that they were getting close to the truth. The warehouse seemed
abandoned, its windows boarded up and its doors covered in rust. But
Clara was not deterred, her determination driving her forward.

As they entered the warehouse, Clara felt a sense of fascination. The
space was vast and empty, the only sound the creaking of the old wooden
beams. Clara's eyes scanned the room, searching for any sign of the
manuscript. But there was nothing, just a sense of emptiness and decay.
Jack, however, seemed to be searching for something specific, his eyes
scanning the room with a keen intensity.

Suddenly, he stopped, his expression serious. "Look at this," he said,
his voice low. Clara followed his gaze, and her eyes widened in
surprise. In the corner of the room, there was a small door, hidden
behind a stack of crates. The door was small, but it seemed to lead to a
secret room, a place that was hidden from the rest of the world. Clara's
heart was racing as she realized the significance of the door. They were
getting close to the truth, and she could sense that they were on the
verge of a major breakthrough.

As they approached the door, Clara felt a sense of trepidation. What
would they find inside? Was the manuscript hidden here, or was it just a
wild goose chase? But Clara was driven by a desire to uncover the truth,
to recover the manuscript and bring it back to its rightful home. The
door was a challenge, a test of her skills and her determination. And
Clara was ready to rise to the challenge, to open the door and see what
secrets lay inside.


────────────────────────────────────────────────────────────
--- Plot Point 13: At the warehouse, Clara finds evidence of a secret meeting between Alex and an unknown individual. ---
────────────────────────────────────────────────────────────
As Clara and Jack entered the secret room, they were met with a sense of
surprise. The room was small, but it was filled with evidence of a
secret meeting. There were chairs and tables, arranged in a circle, and
a sense of intimacy hung in the air. Clara's eyes scanned the room,
searching for any sign of the manuscript. But there was nothing, just a
sense of unease and foreboding.

As they searched the room, Clara found a piece of paper, tucked away in
a corner. It was a note, scribbled in haste, and it seemed to be a
record of the meeting. Clara's eyes widened as she read the words, her
mind racing with possibilities. The note was cryptic, but it seemed to
point to a deeper conspiracy, a plot that involved Alex and the unknown
individual.

Clara felt a sense of fascination with the note, her mind racing with
questions. Who was the unknown individual, and what was their role in
the theft? Was Alex working alone, or was he part of a larger group? The
note was a puzzle, a complex web of words and symbols that required
decoding. But Clara was determined to crack the code, to uncover the
truth behind the note.

As they continued to search the room, Clara and Jack found more evidence
of the secret meeting. There were coffee cups and ashtrays, arranged on
the tables, and a sense of familiarity hung in the air. Clara's eyes
locked onto Jack's, and she felt a sense of excitement. They were
getting close to the truth, and she could sense that they were on the
verge of a major breakthrough.

The meeting had taken place just a few days ago, and Clara could sense
that the participants had been discussing something important. The note
was a clue, a message that pointed to a deeper conspiracy. And Clara was
ready to follow the clue, to see where it would lead. As they finished
searching the room, Clara felt a sense of determination. She was going
to uncover the truth, to recover the manuscript and bring it back to its
rightful home.


────────────────────────────────────────────────────────────
--- Plot Point 14: Clara discovers a hidden room in the warehouse containing rare books and artifacts. ---
────────────────────────────────────────────────────────────
As Clara and Jack continued to explore the warehouse, they stumbled upon
a hidden room, tucked away behind a secret door. The room was small, but
it was filled with a treasure trove of rare books and artifacts. Clara's
eyes widened as she scanned the shelves, her mind racing with
excitement. The room was a bibliophile's paradise, a place where rare
and valuable books were stored.

As they searched the room, Clara found a collection of rare manuscripts,
bound in leather and adorned with gold filigree. There were also
artifacts, ancient relics that seemed to hold secrets and stories of
their own. Clara's eyes locked onto a small, delicate box, adorned with
intricate carvings and symbols. The box seemed to be emitting a strange
glow, and Clara felt a sense of fascination.

As they opened the box, Clara found a small, leather-bound book, adorned
with strange symbols and markings. The book seemed to be emitting a
strange energy, and Clara felt a sense of wonder. The book was a rare
and valuable artifact, one that seemed to hold secrets and stories of
its own. Clara's eyes scanned the pages, searching for any clue that
might lead her to the manuscript.

As they continued to search the room, Clara and Jack found more rare
books and artifacts, each one more valuable and significant than the
last. The room was a treasure trove, a place where rare and valuable
items were stored. And Clara was determined to explore every inch of it,
to uncover the secrets and stories that lay within.

The hidden room was a discovery, a place that seemed to hold the key to
the mystery. Clara was determined to uncover the truth, to recover the
manuscript and bring it back to its rightful home. And as they finished
searching the room, Clara felt a sense of excitement. They were getting
close to the truth, and she could sense that they were on the verge of a
major breakthrough.


────────────────────────────────────────────────────────────
--- Plot Point 15: Among the artifacts, Clara finds a rare book with a note referencing the stolen manuscript. ---    
────────────────────────────────────────────────────────────
As Clara and Jack continued to search the hidden room, they stumbled
upon a rare book, bound in leather and adorned with gold filigree. The
book was old, its pages yellowed with age, and Clara's eyes widened as
she scanned the title page. The book was a rare and valuable artifact,
one that seemed to hold secrets and stories of its own.

As she opened the book, Clara found a note, tucked away between the
pages. The note was a message, scribbled in haste, and it seemed to
reference the stolen manuscript. Clara's eyes locked onto the words, her
mind racing with excitement. The note was a clue, a message that pointed
to the manuscript's location.

The note was cryptic, but it seemed to point to a deeper conspiracy, a
plot that involved Alex and the unknown individual. Clara's eyes scanned
the pages, searching for any clue that might lead her to the manuscript.
As she read the words, Clara felt a sense of fascination, her mind
racing with questions. Who had written the note, and what was their role
in the theft?

The book was a rare and valuable artifact, one that seemed to hold
secrets and stories of its own. And Clara was determined to uncover the
truth, to recover the manuscript and bring it back to its rightful home.
As they finished searching the book, Clara felt a sense of excitement.
They were getting close to the truth, and she could sense that they were
on the verge of a major breakthrough.

The note was a clue, a message that pointed to the manuscript's
location. And Clara was ready to follow the clue, to see where it would
lead. As they left the hidden room, Clara felt a sense of determination.
She was going to uncover the truth, to recover the manuscript and bring
it back to its rightful home. And she was going to do it, no matter what
it took.


────────────────────────────────────────────────────────────
--- Plot Point 16: The note reveals that the manuscript holds a secret that could change the course of historical events. ---
────────────────────────────────────────────────────────────
As Clara and Jack continued to analyze the note, they realized that the
manuscript held a secret, a secret that could change the course of
historical events. The note was cryptic, but it seemed to point to a
deeper truth, a truth that had been hidden for centuries. Clara's eyes
widened as she read the words, her mind racing with possibilities.

The manuscript was more than just a valuable artifact, it was a key to
unlocking a deeper understanding of history. And Clara was determined to
uncover the truth, to recover the manuscript and bring it back to its
rightful home. As they finished analyzing the note, Clara felt a sense
of excitement. They were getting close to the truth, and she could sense
that they were on the verge of a major breakthrough.

The note was a clue, a message that pointed to the manuscript's
location. And Clara was ready to follow the clue, to see where it would
lead. As they left the warehouse, Clara felt a sense of determination.
She was going to uncover the truth, to recover the manuscript and bring
it back to its rightful home. And she was going to do it, no matter what
it took.

The manuscript was a puzzle, a complex web of words and symbols that
required decoding. But Clara was determined to crack the code, to
uncover the truth behind the manuscript. And as they walked away from
the warehouse, Clara felt a sense of excitement. They were getting close
to the truth, and she could sense that they were on the verge of a major
breakthrough.

The note had revealed a secret, a secret that could change the course of
historical events. And Clara was determined to uncover the truth, to
recover the manuscript and bring it back to its rightful home. As they
walked away from the warehouse, Clara felt a sense of determination. She
was going to uncover the truth, no matter what it took.


────────────────────────────────────────────────────────────
--- Plot Point 17: Clara realizes that she is not the only one searching for the manuscript and its secrets. ---      
────────────────────────────────────────────────────────────
As Clara and Jack continued to investigate, they realized that they were
not the only ones searching for the manuscript. There were others,
unknown individuals who seemed to be one step ahead of them. Clara's
eyes locked onto Jack's, and she felt a sense of unease. They were in a
race, a race to uncover the truth and recover the manuscript.

The note had revealed a secret, a secret that could change the course of
historical events. And Clara was determined to uncover the truth, to
recover the manuscript and bring it back to its rightful home. But she
was not alone, there were others who seemed to be searching for the same
thing. Clara's mind was racing with questions, who were these
individuals, and what were their motives?

As they continued to investigate, Clara and Jack realized that they were
in a complex web of intrigue and deception. There were multiple players,
each with their own agenda, and Clara was determined to uncover the
truth. She was a skilled archivist, with years of experience in handling
rare and valuable artifacts. And she was determined to use her skills to
uncover the truth, to recover the manuscript and bring it back to its
rightful home.

The manuscript was a puzzle, a complex web of words and symbols that
required decoding. But Clara was determined to crack the code, to
uncover the truth behind the manuscript. And as they continued to
investigate, Clara felt a sense of excitement. They were getting close
to the truth, and she could sense that they were on the verge of a major
breakthrough.

But Clara was not alone, there were others who seemed to be searching
for the same thing. And Clara was determined to stay one step ahead of
them, to uncover the truth and recover the manuscript before they did.
As they walked away from the warehouse, Clara felt a sense of
determination. She was going to uncover the truth, no matter what it
took.


────────────────────────────────────────────────────────────
--- Plot Point 18: Clara receives a warning from an anonymous source, telling her to drop the investigation. ---      
────────────────────────────────────────────────────────────
As Clara and Jack continued to investigate, Clara received a warning
from an anonymous source. The warning was a message, sent to her phone,
and it seemed to be from someone who knew her. Clara's eyes widened as
she read the words, her mind racing with possibilities. The message was
a warning, a warning to drop the investigation and leave the manuscript
alone.

Clara's heart was racing as she read the words, her mind racing with
questions. Who was this anonymous source, and what were their motives?
The message was cryptic, but it seemed to point to a deeper truth, a
truth that Clara was not supposed to uncover. Clara felt a sense of
unease, a sense of being watched. She was being warned, warned to drop
the investigation and leave the manuscript alone.

But Clara was not one to back down from a challenge. She was a skilled
archivist, with years of experience in handling rare and valuable
artifacts. And she was determined to uncover the truth, to recover the
manuscript and bring it back to its rightful home. As she showed the
message to Jack, Clara felt a sense of determination. They were not
going to drop the investigation, they were going to see it through to
the end.

The message was a warning, a warning to drop the investigation and leave
the manuscript alone. But Clara was not afraid, she was determined to
uncover the truth. And as they continued to investigate, Clara felt a
sense of excitement. They were getting close to the truth, and she could
sense that they were on the verge of a major breakthrough.

The anonymous source was trying to intimidate her, to scare her off the
case. But Clara was not one to be intimidated, she was a skilled
archivist, and she was determined to uncover the truth. As they walked
away from the warehouse, Clara felt a sense of determination. She was
going to uncover the truth, no matter what it took.


────────────────────────────────────────────────────────────
--- Plot Point 19: Clara decides to confide in Jack about the warning and the true significance of the manuscript. ---
────────────────────────────────────────────────────────────
As Clara and Jack continued to investigate, Clara decided to confide in
him about the warning and the true significance of the manuscript. She
showed him the message, and her eyes locked onto his as she explained
the situation. Jack's expression was serious, and he nodded slowly as he
listened.

"I think we should be careful," he said, his voice low. "If someone is
warning you to drop the investigation, it means they're getting
desperate. We need to be careful, and we need to watch our backs." Clara
nodded, her mind racing with possibilities. She knew that Jack was
right, they needed to be careful. But she was not going to drop the
investigation, she was going to see it through to the end.

As they walked away from the warehouse, Clara felt a sense of
determination. She was going to uncover the truth, no matter what it
took. And she was glad to have Jack by her side, he was a skilled
security expert, and she trusted him with her life. Together, they were
going to uncover the truth, and they were going to recover the
manuscript.

The warning had been a warning, a warning to drop the investigation and
leave the manuscript alone. But Clara was not afraid, she was determined
to uncover the truth. And as they continued to investigate,

════════════════════════════════════════════════════════════

════════════════════════════════════════════════════════════
RUN SUMMARY
════════════════════════════════════════════════════════════
  Elapsed time  : 27.4 s
  Total events  : 20
  KG stats      : {'nodes': 115, 'edges': 179, 'edges_by_source': {'domain': 72, 'text': 107}}
  Token usage   : TokenUsage(input=1,220, output=9,669, cost=$0.00 [Groq free tier])

## Rambling Rhino Driver
We will have a class/script/notebook with defined methods for the execution of our system.
