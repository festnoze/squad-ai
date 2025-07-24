import os
import logging
import json
#
from openai import OpenAI
from fastapi import WebSocket, WebSocketDisconnect
#
from utils.envvar import EnvHelper
from speech.text_to_speech import get_text_to_speech_provider
from speech.speech_to_text import get_speech_to_text_provider
from agents.agents_graph import AgentsGraph
from managers.incoming_audio_manager import IncomingAudioManager
from managers.outgoing_audio_manager import OutgoingAudioManager
#from managers.transcription_manager import TranscriptionManager
#
from api_client.studi_rag_inference_api_client import StudiRAGInferenceApiClient
from api_client.salesforce_api_client_interface import SalesforceApiClientInterface
from api_client.salesforce_api_client_fake import SalesforceApiClientFake
from api_client.salesforce_api_client import SalesforceApiClient

class PhoneCallWebsocketEventsHandler:
    # Class variables shared across instances
    compiled_graph = None # LangGraph workflow compilation
    outgoing_audio_processing : OutgoingAudioManager = None
    incoming_audio_processing : IncomingAudioManager = None
    
    def __init__(self, websocket: WebSocket = None):
        # Instance variables
        self.websocket = websocket
        self.logger = logging.getLogger(__name__)
        self.logger.info("IncomingPhoneCallHandler logger started")
        #self.transcription_manager = TranscriptionManager()
        
        # State tracking for this instance
        self.openai_client = None
        self.stream_states = {}
        self.active_streams = {}
        # Flags to track speaking state
        self.is_speaking = False  # Flag to track if system is currently speaking
        self.rag_interrupt_flag = {"interrupted": False}  # Flag to interrupt RAG streaming
        
        # Set audio processing parameters as instance variables
        self.frame_rate = 8000  # Sample rate in Hz (8kHz is standard for telephony)
        self.sample_width = 2   # mu-law in 16 bits
        self.channels = 1       # Mono channel audio
        self.speech_threshold = 250  # Threshold for silence vs. speech
        self.min_audio_bytes_for_processing = 6400  # Minimum buffer size = ~400ms at 8kHz
        self.max_audio_bytes_for_processing = 150000  # Maximum buffer size = ~15s at 8kHz
        self.consecutive_silence_duration_ms = 0.0  # Count consecutive silence duration in milliseconds
        self.required_silence_ms_to_answer = 300  # Require 300ms of silence to process audio
        self.speech_chunk_duration_ms = 500  # Duration of each audio chunk in milliseconds
        
        self.audio_buffer = b""
        self.current_stream = None
        self.start_time = None

        # Environment and configuration settings
        self.OPENAI_API_KEY = EnvHelper.get_openai_api_key()
        os.environ['OPENAI_API_KEY'] = self.OPENAI_API_KEY

        # Set Google Calendar credentials (needed for STT)
        self.project_root = os.path.dirname(os.path.dirname(__file__))
        self.google_calendar_credentials_filename = "secrets/google-calendar-credentials.json"
        self.google_calendar_credentials_path = os.path.join(self.project_root, self.google_calendar_credentials_filename)

        if os.path.exists(self.google_calendar_credentials_path):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = self.google_calendar_credentials_path
            self.logger.info(f"Set GOOGLE_APPLICATION_CREDENTIALS to: {self.google_calendar_credentials_path}")
        else:
            self.logger.error(f"/!\\ Google calendar credentials file not found at {self.google_calendar_credentials_path}")

        # Initialize dependencies
        tts_provider_name = EnvHelper.get_text_to_speech_provider()
        stt_provider_name = EnvHelper.get_speech_to_text_provider()
        can_speech_be_interupted = EnvHelper.get_can_speech_be_interupted()
        self.tts_provider = get_text_to_speech_provider(provider_name=tts_provider_name, frame_rate=self.frame_rate, channels=self.channels, sample_width=self.sample_width)
        self.stt_provider = get_speech_to_text_provider(provider_name=stt_provider_name, language_code="fr-FR", frame_rate=self.frame_rate)
        
        self.studi_rag_inference_api_client = StudiRAGInferenceApiClient()
        self.salesforce_client: SalesforceApiClientInterface = SalesforceApiClient()
        
        self.outgoing_audio_processing = OutgoingAudioManager(
                                    websocket=self.websocket, 
                                    tts_provider=self.tts_provider,
                                    stream_sid=None,
                                    min_chunk_interval=0.05,
                                    can_speech_be_interupted=can_speech_be_interupted,
                                    sample_width=self.sample_width,
                                    frame_rate=self.frame_rate,
                                    channels=self.channels
                                )

        self.compiled_graph = AgentsGraph(
                                    self.outgoing_audio_processing,
                                    self.studi_rag_inference_api_client,
                                    self.salesforce_client,
                                    call_sid=None
                                ).graph

        self.incoming_audio_processing = IncomingAudioManager(
                                    websocket=self.websocket, 
                                    stt_provider=self.stt_provider,
                                    outgoing_manager=self.outgoing_audio_processing,
                                    agents_graph=self.compiled_graph,
                                    sample_width=self.sample_width,
                                    frame_rate=self.frame_rate,
                                    vad_aggressiveness=3
                                )
                                
        if self.openai_client is None:
            self.openai_client = OpenAI(api_key=self.OPENAI_API_KEY)

        self.logger.info("IncomingPhoneCallHandler initialized successfully.")

    def set_websocket(self, websocket: WebSocket):
        self.websocket = websocket
        self.incoming_audio_processing.set_websocket(websocket)
        self.outgoing_audio_processing.set_websocket(websocket)

    async def handle_websocket_all_receieved_events_async(self, calling_phone_number: str, call_sid: str) -> None:
        """Main method: handle a full audio conversation with I/O Twilio streams on a WebSocket."""
        if not self.websocket:
            self.logger.error("WebSocket not set, cannot handle WebSocket connection.")
            return
        
        self.logger.info(f"WebSocket handler started for {self.websocket.client.host}:{self.websocket.client.port}")
        
        # Store the caller's phone number and call SID so we can retrieve them later
        self.incoming_audio_processing.set_call_sid(call_sid)
        self.incoming_audio_processing.set_phone_number(calling_phone_number, call_sid)

        self.outgoing_audio_processing.run_background_streaming_worker()
        self.logger.info("Audio stream manager initialized and started with optimized parameters")

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
                    await self._handle_media_event_async(data)
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
        await self.incoming_audio_processing.init_conversation_async(call_sid, stream_sid)
        self.outgoing_audio_processing.update_stream_sid(stream_sid)
        return stream_sid

    async def _handle_media_event_async(self, media_data: dict) -> None:
        """Handle the 'media' event from Twilio which contains audio data."""
        # Process transcription in parallel with existing audio handling
        #await self.transcription_manager.process_media_event_async(media_data)
        
        # Continue with existing audio processing
        await self.incoming_audio_processing.process_incoming_data_async(media_data)
            
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
        self.incoming_audio_processing.set_call_sid(None)
        self.logger.info("Reset AudioProcessing stream SID as call ended")

    def _handle_mark_event(self, data):
        mark_name = data.get("mark", {}).get("name")
        self.logger.debug(f"Received mark event: {mark_name} for stream {self.current_stream}")

class PhoneCallWebsocketEventsHandlerFactory:
    websocket_events_handler_instance : PhoneCallWebsocketEventsHandler = None
    
    def __init__(self):
        self.build_new_phone_call_websocket_events_handler()

    def build_new_phone_call_websocket_events_handler(self, websocket: WebSocket = None):
        if not self.websocket_events_handler_instance:
            self.websocket_events_handler_instance = PhoneCallWebsocketEventsHandler(websocket=websocket)

    def get_new_phone_call_websocket_events_handler(self, websocket: WebSocket):
        self.build_new_phone_call_websocket_events_handler()
        websocket_events_handler_to_return = self.websocket_events_handler_instance
        # Set the websocket for the handler
        websocket_events_handler_to_return.set_websocket(websocket)
        self.websocket_events_handler_instance = None
        return websocket_events_handler_to_return