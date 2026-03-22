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


def generate_code_from_state(tool_context: ToolContext) -> dict:
    """Generates code using the currently saved specification from session state.

    Returns:
        Dictionary with generated code or error if no spec is saved.
    """
    spec = tool_context.state.get("current_spec")
    if not spec:
        return {
            "status": "error",
            "message": "No specification saved. Use save_specification first.",
        }

    mock_code = (
        f"def solution(data):\n"
        f'    """Implements: {spec}"""\n'
        f"    return sorted(data)\n"
    )
    # temp: prefix = only available during this invocation
    tool_context.state["temp:last_generated_code"] = mock_code
    return {"status": "success", "code": mock_code, "based_on": spec}


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
        "2. When asked to generate code, use generate_code_from_state\n"
        "3. When asked about session info, use get_session_summary"
    ),
    tools=[save_specification, generate_code_from_state, get_session_summary],
    output_key="last_response",
)
