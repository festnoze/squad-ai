"""Step 1 - Basic Agent with One Custom Tool.

Concepts: ADK project structure, Agent, root_agent, function-as-tool, docstrings as LLM schema.

Try in adk web:
  - "Write me a function that filters even numbers from a list"
  - "Generate code to reverse a string"
"""

from google.adk.agents import Agent


def generate_code_snippet(specification: str) -> dict:
    """Generates a Python code snippet from a natural-language specification.

    Args:
        specification: A plain-English description of the desired functionality.

    Returns:
        A dictionary containing the generated Python code.
    """
    # Mock implementation - returns a simple function scaffold
    mock_code = (
        f"def solution(data):\n"
        f'    """Generated from spec: {specification}"""\n'
        f"    result = []\n"
        f"    for item in data:\n"
        f"        result.append(item)\n"
        f"    return result\n"
    )
    return {"status": "success", "code": mock_code}


root_agent = Agent(
    name="code_writer",
    model="gemini-2.5-flash",
    description="An agent that writes Python code from specifications.",
    instruction=(
        "You are CodeWriter, a Python code generation assistant.\n"
        "When the user gives you a specification, use the generate_code_snippet tool "
        "to produce the code. Then present the code to the user with a brief explanation."
    ),
    tools=[generate_code_snippet],
)
