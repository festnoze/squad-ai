import logging

from agents.phone_conversation_state_model import PhoneConversationState
from utils.envvar import EnvHelper


class ConsecutiveErrorManager:
    """Manager for tracking and handling consecutive errors in conversations."""

    def __init__(self, call_sid: str | None = None):
        self.logger = logging.getLogger(__name__)
        self.call_sid = call_sid or "N/A"

    def get_consecutive_error_count(self, state: PhoneConversationState) -> int:
        """Get the current consecutive error count from state."""
        return state.get("agent_scratchpad", {}).get("consecutive_error_count", 0)

    def increment_consecutive_error_count(self, state: PhoneConversationState) -> None:
        """Increment the consecutive error count in state."""
        if not state.get("agent_scratchpad", None):
            state["agent_scratchpad"] = {}
        current_count = self.get_consecutive_error_count(state)
        state["agent_scratchpad"]["consecutive_error_count"] = current_count + 1
        self.logger.warning(
            f"[{self.call_sid[-4:]}] Consecutive errors incremented to: {current_count + 1}"
        )

    def reset_consecutive_error_count(self, state: PhoneConversationState) -> None:
        """Reset the consecutive error count in state."""
        if not state.get("agent_scratchpad", None):
            state["agent_scratchpad"] = {}
        if state["agent_scratchpad"].get("consecutive_error_count", 0) > 0:
            self.logger.info(
                f"[{self.call_sid[-4:]}] Consecutive errors reset from: {state['agent_scratchpad']['consecutive_error_count']}"
            )
        state["agent_scratchpad"]["consecutive_error_count"] = 0

    def is_max_consecutive_errors_reached(self, state: PhoneConversationState) -> bool:
        """Check if consecutive errors have reached the maximum threshold."""
        max_errors = EnvHelper.get_max_consecutive_errors()
        current_count = self.get_consecutive_error_count(state)
        return current_count >= max_errors

    def get_max_consecutive_errors_threshold(self) -> int:
        """Get the maximum consecutive errors threshold from environment."""
        return EnvHelper.get_max_consecutive_errors()
