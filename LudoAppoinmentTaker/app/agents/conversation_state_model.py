from typing import TypedDict, Dict, Any, Annotated, Sequence
from collections.abc import operator

class ConversationState(TypedDict):
    """Represents the state of the conversation at any point."""
    call_sid: str
    user_input: str
    history: Annotated[Sequence[tuple[str, str]], operator.add]
    agent_scratchpad: Dict[str, Any] 