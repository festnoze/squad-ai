# Step 7 - LoopAgent (Boucle iterative)

## Concepts

### LoopAgent
Execute ses sub-agents en sequence, puis **recommence** jusqu'a :
- Atteindre `max_iterations` (securite anti-boucle infinie)
- Recevoir un signal `escalate` (sortie anticipee)

```python
from google.adk.agents import LoopAgent

loop = LoopAgent(
    name="ma_boucle",
    sub_agents=[writer, reviewer],  # writer puis reviewer, en boucle
    max_iterations=5,               # Maximum 5 tours
)
```

### Le pattern creation/critique
C'est le coeur de Code Forge : un agent **cree**, un autre **juge**, et ca boucle jusqu'a satisfaction.

```
Iteration 1: Writer ecrit du code    -> Reviewer: "Score 4/10, ameliore X"
Iteration 2: Writer corrige avec X   -> Reviewer: "Score 6/10, ameliore Y"
Iteration 3: Writer corrige avec Y   -> Reviewer: "Score 9/10, approuve !"  -> ESCALATE
```

### Escalation : sortir de la boucle
Un tool peut signaler la fin de la boucle :

```python
def approve(tool_context: ToolContext) -> dict:
    """Approuve et arrete la boucle."""
    tool_context.actions.escalate = True  # <- Signal de sortie !
    return {"status": "approved"}
```

Le signal `escalate` arrete la boucle **apres** que le sub-agent courant a fini (pas en plein milieu).

### Le state persiste entre iterations
Le feedback de l'iteration N est visible a l'iteration N+1 via le state. C'est ce qui permet l'amelioration progressive :

```
Iteration 1: writer lit state["review_feedback"] = "No prior feedback"
             reviewer ecrit state["review_feedback"] = "Add type hints"
Iteration 2: writer lit state["review_feedback"] = "Add type hints"  <- le feedback precedent !
```

## Diagramme

```
             refinement_loop (LoopAgent, max=4)
    ┌──────────────────────────────────────────────┐
    │                                              │
    │  ┌─────────────┐   ┌──────────────┐         │
    │  │ loop_writer  │──>│ loop_reviewer │         │
    │  │             │   │              │         │
    │  │ lit feedback │   │ score < 8 ? │──┐      │
    │  │ ecrit code   │   │ score >= 8 ?│  │      │
    │  └─────────────┘   └──────┬───────┘  │      │
    │        ▲                  │           │      │
    │        │                  ▼           │      │
    │        │           ┌──────────┐      │      │
    │        │           │ ESCALATE │      │      │
    │        │           │ (sortie) │      │      │
    │        │           └──────────┘      │      │
    │        │                             │      │
    │        └─────── feedback ────────────┘      │
    │          (iteration suivante)                │
    └──────────────────────────────────────────────┘
```

## Exploration

Ouvre [agent.py](agent.py) et observe :
1. `save_code` + `submit_review` + `approve_code` : les 3 tools
2. `approve_code` fait `tool_context.actions.escalate = True`
3. Le `reviewer_in_loop` a les tools `submit_review` ET `approve_code`
4. Le `LoopAgent` avec `max_iterations=4`

## Prompts de test

Lance `adk web` -> `step_07_loop` :

| Prompt | Resultat attendu | Quoi observer |
|--------|-----------------|---------------|
| "Write a function to sort a list" | Plusieurs iterations visibles, code qui s'ameliore | Dans Events : alterner writer/reviewer, scores croissants |
| "Write a hello world function" | Possiblement approuve des la 1ere iteration | Si le code est simple, le reviewer peut approuver rapidement |

**Point cle** : compte le nombre d'appels `save_code` et `submit_review` dans Events. Chaque paire = une iteration de la boucle.

## Exercice

**Mission** : Creer une boucle de devinettes.

Ouvre `exercise_07/agent.py` et complete les `# TODO`.

Le concept : un agent `riddle_master` pose des devinettes, et un agent `guesser` essaie de deviner. La boucle continue jusqu'a ce que le guesser trouve la bonne reponse (ou max 5 iterations).

1. `ask_riddle(tool_context: ToolContext) -> dict` : pose une devinette (mock), stocke la reponse dans `tool_context.state["answer"]`
2. `check_guess(guess: str, tool_context: ToolContext) -> dict` : compare avec state["answer"]. Si correct, appelle `tool_context.actions.escalate = True`
3. `riddle_master` : pose la devinette, `output_key="current_riddle"`
4. `guesser` : tente une reponse, lit `{current_riddle}` et `{hint}`
5. `root_agent` = `LoopAgent` avec `max_iterations=5`

Teste : "Start a riddle game"

## Quiz

Teste tes connaissances : ouvre [quiz/index.html](../quiz/index.html) dans ton navigateur et selectionne **Step 8**.
