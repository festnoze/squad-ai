"""Corrige exercice 8 - Callbacks guardrails."""

from typing import Optional

from google.adk.agents import Agent
from google.adk.agents.context import Context
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.genai import types

FORBIDDEN_WORDS = ["badword", "inappropriate", "offensive"]


def rate_limiter(context: Context, llm_request: LlmRequest) -> Optional[LlmResponse]:
    """Blocks requests after 5 messages in the session."""
    count = context.state.get("message_count", 0) + 1
    context.state["message_count"] = count
    if count > 5:
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=f"Rate limit atteint ! ({count}/5 messages max)")],
            )
        )
    return None


def content_filter(tool: BaseTool, args: dict, context: Context) -> Optional[dict]:
    """Blocks tool execution if arguments contain forbidden words."""
    for value in args.values():
        if isinstance(value, str):
            for word in FORBIDDEN_WORDS:
                if word in value.lower():
                    return {"status": "blocked", "message": f"Contenu inapproprie detecte: '{word}'."}
    return None


def log_response(context: Context, llm_response: LlmResponse) -> Optional[LlmResponse]:
    """Logs the LLM response without modifying it."""
    if llm_response.content and llm_response.content.parts:
        text = llm_response.content.parts[0].text or ""
        print(f"[LOG] Agent {context.agent_name}: {text[:100]}...")
    return None


def echo_message(message: str) -> dict:
    """Echoes the user message with a comment.

    Args:
        message: The message to echo.

    Returns:
        Dictionary with the echoed message.
    """
    return {"status": "success", "echo": message, "comment": "Message bien recu !"}


root_agent = Agent(
    name="guarded_chat",
    model="gemini-2.5-flash",
    description="A chat agent with rate limiting, content filtering, and response logging.",
    instruction=(
        "You are a helpful chat assistant. Use echo_message to acknowledge user messages.\n"
        "Be brief and friendly."
    ),
    tools=[echo_message],
    before_model_callback=rate_limiter,
    before_tool_callback=content_filter,
    after_model_callback=log_response,
)
