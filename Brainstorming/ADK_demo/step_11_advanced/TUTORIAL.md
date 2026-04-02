# Step 11 - Concepts avances

## Concepts

Ce step couvre les concepts avances d'ADK qui completent le toolkit. Chacun est present en reference avec un exemple minimal.

---

### 1. BaseAgent : agent custom

Quand `SequentialAgent`, `ParallelAgent` et `LoopAgent` ne suffisent pas, on cree un **agent custom** en heritant de `BaseAgent` :

```python
from google.adk.agents.base_agent import BaseAgent

class ConditionalAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        mood = ctx.session.state.get("user_mood", "neutral")
        if mood == "frustrated":
            async for event in self.empathy_agent.run_async(ctx):
                yield event
        else:
            async for event in self.standard_agent.run_async(ctx):
                yield event
```

**Quand l'utiliser :** conditions if/else, routing dynamique base sur le state, appels API directs, patterns d'orchestration non-standard.

---

### 2. LongRunningFunctionTool

Pour les operations qui prennent du temps (approbation humaine, API lente) :

```python
from google.adk.tools import LongRunningFunctionTool

def request_approval(purpose: str, amount: float) -> dict:
    """Requests human approval."""
    return {"status": "pending", "ticket_id": "APPROVAL-001"}

approval_tool = LongRunningFunctionTool(func=request_approval)
agent = Agent(tools=[approval_tool])
```

Le tool retourne `"status": "pending"`, l'agent **pause**, et le client peut envoyer la reponse d'approbation plus tard.

---

### 3. Plugins de securite

Plus robustes que les callbacks manuels (Step 9), les plugins s'appliquent a **tous** les agents :

| Plugin | Fonction |
|--------|----------|
| **Gemini-as-Judge** | Detecte prompt injection, jailbreak, contenu inapproprie |
| **PII Redaction** | Masque emails, telephones, SSN avant traitement |
| **Model Armor** | Verifie la securite via l'API Model Armor |

Les plugins sont **transversaux** (1 plugin protege tout le systeme) vs callbacks (par agent).

---

### 4. Evaluation (adk eval)

Tester systematiquement un agent avec des cas de test :

```bash
adk eval my_agent my_agent/eval_set.evalset.json
```

Fichier `eval_set.evalset.json` :
```json
[{
  "name": "test_basics",
  "data": [
    {"query": "Hello", "expected_response": "contains:Hi"},
    {"query": "What is 2+2?", "expected_response": "contains:4"}
  ]
}]
```

---

### 5. Streaming

Reponses en temps reel (token par token) pour l'UX en production :

```bash
adk run --streaming my_agent           # Terminal
POST /run_sse {"streaming": true}      # API
```

---

### 6. MCP Tools (Model Context Protocol)

Standard ouvert pour connecter des services externes comme tools :

```python
from google.adk.tools.mcp_tool import MCPTool
mcp_tool = MCPTool(server_url="http://localhost:3000", tool_name="search")
```

---

### 7. OpenAPI Tools

Integrer une API REST via sa specification OpenAPI :

```python
from google.adk.tools.openapi_tool import OpenAPITool
api_tool = OpenAPITool.from_spec(
    spec_url="https://api.example.com/openapi.json",
    operation_id="getUser"
)
```

---

### 8. A2A Protocol (Agent-to-Agent)

Communication entre agents de systemes differents. Un agent ADK peut etre expose comme service A2A :

```bash
adk deploy cloud_run --a2a  # Expose l'agent via le protocol A2A
```

---

### 9. Context caching / compression

Pour les longues conversations, ADK peut :
- **Cacher** le contexte pour eviter de re-traiter l'historique
- **Compresser** le contexte pour rester dans la fenetre du modele

---

## Exploration

Ouvre [agent.py](agent.py) et observe :
1. Le `LongRunningFunctionTool` wrappant `request_approval`
2. Les commentaires detaillant chaque concept avance
3. L'agent demo qui utilise `approval_tool` et `save_code`

## Prompts de test

Lance `adk web` -> `step_11_advanced` :

| Prompt | Resultat attendu | Quoi observer |
|--------|-----------------|---------------|
| "I need to buy a new laptop for $1200" | Appel `request_approval` avec status "pending" | Le tool retourne "pending", l'agent signale qu'il attend l'approbation |
| "Write a fibonacci function" | Code genere + `save_code` | Comportement classique pour comparaison |

## Quiz

Teste tes connaissances : ouvre [quiz/index.html](../quiz/index.html) dans ton navigateur et selectionne **Step 11**.
