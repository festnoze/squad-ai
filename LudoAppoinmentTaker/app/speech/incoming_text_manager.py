# c:\Dev\squad-ai\LudoAppoinmentTaker\app\speech\incoming_text_manager.py
import logging
from typing import Optional, Any

from app.speech.incoming_manager import IncomingManager
from app.agents.agents_graph import AgentsGraph # Assuming this is your agent graph orchestrator

class IncomingTextManager(IncomingManager):
    """
    Manages incoming text data streams and passes the text to the agent graph.
    """
    def __init__(self, compiled_graph: AgentsGraph):
        super().__init__()
        self.compiled_graph = compiled_graph
        self.logger = logging.getLogger(__name__)
        self.logger.info("IncomingTextManager initialized.")

    async def process_data(self, data: Any, call_sid: Optional[str] = None) -> None:
        """
        Process incoming text data.

        Args:
            data: Text string.
            call_sid: Optional call SID for tracking the conversation.
        """
        if not self.is_active:
            self.logger.warning("Process_data called but manager is not active. Ignoring.")
            return

        if not isinstance(data, str):
            self.logger.error(f"Invalid data type for text processing: {type(data)}. Expected string.")
            return

        text_input = data.strip()
        if text_input:
            self.logger.info(f"Received Text Input: '{text_input}'")
            # Pass text to the agent graph
            await self.compiled_graph.process_user_input(
                text=text_input,
                conversation_id=self.get_conversation_id(), # from IncomingManager
                call_sid=call_sid or self.get_call_sid()    # from IncomingManager
            )
        else:
            self.logger.debug("Received empty text input.")

    async def start_stream(self, stream_sid: str, call_sid: Optional[str] = None) -> None:
        """Handle the start of a new text stream."""
        await super().start_stream(stream_sid, call_sid)
        self.logger.info(f"IncomingTextManager stream {stream_sid} started for call {call_sid}.")

    async def stop_stream(self) -> None:
        """Handle the end of a text stream."""
        await super().stop_stream()
        self.logger.info("IncomingTextManager stream stopped.")