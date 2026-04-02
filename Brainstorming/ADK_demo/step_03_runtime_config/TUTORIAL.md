# Step 3 - Runtime, Configuration et Donnees avancees

## Concepts

### 1. generate_content_config : controle du LLM

Chaque agent peut configurer le comportement du LLM :

```python
from google.genai import types

agent = Agent(
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,        # 0=deterministe, 1=creatif
        max_output_tokens=500,  # Limite de la reponse
    )
)
```

| Parametre | Effet | Cas d'usage |
|-----------|-------|-------------|
| `temperature=0.2` | Precis, reproductible | Reviewer, analyseur |
| `temperature=0.9` | Creatif, varie | Writer, generateur |
| `max_output_tokens` | Limite la longueur | Eviter les reponses trop longues |

### 2. output_schema : reponses structurees

Forcer le LLM a retourner du JSON avec un schema Pydantic :

```python
from pydantic import BaseModel, Field

class CodeAnalysis(BaseModel):
    language: str = Field(description="Langage detecte")
    score: int = Field(description="Score de 1 a 10")
    issues: list[str] = Field(description="Problemes trouves")

agent = Agent(
    output_schema=CodeAnalysis,  # Le LLM DOIT retourner ce format
)
```

> **Note** : `output_schema` + `tools` ensemble n'est fiable que sur Gemini 3.0+.

### 3. Artifacts : fichiers binaires persistants

State = key-value texte. **Artifacts** = fichiers (images, PDF, rapports). Versiones automatiquement.

```python
# Sauvegarder (dans un tool async)
artifact = types.Part.from_text(text="Mon rapport...")
version = await tool_context.save_artifact("report.txt", artifact)

# Charger
artifact = await tool_context.load_artifact("report.txt")

# Lister
files = await tool_context.list_artifacts()  # ["report.txt", ...]
```

| | State | Artifacts |
|---|---|---|
| **Type** | Strings, nombres, listes | Fichiers binaires (images, PDF) |
| **Acces** | `tool_context.state["key"]` | `await tool_context.save/load_artifact()` |
| **Versioning** | Non | Oui (chaque save = nouvelle version) |
| **Scope** | Session ou `user:` | Session ou `user:` (prefixe "user:") |

### 4. Memory : memoire cross-sessions

State persiste dans UNE session. **Memory** persiste entre TOUTES les sessions.

```python
from google.adk.tools import load_memory

agent = Agent(
    tools=[load_memory],  # Tool built-in pour chercher dans la memoire
    instruction="Use load_memory if the answer might be in past conversations.",
)
```

| | State | Memory |
|---|---|---|
| **Portee** | 1 session | Toutes les sessions |
| **Recherche** | Par cle exacte | Par requete semantique |
| **Utilisation** | `tool_context.state` | `load_memory` tool |

### 5. Runner : execution programmatique

`adk web` est pour le dev. En production, on utilise **Runner** pour executer un agent depuis du code :

```python
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

runner = Runner(
    agent=root_agent,
    app_name="my_app",
    session_service=InMemorySessionService(),
)

# Executer
async for event in runner.run_async(
    user_id="user1",
    session_id="session1",
    new_message=types.Content(
        role="user",
        parts=[types.Part.from_text("Hello!")]
    ),
):
    if event.is_final_response():
        print(event.content.parts[0].text)
```

## Exploration

Ouvre [agent.py](agent.py) et observe :
1. `PRECISE_CONFIG` et `CREATIVE_CONFIG` : deux configurations de temperature
2. `CodeAnalysis` : schema Pydantic pour `output_schema`
3. Les 3 tools async d'artifacts : `asave_report_artifact`, `aload_report_artifact`, `alist_artifacts`
4. `load_memory` : tool built-in importe depuis ADK
5. Le `code_analyzer` avec `output_schema=CodeAnalysis`

## Prompts de test

Lance `adk web` -> `step_03_runtime_config` :

| Prompt | Resultat attendu | Quoi observer |
|--------|-----------------|---------------|
| "Save a report about Python best practices" | Appel `asave_report_artifact` | L'artifact est cree avec un numero de version |
| "List all saved artifacts" | Liste des fichiers sauvegardes | `alist_artifacts` retourne la liste |
| "Load the report" | Contenu du rapport | `aload_report_artifact` recupere le fichier |

## Exercice

**Mission** : Creer un agent `note_taker` qui sauvegarde des notes comme artifacts.

Ouvre `exercise_03/agent.py` et complete les `# TODO`.

1. `asave_note(title: str, content: str, tool_context)` : sauvegarde une note comme artifact
2. `aload_note(title: str, tool_context)` : charge une note
3. `alist_notes(tool_context)` : liste toutes les notes
4. Un `root_agent` avec `generate_content_config` a temperature basse (precision)

Teste :
- "Save a note titled 'meeting' with content 'Discuss roadmap Q2'"
- "List my notes"
- "Load the meeting note"

## Quiz

Teste tes connaissances : ouvre [quiz/index.html](../quiz/index.html) dans ton navigateur et selectionne **Step 3**.
