"""Step 7 - LoopAgent (Iteration with Escalate).

Concepts: LoopAgent, max_iterations, tool_context.actions.escalate,
          state persistence across iterations, feedback loop.

The loop: Writer generates/refines -> Reviewer scores -> if approved: escalate

Try in adk web:
  - "Write a function to sort a list"
  (Watch the loop iterate: write -> review -> refine -> review -> ... -> approved!)
"""

from google.adk.agents import Agent, LoopAgent
from google.adk.tools.tool_context import ToolContext


# --- Tools ---
def save_code(code: str, tool_context: ToolContext) -> dict:
    """Saves the written or refined code and tracks the iteration count.

    Args:
        code: The Python source code to save.

    Returns:
        Dictionary with save confirmation and iteration info.
    """
    iteration = tool_context.state.get("iteration", 0) + 1
    tool_context.state["iteration"] = iteration
    tool_context.state["current_code"] = code
    feedback = tool_context.state.get("review_feedback", "No prior feedback.")
    return {
        "status": "success",
        "iteration": iteration,
        "line_count": len(code.strip().splitlines()),
        "incorporated_feedback": feedback,
    }


def submit_review(score: int, feedback: str, tool_context: ToolContext) -> dict:
    """Submits a code review with a quality score.

    If the score is 8 or above, the code is approved.
    If below 8, the feedback is saved for the next iteration.

    Args:
        score: Quality score from 1 to 10.
        feedback: Detailed review feedback.

    Returns:
        Dictionary with review result.
    """
    tool_context.state["review_feedback"] = feedback
    tool_context.state["last_score"] = score
    if score >= 8:
        return {"status": "approved", "score": score, "feedback": feedback}
    return {"status": "needs_work", "score": score, "feedback": feedback}


def approve_code(tool_context: ToolContext) -> dict:
    """Approves the code and exits the refinement loop.

    Call this only when the code review score is 8 or above.

    Returns:
        Confirmation that the loop is complete.
    """
    tool_context.actions.escalate = True
    score = tool_context.state.get("last_score", "?")
    return {
        "status": "loop_complete",
        "message": f"Code approved with score {score}/10. Exiting refinement loop.",
    }


# --- Loop sub-agents ---
writer_in_loop = Agent(
    name="loop_writer",
    model="gemini-2.5-flash",
    description="Writes or refines code based on feedback.",
    instruction=(
        "You are a code writer in a refinement loop.\n"
        "Previous review feedback: {review_feedback}\n\n"
        "Write or improve Python code based on the user's original request "
        "and the feedback above. Then use save_code to save your code."
    ),
    tools=[save_code],
    output_key="current_code",
)

reviewer_in_loop = Agent(
    name="loop_reviewer",
    model="gemini-2.5-flash",
    description="Reviews code and decides if the loop should continue.",
    instruction=(
        "Review this code:\n\n{current_code}\n\n"
        "Use submit_review to give a score (1-10) and detailed feedback.\n"
        "- If score >= 8: also call approve_code to exit the loop\n"
        "- If score < 8: just provide the feedback (do NOT call approve_code)\n\n"
        "Be constructive but demanding. Look for: type hints, docstrings, "
        "error handling, edge cases, clean style."
    ),
    tools=[submit_review, approve_code],
    output_key="review_result",
)

# --- LoopAgent ---
root_agent = LoopAgent(
    name="refinement_loop",
    description="Iteratively writes and reviews code until quality passes.",
    sub_agents=[writer_in_loop, reviewer_in_loop],
    max_iterations=4,
)
