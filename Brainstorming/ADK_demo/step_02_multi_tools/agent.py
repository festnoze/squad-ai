"""Step 2 - Multiple Tools.

Concepts: Multiple tools on one agent, LLM-driven tool selection, docstrings as schema.

Try in adk web:
  - "Write a sorting function"              -> generate_code_snippet
  - "Analyze the complexity of this code"   -> analyze_code_complexity
  - "What templates are available?"          -> list_code_templates
"""

from google.adk.agents import Agent


def generate_code_snippet(specification: str) -> dict:
    """Generates a Python code snippet from a natural-language specification.

    Args:
        specification: A plain-English description of the desired functionality.

    Returns:
        A dictionary containing the generated Python code.
    """
    mock_code = (
        f"def solution(data):\n"
        f'    """Generated for: {specification}"""\n'
        f"    return data\n"
    )
    return {"status": "success", "code": mock_code}


def analyze_code_complexity(code: str) -> dict:
    """Analyzes the cyclomatic complexity of a given Python code snippet.

    Args:
        code: The Python source code to analyze.

    Returns:
        A dictionary with complexity metrics.
    """
    line_count = len(code.strip().splitlines())
    return {
        "status": "success",
        "line_count": line_count,
        "cyclomatic_complexity": 3,
        "maintainability_index": 72.5,
        "rating": "A",
    }


def list_code_templates() -> dict:
    """Lists all available Python code templates.

    Returns:
        A dictionary with template names and descriptions.
    """
    return {
        "status": "success",
        "templates": [
            {"name": "rest_api", "description": "Flask REST API boilerplate"},
            {"name": "cli_tool", "description": "Click CLI application skeleton"},
            {"name": "data_pipeline", "description": "Pandas ETL pipeline"},
            {"name": "unit_tests", "description": "pytest test suite scaffold"},
        ],
    }


root_agent = Agent(
    name="code_writer_v2",
    model="gemini-2.5-flash",
    description="An agent that writes, analyzes, and manages Python code.",
    instruction=(
        "You are CodeWriter v2, a Python code assistant with three capabilities:\n"
        "1. Generate code from specifications using generate_code_snippet\n"
        "2. Analyze code complexity using analyze_code_complexity\n"
        "3. List available templates using list_code_templates\n\n"
        "Choose the right tool based on the user's request."
    ),
    tools=[generate_code_snippet, analyze_code_complexity, list_code_templates],
)
