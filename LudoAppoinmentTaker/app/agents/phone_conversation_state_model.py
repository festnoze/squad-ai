from typing import TypedDict, Annotated, Sequence
import operator

class ConversationState(TypedDict):
    """Represents the state of the conversation at any point."""
    history: Annotated[Sequence[tuple[str, str]], operator.add]
    agent_scratchpad: dict[str, any]

class PhoneConversationState(ConversationState):
    """Represents the state of the phone conversation at any point."""
    call_sid: str
    caller_phone: str
    user_input: str