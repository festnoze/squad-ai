import base64
import io
import os
import json
import uuid
import audioop
import asyncio
import logging
import wave
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from google.cloud import speech, texttospeech
from openai import OpenAI
from typing import Dict, Optional
from fastapi import WebSocket, WebSocketDisconnect
from agents_graph import AgentsGraph
from app.agents.conversation_state_model import ConversationState
from app.text_to_speech import get_text_to_speech_provider
from app.speech_to_text import get_speech_to_text_provider

class BusinessLogic:
    # Class variables shared across instances
    compiled_graph = None
    
    def __init__(self, websocket: WebSocket = None):
        # Instance variables
        self.websocket = websocket
        self.logger = logging.getLogger(__name__)
        
        # State tracking for this instance
        self.openai_client = None
        self.stream_states = {}
        self.active_streams = {}
        self.active_calls = {}
        self.current_stream = None
        
        # Initialize the instance
        self._initialize()
    
    def _initialize(self):
        """Initialize the BusinessLogic instance"""
        self.logger.info("Logger in BusinessLogic initialized")

        # Environment and configuration settings
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.VOICE_ID = os.getenv("VOICE_ID", "")
        self.TEMP_DIR = "static/audio"
        self.PUBLIC_HOST = os.getenv("PUBLIC_HOST", "http://localhost:8000")
        self.TWILIO_SID = os.getenv("TWILIO_SID", "")
        self.TWILIO_AUTH = os.getenv("TWILIO_AUTH", "")
        
        # Create temp directory if it doesn't exist
        os.makedirs(self.TEMP_DIR, exist_ok=True)

        self.tts_provider = get_text_to_speech_provider(self.TEMP_DIR)
        self.stt_provider = get_speech_to_text_provider(self.TEMP_DIR)

        # Initialize API clients
        if self.openai_client is None:
            self.openai_client = OpenAI(api_key=self.OPENAI_API_KEY)

        if self.compiled_graph is None:
            self.init_graph()

        self.logger.info("BusinessLogic initialized successfully.")
    
    # State tracking dictionaries
    phones: Dict[str, str] = {}  # Map call_sid to phone numbers
    
    def init_graph(self):
        """Initialize the LangGraph workflow compilation."""
        agents_graph = AgentsGraph()
        self.compiled_graph = agents_graph.graph
        if self.logger and self.compiled_graph:
            self.logger.info("BusinessLogic initialized: langgraph workflow - success.")

    def _init_stream_vars(self):
        """Initialize variables needed for audio stream processing."""
        # Reset state tracking dictionaries
        self.stream_states = {}
        self.active_streams = {}
        self.active_calls = {}
        
        # Set audio processing parameters as instance variables
        self.sample_width = 2  # 16-bit PCM
        self.silence_threshold = 2000  # RMS threshold for silence detection
        self.max_silence_bytes = 30 * 320  # ~600ms at 8kHz
        self.min_audio_bytes_for_processing = 5000  # Minimum buffer size to process
        
        self.audio_buffer = b""
        self.silence_counter_bytes = 0
        self.current_stream = None        
    
    def _decode_json(self, message: str) -> Optional[Dict]:
        """Safely decode JSON message from WebSocket."""
        try:
            return json.loads(message)
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode JSON message: {e}")
            return None
    
    def _handle_connected_event(self):
        """Handle the 'connected' event from Twilio."""
        self.logger.info("Twilio WebSocket connected")
    
    async def _handle_start_event(self, start_data: Dict) -> str:
        """Handle the 'start' event from Twilio which begins a new call."""
        call_sid = start_data.get("callSid")
        stream_sid = start_data.get("streamSid")
        
        self.logger.info(f"Call started - CallSid: {call_sid}, StreamSid: {stream_sid}")
        
        # Initialize conversation state for this stream
        phone_number = self.phones.get(call_sid, "Unknown")
        
        # Create initial state for the graph
        initial_state: ConversationState = {
            "call_sid": call_sid,
            "caller_phone": phone_number,
            "user_input": "",
            "history": [],
            "agent_scratchpad": {}
        }
        
        # Store the state
        self.stream_states[stream_sid] = initial_state
        
        # Invoke the graph with initial state to get welcome message
        try:
            updated_state = await self.compiled_graph.ainvoke(initial_state)
            self.stream_states[stream_sid] = updated_state
            
            # Check if there's an initial AI message to send
            if updated_state.get('history') and updated_state['history'][0][0] == 'AI':
                initial_message = updated_state['history'][0][1]
                await self._speak_and_send(initial_message, stream_sid)
        
        except Exception as e:
            self.logger.error(f"Error in initial graph invocation: {e}", exc_info=True)
            # Fallback welcome message
            await self._speak_and_send("Bonjour, bienvenue chez Studi.", stream_sid)
        
        return stream_sid
    
    async def websocket_handler(self, calling_phone_number: str, call_sid: str) -> None:
        """Main WebSocket handler for Twilio streams."""
        if not self.websocket:
            self.logger.error("WebSocket not set, cannot handle WebSocket connection.")
            return
        
        if not self.compiled_graph:
            self.logger.error("Graph not compiled, cannot handle WebSocket connection.")
            await self.websocket.close(code=1011, reason="Server configuration error")
            return

        # Initialize audio processing variables
        self._init_stream_vars()
        self.logger.info(f"WebSocket handler started for {self.websocket.client.host}:{self.websocket.client.port}")
        
        # Store the caller's phone number and call SID so we can retrieve them later
        self.phones[call_sid] = calling_phone_number

        # Give a welcome message
        text = f"""
        Bonjour. Bienvenue chez Studi, l'école 100% en ligne !
        Je suis l'assistant virtuel Stud'IA, je prends le relais lorsque nos conseillers en formation ne sont pas présents.
        """
        audio_file_path = self.tts_provider.synthesize_speech(text)
        await self.send_audio_to_twilio(audio_file_path)
        self.remove_audio_file(audio_file_path)
        await asyncio.sleep(20)

        try:            
            while True:
                try:
                    msg = await self.websocket.receive_text()
                    data = self._decode_json(msg)
                    if data is None:
                        continue
                except WebSocketDisconnect as disconnect_err:
                    self.logger.info(f"WebSocket disconnected: {self.websocket.client.host}:{self.websocket.client.port} - Code: {disconnect_err.code}")
                    break
                    
                event = data.get("event")
                if event == "connected":
                    self._handle_connected_event()
                elif event == "start":
                    self.current_stream = await self._handle_start_event(data.get("start", {}))
                elif event == "media":
                    if not self.current_stream:
                        self.logger.warning("Received media before start event")
                        continue
                    await self._handle_media_event(data)
                elif event == "stop":
                    await self._handle_stop_event()
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
    
    async def _handle_media_event(self, data):
        # 1. Decode audio chunk
        chunk = self._decode_audio_chunk(data)
        if chunk is None: return
        
        self.audio_buffer += chunk

        # 2. Silence detection
        self.silence_counter_bytes = self._update_silence_counter(chunk)

        # 3. Process audio if: prolonged silence & buffer is large enough
        if self.silence_counter_bytes >= self.max_silence_bytes and len(self.audio_buffer) > self.min_audio_bytes_for_processing:
            self.logger.info(f"Silence detected for stream {self.current_stream}, processing audio (buffer: {len(self.audio_buffer)} bytes).")
            buffer_to_process = self.audio_buffer
            self.audio_buffer = b""
            self.silence_counter_bytes = 0

            transcript = self._transcribe_buffer(buffer_to_process)
            if transcript is None:
                return

            # 4. Orchestrate the conversation graph and generate a response
            response_text = await self._process_conversation(transcript)
            if response_text:
                await self._speak_and_send(response_text)
        return
   
    def _decode_audio_chunk(self, data):
        media_data = data.get("media", {})
        payload = media_data.get("payload")
        if not payload:
            self.logger.warning("Received media event without payload")
            return None
        try:
            return audioop.ulaw2lin(base64.b64decode(payload), self.sample_width)
        except Exception as decode_err:
            self.logger.error(f"Error decoding/converting audio chunk: {decode_err}")
            return None

    def _update_silence_counter(self, chunk):
        rms: int = audioop.rms(chunk, self.sample_width)
        if rms < self.silence_threshold:
            return self.silence_counter_bytes + len(chunk)
        else:
            return 0

    def _transcribe_buffer(self, buffer_to_process):
        try:
            wav_file_name = self.save_as_wav_file(buffer_to_process)
            transcript: str = self.stt_provider.transcribe_audio(wav_file_name)
            self.logger.info(f"Transcript: {transcript}")
            self.remove_audio_file(wav_file_name)
            return transcript
        except Exception as speech_err:
            self.logger.error(f"Error during transcription: {speech_err}", exc_info=True)
            return None
    
    def remove_audio_file(self, file_name: str):
        file_path: str = os.path.join(self.TEMP_DIR, file_name)
        if os.path.exists(file_path):
            os.remove(file_path)
    
    async def _process_conversation(self, transcript):
        """Process user input through the conversation graph and get a response."""
        response_text = "Désolé, une erreur interne s'est produite."
        
        if not self.current_stream:
            self.logger.error("No active stream, cannot process conversation")
            return response_text
        
        if self.current_stream in self.stream_states:
            # Get current state and update with user input
            current_state = self.stream_states[self.current_stream]
            current_state['user_input'] = transcript
            
            try:
                # Log the conversation for debugging
                self.logger.info(f"User [{self.current_stream[:8]}]: '{transcript[:50]}...'")
                
                # Invoke the graph with the updated state
                updated_state: ConversationState = await self.compiled_graph.ainvoke(
                    current_state,
                    {"recursion_limit": 15}  # Prevent infinite loops
                )
                
                # Save the updated state
                self.stream_states[self.current_stream] = updated_state
                
                # Extract the AI response from history
                if updated_state.get('history') and updated_state['history'][-1][0] == 'AI':
                    response_text = updated_state['history'][-1][1]
                    self.logger.info(f"AI [{self.current_stream[:8]}]: '{response_text[:50]}...'")
                else:
                    self.logger.warning(f"No AI response found in history after graph invocation.")
            except Exception as graph_err:
                self.logger.error(f"Error invoking graph: {graph_err}", exc_info=True)
            
            return response_text
        else:
            self.logger.error(f"Stream {self.current_stream} not found in states, cannot invoke graph.")
            return None

    async def _speak_and_send(self, response_text, stream_sid=None):
        """Synthesize speech from text and send to Twilio"""
        try:
            # Use provided stream_sid if available, otherwise use current_stream
            active_stream = stream_sid if stream_sid else self.current_stream
            
            if not active_stream:
                self.logger.error("No active stream, cannot send audio")
                return
                
            # If stream_sid is provided, set it as the current_stream
            if stream_sid:
                self.current_stream = stream_sid
                
            path = self.tts_provider.synthesize_speech(response_text)
            await self.send_audio_to_twilio(path)
            self.logger.info(f"Sent graph response to stream {active_stream}: '{response_text[:50]}...'")
        except Exception as e:
            self.logger.error(f"Error sending graph response for stream {active_stream}: {e}", exc_info=True)

    async def _handle_stop_event(self):
        """Handle the stop event from Twilio which ends a call"""
        if not self.current_stream:
            self.logger.warning("Received stop event but no active stream")
            return
            
        self.logger.info(f"Received stop event for stream: {self.current_stream}")
        if self.current_stream in self.stream_states:
            del self.stream_states[self.current_stream]
            self.logger.info(f"Cleaned up state for stream {self.current_stream}")
        else:
            self.logger.warning(f"Received stop for unknown or already cleaned stream: {self.current_stream}")
            
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                self.logger.error(f"Error closing websocket: {e}")
        
        # Reset current stream
        self.current_stream = None

    def _handle_mark_event(self, data):
        mark_name = data.get("mark", {}).get("name")
        self.logger.debug(f"Received mark event: {mark_name} for stream {self.current_stream}")
    
    def save_as_wav_file(self, pcm_data: bytes):
        """Save PCM data (16-bit, 8kHz, mono) to a WAV file at the specified path."""
        file_name = f"{uuid.uuid4()}.wav"
        with wave.open(os.path.join(self.TEMP_DIR, file_name), "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(8000)
            wav_file.writeframes(pcm_data)
        return file_name
    
    def prepare_voice_stream(self, file_path: str=None, audio_bytes: bytes=None, frame_rate: int=8000, channels: int=1, sample_width: int=2, convert_to_mulaw: bool = False):
        if (file_path and audio_bytes) or (not file_path and not audio_bytes):
            raise ValueError("Must provide either file_path or audio_bytes, but not both.")
        
        if file_path:
            audio = AudioSegment.from_file(file_path).set_frame_rate(frame_rate).set_channels(channels).set_sample_width(sample_width)
        else:
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            audio = audio.set_frame_rate(frame_rate).set_channels(channels).set_sample_width(sample_width)
        pcm_data = audio.raw_data
        if convert_to_mulaw:
            mulaw_audio = audioop.lin2ulaw(pcm_data, sample_width)  # Convert to 8-bit μ-law
            return mulaw_audio
        else:
            return pcm_data
    
    async def send_audio_to_twilio(self, mp3_path):
        """Convert mp3 to μ-law and send to Twilio over WebSocket."""
        if not self.websocket:
            self.logger.error("WebSocket not set, cannot send audio")
            return False
            
        if not self.current_stream:
            self.logger.error("No active stream, cannot send audio")
            return False
            
        try:
            self.logger.info(f"Sending audio file {mp3_path} to stream {self.current_stream}")
            
            # Convertir en PCM mono 16-bit 8kHz
            audio = AudioSegment.from_file(mp3_path).set_frame_rate(8000).set_channels(1).set_sample_width(2)
            pcm_data = audio.raw_data

            # Convertir en μ-law
            ulaw_data = audioop.lin2ulaw(pcm_data, 2)  # 2 = 16 bits

            # Découper en petits chunks (20ms = 160 samples * 2 bytes = 320 bytes)
            chunk_size = 320
            for i in range(0, len(ulaw_data), chunk_size):
                chunk = ulaw_data[i:i + chunk_size]
                payload = base64.b64encode(chunk).decode()
                
                msg = {
                    "event": "media",
                    "streamSid": self.current_stream,
                    "media": {
                        "payload": payload
                    }
                }
            
                await self.websocket.send_text(json.dumps(msg))
                await asyncio.sleep(0.02)  # 20ms pour simuler temps réel
                
            # Send mark to indicate end of message
            mark_msg = {
                "event": "mark",
                "streamSid": self.current_stream,
                "mark": {
                    "name": "msg_retour"
                }
            }
            
            await self.websocket.send_text(json.dumps(mark_msg))
            
            self.logger.info(f"Audio sent to Twilio for stream {self.current_stream}")
            return True
        except Exception as e:
            self.logger.error(f"Error sending audio to Twilio: {e}", exc_info=True)
            return False

    async def send_audio_to_twilio2(self, path: str, audio_bytes: bytes=None, frame_rate: int=8000, channels: int=1, sample_width: int=2, convert_to_mulaw: bool = False):
        """Convert mp3 to μ-law and send to Twilio over WebSocket."""
        if not self.websocket:
            self.logger.error("WebSocket not set, cannot send audio")
            return False
            
        try:
            # Load audio and convert to appropriate format for Twilio (8kHz μ-law)
            ulaw_data = self.prepare_voice_stream(file_path=path, audio_bytes=audio_bytes, frame_rate=frame_rate, channels=channels, sample_width=sample_width, convert_to_mulaw=True)

            # Send in chunks with slight delay to simulate real-time streaming
            chunk_size = 320  # ~20ms at 8kHz
            for i in range(0, len(ulaw_data), chunk_size):
                chunk = ulaw_data[i:i + chunk_size]
                payload = base64.b64encode(chunk).decode()

                msg = {
                    "event": "media",
                    "streamSid": self.current_stream,
                    "media": {
                        "payload": payload
                    }
                }

                await self.websocket.send_text(json.dumps(msg))
                await asyncio.sleep(0.02)  # 20ms for real-time simulation

            # Send mark to indicate end of message
            mark_msg = {
                "event": "mark",
                "streamSid": self.current_stream,
                "mark": {
                    "name": "msg_retour"
                }
            }
            await self.websocket.send_text(json.dumps(mark_msg))

            self.logger.info(f"Audio sent to Twilio for stream {self.current_stream}")
            return True
        except Exception as e:
            self.logger.error(f"Error sending audio to Twilio: {e}", exc_info=True)
            return False