import logging
from app.managers.incoming_manager import IncomingManager
from app.agents.agents_graph import AgentsGraph
from app.managers.outgoing_manager import OutgoingManager

logger = logging.getLogger(__name__)

class IncomingTextManager(IncomingManager):

    def __init__(self, outgoing_manager: OutgoingManager, agents_graph: AgentsGraph, call_sid: str):
        super().__init__()
        self.agents_graph = agents_graph
        self.is_processing = False
        self.outgoing_manager = outgoing_manager
        self.call_sid = call_sid
        logger.info(f"IncomingTextManager initialized for call_sid: {call_sid}")

    async def process_incoming_data_async(self, text_data: str):
        """
        Processes incoming text data by sending it to the agent graph.
        """
        if not self.is_processing:
            logger.warning(f"IncomingTextManager for call {self.call_sid} is not processing. Ignoring data: {text_data}")
            return

        logger.info(f"IncomingTextManager received text for call {self.call_sid}: {text_data}")
        try:
            await self.agents_graph.ainvoke(
                {"data": text_data, "type": "text"}, 
                config={"configurable": {"thread_id": self.call_sid, "config_name": AGENT_REQUEST_RESPONSE_MODEL_CONFIG_NAME}}
            )
            logger.info(f"Text data processed by AgentsGraph for call {self.call_sid}")
        except Exception as e:
            logger.error(f"Error processing text data in IncomingTextManager for call {self.call_sid}: {e}", exc_info=True)

            
    def set_stream_sid(self, stream_sid: str) -> None:
        self.stream_sid = stream_sid
        self.outgoing_manager.update_stream_sid(stream_sid)        
        self.logger.info(f"Updated Incoming / Outgoing TextManagers to stream SID: {stream_sid}")

    def set_phone_number(self, phone_number: str, stream_sid: str) -> None:
        self.phone_number = phone_number
        self.phones_by_call_sid[stream_sid] = phone_number