"""Step 1 - Basic Agent with One Custom Tool.

Concepts: ADK project structure, Agent, root_agent, function-as-tool, docstrings as LLM schema.

Try in adk web:
  - "Write me a function that filters even numbers from a list"
  - "Generate code to reverse a string"
"""

from google.adk.agents import Agent


def save_code_snippet(code: str, language: str = "python") -> dict:
    """Saves a code snippet and returns confirmation with metadata.

    Use this tool after writing code to save it and get a quality summary.

    Args:
        code: The source code to save.
        language: The programming language of the code. Defaults to "python".

    Returns:
        A dictionary with save confirmation and code metrics.
    """
    line_count = len(code.strip().splitlines())
    has_docstring = '"""' in code or "'''" in code
    has_type_hints = "->" in code or ": str" in code or ": int" in code or ": list" in code
    return {
        "status": "success",
        "message": f"Code saved successfully ({line_count} lines, {language})",
        "metrics": {
            "line_count": line_count,
            "has_docstring": has_docstring,
            "has_type_hints": has_type_hints,
        },
    }


root_agent = Agent(
    name="code_writer",
    model="gemini-2.5-flash",
    description="An agent that writes Python code from specifications.",
    instruction=(
        "You are CodeWriter, a Python code generation assistant.\n"
        "When the user asks you to write code:\n"
        "1. Write the Python code yourself based on their specification\n"
        "2. Use the save_code_snippet tool to save it and get quality metrics\n"
        "3. Present the code and metrics to the user"
    ),
    tools=[save_code_snippet],
)
