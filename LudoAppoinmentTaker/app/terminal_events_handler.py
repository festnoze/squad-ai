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

class TerminalEventsHandler:
    # Class variables shared across instances
    compiled_graph = None # LangGraph workflow compilation
    outgoing_text_processing : OutgoingTextManager = None
    incoming_text_processing : IncomingTextManager = None
    
    def __init__(self):
        # Instance variables
        self.logger = logging.getLogger(__name__)
        self.logger.info("TerminalEventsHandler logger started")
        
        # State tracking for this instance
        self.openai_client = None
        self.stream_states = {}
        self.active_streams = {}
        # Flags to track speaking state
        self.is_speaking = False  # Flag to track if system is currently speaking
        self.rag_interrupt_flag = {"interrupted": False}  # Flag to interrupt RAG streaming
        
        self.start_time = None         

        # Set OpenAI API key
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        os.environ['OPENAI_API_KEY'] = self.OPENAI_API_KEY

        # Set Google Calendar credentials
        self.project_root = os.path.dirname(os.path.dirname(__file__))
        self.google_calendar_credentials_filename = os.getenv(
            "GOOGLE_CALENDAR_CREDENTIALS_FILENAME", 
            "secrets/google-calendar-credentials.json"
        )
        self.google_calendar_credentials_path = os.path.join(self.project_root, self.google_calendar_credentials_filename)
        print(self.google_calendar_credentials_path)

        if os.path.exists(self.google_calendar_credentials_path):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = self.google_calendar_credentials_path
            self.logger.info(f"Set GOOGLE_APPLICATION_CREDENTIALS to: {self.google_calendar_credentials_path}")
        else:
            self.logger.error(f"/!\\ Google calendar credentials file not found at {self.google_calendar_credentials_path}")

        # Initialize dependencies
        self.studi_rag_inference_api_client = StudiRAGInferenceApiClient()
        self.salesforce_api_client = SalesforceApiClient()
        
        self.outgoing_text_processing = OutgoingTextManager(
                                    streamSid=None,
                                    min_chunk_interval=0.05,
                                    frame_rate=self.frame_rate,
                                    channels=self.channels
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

    async def init_incoming_text_handler(self, calling_phone_number: str, call_sid: str) -> None:
        # Store the caller's phone number and call SID so we can retrieve them later
        self.call_sid = call_sid
        self.phones[call_sid] = calling_phone_number
        self.incoming_text_processing.set_stream_sid(call_sid)
        self.incoming_text_processing.set_phone_number(calling_phone_number, call_sid)

        self.outgoing_text_processing.run_background_streaming_worker()
        self.logger.info("Text stream manager initialized and started with optimized parameters")

        # Main loop to handle WebSocket events
        try:            
            while True:
                try:
                    msg = await self.websocket.receive_text()
                    data = json.loads(msg)
                    if data is None:
                        continue
                except WebSocketDisconnect as disconnect_err:
                    self.logger.info(f"WebSocket disconnected: {self.websocket.client.host}:{self.websocket.client.port} - Code: {disconnect_err.code}")
                    break
                    
                event = data.get("event")
                if event == "connected":
                    self._handle_connected_event()
                elif event == "start":
                    await self._handle_start_event_async(data.get("start", {}))
                elif event == "media":
                    await self.incoming_text_async(data)
                elif event == "stop":
                    await self._handle_stop_event_async()
                    return
                elif event == "mark":
                    self._handle_mark_event(data)
                else:
                    self.logger.warning(f"Received unknown event type: {event}")

        except Exception as e:
            self.logger.error(f"Unhandled error in WebSocket handler: {e}", exc_info=True)
        finally:
            await self.outgoing_audio_processing.stop_background_streaming_worker_async()
            if self.current_stream and self.current_stream in self.stream_states:
                self.logger.warning(f"Cleaning up state for stream {self.current_stream} due to handler exit/error.")
                del self.stream_states[self.current_stream]
            self.logger.info(f"WebSocket handler finished for {self.websocket.client.host}:{self.websocket.client.port} (Stream: {self.current_stream})" )
    
    def _handle_connected_event(self):
        """Handle the 'connected' event from Twilio."""
        self.logger.info("Twilio WebSocket connected")
    
    async def _handle_start_event_async(self, start_data: dict) -> str:
        """Handle the 'start' event from Twilio which begins a new call."""
        call_sid = start_data.get("callSid")
        stream_sid = start_data.get("streamSid")
        await self.incoming_text_processing.handle_incoming_websocket_start_event_async(call_sid, stream_sid)
        return stream_sid

    async def incoming_text_async(self, media_data: dict) -> None:
        """Handle the 'media' event from Twilio which contains audio data."""
        await self.incoming_text_processing.process_incoming_data_async(media_data)
            
    def _is_websocket_connected(self) -> bool:
        """Check if the websocket is still connected"""
        if not self.websocket:
            return False            
        try:
            if hasattr(self.websocket, 'client_state'):
                if hasattr(self.websocket.client_state, 'CONNECTED'):
                    return True
                if isinstance(self.websocket.client_state, str):
                    return 'connect' in self.websocket.client_state.lower()
                return True
            if hasattr(self.websocket, 'closed'):
                return not self.websocket.closed
            return True
        except Exception as e:
            self.logger.error(f"Error checking websocket connection: {e}")
            return True
   
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
            
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                self.logger.error(f"Error closing websocket: {e}")
        
        self.current_stream = None
        self.incoming_audio_processing.set_stream_sid(None)
        self.logger.info("Reset AudioProcessing stream SID as call ended")

    def _handle_mark_event(self, data):
        mark_name = data.get("mark", {}).get("name")
        self.logger.debug(f"Received mark event: {mark_name} for stream {self.current_stream}")

        self.build_new_phone_call_websocket_events_handler()
        websocket_events_handler_to_return = self.websocket_events_handler_instance
        # Set the websocket for the handler
        websocket_events_handler_to_return.set_websocket(websocket)
        self.websocket_events_handler_instance = None
        return websocket_events_handler_to_return