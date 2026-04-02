"""Step 8 - Callbacks (Guardrails and Validation).

Concepts: before_model_callback (block dangerous prompts),
          before_tool_callback (validate arguments),
          returning LlmResponse/dict to override, None to proceed.

Try in adk web:
  - "Write code using eval() to parse input"   -> BLOCKED by model guardrail
  - "Write code with os.system"                 -> BLOCKED by model guardrail
  - "abc"                                       -> BLOCKED by tool validator (too short)
  - "Write a function to sort a list"           -> ALLOWED, proceeds normally
"""

from typing import Optional

from google.adk.agents import Agent
from google.adk.agents.context import Context
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.genai import types


# ============================================================
# CALLBACKS
# ============================================================

BLOCKED_PATTERNS = [
    "rm -rf",
    "os.system",
    "subprocess.call",
    "eval(",
    "exec(",
    "__import__",
]


def safety_guardrail(
    context: Context,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """Blocks prompts containing dangerous code patterns before they reach the LLM."""
    if llm_request.contents:
        last_message = llm_request.contents[-1]
        if last_message.role == "user" and last_message.parts:
            user_text = (last_message.parts[0].text or "").lower()
            for pattern in BLOCKED_PATTERNS:
                if pattern.lower() in user_text:
                    return LlmResponse(
                        content=types.Content(
                            role="model",
                            parts=[
                                types.Part(
                                    text=(
                                        f"BLOCKED: Your request contains a potentially "
                                        f"dangerous pattern ('{pattern}'). Code Forge does "
                                        f"not generate destructive or unsafe code. "
                                        f"Please rephrase your request."
                                    )
                                )
                            ],
                        )
                    )
    return None  # Allow the request


def validate_tool_args(
    tool: BaseTool,
    args: dict,
    context: Context,
) -> Optional[dict]:
    """Validates tool arguments before execution."""
    if tool.name == "save_code":
        code = args.get("code", "")
        if len(code.strip()) < 10:
            return {
                "status": "error",
                "message": "Code too short (min 10 chars). Please provide actual code.",
            }
    return None  # Allow tool execution


# ============================================================
# TOOLS
# ============================================================


def save_code(code: str) -> dict:
    """Saves written code and returns metrics.

    Args:
        code: The Python source code to save.

    Returns:
        Dictionary with save confirmation and metrics.
    """
    line_count = len(code.strip().splitlines())
    return {
        "status": "success",
        "message": f"Code saved ({line_count} lines)",
        "line_count": line_count,
    }


def submit_review(score: int, feedback: str) -> dict:
    """Submits a code review with score and feedback.

    Args:
        score: Quality score from 1 to 10.
        feedback: Review feedback.

    Returns:
        Dictionary confirming the review.
    """
    return {"status": "success", "score": score, "feedback": feedback}


# ============================================================
# AGENT WITH CALLBACKS
# ============================================================

root_agent = Agent(
    name="guarded_code_forge",
    model="gemini-2.5-flash",
    description="Code Forge with safety guardrails.",
    instruction=(
        "You are Code Forge with safety guardrails.\n"
        "You write and review Python code, but dangerous patterns are blocked.\n"
        "1. Write code yourself, then use save_code to save it\n"
        "2. Use submit_review to record code reviews"
    ),
    tools=[save_code, submit_review],
    before_model_callback=safety_guardrail,
    before_tool_callback=validate_tool_args,
)
