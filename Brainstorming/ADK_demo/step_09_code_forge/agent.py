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
    if tool.name == "write_code":
        spec = args.get("specification", "")
        if len(spec.strip()) < 5:
            return {"status": "error", "message": "Specification too short."}
    return None


# ============================================================
# TOOLS
# ============================================================


def write_code(specification: str, tool_context: ToolContext) -> dict:
    """Writes Python code from a specification, incorporating prior feedback if available.

    Args:
        specification: Detailed description of what the code should do.

    Returns:
        Dictionary with the generated code.
    """
    iteration = tool_context.state.get("iteration", 0)
    feedback = tool_context.state.get("synthesis_report", "No prior feedback.")

    if iteration == 0:
        code = (
            f"def solution(data):\n"
            f'    """Spec: {specification}"""\n'
            f"    return data\n"
        )
    elif iteration == 1:
        code = (
            f"def solution(data):\n"
            f'    """Spec: {specification}"""\n'
            f"    if not data:\n"
            f"        raise ValueError('Empty input')\n"
            f"    return sorted(data)\n"
        )
    else:
        code = (
            f"def solution(data: list) -> list:\n"
            f'    """Spec: {specification}\n\n'
            f"    Args:\n"
            f"        data: Input list to process.\n\n"
            f"    Returns:\n"
            f"        Sorted list.\n\n"
            f"    Raises:\n"
            f"        TypeError: If input is not a list.\n"
            f"        ValueError: If input is empty.\n"
            f'    """\n'
            f"    if not isinstance(data, list):\n"
            f"        raise TypeError('Expected list')\n"
            f"    if not data:\n"
            f"        raise ValueError('Empty input')\n"
            f"    return sorted(data)\n"
        )

    tool_context.state["current_code"] = code
    tool_context.state["iteration"] = iteration + 1
    return {"status": "success", "code": code, "iteration": iteration + 1}


def check_security(code: str) -> dict:
    """Checks Python code for security vulnerabilities.

    Args:
        code: Python source code to analyze.

    Returns:
        Dictionary with security findings.
    """
    findings = []
    if "eval(" in code or "exec(" in code:
        findings.append({"severity": "CRITICAL", "issue": "Use of eval/exec"})
    if "f'" in code or 'f"' in code:
        findings.append({"severity": "HIGH", "issue": "Potential injection via f-strings"})
    if not findings:
        findings.append({"severity": "NONE", "issue": "No security issues found"})
    return {"status": "success", "findings": findings}


def check_performance(code: str) -> dict:
    """Analyzes Python code for performance issues.

    Args:
        code: Python source code to analyze.

    Returns:
        Dictionary with performance findings.
    """
    return {
        "status": "success",
        "findings": [
            {"severity": "LOW", "issue": "Consider using generator for large datasets"},
        ],
    }


def check_style(code: str) -> dict:
    """Reviews Python code for PEP 8 compliance and style.

    Args:
        code: Python source code to review.

    Returns:
        Dictionary with style findings.
    """
    findings = []
    if '"""' not in code:
        findings.append({"severity": "WARNING", "issue": "Missing docstring"})
    if "->" not in code:
        findings.append({"severity": "INFO", "issue": "Missing return type hint"})
    if not findings:
        findings.append({"severity": "NONE", "issue": "Style is clean"})
    return {"status": "success", "findings": findings}


def evaluate_and_decide(review_summary: str, tool_context: ToolContext) -> dict:
    """Evaluates the synthesis report and decides if code passes or needs more work.

    Args:
        review_summary: The combined review report.

    Returns:
        Dictionary with approval status.
    """
    iteration = tool_context.state.get("iteration", 1)
    if iteration >= 3:
        tool_context.actions.escalate = True
        return {"status": "approved", "message": "Code meets quality bar. Exiting loop."}
    return {
        "status": "needs_work",
        "message": f"Iteration {iteration}: Code needs further refinement.",
    }


def generate_tests(code: str) -> dict:
    """Generates pytest unit tests for the given code.

    Args:
        code: Python source code to generate tests for.

    Returns:
        Dictionary with the generated tests.
    """
    tests = (
        "import pytest\n\n\n"
        "def test_basic():\n"
        "    assert solution([3, 1, 2]) == [1, 2, 3]\n\n\n"
        "def test_empty():\n"
        "    with pytest.raises(ValueError):\n"
        "        solution([])\n\n\n"
        "def test_invalid_type():\n"
        "    with pytest.raises(TypeError):\n"
        '        solution("not a list")\n\n\n'
        "def test_single_element():\n"
        "    assert solution([42]) == [42]\n"
    )
    return {"status": "success", "tests": tests}


# ============================================================
# AGENTS
# ============================================================

# --- 1. CodeWriter (with guardrails) ---
code_writer = Agent(
    name="code_writer",
    model="gemini-2.5-flash",
    description="Generates Python code from a specification.",
    instruction=(
        "Write Python code for the user's request using the write_code tool.\n"
        "If there is prior feedback, incorporate it:\n"
        "Feedback: {synthesis_report}"
    ),
    tools=[write_code],
    output_key="current_code",
    before_model_callback=safety_guardrail,
    before_tool_callback=validate_tool_args,
)

# --- 2. Parallel Reviewers ---
security_reviewer = Agent(
    name="security_reviewer",
    model="gemini-2.5-flash",
    description="Security vulnerability scanner.",
    instruction="Analyze this code for security issues using check_security:\n\n{current_code}",
    tools=[check_security],
    output_key="security_review",
)

performance_reviewer = Agent(
    name="performance_reviewer",
    model="gemini-2.5-flash",
    description="Performance analyzer.",
    instruction="Analyze this code for performance issues using check_performance:\n\n{current_code}",
    tools=[check_performance],
    output_key="performance_review",
)

style_reviewer = Agent(
    name="style_reviewer",
    model="gemini-2.5-flash",
    description="Style and PEP 8 reviewer.",
    instruction="Review this code for style issues using check_style:\n\n{current_code}",
    tools=[check_style],
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
        "Then call evaluate_and_decide with your summary.\n"
        "If approved, present the final verdict.\n"
        "If needs_work, present feedback for the next iteration."
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
        "Generate pytest tests for the approved code using generate_tests:\n\n"
        "{current_code}\n\n"
        "Present the tests clearly."
    ),
    tools=[generate_tests],
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
