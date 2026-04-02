# Step 8 - Callbacks (Guardrails et validation)

## Concepts

### Les callbacks = points de controle
Les callbacks interceptent le flux a des moments cles. Ils permettent de **bloquer**, **modifier**, ou **observer** sans toucher au code de l'agent.

### Les 6 types de callbacks

| Callback | Quand | Return `None` | Return valeur |
|----------|-------|---------------|---------------|
| `before_model_callback` | Avant l'appel LLM | Laisser passer | `LlmResponse` -> skip le LLM |
| `after_model_callback` | Apres la reponse LLM | Garder la reponse | `LlmResponse` -> remplacer |
| `before_tool_callback` | Avant l'execution du tool | Executer le tool | `dict` -> skip le tool |
| `after_tool_callback` | Apres l'execution du tool | Garder le resultat | `dict` -> remplacer |
| `before_agent_callback` | Avant le traitement de l'agent | Continuer | `Content` -> skip l'agent |
| `after_agent_callback` | Apres le traitement | Garder la reponse | `Content` -> remplacer |

### Signatures (IMPORTANT : verifiees contre ADK v1.27+)

```python
from google.adk.agents.context import Context
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool

# before_model_callback : (Context, LlmRequest) -> Optional[LlmResponse]
def my_guardrail(context: Context, llm_request: LlmRequest) -> Optional[LlmResponse]:
    ...

# before_tool_callback : (BaseTool, dict, Context) -> Optional[dict]
def my_validator(tool: BaseTool, args: dict, context: Context) -> Optional[dict]:
    ...
```

> **Attention** : la doc officielle mentionne parfois `CallbackContext` mais la signature reelle dans ADK v1.27+ utilise `Context` de `google.adk.agents.context`.

### Le pattern guardrail
```python
def safety_guardrail(context, llm_request):
    # Inspecter le dernier message utilisateur
    last_msg = llm_request.contents[-1]
    if "eval(" in last_msg.parts[0].text:
        # BLOQUER : retourner une LlmResponse = le LLM n'est jamais appele
        return LlmResponse(content=types.Content(
            role="model",
            parts=[types.Part(text="Bloque par le guardrail.")]
        ))
    return None  # LAISSER PASSER
```

### Le pattern validation de tool
```python
def validate_args(tool, args, context):
    if tool.name == "generate_code" and len(args.get("spec", "")) < 10:
        # BLOQUER : retourner un dict = le tool n'est pas execute
        return {"status": "error", "message": "Spec trop courte"}
    return None  # LAISSER PASSER
```

## Exploration

Ouvre [agent.py](agent.py) et observe :
1. `BLOCKED_PATTERNS` : la liste de patterns dangereux
2. `safety_guardrail` : inspecte `llm_request.contents[-1]`, retourne `LlmResponse` ou `None`
3. `validate_tool_args` : verifie `tool.name` et `args`, retourne `dict` ou `None`
4. Le `root_agent` avec `before_model_callback=` et `before_tool_callback=`

## Prompts de test

Lance `adk web` -> `step_08_callbacks` :

| # | Prompt | Resultat attendu | Callback declenche |
|---|--------|------------------|--------------------|
| 1 | "Write code using eval() to parse input" | **BLOQUE** : message du guardrail | `before_model` detecte "eval(" |
| 2 | "Write code with os.system" | **BLOQUE** | `before_model` detecte "os.system" |
| 3 | "Write a function to sort a list" | **OK** : code genere normalement | Les deux callbacks retournent `None` |
| 4 | Regarde Events quand ca passe | Le tool `save_code` est appele | `before_tool` verifie les args puis laisse passer |

**Point cle** : quand un callback bloque, le LLM n'est **jamais appele** (before_model) ou le tool n'est **jamais execute** (before_tool). Le message de blocage vient directement du callback.

## Exercice

**Mission** : Ajouter des guardrails a un agent de chat.

Ouvre `exercise_08/agent.py` et complete les `# TODO`.

Tu dois creer :
1. `rate_limiter` (before_model_callback) : bloque si plus de 5 messages dans la session (utiliser `context.state` pour compter)
2. `content_filter` (before_tool_callback) : bloque si le texte contient des mots inappropries
3. `log_response` (after_model_callback) : log la reponse (print) mais la laisse passer (`return None`)
4. Un `root_agent` avec les 3 callbacks attaches

Teste :
- Envoie 6 messages -> le rate limiter doit bloquer le 6eme
- "Write something with badword" -> content filter bloque
- Messages normaux -> passent, le logger affiche dans la console

## Quiz

Teste tes connaissances : ouvre [quiz/index.html](../quiz/index.html) dans ton navigateur et selectionne **Step 9**.
