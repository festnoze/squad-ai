# Tools Reference

## Table of Contents
- [Function Tools](#function-tools)
- [Parameter Types](#parameter-types)
- [ToolContext](#toolcontext)
- [LongRunningFunctionTool](#longrunningfunctiontool)
- [Built-in Tools](#built-in-tools)
- [AgentTool](#agenttool)
- [OpenAPI Tools](#openapi-tools)
- [MCP Tools](#mcp-tools)
- [Best Practices](#best-practices)

## Function Tools

Plain Python functions are automatically wrapped as `FunctionTool` when added to an agent's `tools` list. The framework inspects function name, docstring, parameter names, type hints, and defaults to generate the LLM schema.

```python
from google.adk.agents import Agent

def get_weather(city: str) -> dict:
    """Retrieves the current weather report for a specified city.

    Args:
        city (str): The name of the city.

    Returns:
        dict: status and result or error msg.
    """
    if city.lower() == "new york":
        return {
            "status": "success",
            "report": "The weather in New York is sunny, 25C (77F)."
        }
    return {
        "status": "error",
        "error_message": f"Weather information for '{city}' is not available."
    }

root_agent = Agent(
    name="weather_agent",
    model="gemini-2.0-flash",
    instruction="You answer weather questions.",
    tools=[get_weather]
)
```

**Return types:**
- Preferred: `dict` with `"status"` key (`"success"`, `"error"`, `"pending"`)
- Non-dict returns are auto-wrapped as `{"result": value}`

## Parameter Types

### Required parameters
Parameters with type hints but no default:

```python
def get_weather(city: str, unit: str):
    """Get weather.
    Args:
        city (str): The city name.
        unit (str): Temperature unit, 'Celsius' or 'Fahrenheit'.
    """
```

### Optional parameters (with defaults)

```python
def search_flights(destination: str, departure_date: str, flexible_days: int = 0):
    """Search for flights.
    Args:
        destination (str): The destination city.
        departure_date (str): The departure date.
        flexible_days (int, optional): Flexibility window. Defaults to 0.
    """
```

### Optional with typing.Optional

```python
from typing import Optional

def create_profile(username: str, bio: Optional[str] = None):
    """Create a user profile.
    Args:
        username (str): The username.
        bio (str, optional): Short biography. Defaults to None.
    """
```

## ToolContext

Tools can receive a `ToolContext` parameter for state access and flow control. The parameter is automatically injected and NOT exposed to the LLM.

```python
from google.adk.tools import ToolContext

def save_preference(preference: str, tool_context: ToolContext) -> dict:
    """Save user preference.
    Args:
        preference (str): The preference to save.
    """
    tool_context.state["user:preference"] = preference
    return {"status": "success", "message": f"Saved: {preference}"}
```

**ToolContext capabilities:**
- `tool_context.state` - Read/write session state (supports all prefixes)
- `tool_context.actions.escalate = True` - Signal loop termination (LoopAgent)
- `tool_context.actions.transfer_to_agent = "AgentName"` - Transfer to another agent

**Passing data between tools via temp state:**
```python
def tool_a(query: str, tool_context: ToolContext) -> dict:
    """Process query."""
    tool_context.state["temp:processed"] = query.upper()
    return {"status": "success"}

def tool_b(tool_context: ToolContext) -> dict:
    """Use processed data."""
    data = tool_context.state.get("temp:processed", "")
    return {"status": "success", "result": data}
```

## LongRunningFunctionTool

For operations that take significant time (human approval, external API waits):

```python
from google.adk.tools import LongRunningFunctionTool

def ask_for_approval(purpose: str, amount: float) -> dict:
    """Ask for approval for a reimbursement."""
    return {
        "status": "pending",
        "approver": "Manager",
        "purpose": purpose,
        "amount": amount,
        "ticket_id": "approval-ticket-1"
    }

approval_tool = LongRunningFunctionTool(func=ask_for_approval)
```

Pauses agent execution, allowing the client to query progress and send intermediate/final responses.

## Built-in Tools

```python
from google.adk.tools import google_search, code_execution

agent = Agent(tools=[google_search])       # Web search
agent = Agent(tools=[code_execution])      # Code execution sandbox
```

## AgentTool

Nest specialized agents as tools within parent agents:

```python
from google.adk.tools import AgentTool

specialist = LlmAgent(
    name="DataAnalyst",
    model="gemini-2.5-flash",
    instruction="Analyze data and return insights."
)

parent = LlmAgent(
    name="Coordinator",
    model="gemini-2.5-flash",
    tools=[AgentTool(agent=specialist)]
)
```

## OpenAPI Tools

Integrate RESTful APIs using OpenAPI specifications with built-in authentication and schema validation.

## MCP Tools

Model Context Protocol tools for standardized integration with compatible services.

## Best Practices

1. **Minimize parameters**: Fewer, simpler params reduce LLM errors
2. **Use simple data types**: Prefer `str`, `int`, `float`, `bool` over custom classes
3. **Meaningful names**: Function and parameter names guide LLM understanding
4. **Comprehensive docstrings**: They ARE the tool description sent to the LLM
5. **Return dicts**: With `"status"` key for structured responses
6. **Async design**: Build for parallel execution when possible
