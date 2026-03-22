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
    if tool.name == "generate_code":
        spec = args.get("specification", "")
        if len(spec.strip()) < 10:
            return {
                "status": "error",
                "message": "Specification too short (min 10 chars). Please provide more detail.",
            }
        for forbidden in ["hack", "exploit", "vulnerability"]:
            if forbidden in spec.lower():
                return {
                    "status": "blocked",
                    "message": f"Specification contains forbidden term: '{forbidden}'.",
                }
    return None  # Allow tool execution


# ============================================================
# TOOLS
# ============================================================


def generate_code(specification: str) -> dict:
    """Generates Python code from a specification.

    Args:
        specification: Detailed description of desired functionality.

    Returns:
        Dictionary with generated code.
    """
    return {
        "status": "success",
        "code": (
            f"def solution(data):\n"
            f'    """Generated for: {specification}"""\n'
            f"    return data\n"
        ),
    }


def review_code(code: str) -> dict:
    """Reviews Python code for quality.

    Args:
        code: Python source code to review.

    Returns:
        Dictionary with score and feedback.
    """
    return {"status": "success", "score": 8, "feedback": "Code looks good."}


# ============================================================
# AGENT WITH CALLBACKS
# ============================================================

root_agent = Agent(
    name="guarded_code_forge",
    model="gemini-2.5-flash",
    description="Code Forge with safety guardrails.",
    instruction=(
        "You are Code Forge with safety guardrails.\n"
        "You can generate and review Python code, but dangerous patterns are blocked.\n"
        "Use generate_code for code generation and review_code for reviews."
    ),
    tools=[generate_code, review_code],
    before_model_callback=safety_guardrail,
    before_tool_callback=validate_tool_args,
)
