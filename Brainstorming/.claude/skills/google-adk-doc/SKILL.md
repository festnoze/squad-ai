---
name: google-adk-doc
description: "Expert guide for Google's Agent Development Kit (ADK) Python - an open-source, code-first toolkit for building, evaluating, and deploying AI agents. Use when building ADK agents, creating multi-agent systems, implementing workflow agents (sequential, parallel, loop), integrating tools (google_search, code_execution, custom functions), deploying to Cloud Run or Vertex AI, managing sessions/state/memory, using callbacks for guardrails, or any task involving google.adk imports. Triggers on ADK, google adk, Agent Development Kit, adk agent, adk web, adk run, google.adk, LlmAgent, SequentialAgent, ParallelAgent, LoopAgent."
---

# Google ADK Python

Code-first toolkit for building, evaluating, and deploying AI agents. Optimized for Gemini models.

## Quick Reference

```bash
pip install google-adk          # Install
adk web                         # Dev UI at http://localhost:8000
adk run my_agent                # Terminal interaction
adk api_server                  # RESTful API server
```

## Project Structure

```
parent_folder/           # Run `adk web` from here
  my_agent/              # Agent package (folder name = agent name)
    __init__.py          # from . import agent
    agent.py             # Agent definition with root_agent variable
    .env                 # GOOGLE_API_KEY or Vertex AI config
```

`.env` (Google AI Studio):
```
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=YOUR_KEY_HERE
```

## Agent Types

### LlmAgent (aka Agent)
LLM-powered agent with dynamic routing, tool use, and adaptive behavior.

```python
from google.adk.agents import Agent

root_agent = Agent(
    name="assistant",
    model="gemini-2.5-flash",
    description="A helpful assistant.",        # Used by parent agents for routing
    instruction="Answer user questions.",       # Supports {state_var} templating
    tools=[my_tool],                           # Functions auto-wrapped as FunctionTool
    output_key="result",                       # Store response in session state
)
```

For full constructor parameters, dynamic instructions, and advanced config: see [references/agent-types.md](references/agent-types.md)

### Workflow Agents (non-LLM, deterministic)

- **SequentialAgent**: Execute sub-agents in order. Share data via `output_key` + `{state_var}`.
- **ParallelAgent**: Execute sub-agents concurrently. No automatic state sharing between branches.
- **LoopAgent**: Iterate sub-agents until `max_iterations` or `tool_context.actions.escalate = True`.

For patterns, examples, and data sharing: see [references/agent-types.md](references/agent-types.md)

## Tools

Plain Python functions are auto-wrapped as tools. Docstrings become tool descriptions.

```python
def get_weather(city: str) -> dict:
    """Retrieves weather for a city.

    Args:
        city (str): The city name.
    """
    return {"status": "success", "report": f"Sunny in {city}."}

agent = Agent(name="weather", model="gemini-2.5-flash", tools=[get_weather])
```

**Key rules:**
- Type hints + docstrings = LLM schema (critical for tool selection)
- Return `dict` with `"status"` key preferred
- Use `ToolContext` param for state access and flow control
- `LongRunningFunctionTool` for async/human-approval operations
- Built-in: `google_search`, `code_execution`
- `AgentTool` to nest agents as tools

For full tool patterns, ToolContext, and best practices: see [references/tools.md](references/tools.md)

## Sessions and State

State is a key-value scratchpad scoped by prefix:

| Prefix | Scope | Persistence |
|--------|-------|-------------|
| (none) | Current session | Service-dependent |
| `user:` | All sessions for user | DB/VertexAI |
| `app:` | All users/sessions | DB/VertexAI |
| `temp:` | Current invocation only | Never |

Access state in instructions via `{key}` templating. Store output via `output_key`. Modify state through `CallbackContext.state` or `ToolContext.state` (never directly on session objects).

For session services, state management patterns, and memory: see [references/sessions-state.md](references/sessions-state.md)

## Callbacks

Six callback types control agent behavior at execution checkpoints:

| Callback | Return None | Return Value |
|----------|-------------|--------------|
| `before/after_agent_callback` | Proceed | `Content` overrides |
| `before/after_model_callback` | Proceed | `LlmResponse` overrides |
| `before/after_tool_callback` | Proceed | `dict` overrides |

For callback signatures, guardrail examples, and patterns: see [references/callbacks.md](references/callbacks.md)

## Deployment

```bash
# Cloud Run (recommended)
adk deploy cloud_run --project=$PROJECT --region=$REGION --with_ui ./my_agent

# Evaluation
adk eval my_agent my_agent/eval_set.evalset.json
```

For Cloud Run with gcloud, Dockerfile, Vertex AI, and API testing: see [references/deployment.md](references/deployment.md)

## Model Support

Optimized for Gemini: `gemini-2.5-flash` (recommended), `gemini-2.5-pro`, `gemini-2.0-flash`. Model-agnostic via standard APIs.

## Resources

- GitHub: https://github.com/google/adk-python
- Docs: https://google.github.io/adk-docs/
