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
def save_code(code: str) -> dict:
    """Saves the written code and returns metrics.

    Args:
        code: The Python source code to save.

    Returns:
        Dictionary with code metrics.
    """
    line_count = len(code.strip().splitlines())
    has_docstring = '"""' in code or "'''" in code
    return {
        "status": "success",
        "line_count": line_count,
        "has_docstring": has_docstring,
    }


def submit_review(score: int, feedback: str, verdict: str) -> dict:
    """Submits a code review with score and feedback.

    Args:
        score: Quality score from 1 to 10.
        feedback: Detailed review feedback.
        verdict: Either "APPROVED" or "NEEDS_IMPROVEMENT".

    Returns:
        Dictionary confirming the review.
    """
    return {
        "status": "success",
        "score": score,
        "feedback": feedback,
        "verdict": verdict,
    }


def submit_refactored_code(code: str, changes_made: str) -> dict:
    """Submits the refactored version of code with a summary of changes.

    Args:
        code: The refactored Python source code.
        changes_made: Summary of what was changed.

    Returns:
        Dictionary confirming the refactoring.
    """
    line_count = len(code.strip().splitlines())
    return {
        "status": "success",
        "line_count": line_count,
        "changes_made": changes_made,
    }


# --- Pipeline stages ---
writer_agent = Agent(
    name="writer",
    model="gemini-2.5-flash",
    description="Writes initial Python code.",
    instruction=(
        "Write Python code for the user's request. "
        "Then use save_code to save it. Present the code."
    ),
    tools=[save_code],
    output_key="generated_code",
)

reviewer_agent = Agent(
    name="reviewer",
    model="gemini-2.5-flash",
    description="Reviews Python code.",
    instruction=(
        "Review the following code for correctness, style, and potential improvements:\n\n"
        "{generated_code}\n\n"
        "Use submit_review to record your score (1-10), detailed feedback, "
        "and verdict (APPROVED or NEEDS_IMPROVEMENT)."
    ),
    tools=[submit_review],
    output_key="review_feedback",
)

refactorer_agent = Agent(
    name="refactorer",
    model="gemini-2.5-flash",
    description="Refactors code based on review feedback.",
    instruction=(
        "Refactor the code below based on the review feedback.\n\n"
        "Original code:\n{generated_code}\n\n"
        "Review feedback:\n{review_feedback}\n\n"
        "Write the improved code and use submit_refactored_code to save it "
        "with a summary of what you changed."
    ),
    tools=[submit_refactored_code],
    output_key="final_code",
)

# --- SequentialAgent: writer -> reviewer -> refactorer ---
root_agent = SequentialAgent(
    name="code_pipeline",
    description="A sequential code writing, reviewing, and refactoring pipeline.",
    sub_agents=[writer_agent, reviewer_agent, refactorer_agent],
)
