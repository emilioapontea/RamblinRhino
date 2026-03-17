# Reading Model Driven Story Generation
> Team Rambling Rhino

To install our conda environment (`rhino`) with necessary dependencies:
```bash
conda env create -file environment.yml
conda activate rhino
```

If you have pip dependencies to add (be sure you are in the `rhino` environment):
```bash
conda install <package> pip
conda env export > environment.yml
```

## Engagement Modules
### ContextPrompter
A class that manages feedback from the `ComplexityChecker` and generates an engineered prompt to pass on to the LLM.
### LLM
A wrapper class to handle API requests to our chosen LLM and receive output in the form of QUEST events, goals, etc. to be parsed into the QUEST `KnowledgeGraph`.

## Reflection Modules
### KnowledgeGraph
A class to support `(subject --predicate--> object)` relationships in our QUEST graph. We will primarily be using the `NLPIngestor` class which uses `spaCy`'s [`en_core_web_sm`](https://spacy.io/models/en#en_core_web_sm) (12 MB) CPU pipeline for tokenization, part of speech tagging, named entity recognition, etc., to build up the knowledge graph from our LLM's text responses.

### ComplexityChecker
A class with defined methods to evaluate the complexity of the quest graph in order to determine the system's control flow.

## Rambling Rhino Driver
We will have a class/script/notebook with defined methods for the execution of our system.