import logging
from app.managers.incoming_manager import IncomingManager
from app.agents.agents_graph import AgentsGraph

logger = logging.getLogger(__name__)

class IncomingTextManager(IncomingManager):
    
    def __init__(self, agents_graph: AgentsGraph, call_sid: str):
        super().__init__(call_sid)
        self.agents_graph = agents_graph
        self.is_processing = False
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