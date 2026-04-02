# Step 5 - SequentialAgent (Pipeline deterministe)

## Concepts

### SequentialAgent vs delegation LLM
| | Delegation (Step 4) | SequentialAgent (Step 5) |
|---|---|---|
| Qui decide ? | Le LLM | L'ordre de la liste |
| Previsible ? | Non (le LLM choisit) | Oui (toujours le meme ordre) |
| Le SequentialAgent a un model ? | N/A | **Non** |
| Cas d'usage | Routing dynamique | Pipeline fixe |

### Anatomie d'un SequentialAgent
```python
from google.adk.agents import SequentialAgent

pipeline = SequentialAgent(
    name="mon_pipeline",
    description="Description du pipeline",
    sub_agents=[agent_a, agent_b, agent_c],  # Toujours dans cet ordre
    # PAS de model= ni instruction= (ce n'est pas un LLM agent)
)
```

### Chainage de donnees : output_key + {state_var}
C'est le pattern cle : chaque agent **ecrit** dans le state via `output_key`, et le suivant **lit** via `{cle}` dans son instruction.

```
Agent A (output_key="resultat_a")
   |  ecrit state["resultat_a"] = "sa reponse"
   v
Agent B (instruction="Voici le resultat : {resultat_a}")
   |  le LLM recoit : "Voici le resultat : sa reponse"
   v
Agent C (instruction="Donnees : {resultat_a} et {resultat_b}")
```

### Pourquoi c'est puissant
- Pipeline **reproductible** : meme entree = meme flux
- Chaque agent est specialise dans UNE tache
- Les donnees circulent via le state de facon transparente

## Diagramme

```
                     code_pipeline (SequentialAgent)
    ┌─────────────────────┬─────────────────────┬─────────────────────┐
    │                     │                     │                     │
    ▼                     │                     │                     │
 ┌────────┐              ▼                     │                     │
 │ Writer │ ──output_key──> state["generated_code"] ──{generated_code}──>
 │        │              │                     │                     │
 └────────┘              │  ┌──────────┐       │                     │
                         │  │ Reviewer │ ──output_key──> state["review_feedback"]
                         │  └──────────┘       │                     │
                         │                     │  ┌────────────┐     │
                         │                     │  │ Refactorer │ ──output_key──> state["final_code"]
                         │                     │  └────────────┘     │
                         │                     │   lit {generated_code}
                         │                     │   ET {review_feedback}
```

## Exploration

Ouvre [agent.py](agent.py) et observe :
1. `writer_agent` a `output_key="generated_code"` -> ecrit dans le state
2. `reviewer_agent` a `{generated_code}` dans son instruction -> lit le state
3. `refactorer_agent` lit `{generated_code}` ET `{review_feedback}`
4. `root_agent` est un `SequentialAgent` sans `model` ni `instruction`

## Prompts de test

Lance `adk web` -> `step_05_sequential` :

| Prompt | Resultat attendu | Quoi observer |
|--------|-----------------|---------------|
| "Write a function to merge two sorted lists" | 3 reponses enchainees : code, review, code ameliore | Dans Events : 3 agents s'executent dans l'ordre |
| "Create a binary search function" | Meme pipeline, code different | Le writer ecrit, le reviewer donne un score, le refactorer ameliore |

**Point cle** : tu ne controles PAS quel agent repond. Le pipeline s'execute automatiquement dans l'ordre.

## Exercice

**Mission** : Creer un pipeline de creation de blagues en 3 etapes.

Ouvre `exercise_05/agent.py` et complete les `# TODO`.

Pipeline : `JokeWriter` -> `JokeCritic` -> `JokeFormatter`

1. `JokeWriter` : genere une blague brute (tool `write_joke`), `output_key="raw_joke"`
2. `JokeCritic` : critique la blague (tool `critique_joke`), lit `{raw_joke}`, `output_key="critique"`
3. `JokeFormatter` : formate la version finale, lit `{raw_joke}` et `{critique}`, `output_key="final_joke"`
4. `root_agent` = `SequentialAgent` avec les 3 agents

Teste : "Tell me a joke about programmers"

## Quiz

Teste tes connaissances : ouvre [quiz/index.html](../quiz/index.html) dans ton navigateur et selectionne **Step 6**.
