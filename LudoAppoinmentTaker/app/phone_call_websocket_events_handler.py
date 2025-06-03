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
from app.speech.incoming_manager import IncomingManager
from app.speech.outgoing_manager import OutgoingManager
from app.speech.incoming_audio_manager import IncomingAudioManager
from app.speech.outgoing_audio_manager import OutgoingAudioManager
from app.speech.incoming_text_manager import IncomingTextManager
from app.speech.outgoing_text_manager import OutgoingTextManager
#
from app.api_client.studi_rag_inference_api_client import StudiRAGInferenceApiClient
from app.api_client.salesforce_api_client import SalesforceApiClient

class PhoneCallWebsocketEventsHandler:
    phones: dict[str, str] = {}  # Map call_sid to phone numbers - consider if this should be instance or truly static

    def __init__(self, websocket: WebSocket = None, data_mode: str = "audio"):
        # Instance variables
        self.websocket = websocket
        self.logger = logging.getLogger(__name__)
        self.logger.info("IncomingPhoneCallHandler logger started")
        
        # Environment and configuration settings
        self.VOICE_ID = os.getenv("VOICE_ID", "")
        self.TEMP_DIR = "static/audio"
        self.TWILIO_SID = os.getenv("TWILIO_SID", "")
        self.TWILIO_AUTH = os.getenv("TWILIO_AUTH", "")

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

        # Create temp directory if it doesn't exist
        os.makedirs(self.TEMP_DIR, exist_ok=True)

        if os.path.exists(self.google_calendar_credentials_path):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = self.google_calendar_credentials_path
            self.logger.info(f"Set GOOGLE_APPLICATION_CREDENTIALS to: {self.google_calendar_credentials_path}")
        else:
            self.logger.error(f"/!\\ Google calendar credentials file not found at {self.google_calendar_credentials_path}")

        # Initialize dependencies
        self.tts_provider = get_text_to_speech_provider(self.TEMP_DIR, provider_name="openai", frame_rate=8000, channels=1, sample_width=2)
        self.stt_provider = get_speech_to_text_provider(self.TEMP_DIR, provider_name="hybrid", language_code="fr-FR", frame_rate=8000)
        
        self.studi_rag_inference_api_client = StudiRAGInferenceApiClient()
        self.salesforce_api_client = SalesforceApiClient()

        self.data_mode = data_mode
        self.outgoing_manager: OutgoingManager
        self.incoming_manager: IncomingManager

        if self.data_mode == "text":
            self.logger.info("Initializing in TEXT mode.")
            self.outgoing_manager = OutgoingTextManager(websocket=self.websocket)
            # compiled_graph needs outgoing_manager, so initialize it after outgoing_manager
            self.compiled_graph = AgentsGraph(
                                    self.outgoing_manager, 
                                    self.studi_rag_inference_api_client,
                                    self.salesforce_api_client
                                ).graph
            self.incoming_manager = IncomingTextManager(compiled_graph=self.compiled_graph)
        else:  # Default to audio mode
            self.logger.info("Initializing in AUDIO mode.")
            self.outgoing_manager = OutgoingAudioManager(
                                    tts_provider=self.tts_provider,
                                    websocket=self.websocket
                                )
            self.compiled_graph = AgentsGraph(
                                    self.outgoing_manager, 
                                    self.studi_rag_inference_api_client,
                                    self.salesforce_api_client
                                ).graph
            self.incoming_manager = IncomingAudioManager(
                                    stt_provider=self.stt_provider,
                                    compiled_graph=self.compiled_graph
                                )   

        if self.openai_client is None:
            self.openai_client = OpenAI(api_key=self.OPENAI_API_KEY)

        self.logger.info("IncomingPhoneCallHandler initialized successfully.")

    def set_websocket(self, websocket: WebSocket):
        self.websocket = websocket
        # self.incoming_manager might not have set_websocket, depends on implementation
        # if hasattr(self.incoming_manager, 'set_websocket'):
        #     self.incoming_manager.set_websocket(websocket)
        if hasattr(self.outgoing_manager, 'set_websocket'):
            self.outgoing_manager.set_websocket(websocket)
        else:
            self.logger.warning(f"Outgoing manager of type {type(self.outgoing_manager)} does not have set_websocket method.")

    async def handle_all_websocket_receieved_events_async(self, calling_phone_number: str, call_sid: str) -> None:
        """Main method: handle a full audio conversation with I/O Twilio streams on a WebSocket."""
        if not self.websocket:
            self.logger.error("WebSocket not set, cannot handle WebSocket connection.")
            return
        
        self.logger.info(f"WebSocket handler started for {self.websocket.client.host}:{self.websocket.client.port}")
        
        # Store the caller's phone number and call SID so we can retrieve them later
        self.phones[call_sid] = calling_phone_number
        
        # Managers are started by _handle_start_event_async upon receiving the 'start' event from Twilio.
        # self.current_stream will be set there. Call SID and Stream SID are passed to managers there.
        # Phone number association with conversation_id can be handled within AgentsGraph if needed.

        # await self.outgoing_manager.start() # Moved to _handle_start_event_async
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
                    await self._handle_stop_event_async(data.get("stop", {}))
                    return
                elif event == "mark":
                    self._handle_mark_event(data)
                else:
                    self.logger.warning(f"Received unknown event type: {event}")

        except Exception as e:
            self.logger.error(f"Unhandled error in WebSocket handler: {e}", exc_info=True)
        finally:
            await self.outgoing_manager.stop()
            if self.current_stream and self.current_stream in self.stream_states:
                self.logger.warning(f"Cleaning up state for stream {self.current_stream} due to handler exit/error.")
                del self.stream_states[self.current_stream]
            self.logger.info(f"WebSocket handler finished for {self.websocket.client.host}:{self.websocket.client.port} (Stream: {self.current_stream})" )
    
    def _handle_connected_event(self):
        """Handle the 'connected' event from Twilio."""
        self.logger.info("Twilio WebSocket connected")
    
    async def _handle_start_event_async(self, start_data: dict) -> str:
        """Handle the 'start' event from Twilio which begins a new call."""
        self.current_call_sid = start_data.get("callSid") # Store for use in media events if needed
        self.current_stream_sid = start_data.get("streamSid")
        self.current_stream = self.current_stream_sid # Keep self.current_stream for existing logic that might use it

        self.logger.info(f"Handling start event: CallSID={self.current_call_sid}, StreamSID={self.current_stream_sid}")
        
        if not self.current_call_sid or not self.current_stream_sid:
            self.logger.error("Missing callSid or streamSid in start event.")
            # Potentially close websocket or return error
            return ""

        await self.incoming_manager.start_stream(stream_sid=self.current_stream_sid, call_sid=self.current_call_sid)
        await self.outgoing_manager.start()
        self.logger.info(f"Incoming and Outgoing managers started for stream {self.current_stream_sid}.")
        return self.current_stream_sid

    async def _handle_media_event_async(self, media_data: dict) -> None:
        """Handle the 'media' event from Twilio which contains audio data or text."""
        stream_sid = media_data.get("streamSid")
        if stream_sid != self.current_stream_sid:
            self.logger.warning(f"Media event for unexpected stream SID {stream_sid}. Current is {self.current_stream_sid}. Ignoring.")
            return

        call_sid_for_data = self.incoming_manager.get_call_sid() # Get call_sid from manager state
        if not call_sid_for_data:
            call_sid_for_data = self.current_call_sid # Fallback if manager hasn't set it yet (should be set by start_stream)
            self.logger.warning(f"Call SID not found in incoming_manager, using current_call_sid: {call_sid_for_data}")

        if self.data_mode == "text":
            # Assuming text comes in a specific field, e.g., media_data['text']
            # This part is hypothetical as Twilio media events are for audio.
            # For a text-based interaction over WebSocket, the message format would be different.
            text_payload = media_data.get("text") 
            if text_payload is not None:
                self.logger.debug(f"Received text media: {text_payload[:50]}...")
                await self.incoming_manager.process_data(text_payload, call_sid=call_sid_for_data)
            else:
                self.logger.warning("Text mode active, but no 'text' field in media_data.")
        else: # Audio mode
            payload_b64 = media_data.get("media", {}).get("payload")
            if payload_b64:
                try:
                    audio_bytes = base64.b64decode(payload_b64)
                    await self.incoming_manager.process_data(audio_bytes, call_sid=call_sid_for_data)
                except Exception as e:
                    self.logger.error(f"Error decoding or processing audio media: {e}", exc_info=True)
            else:
                self.logger.warning("Audio mode active, but no 'payload' in media_data.media.")
            
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
   
    async def _handle_stop_event_async(self, stop_data: dict) -> None:
        """Handle the 'stop' event from Twilio which ends a stream."""
        # Twilio stop event contains accountSid, callSid, streamSid
        stopped_stream_sid = stop_data.get("streamSid", self.current_stream_sid) # Use current if not in stop_data
        self.logger.info(f"Received stop event for stream: {stopped_stream_sid}")

        if stopped_stream_sid == self.current_stream_sid and self.incoming_manager.is_active:
            await self.incoming_manager.stop_stream()
            await self.outgoing_manager.stop()
            self.logger.info(f"Incoming and Outgoing managers stopped for stream {stopped_stream_sid}.")
            
            # Clean up state for this stream
            if self.current_stream_sid in self.stream_states:
                del self.stream_states[self.current_stream_sid]
            if self.current_stream_sid in self.active_streams:
                del self.active_streams[self.current_stream_sid]
        elif not self.incoming_manager.is_active:
            self.logger.info(f"Received stop for stream {stopped_stream_sid}, but managers were already inactive.")
        else:
            self.logger.error(f"Received stop for stream {stopped_stream_sid}, but current stream is {self.current_stream_sid}. State mismatch or late event.")

        if self.websocket:
            try:
                # Check if websocket is already closing or closed to avoid errors
                if self.websocket.client_state == self.websocket.client_state.CONNECTED:
                    await self.websocket.close()
                    self.logger.info(f"WebSocket closed for stream {stopped_stream_sid}.")
                else:
                    self.logger.info(f"WebSocket already closing/closed for stream {stopped_stream_sid}.")                    
            except Exception as e:
                self.logger.error(f"Error closing websocket for stream {stopped_stream_sid}: {e}")
        
        self.current_stream_sid = None
        self.current_call_sid = None
        self.current_stream = None # Keep this for compatibility if other parts use it
        self.logger.info("Stream identifiers reset as call ended.")

    def _handle_mark_event(self, data):
        mark_name = data.get("mark", {}).get("name")
        self.logger.debug(f"Received mark event: {mark_name} for stream {self.current_stream}")

class PhoneCallWebsocketEventsHandlerFactory:
    # This factory pattern seems to intend to reuse a single handler instance, 
    # but then nullifies it. If the goal is one handler per call, it should create a new one each time.
    # For now, adapting to pass data_mode.
    
    def __init__(self): # Factory doesn't need to build one on init if it's per-request
        pass

    def get_new_phone_call_websocket_events_handler(self, websocket: WebSocket, data_mode: str = "audio") -> PhoneCallWebsocketEventsHandler:
        # Always create a new handler for a new call/websocket session
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"Creating new PhoneCallWebsocketEventsHandler with data_mode='{data_mode}'")
        handler = PhoneCallWebsocketEventsHandler(websocket=websocket, data_mode=data_mode)
        # The websocket is set in the constructor. If it needs to be updated later, 
        # the handler's set_websocket method can be used.
        return handler