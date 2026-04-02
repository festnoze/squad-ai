# Step 1 - Agent basique avec un outil custom

## Concepts

### Structure d'un projet ADK
ADK attend une structure precise. Chaque agent est un **package Python** (un dossier avec `__init__.py`) :

```
ADK_demo/                  # <- on lance `adk web` depuis ici
  step_01_basic_agent/     # <- nom du dossier = nom dans le dropdown
    __init__.py            # <- doit contenir: from . import agent
    agent.py               # <- doit definir: root_agent
    .env                   # <- cle API
```

### L'objet Agent
```python
from google.adk.agents import Agent

root_agent = Agent(
    name="mon_agent",              # Identifiant unique
    model="gemini-2.5-flash",      # Le LLM utilise
    description="Ce que fait l'agent",  # Resume (utilise par les parents pour le routing)
    instruction="Tu es un assistant...",  # Le prompt systeme
    tools=[ma_fonction],           # Liste des outils
)
```

- `root_agent` est le nom de variable **obligatoire** qu'ADK cherche.
- `Agent` est un alias de `LlmAgent`.

### Les tools = des fonctions Python
N'importe quelle fonction Python peut devenir un outil :
- Le **nom** de la fonction = nom de l'outil pour le LLM
- La **docstring** = description de l'outil (critique pour le LLM !)
- Les **type hints** = schema des parametres
- Le **retour** prefere : un `dict` avec une cle `"status"`

```python
def get_weather(city: str) -> dict:
    """Recupere la meteo pour une ville.     # <- Le LLM lit ceci !

    Args:
        city: Le nom de la ville.            # <- Et ceci aussi !
    """
    return {"status": "success", "report": "Ensoleille, 25C"}
```

## Exploration

Ouvre [agent.py](agent.py) et observe :
1. L'import `from google.adk.agents import Agent`
2. La fonction `save_code_snippet` : regarde sa docstring et ses type hints
3. Le `root_agent` avec `tools=[save_code_snippet]`

## Prompts de test

Lance `adk web` -> `step_01_basic_agent` et teste ces prompts :

| Prompt | Resultat attendu | Quoi observer dans Events |
|--------|-----------------|--------------------------|
| "Write a function that filters even numbers" | Le LLM ecrit le code puis appelle `save_code_snippet` | Un appel tool avec le code en parametre `code` |
| "Generate code to reverse a string" | Code Python + metriques (line_count, has_docstring) | Le tool retourne des metriques, le LLM les presente |
| "Hello, how are you?" | Reponse conversationnelle, PAS d'appel tool | Aucun tool call dans Events (le LLM juge que c'est inutile) |

## Exercice

**Mission** : Creer un agent `poem_writer` qui genere des haikus sur un sujet donne.

Ouvre `exercise_01/agent.py` et complete les `# TODO`.

Tu dois :
1. Creer une fonction `generate_haiku(topic: str) -> dict` avec une bonne docstring
2. La fonction retourne un dict avec `status` et `haiku` (un haiku mock hardcode suffit)
3. Creer un `root_agent` nomme `"poem_writer"` qui utilise cet outil

Teste dans `adk web` en selectionnant `exercise_01` :
- "Write a haiku about the ocean"
- "Create a poem about coding"

## Quiz

Teste tes connaissances : ouvre [quiz/index.html](../quiz/index.html) dans ton navigateur et selectionne **Step 1**.
