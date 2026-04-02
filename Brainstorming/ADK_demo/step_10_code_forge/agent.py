"""Step 9 - Code Forge: Complete Pipeline.

Combines ALL concepts: Agent, tools, ToolContext, state, output_key, sub_agents,
SequentialAgent, ParallelAgent, LoopAgent, callbacks.

Architecture:
  code_forge (SequentialAgent)
    +-- refinement_loop (LoopAgent, max=3)
    |     +-- code_writer (LlmAgent + guardrails)
    |     +-- review_cycle (SequentialAgent)
    |           +-- parallel_reviewers (ParallelAgent)
    |           |     +-- security_reviewer
    |           |     +-- performance_reviewer
    |           |     +-- style_reviewer
    |           +-- synthesizer (evaluate_and_decide + escalate)
    +-- test_writer (LlmAgent)
    +-- final_presenter (LlmAgent)

Try in adk web:
  - "Write a function to validate email addresses"
  (Full pipeline: write -> parallel review -> refine loop -> tests -> final report)
"""

from typing import Optional

from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.agents.context import Context
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types


# ============================================================
# CALLBACKS (Guardrails)
# ============================================================

BLOCKED_PATTERNS = ["rm -rf", "os.system", "subprocess.call", "eval(", "exec("]


def safety_guardrail(
    context: Context,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """Blocks dangerous prompts before they reach the LLM."""
    if llm_request.contents:
        last_msg = llm_request.contents[-1]
        if last_msg.role == "user" and last_msg.parts:
            text = (last_msg.parts[0].text or "").lower()
            for p in BLOCKED_PATTERNS:
                if p.lower() in text:
                    return LlmResponse(
                        content=types.Content(
                            role="model",
                            parts=[types.Part(text=f"BLOCKED: dangerous pattern '{p}' detected.")],
                        )
                    )
    return None


def validate_tool_args(
    tool: BaseTool,
    args: dict,
    context: Context,
) -> Optional[dict]:
    """Validates tool arguments before execution."""
    if tool.name == "save_code":
        code = args.get("code", "")
        if len(code.strip()) < 5:
            return {"status": "error", "message": "Code too short."}
    return None


# ============================================================
# TOOLS
# ============================================================


def save_code(code: str, tool_context: ToolContext) -> dict:
    """Saves the written or refined code and tracks iteration count.

    Args:
        code: The Python source code to save.

    Returns:
        Dictionary with save confirmation.
    """
    iteration = tool_context.state.get("iteration", 0) + 1
    tool_context.state["iteration"] = iteration
    tool_context.state["current_code"] = code
    return {
        "status": "success",
        "iteration": iteration,
        "line_count": len(code.strip().splitlines()),
    }


def submit_security_findings(findings: list[str], risk_level: str) -> dict:
    """Submits security review findings.

    Args:
        findings: List of security issues found.
        risk_level: Risk level: "LOW", "MEDIUM", "HIGH", or "CRITICAL".

    Returns:
        Dictionary confirming the review.
    """
    return {"status": "success", "findings": findings, "risk_level": risk_level}


def submit_performance_findings(findings: list[str], rating: str) -> dict:
    """Submits performance review findings.

    Args:
        findings: List of performance issues or suggestions.
        rating: Rating: "GOOD", "ACCEPTABLE", or "NEEDS_WORK".

    Returns:
        Dictionary confirming the review.
    """
    return {"status": "success", "findings": findings, "rating": rating}


def submit_style_findings(findings: list[str], pep8_compliant: bool) -> dict:
    """Submits code style review findings.

    Args:
        findings: List of style issues found.
        pep8_compliant: Whether the code follows PEP 8.

    Returns:
        Dictionary confirming the review.
    """
    return {"status": "success", "findings": findings, "pep8_compliant": pep8_compliant}


def evaluate_and_decide(overall_score: int, summary: str, tool_context: ToolContext) -> dict:
    """Evaluates all reviews and decides if the code passes or needs more work.

    If overall_score >= 8, approves the code and exits the refinement loop.

    Args:
        overall_score: Combined score from 1 to 10 based on all reviews.
        summary: Summary of all review findings.

    Returns:
        Dictionary with approval status.
    """
    tool_context.state["synthesis_report"] = summary
    if overall_score >= 8:
        tool_context.actions.escalate = True
        return {"status": "approved", "score": overall_score, "message": "Code approved!"}
    return {
        "status": "needs_work",
        "score": overall_score,
        "message": "Code needs refinement. See feedback.",
    }


def save_tests(tests: str) -> dict:
    """Saves the generated test code.

    Args:
        tests: The pytest test source code.

    Returns:
        Dictionary with save confirmation.
    """
    line_count = len(tests.strip().splitlines())
    test_count = tests.count("def test_")
    return {
        "status": "success",
        "line_count": line_count,
        "test_count": test_count,
    }


# ============================================================
# AGENTS
# ============================================================

# --- 1. CodeWriter (with guardrails) ---
code_writer = Agent(
    name="code_writer",
    model="gemini-2.5-flash",
    description="Generates Python code from a specification.",
    instruction=(
        "Write Python code for the user's request.\n"
        "If there is prior feedback, incorporate it:\n"
        "Feedback: {synthesis_report}\n\n"
        "Then use save_code to save your code."
    ),
    tools=[save_code],
    output_key="current_code",
    before_model_callback=safety_guardrail,
    before_tool_callback=validate_tool_args,
)

# --- 2. Parallel Reviewers ---
security_reviewer = Agent(
    name="security_reviewer",
    model="gemini-2.5-flash",
    description="Security vulnerability scanner.",
    instruction=(
        "Analyze this code for security vulnerabilities:\n\n{current_code}\n\n"
        "Use submit_security_findings to record your findings and risk level."
    ),
    tools=[submit_security_findings],
    output_key="security_review",
)

performance_reviewer = Agent(
    name="performance_reviewer",
    model="gemini-2.5-flash",
    description="Performance analyzer.",
    instruction=(
        "Analyze this code for performance issues:\n\n{current_code}\n\n"
        "Use submit_performance_findings to record your findings and rating."
    ),
    tools=[submit_performance_findings],
    output_key="performance_review",
)

style_reviewer = Agent(
    name="style_reviewer",
    model="gemini-2.5-flash",
    description="Style and PEP 8 reviewer.",
    instruction=(
        "Review this code for style and PEP 8 compliance:\n\n{current_code}\n\n"
        "Use submit_style_findings to record your findings."
    ),
    tools=[submit_style_findings],
    output_key="style_review",
)

parallel_reviewers = ParallelAgent(
    name="parallel_reviewers",
    description="Runs security, performance, and style reviews concurrently.",
    sub_agents=[security_reviewer, performance_reviewer, style_reviewer],
)

# --- 3. Synthesizer + Gate ---
synthesizer = Agent(
    name="synthesizer",
    model="gemini-2.5-flash",
    description="Combines reviews and decides pass/fail.",
    instruction=(
        "Combine these reviews into a unified report:\n\n"
        "Security: {security_review}\n\n"
        "Performance: {performance_review}\n\n"
        "Style: {style_review}\n\n"
        "Give an overall score (1-10) and use evaluate_and_decide.\n"
        "Score >= 8 means approved, < 8 means needs work."
    ),
    tools=[evaluate_and_decide],
    output_key="synthesis_report",
)

# --- 4. Review cycle = parallel review + synthesis ---
review_cycle = SequentialAgent(
    name="review_cycle",
    description="One full review cycle: parallel reviewers then synthesis.",
    sub_agents=[parallel_reviewers, synthesizer],
)

# --- 5. Refinement loop = write + review cycle, repeated ---
refinement_loop = LoopAgent(
    name="refinement_loop",
    description="Iterates code writing and reviewing until approved.",
    sub_agents=[code_writer, review_cycle],
    max_iterations=3,
)

# --- 6. TestWriter (post-loop) ---
test_writer = Agent(
    name="test_writer",
    model="gemini-2.5-flash",
    description="Generates unit tests for the final code.",
    instruction=(
        "Write pytest unit tests for this code:\n\n"
        "{current_code}\n\n"
        "Cover normal cases, edge cases, and error cases. "
        "Use save_tests to save them."
    ),
    tools=[save_tests],
    output_key="generated_tests",
)

# --- 7. Final Presenter ---
final_presenter = Agent(
    name="final_presenter",
    model="gemini-2.5-flash",
    description="Presents the complete Code Forge output.",
    instruction=(
        "Present the complete Code Forge output:\n\n"
        "## Final Code\n{current_code}\n\n"
        "## Review Report\n{synthesis_report}\n\n"
        "## Unit Tests\n{generated_tests}\n\n"
        "Format everything clearly with markdown."
    ),
    output_key="final_output",
)

# ============================================================
# ROOT AGENT: Full Pipeline
# ============================================================
root_agent = SequentialAgent(
    name="code_forge",
    description="Complete Code Forge pipeline: write, review, refine, test.",
    sub_agents=[refinement_loop, test_writer, final_presenter],
)
