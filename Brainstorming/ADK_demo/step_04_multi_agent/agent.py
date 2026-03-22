"""Step 4 - Multi-Agent Delegation.

Concepts: sub_agents, description-based routing, transfer_to_agent,
          coordinator agent without tools.

Try in adk web:
  - "Write me a function to calculate fibonacci numbers"  -> delegates to code_writer
  - "Review this code: def add(a,b): return a+b"          -> delegates to code_reviewer
  - "Hello, how are you?"                                 -> delegates to greeter
"""

from google.adk.agents import Agent


# --- Tools for CodeWriter ---
def generate_code(specification: str) -> dict:
    """Generates Python code from a specification.

    Args:
        specification: What the code should do.

    Returns:
        Dictionary with the generated code.
    """
    mock_code = (
        f"def solution(data):\n"
        f'    """Generated for: {specification}"""\n'
        f"    return [x for x in data if x > 0]\n"
    )
    return {"status": "success", "code": mock_code}


# --- Tools for CodeReviewer ---
def review_code(code: str) -> dict:
    """Reviews Python code for correctness, style, and potential issues.

    Args:
        code: The Python source code to review.

    Returns:
        Dictionary with review findings and a score.
    """
    return {
        "status": "success",
        "score": 7,
        "issues": [
            {"severity": "warning", "message": "Function lacks type hints"},
            {"severity": "info", "message": "Consider adding a docstring"},
        ],
        "verdict": "NEEDS_IMPROVEMENT",
    }


# --- Sub-agents ---
code_writer_agent = Agent(
    name="code_writer",
    model="gemini-2.5-flash",
    description="Specialist in writing Python code from specifications. Delegate here for code generation tasks.",
    instruction=(
        "You are CodeWriter. When given a specification, use the generate_code tool "
        "to produce Python code. Present the result clearly."
    ),
    tools=[generate_code],
)

code_reviewer_agent = Agent(
    name="code_reviewer",
    model="gemini-2.5-flash",
    description="Specialist in reviewing Python code for quality. Delegate here for code review tasks.",
    instruction=(
        "You are CodeReviewer. When given code to review, use the review_code tool "
        "to evaluate it. Present the review findings with actionable suggestions."
    ),
    tools=[review_code],
)

greeter_agent = Agent(
    name="greeter",
    model="gemini-2.5-flash",
    description="Handles greetings and casual conversation. Delegate here for non-code requests.",
    instruction="You are a friendly greeter. Respond warmly and briefly to casual conversation.",
)

# --- Coordinator (root agent) - no tools, only routes ---
root_agent = Agent(
    name="coordinator",
    model="gemini-2.5-flash",
    description="Coordinates code writing and reviewing tasks.",
    instruction=(
        "You are the Code Forge Coordinator. Route requests to the right specialist:\n"
        "- Code writing/generation requests -> delegate to code_writer\n"
        "- Code review/analysis requests -> delegate to code_reviewer\n"
        "- Greetings and casual conversation -> delegate to greeter\n\n"
        "Always delegate. Never handle tasks yourself."
    ),
    sub_agents=[code_writer_agent, code_reviewer_agent, greeter_agent],
)
