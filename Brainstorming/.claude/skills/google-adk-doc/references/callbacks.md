# Callbacks Reference

## Table of Contents
- [Overview](#overview)
- [The Six Callback Types](#the-six-callback-types)
- [Callback Signatures](#callback-signatures)
- [Guardrail Example](#guardrail-example)
- [Tool Validation Example](#tool-validation-example)
- [Logging Example](#logging-example)
- [Registration](#registration)

## Overview

Callbacks are functions associated with agents to observe, customize, and control behavior at predefined execution points. They act as checkpoints without modifying core framework code.

## The Six Callback Types

| Callback | When | Return `None` | Return Value |
|----------|------|---------------|--------------|
| `before_agent_callback` | Before agent processing | Proceed normally | `Content` -> skip agent, use as output |
| `after_agent_callback` | After agent completes | Use original output | `Content` -> replace output |
| `before_model_callback` | Before LLM call | Proceed to LLM | `LlmResponse` -> skip LLM call |
| `after_model_callback` | After LLM response | Use original response | `LlmResponse` -> replace response |
| `before_tool_callback` | Before tool execution | Execute tool normally | `dict` -> skip tool, use as result |
| `after_tool_callback` | After tool execution | Use original result | `dict` -> replace result |

## Callback Signatures

All callbacks receive a `Context` object (from `google.adk.agents.context`). The exact signatures are:

```python
from google.adk.agents.context import Context
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool

# before_model_callback
def before_model(context: Context, llm_request: LlmRequest) -> Optional[LlmResponse]: ...

# after_model_callback
def after_model(context: Context, llm_response: LlmResponse) -> Optional[LlmResponse]: ...

# before_tool_callback
def before_tool(tool: BaseTool, args: dict, context: Context) -> Optional[dict]: ...

# after_tool_callback
def after_tool(tool: BaseTool, args: dict, context: Context, result: dict) -> Optional[dict]: ...

# before_agent_callback / after_agent_callback
def before_agent(context: Context) -> Optional[types.Content]: ...
```

## Guardrail Example

```python
from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.models import LlmResponse, LlmRequest
from google.genai import types
from typing import Optional

def before_model_guardrail(
    context: Context,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    if llm_request.contents and llm_request.contents[-1].role == 'user':
        message = llm_request.contents[-1].parts[0].text
        if "BLOCKED_WORD" in message.upper():
            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="Request blocked by guardrail.")]
                )
            )
    return None  # Proceed normally

agent = LlmAgent(
    name="GuardedAgent",
    model="gemini-2.5-flash",
    instruction="Be helpful.",
    before_model_callback=before_model_guardrail,
)
```

## Tool Validation Example

```python
from google.adk.agents.context import Context
from google.adk.tools.base_tool import BaseTool
from typing import Optional

def validate_tool_args(
    tool: BaseTool,
    args: dict,
    context: Context,
) -> Optional[dict]:
    if tool.name == "generate_code":
        spec = args.get("specification", "")
        if len(spec.strip()) < 10:
            return {"status": "error", "message": "Specification too short."}
    return None  # Allow tool execution

agent = LlmAgent(
    name="ValidatedAgent",
    model="gemini-2.5-flash",
    instruction="Be helpful.",
    before_tool_callback=validate_tool_args,
)
```

## Logging Example

```python
from google.adk.agents.context import Context
from google.genai import types
from typing import Optional

def log_before_agent(context: Context) -> Optional[types.Content]:
    print(f"Agent {context.agent_name} starting...")
    return None

def log_after_agent(context: Context) -> Optional[types.Content]:
    print(f"Agent {context.agent_name} finished.")
    return None

agent = LlmAgent(
    name="LoggedAgent",
    model="gemini-2.5-flash",
    instruction="Be helpful.",
    before_agent_callback=log_before_agent,
    after_agent_callback=log_after_agent,
)
```

## Registration

All callbacks are registered during agent creation via constructor parameters:

```python
agent = LlmAgent(
    name="MyAgent",
    model="gemini-2.5-flash",
    before_agent_callback=my_before_fn,
    after_agent_callback=my_after_fn,
    before_model_callback=my_before_model_fn,
    after_model_callback=my_after_model_fn,
    before_tool_callback=my_before_tool_fn,
    after_tool_callback=my_after_tool_fn,
)
```

Callbacks enable: observation/debugging via logging, customization by modifying request/response data, control via guardrails, state management through context, and integration with external systems.
