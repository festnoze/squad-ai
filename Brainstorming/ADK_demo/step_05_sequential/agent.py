"""Step 5 - SequentialAgent (Deterministic Pipeline).

Concepts: SequentialAgent, output_key chaining, {state_var} templating,
          deterministic flow vs LLM-driven delegation.

Pipeline: Writer -> Reviewer -> Refactorer

Try in adk web:
  - "Write a function to merge two sorted lists"
  (The pipeline runs automatically: write -> review -> refactor)
"""

from google.adk.agents import Agent, SequentialAgent


# --- Tools ---
def generate_code(specification: str) -> dict:
    """Generates Python code from a specification.

    Args:
        specification: What the code should do.

    Returns:
        Dictionary with generated code.
    """
    return {
        "status": "success",
        "code": (
            f"def process(data):\n"
            f'    # {specification}\n'
            f"    return [x for x in data if x > 0]\n"
        ),
    }


def review_code(code: str) -> dict:
    """Reviews Python code and produces a critique with score.

    Args:
        code: The Python source code to review.

    Returns:
        Dictionary with score and feedback.
    """
    return {
        "status": "success",
        "score": 6,
        "feedback": (
            "Missing type hints. No error handling. "
            "List comprehension could use filter(). No docstring."
        ),
        "verdict": "NEEDS_IMPROVEMENT",
    }


def refactor_code(code: str, feedback: str) -> dict:
    """Refactors Python code based on review feedback.

    Args:
        code: The original Python source code.
        feedback: Review feedback to incorporate.

    Returns:
        Dictionary with the refactored code.
    """
    return {
        "status": "success",
        "refactored_code": (
            "def process(data: list[int]) -> list[int]:\n"
            '    """Filters positive integers from a list."""\n'
            "    if not isinstance(data, list):\n"
            "        raise TypeError('Expected a list')\n"
            "    return list(filter(lambda x: x > 0, data))\n"
        ),
    }


# --- Pipeline stages ---
writer_agent = Agent(
    name="writer",
    model="gemini-2.5-flash",
    description="Writes initial Python code.",
    instruction=(
        "Generate Python code for the user's request using the generate_code tool. "
        "Present only the code."
    ),
    tools=[generate_code],
    output_key="generated_code",
)

reviewer_agent = Agent(
    name="reviewer",
    model="gemini-2.5-flash",
    description="Reviews Python code.",
    instruction=(
        "Review the following code using the review_code tool:\n\n"
        "{generated_code}\n\n"
        "Provide detailed feedback."
    ),
    tools=[review_code],
    output_key="review_feedback",
)

refactorer_agent = Agent(
    name="refactorer",
    model="gemini-2.5-flash",
    description="Refactors code based on review feedback.",
    instruction=(
        "Refactor the code based on feedback using the refactor_code tool.\n\n"
        "Original code:\n{generated_code}\n\n"
        "Review feedback:\n{review_feedback}\n\n"
        "Present the improved code."
    ),
    tools=[refactor_code],
    output_key="final_code",
)

# --- SequentialAgent: writer -> reviewer -> refactorer ---
root_agent = SequentialAgent(
    name="code_pipeline",
    description="A sequential code writing, reviewing, and refactoring pipeline.",
    sub_agents=[writer_agent, reviewer_agent, refactorer_agent],
)
