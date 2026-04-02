# Step 4 - Delegation multi-agent

## Concepts

### sub_agents : creer une equipe
Un agent peut avoir des **sub-agents** specialises. L'agent parent (coordinateur) delegue les requetes aux bons specialistes :

```python
coordinator = Agent(
    name="coordinator",
    sub_agents=[specialist_a, specialist_b],  # L'equipe
    # PAS de tools ! Le coordinateur route, il ne fait rien lui-meme
)
```

### Le routing est base sur `description`
Le LLM du coordinateur lit le `description` de chaque sub-agent pour decider a qui deleguer. C'est pourquoi les descriptions doivent etre **claires et specifiques** :

```python
# BON - le LLM sait exactement quand deleguer ici
writer = Agent(
    description="Specialist in writing Python code from specifications. Delegate here for code generation.",
    ...
)

# MAUVAIS - trop vague, le LLM hesite
writer = Agent(
    description="Handles stuff.",
    ...
)
```

### transfer_to_agent
Quand le LLM decide de deleguer, il genere automatiquement un appel `transfer_to_agent(agent_name="code_writer")`. Tu n'as rien a coder pour ca - ADK le gere.

### Chaque sub-agent a ses propres tools
Le coordinateur n'a pas de tools. Chaque specialiste a les siens :

```
Coordinator (pas de tools)
  ├── Writer (tools: [save_code])
  ├── Reviewer (tools: [submit_review])
  └── Greeter (pas de tools, juste conversation)
```

### AgentTool : un agent comme tool

Il existe une **deuxieme facon** de faire collaborer des agents : `AgentTool`. Au lieu de deleguer le controle (sub_agents), on utilise un agent **comme un tool** :

```python
from google.adk.tools import AgentTool

specialist = Agent(
    name="data_analyst",
    model="gemini-2.5-flash",
    instruction="Analyze data and return insights."
)

parent = Agent(
    name="manager",
    model="gemini-2.5-flash",
    tools=[AgentTool(agent=specialist)],  # L'agent est un tool !
)
```

### sub_agents vs AgentTool - quelle difference ?

| | `sub_agents` | `AgentTool` |
|---|---|---|
| **Controle** | Le parent **transfere** le controle au sub-agent | Le parent **garde** le controle, l'agent-tool repond comme un tool |
| **Conversation** | Le sub-agent parle directement a l'utilisateur | Le parent recoit le resultat et le reformule |
| **Quand l'utiliser** | Routing dynamique, chaque agent a son propre flux | Besoin d'une "competence" specifique dans un flux plus large |
| **Analogie** | "Va voir ce collegue, il gere" | "Appelle ce collegue pour moi et rapporte-moi sa reponse" |

Un `AgentTool` peut aussi etre un appel a un autre LLM, un agent externe, une API... Le tool peut etre n'importe quoi tant que le retour est coherent avec sa docstring.

## Exploration

Ouvre [agent.py](agent.py) et observe :
1. `code_writer_agent` et `code_reviewer_agent` ont chacun leurs tools
2. `greeter_agent` n'a pas de tools (conversation simple)
3. Le `root_agent` (coordinator) a `sub_agents=[...]` mais PAS de `tools`
4. Les `description` expliquent clairement quand deleguer a chaque agent

> **Note** : cet exemple utilise `sub_agents` (delegation). Pour voir `AgentTool` en action, regarde la section bonus dans l'agent.py.

## Prompts de test

Lance `adk web` -> `step_04_multi_agent` :

| Prompt | Agent delegue | Quoi observer dans Events |
|--------|--------------|--------------------------|
| "Write me a fibonacci function" | `code_writer` | `transfer_to_agent(agent_name="code_writer")` puis appel `save_code` |
| "Review this code: def add(a,b): return a+b" | `code_reviewer` | `transfer_to_agent(agent_name="code_reviewer")` puis `submit_review` |
| "Hello, how are you?" | `greeter` | `transfer_to_agent(agent_name="greeter")` SANS appel de tool |
| "Write a sorting function and then review it" | Les 2 ? | Observe comment le coordinateur gere (delegue a un, puis l'autre ?) |
| "Explain this code: def fib(n): return n if n<2 else fib(n-1)+fib(n-2)" | `code_explainer` (AgentTool) | Pas de `transfer_to_agent` ! Le coordinateur appelle le tool et **reste en controle** |

**Point cle** : compare le comportement "Write me a function" (transfer_to_agent, le writer repond directement) vs "Explain this code" (tool call, le coordinateur reformule la reponse). C'est la difference `sub_agents` vs `AgentTool`.

## Exercice

**Mission** : Creer un bureau de traduction avec 3 traducteurs specialises.

Ouvre `exercise_04/agent.py` et complete les `# TODO`.

Tu dois creer :
1. Un `french_translator` avec un tool `translate_to_french(text: str) -> dict`
2. Un `spanish_translator` avec un tool `translate_to_spanish(text: str) -> dict`
3. Un `german_translator` avec un tool `translate_to_german(text: str) -> dict`
4. Un `root_agent` coordinateur qui delegue selon la langue demandee

Teste :
- "Translate 'Hello world' to French"
- "How do you say 'Good morning' in Spanish?"
- "Translate 'Thank you' to German"

## Quiz

Teste tes connaissances : ouvre [quiz/index.html](../quiz/index.html) dans ton navigateur et selectionne **Step 5**.
