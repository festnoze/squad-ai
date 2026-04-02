"""Step 4 - Multi-Agent Delegation.

Concepts: sub_agents, description-based routing, transfer_to_agent,
          coordinator agent without tools, AgentTool.

Try in adk web:
  - "Write me a function to calculate fibonacci numbers"  -> delegates to code_writer
  - "Review this code: def add(a,b): return a+b"          -> delegates to code_reviewer
  - "Hello, how are you?"                                 -> delegates to greeter
  - "Summarize what this code does: def fib(n): ..."      -> uses code_explainer (AgentTool)
"""

from google.adk.agents import Agent
from google.adk.tools import AgentTool


# --- Tools for CodeWriter ---
def save_code(code: str, filename: str = "solution.py") -> dict:
    """Saves written code to a file and returns confirmation.

    Args:
        code: The Python source code to save.
        filename: The target filename. Defaults to "solution.py".

    Returns:
        Dictionary with save confirmation.
    """
    line_count = len(code.strip().splitlines())
    return {
        "status": "success",
        "message": f"Code saved to {filename} ({line_count} lines)",
    }


# --- Tools for CodeReviewer ---
def submit_review(score: int, issues: list[str], verdict: str) -> dict:
    """Submits a code review with score, issues found, and verdict.

    Args:
        score: Quality score from 1 to 10.
        issues: List of issues found in the code.
        verdict: Either "APPROVED" or "NEEDS_IMPROVEMENT".

    Returns:
        Dictionary confirming the review submission.
    """
    return {
        "status": "success",
        "message": f"Review submitted: {verdict} (score: {score}/10, {len(issues)} issues)",
    }


# --- Sub-agents ---
code_writer_agent = Agent(
    name="code_writer",
    model="gemini-2.5-flash",
    description="Specialist in writing Python code from specifications. Delegate here for code generation tasks.",
    instruction=(
        "You are CodeWriter. When given a specification:\n"
        "1. Write the Python code yourself\n"
        "2. Use the save_code tool to save it\n"
        "3. Present the code to the user"
    ),
    tools=[save_code],
)

code_reviewer_agent = Agent(
    name="code_reviewer",
    model="gemini-2.5-flash",
    description="Specialist in reviewing Python code for quality. Delegate here for code review tasks.",
    instruction=(
        "You are CodeReviewer. When given code to review:\n"
        "1. Analyze the code for correctness, style, and potential issues\n"
        "2. Use submit_review to record your findings with a score (1-10), "
        "list of issues, and verdict (APPROVED or NEEDS_IMPROVEMENT)\n"
        "3. Present actionable suggestions to the user"
    ),
    tools=[submit_review],
)

greeter_agent = Agent(
    name="greeter",
    model="gemini-2.5-flash",
    description="Handles greetings and casual conversation. Delegate here for non-code requests.",
    instruction="You are a friendly greeter. Respond warmly and briefly to casual conversation.",
)

# --- AgentTool: an agent used AS a tool (parent keeps control) ---
# Unlike sub_agents (where control transfers), AgentTool lets the
# coordinator call a specialist and get a result back, like a function call.
code_explainer_agent = Agent(
    name="code_explainer",
    model="gemini-2.5-flash",
    description="Explains what a piece of code does in plain English.",
    instruction=(
        "You are a code explainer. When given code, explain what it does "
        "in simple, clear language. Be concise."
    ),
)

# --- Coordinator (root agent) ---
# - sub_agents: delegates control (writer, reviewer, greeter)
# - tools: AgentTool keeps control (explainer responds to coordinator)
root_agent = Agent(
    name="coordinator",
    model="gemini-2.5-flash",
    description="Coordinates code writing, reviewing, and explanation tasks.",
    instruction=(
        "You are the Code Forge Coordinator. Route requests to the right specialist:\n"
        "- Code writing/generation requests -> delegate to code_writer\n"
        "- Code review/analysis requests -> delegate to code_reviewer\n"
        "- Greetings and casual conversation -> delegate to greeter\n"
        "- Code explanation requests -> use the code_explainer tool (you stay in control)\n\n"
        "For writing/reviewing/greetings: always delegate.\n"
        "For explanations: use the code_explainer tool and present its answer."
    ),
    sub_agents=[code_writer_agent, code_reviewer_agent, greeter_agent],
    tools=[AgentTool(agent=code_explainer_agent)],
)
