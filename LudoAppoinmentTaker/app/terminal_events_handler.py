import base64
import io
import os
import json
import logging
#
from openai import OpenAI
from fastapi import WebSocket, WebSocketDisconnect
#
from app.speech.text_to_speech import get_text_to_speech_provider
from app.speech.speech_to_text import get_speech_to_text_provider
from app.agents.agents_graph import AgentsGraph
from app.managers.incoming_text_manager import IncomingTextManager
from app.managers.outgoing_text_manager import OutgoingTextManager
#
from app.api_client.studi_rag_inference_api_client import StudiRAGInferenceApiClient
from app.api_client.salesforce_api_client import SalesforceApiClient
from app.api_client.salesforce_api_client_interface import SalesforceApiClientInterface

class TerminalEventsHandler:
    # Class variables shared across instances
    compiled_graph = None # LangGraph workflow compilation
    incoming_text_processing : IncomingTextManager = None
    outgoing_text_processing : OutgoingTextManager = None
    
    def __init__(self, outgoing_text_func=None):
        # Instance variables
        self.logger = logging.getLogger(__name__)
        self.logger.info("TerminalEventsHandler logger started")
        
        # State tracking for this instance
        self.openai_client = None
        self.stream_states = {}
        self.active_streams = {}
        self.phones_by_call_sid = {}

        # Flags to track speaking state
        self.is_speaking = False  # Flag to track if system is currently speaking
        self.rag_interrupt_flag = {"interrupted": False}  # Flag to interrupt RAG streaming
        
        self.start_time = None         

        # Set OpenAI API key
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        os.environ['OPENAI_API_KEY'] = self.OPENAI_API_KEY

        # Initialize dependencies
        self.studi_rag_inference_api_client = StudiRAGInferenceApiClient()
        self.salesforce_api_client: SalesforceApiClientInterface = SalesforceApiClient()
        
        self.outgoing_text_processing = OutgoingTextManager(
            call_sid=None,
            outgoing_text_func=outgoing_text_func
        )

        self.compiled_graph = AgentsGraph(
                                    self.outgoing_text_processing,
                                    self.studi_rag_inference_api_client,
                                    self.salesforce_api_client,
                                    call_sid=None
                                ).graph

        self.incoming_text_processing = IncomingTextManager(
                                    outgoing_manager=self.outgoing_text_processing,
                                    agents_graph=self.compiled_graph,
                                    call_sid=None
                                )
                                
        if self.openai_client is None:
            self.openai_client = OpenAI(api_key=self.OPENAI_API_KEY)

        self.logger.info("TerminalEventsHandler initialized successfully.")

    def set_call_sid_and_phone_number(self, calling_phone_number: str, call_sid: str) -> None:
        # Store the caller's phone number and call SID so we can retrieve them later
        self.call_sid = call_sid
        self.phones_by_call_sid[call_sid] = calling_phone_number
        self.incoming_text_processing.set_call_sid(call_sid)
        self.incoming_text_processing.set_phone_number(calling_phone_number, call_sid)

    async def init_incoming_data_handler_async(self, calling_phone_number: str, call_sid: str) -> None:
        self.set_call_sid_and_phone_number(calling_phone_number, call_sid)

        self.outgoing_text_processing.run_background_streaming_worker()
        self.logger.info("Text stream manager initialized and started with optimized parameters")

        await self._handle_start_event_async(start_data={"callSid": call_sid, "streamSid": "terminal_stream_sid"})

        # Loop of input/output from and to the terminal
        while True:
            try:
                input_text = self.incoming_text()
                
                if input_text.lower() == "bye": 
                    break
                await self.process_incoming_text_async(media_data={"text": input_text})

            except Exception as e:
                self.logger.error(f"Error in terminal input loop: {e}")
                break

    def incoming_text() -> str:
        input_text = input("User: ")
        return input_text

    async def process_incoming_text_async(self, media_data: dict) -> None:
        """Handle the incoming of new text data from the terminal"""
        await self.incoming_text_processing.process_incoming_data_async(media_data)
    
    async def close_session_async(self):
        await self.outgoing_text_processing.stop_background_streaming_worker_async()
        if self.current_stream and self.current_stream in self.stream_states:
            self.logger.warning(f"Cleaning up state for stream {self.current_stream} due to handler exit/error.")
            del self.stream_states[self.current_stream]
    
    
    async def _handle_start_event_async(self, start_data: dict) -> str:
        """Handle the 'start' event from Twilio which begins a new call."""
        call_sid = start_data.get("callSid")
        stream_sid = start_data.get("streamSid")
        await self.incoming_text_processing.init_conversation_async(call_sid, stream_sid)
        return stream_sid
   
    async def _handle_stop_event_async(self):
        """Handle the stop event from Twilio which ends a call"""
        if not self.current_stream:
            self.logger.error("Received stop event but no active stream")
            return
            
        self.logger.info(f"Received stop event for stream: {self.current_stream}")
        if self.current_stream in self.stream_states:
            del self.stream_states[self.current_stream]
            self.logger.info(f"Cleaned up state for stream {self.current_stream}")
        else:
            self.logger.error(f"Received stop for unknown or already cleaned stream: {self.current_stream}")
            
        self.current_stream = None
        self.incoming_text_processing.set_call_sid(None)
        self.logger.info("Reset TextProcessing call SID as call ended")