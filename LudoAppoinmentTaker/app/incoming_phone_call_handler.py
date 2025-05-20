import base64
import io
import os
import json
import uuid
import random
import audioop
import asyncio
import logging
import wave
import time
from uuid import UUID
from datetime import datetime
#
from pydub import AudioSegment
from openai import OpenAI
from typing import Dict, Any, Optional, Tuple, List
from app.speech.text_processing import ProcessText
from fastapi import WebSocket, WebSocketDisconnect
#
from app.agents.agents_graph import AgentsGraph
from app.agents.conversation_state_model import ConversationState
from app.api_client.studi_rag_inference_client import StudiRAGInferenceClient
from app.api_client.request_models.user_request_model import UserRequestModel, DeviceInfoRequestModel
from app.api_client.request_models.conversation_request_model import ConversationRequestModel
from app.api_client.request_models.query_asking_request_model import QueryAskingRequestModel
from app.speech.text_to_speech import get_text_to_speech_provider
from app.speech.speech_to_text import get_speech_to_text_provider
from app.speech.incoming_audio_processing import IncomingAudioProcessing
from app.speech.audio_streaming import AudioStreamManager

class IncomingPhoneCallHandler:
    # Class variables shared across instances
    compiled_graph = None # LangGraph workflow compilation
    phones: Dict[str, str] = {}  # Map call_sid to phone numbers
    
    def __init__(self, websocket: WebSocket = None):
        # Instance variables
        self.websocket = websocket
        self.logger = logging.getLogger(__name__)
        self.logger.info("IncomingPhoneCallHandler logger started")
        
        # State tracking for this instance
        self.openai_client = None
        self.stream_states = {}
        self.active_streams = {}
        # Flags to track speaking state
        self.is_speaking = False  # Flag to track if system is currently speaking
        self.rag_interrupt_flag = {"interrupted": False}  # Flag to interrupt RAG streaming
        
        # Set audio processing parameters as instance variables
        self.frame_rate = 8000  # Sample rate in Hz (8kHz is standard for telephony)
        self.sample_width = 2    # 16-bit PCM
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
        self.VOICE_ID = os.getenv("VOICE_ID", "")
        self.TEMP_DIR = "static/audio"
        self.PUBLIC_HOST = os.getenv("PUBLIC_HOST", "http://localhost:8000")
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

        self.tts_provider = get_text_to_speech_provider(self.TEMP_DIR)
        self.stt_provider = get_speech_to_text_provider(self.TEMP_DIR, provider="hybrid")
        
        # Initialize audio processor for better quality
        self.incoming_audio = IncomingAudioProcessing(sample_width=self.sample_width, frame_rate=self.frame_rate, vad_aggressiveness=3)
        
        # Initialize the audio stream manager for throttled Twilio audio streaming
        self.audio_stream_manager = None

        self.studi_rag_inference_client = StudiRAGInferenceClient()

        # Initialize API clients
        if self.openai_client is None:
            self.openai_client = OpenAI(api_key=self.OPENAI_API_KEY)

        self.compiled_graph = AgentsGraph().graph

        self.logger.info("IncomingPhoneCallHandler initialized successfully.")

    async def handle_call_websocket_events_async(self, calling_phone_number: str, call_sid: str) -> None:
        """Main method: handle a full audio conversation with I/O Twilio streams on a WebSocket."""
        if not self.websocket:
            self.logger.error("WebSocket not set, cannot handle WebSocket connection.")
            return
        
        self.logger.info(f"WebSocket handler started for {self.websocket.client.host}:{self.websocket.client.port}")
        
        # Store the caller's phone number and call SID so we can retrieve them later
        self.phones[call_sid] = calling_phone_number
        
        # Initialize the audio stream manager for text-based TTS streaming with optimized parameters
        # We'll set the streamSid later when the call starts
        self.audio_stream_manager = AudioStreamManager(
            websocket=self.websocket,
            tts_provider=self.tts_provider,  # Add TTS provider for text-to-speech conversion
            streamSid=None,  # Will be set when the call starts
            min_chunk_interval=0.05  # Faster refresh rate (20ms)
        )
        # Start the background streaming task
        self.audio_stream_manager.run_background_streaming_worker()
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
            if self.current_stream and self.current_stream in self.stream_states:
                self.logger.warning(f"Cleaning up state for stream {self.current_stream} due to handler exit/error.")
                del self.stream_states[self.current_stream]
            self.logger.info(f"WebSocket handler finished for {self.websocket.client.host}:{self.websocket.client.port} (Stream: {self.current_stream})" )
    
    def _handle_connected_event(self):
        """Handle the 'connected' event from Twilio."""
        self.logger.info("Twilio WebSocket connected")
    
    async def _handle_start_event_async(self, start_data: Dict) -> str:
        """Handle the 'start' event from Twilio which begins a new call."""
        call_sid = start_data.get("callSid")
        stream_sid = start_data.get("streamSid")
        await self.incoming_audio.handle_incoming_websocket_media_event_async(call_sid, stream_sid)
        return stream_sid

    async def _handle_media_event_async(self, media_data: dict) -> None:
        """Handle the 'media' event from Twilio which contains audio data."""
        await self.incoming_audio.handle_incoming_websocket_media_event_async(media_data)
            
    def _is_websocket_connected(self) -> bool:
        """Check if the websocket is still connected"""
        if not self.websocket:
            return False
            
        try:
            # First, handle the case from the old implementation that was working
            # The client_state is an enum in some WebSocket libraries
            if hasattr(self.websocket, 'client_state'):
                # If client_state is an attribute that contains CONNECTED as a property
                if hasattr(self.websocket.client_state, 'CONNECTED'):
                    return True
                # If client_state is a string
                if isinstance(self.websocket.client_state, str):
                    return 'connect' in self.websocket.client_state.lower()
                # Otherwise assume it's connected (we know the attribute exists)
                return True
                
            # Alternative check for other WebSocket implementations
            if hasattr(self.websocket, 'closed'):
                return not self.websocket.closed
                
            # Default to assuming it's connected if we can't check
            # This is a safe default since the connection was established
            return True
        except Exception as e:
            self.logger.error(f"Error checking websocket connection: {e}")
            # For safety, if we had an exception checking, assume connected
            # This prevents the regression where audio wasn't being sent
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
        
        # Reset current stream and audio streaming state
        self.current_stream = None
        
        # Set the audio stream manager's streamSid to None
        if self.audio_stream_manager:
            self.audio_stream_manager.update_stream_sid(None)
            self.logger.info("Reset AudioStreamManager stream SID as call ended")

    def _handle_mark_event(self, data):
        mark_name = data.get("mark", {}).get("name")
        self.logger.debug(f"Received mark event: {mark_name} for stream {self.current_stream}")

class IncomingPhoneCallHandlerFactory:
    def __init__(self):
        self.build_new_incoming_phone_call_handler()

    def build_new_incoming_phone_call_handler(self):
        self.incoming_phone_call_handler = IncomingPhoneCallHandler(websocket=None)

    def get_new_incoming_phone_call_handler(self, websocket: WebSocket):
        if not self.incoming_phone_call_handler:
            self.build_new_incoming_phone_call_handler()
        incoming_phone_call_handler_to_return = self.incoming_phone_call_handler
        incoming_phone_call_handler_to_return.websocket = websocket
        self.incoming_phone_call_handler = None
        #self.build_new_incoming_phone_call_handler()
        return incoming_phone_call_handler_to_return
    