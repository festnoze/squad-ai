from typing import Any, TypedDict

class ConversationState(TypedDict):
    """Represents the state of the conversation at any point."""

    history: list[tuple[str, str]]
    agent_scratchpad: dict[str, Any]

class PhoneConversationState(ConversationState):
    """Represents the state of the phone conversation at any point."""
    call_sid: str
    caller_phone: str
    user_input: str
