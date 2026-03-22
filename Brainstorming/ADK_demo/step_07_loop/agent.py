"""Step 7 - LoopAgent (Iteration with Escalate).

Concepts: LoopAgent, max_iterations, tool_context.actions.escalate,
          state persistence across iterations, feedback loop.

The loop: Writer generates/refines -> Reviewer scores -> if score >= 8: escalate (exit loop)
Mock data simulates progressive improvement: scores 4 -> 6 -> 7 -> 9

Try in adk web:
  - "Write a function to sort a list"
  (Watch the loop iterate: write -> review -> refine -> review -> ... -> approved!)
"""

from google.adk.agents import Agent, LoopAgent
from google.adk.tools.tool_context import ToolContext


# --- Mock data: simulates progressive code improvement ---
CODE_VERSIONS = [
    "def sort(lst):\n    return sorted(lst)\n",
    (
        "def sort(lst: list) -> list:\n"
        "    return sorted(lst)\n"
    ),
    (
        "def sort(lst: list[int]) -> list[int]:\n"
        '    """Sorts a list of integers in ascending order."""\n'
        "    if not isinstance(lst, list):\n"
        "        raise TypeError('Expected a list')\n"
        "    return sorted(lst)\n"
    ),
    (
        "def sort(lst: list[int]) -> list[int]:\n"
        '    """Sorts a list of integers in ascending order.\n\n'
        "    Args:\n"
        "        lst: List of integers to sort.\n\n"
        "    Returns:\n"
        "        New sorted list.\n\n"
        "    Raises:\n"
        "        TypeError: If input is not a list.\n"
        '    """\n'
        "    if not isinstance(lst, list):\n"
        "        raise TypeError('Expected a list')\n"
        "    return sorted(lst)\n"
    ),
]

SCORES = [4, 6, 7, 9]


# --- Tools ---
def generate_or_refine_code(specification: str, tool_context: ToolContext) -> dict:
    """Generates or refines Python code based on specification and any prior feedback.

    Args:
        specification: What the code should do.

    Returns:
        Dictionary with the generated/refined code.
    """
    iteration = tool_context.state.get("iteration", 0)
    idx = min(iteration, len(CODE_VERSIONS) - 1)
    code = CODE_VERSIONS[idx]

    tool_context.state["current_code"] = code
    tool_context.state["iteration"] = iteration + 1
    feedback = tool_context.state.get("review_feedback", "No prior feedback.")

    return {
        "status": "success",
        "code": code,
        "iteration": iteration + 1,
        "incorporated_feedback": feedback,
    }


def review_and_score(code: str, tool_context: ToolContext) -> dict:
    """Reviews code and assigns a quality score from 1 to 10.

    Args:
        code: The Python code to review.

    Returns:
        Dictionary with score and feedback.
    """
    iteration = tool_context.state.get("iteration", 1) - 1
    idx = min(iteration, len(SCORES) - 1)
    score = SCORES[idx]

    if score < 8:
        feedback = (
            f"Score: {score}/10. Needs improvement: "
            "add type hints, docstrings, and error handling."
        )
        tool_context.state["review_feedback"] = feedback
        return {"status": "needs_work", "score": score, "feedback": feedback}
    else:
        tool_context.state["review_feedback"] = f"Score: {score}/10. Excellent code!"
        return {
            "status": "approved",
            "score": score,
            "feedback": "Code meets quality standards.",
        }


def exit_loop(tool_context: ToolContext) -> dict:
    """Signals that the code has passed review and the refinement loop should end.

    Returns:
        Confirmation that the loop is complete.
    """
    tool_context.actions.escalate = True
    return {"status": "loop_complete", "message": "Code approved. Exiting refinement loop."}


# --- Loop sub-agents ---
writer_in_loop = Agent(
    name="loop_writer",
    model="gemini-2.5-flash",
    description="Writes or refines code based on feedback.",
    instruction=(
        "Generate or refine Python code using the generate_or_refine_code tool.\n"
        "Previous feedback: {review_feedback}\n"
        "Use the feedback to improve the code."
    ),
    tools=[generate_or_refine_code],
    output_key="current_code",
)

reviewer_in_loop = Agent(
    name="loop_reviewer",
    model="gemini-2.5-flash",
    description="Reviews code and decides if the loop should continue.",
    instruction=(
        "Review the code using review_and_score:\n\n"
        "{current_code}\n\n"
        "If the score is 8 or above, call exit_loop to end the refinement process.\n"
        "If the score is below 8, just present the feedback (do NOT call exit_loop)."
    ),
    tools=[review_and_score, exit_loop],
    output_key="review_result",
)

# --- LoopAgent ---
root_agent = LoopAgent(
    name="refinement_loop",
    description="Iteratively writes and reviews code until quality passes.",
    sub_agents=[writer_in_loop, reviewer_in_loop],
    max_iterations=4,
)
