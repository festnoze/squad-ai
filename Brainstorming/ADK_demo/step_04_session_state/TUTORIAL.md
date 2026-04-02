# Step 3 - Session State et ToolContext

## Concepts

### ToolContext : le pont entre tools et state
Un tool peut acceder au state de la session en ajoutant `tool_context: ToolContext` comme **dernier parametre**. ADK l'injecte automatiquement - le LLM ne le voit PAS dans le schema.

```python
from google.adk.tools.tool_context import ToolContext

def save_item(item: str, tool_context: ToolContext) -> dict:
    """Sauvegarde un item."""
    tool_context.state["saved_item"] = item  # Ecriture dans le state
    return {"status": "success"}

def read_item(tool_context: ToolContext) -> dict:
    """Lit l'item sauvegarde."""
    item = tool_context.state.get("saved_item", "Rien")  # Lecture du state
    return {"status": "success", "item": item}
```

### Prefixes de state
| Prefixe | Portee | Persiste ? |
|---------|--------|-----------|
| (aucun) | Session courante | Depend du service |
| `user:` | Toutes les sessions d'un user | Oui (DB) |
| `app:` | Toutes les sessions, tous les users | Oui (DB) |
| `temp:` | Invocation courante uniquement | Jamais |

### Injection de state dans les instructions
Les `{cles}` dans l'instruction sont remplacees par les valeurs du state :

```python
root_agent = Agent(
    instruction="Le sujet actuel est : {topic}. Nombre de sujets : {count}.",
    # Si state["topic"] = "Python" et state["count"] = 3
    # -> Le LLM recoit : "Le sujet actuel est : Python. Nombre de sujets : 3."
)
```

### output_key : sauvegarder la reponse de l'agent
```python
root_agent = Agent(
    output_key="last_response",
    # -> La reponse texte de l'agent est automatiquement stockee dans state["last_response"]
)
```

## Exploration

Ouvre [agent.py](agent.py) et observe :
1. `save_specification` ecrit dans `tool_context.state`
2. `save_generated_code` lit le spec depuis le state
3. `{current_spec}` et `{spec_count}` dans l'instruction
4. `output_key="last_response"` sur le root_agent

## Prompts de test

Lance `adk web` -> `step_03_session_state`. Teste **dans cet ordre** (le state evolue entre les tours) :

| # | Prompt | Resultat attendu | Quoi observer |
|---|--------|-----------------|---------------|
| 1 | "Save spec: a function that sorts integers" | Confirmation de sauvegarde | `save_specification` appele, state["current_spec"] ecrit |
| 2 | "Generate the code" | Code Python base sur le spec sauvegarde | Le LLM ecrit le code, `save_generated_code` le stocke |
| 3 | "Save spec: a fibonacci calculator" | 2eme spec sauvegardee | spec_count passe a 2 |
| 4 | "Show session summary" | Historique des 2 specs | `get_session_summary` retourne spec_history avec 2 entrees |

**Point cle** : entre les tours 1 et 2, le state persiste. L'agent "se souvient" du spec.

## Exercice

**Mission** : Creer un agent `shopping_list` qui gere une liste de courses persistante.

Ouvre `exercise_03/agent.py` et complete les `# TODO`.

Tu dois creer :
1. `add_item(item: str, quantity: int, tool_context: ToolContext) -> dict` - ajoute a la liste
2. `remove_item(item: str, tool_context: ToolContext) -> dict` - retire de la liste
3. `show_list(tool_context: ToolContext) -> dict` - affiche la liste actuelle
4. Un `root_agent` avec `output_key="last_action"` et `{item_count}` dans l'instruction

Teste :
1. "Add 3 apples" -> ajoute
2. "Add 2 breads" -> ajoute
3. "Show my list" -> affiche les 2 items
4. "Remove apples" -> retire
5. "Show my list" -> ne montre que bread

## Quiz

Teste tes connaissances : ouvre [quiz/index.html](../quiz/index.html) dans ton navigateur et selectionne **Step 4**.
