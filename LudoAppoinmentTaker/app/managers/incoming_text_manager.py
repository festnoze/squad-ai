import logging
from app.managers.incoming_manager import IncomingManager
from app.agents.agents_graph import AgentsGraph
from app.managers.outgoing_manager import OutgoingManager
from app.agents.phone_conversation_state_model import ConversationState, PhoneConversationState

class IncomingTextManager(IncomingManager):

    def __init__(self, outgoing_manager: OutgoingManager, agents_graph: AgentsGraph, call_sid: str):
        super().__init__()
        self.calls_states : dict[str, ConversationState] = {}
        self.agents_graph: AgentsGraph = agents_graph
        self.outgoing_manager: OutgoingManager = outgoing_manager
        self.call_sid: str = call_sid
        self.phones_by_call_sid: dict[str, str] = {}
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.logger.info(f"IncomingTextManager initialized for call_sid: {call_sid}")

    async def process_incoming_data_async(self, text_data: str):
        """
        Processes incoming text data by sending it to the agent graph.
        """
        self.logger.info(f"IncomingTextManager received text for call {self.call_sid}: {text_data}")
        try:
            # Get the current state
            if self.call_sid in self.calls_states:
                current_state : PhoneConversationState= self.calls_states[self.call_sid]
            else:
                current_state : PhoneConversationState = {
                    "call_sid": self.call_sid,
                    "caller_phone": self.phones_by_call_sid[self.call_sid],
                    "user_input": text_data,
                    "history": [], #TODO: Add history
                    "agent_scratchpad": {}
                }
                self.calls_states[self.call_sid] = current_state
                        
            # Invoke the graph with current state to get the AI-generated welcome message
            updated_state = await self.agents_graph.ainvoke(current_state)
            self.calls_states[self.call_sid] = updated_state
            self.logger.info(f"Text data processed by AgentsGraph for call {self.call_sid}")
        except Exception as e:
            self.logger.error(f"Error processing text data in IncomingTextManager for call {self.call_sid}: {e}", exc_info=True)
    
    async def init_conversation_async(self, call_sid: str, stream_sid: str) -> None:
        """Initialize a new conversation for the given call SID."""        
        phone_number = self.phones_by_call_sid.get(call_sid)
        if phone_number is None:
            self.logger.error(f"Phone number not found for call SID: {call_sid}")
            return None
        self.logger.info(f"--- Call started --- \nPhone number: {phone_number}, CallSid: {call_sid}, StreamSid: {stream_sid}.")
                
        # Get or Create the state for the graph
        if call_sid in self.calls_states:
            current_state = self.calls_states[call_sid]
        else:
            current_state: PhoneConversationState = PhoneConversationState(
                call_sid=call_sid,
                caller_phone=phone_number,
                user_input="",
                history=[], #TODO: Add history
                agent_scratchpad={}
            )
        
        self.calls_states[call_sid] = current_state        
        # Then invoke the graph with initial state to get the AI-generated welcome message
        try:            
            updated_state = await self.agents_graph.ainvoke(current_state)
            self.calls_states[call_sid] = updated_state

        except Exception as e:
            self.logger.error(f"Error in initial graph invocation: {e}", exc_info=True)
            
    def set_call_sid(self, call_sid: str) -> None:
        self.call_sid = call_sid       
        self.logger.info(f"Updated Incoming / Outgoing TextManagers to call SID: {call_sid}")

    def set_stream_sid(self, stream_sid: str) -> None:
        self.stream_sid = stream_sid
        self.outgoing_manager.update_stream_sid(stream_sid)        
        self.logger.info(f"Updated Incoming / Outgoing TextManagers to stream SID: {stream_sid}")

    def set_phone_number(self, phone_number: str, call_sid: str) -> None:
        self.phone_number = phone_number
        self.phones_by_call_sid[call_sid] = phone_number