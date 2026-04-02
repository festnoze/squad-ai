"""Step 3 - Session State and ToolContext.

Concepts: ToolContext, state read/write, {state_var} templating in instructions,
          output_key, temp: prefix for invocation-scoped state.

Try in adk web:
  - "Save spec: a function that sorts a list of integers"
  - "Now generate the code"              (uses saved spec from state)
  - "Show me the session summary"        (reads state history)
"""

from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext


def save_specification(specification: str, tool_context: ToolContext) -> dict:
    """Saves a code specification to the session for later reference.

    Args:
        specification: The code specification to store.

    Returns:
        Confirmation that the specification was saved.
    """
    tool_context.state["current_spec"] = specification

    history = tool_context.state.get("spec_history", [])
    history.append(specification)
    tool_context.state["spec_history"] = history
    tool_context.state["spec_count"] = len(history)

    return {
        "status": "success",
        "message": f"Specification saved. Total specs: {len(history)}",
    }


def save_generated_code(code: str, tool_context: ToolContext) -> dict:
    """Saves generated code to the session state for tracking.

    Args:
        code: The Python code to save.

    Returns:
        Confirmation with code metrics.
    """
    tool_context.state["last_code"] = code
    spec = tool_context.state.get("current_spec", "unknown")
    # temp: prefix = only available during this invocation
    tool_context.state["temp:just_saved"] = True
    line_count = len(code.strip().splitlines())
    return {
        "status": "success",
        "message": f"Code saved ({line_count} lines) for spec: {spec}",
    }


def get_session_summary(tool_context: ToolContext) -> dict:
    """Returns a summary of the current session state.

    Returns:
        Dictionary with session information.
    """
    return {
        "status": "success",
        "current_spec": tool_context.state.get("current_spec", "None"),
        "spec_count": tool_context.state.get("spec_count", 0),
        "spec_history": tool_context.state.get("spec_history", []),
        "has_code": tool_context.state.get("last_code") is not None,
    }


root_agent = Agent(
    name="stateful_code_writer",
    model="gemini-2.5-flash",
    description="A code writer that remembers specifications across turns.",
    instruction=(
        "You are CodeWriter with memory. You can save specifications "
        "and generate code from them later.\n\n"
        "Current specification: {current_spec}\n"
        "Total specifications saved: {spec_count}\n\n"
        "Workflow:\n"
        "1. When the user provides a spec, use save_specification to store it\n"
        "2. When asked to generate code, write the code yourself based on the saved spec, "
        "then use save_generated_code to save it\n"
        "3. When asked about session info, use get_session_summary"
    ),
    tools=[save_specification, save_generated_code, get_session_summary],
    output_key="last_response",
)
