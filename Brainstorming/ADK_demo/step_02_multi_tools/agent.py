"""Step 2 - Multiple Tools.

Concepts: Multiple tools on one agent, LLM-driven tool selection, docstrings as schema.

Try in adk web:
  - "Write a sorting function"              -> save_code_snippet
  - "Analyze the complexity of this code"   -> analyze_code_complexity
  - "What templates are available?"          -> list_code_templates
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
    has_type_hints = "->" in code
    return {
        "status": "success",
        "message": f"Code saved ({line_count} lines, {language})",
        "metrics": {
            "line_count": line_count,
            "has_docstring": has_docstring,
            "has_type_hints": has_type_hints,
        },
    }


def analyze_code_complexity(code: str) -> dict:
    """Analyzes the cyclomatic complexity of a given Python code snippet.

    Args:
        code: The Python source code to analyze.

    Returns:
        A dictionary with complexity metrics.
    """
    line_count = len(code.strip().splitlines())
    # Simple heuristic-based mock analysis
    indent_levels = max(line.count("    ") for line in code.splitlines() if line.strip())
    branch_keywords = sum(1 for word in ["if ", "elif ", "else:", "for ", "while ", "try:", "except"]
                          if word in code)
    complexity = max(1, branch_keywords + 1)
    return {
        "status": "success",
        "line_count": line_count,
        "cyclomatic_complexity": complexity,
        "nesting_depth": indent_levels,
        "rating": "A" if complexity <= 5 else "B" if complexity <= 10 else "C",
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
        "1. Write code yourself, then use save_code_snippet to save it\n"
        "2. Analyze code complexity using analyze_code_complexity\n"
        "3. List available templates using list_code_templates\n\n"
        "Choose the right tool based on the user's request."
    ),
    tools=[save_code_snippet, analyze_code_complexity, list_code_templates],
)
