import base64
import os
import uuid
import json
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

class BusinessLogic:
    _instance = None
    logger: logging.Logger = None
    compiled_graph = None
    
    # Client and state tracking
    openai_client = None
    stream_states = {}
    active_streams = {}
    active_calls = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BusinessLogic, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize the singleton instance of BusinessLogic"""
        if self.logger is None:
            self.logger = logging.getLogger(__name__)
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
        # These are already initialized in __new__
        # Just reset them if needed
        self.stream_states = {}
        self.active_streams = {}
        self.active_calls = {}
        return (
            b"",  # audio_buffer
            0,    # silence_counter_bytes
            None, # current_stream_sid
            {
                "sample_width": 2,  # 16-bit PCM 
                "silence_threshold": 2000,  # RMS threshold for silence detection
                "max_silence_bytes": 30 * 320,  # ~600ms at 8kHz
                "min_audio_bytes_for_processing": 5000  # Minimum buffer size to process
            }
        )
        
    
    def _decode_json(self, message: str) -> Optional[Dict]:
        """Safely decode JSON message from WebSocket."""
        try:
            return json.loads(message)
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode JSON message: {e}")
            return None
    
    def _handle_connected_event(self, ws: WebSocket):
        """Handle the 'connected' event from Twilio."""
        self.logger.info("Twilio WebSocket connected")
    
    async def _handle_start_event(self, ws: WebSocket, start_data: Dict) -> str:
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
                await self._speak_and_send(ws, initial_message, stream_sid)
        
        except Exception as e:
            self.logger.error(f"Error in initial graph invocation: {e}", exc_info=True)
            # Fallback welcome message
            await self._speak_and_send(ws, "Bonjour, bienvenue chez Studi.", stream_sid)
        
        return stream_sid
    
    async def handler_websocket(self, ws: WebSocket, calling_phone_number: str, stream_sid: str) -> None:
        """Main WebSocket handler for Twilio streams."""
        if not self.compiled_graph:
            self.logger.error("Graph not compiled, cannot handle WebSocket connection.")
            await ws.close(code=1011, reason="Server configuration error")
            return

        text = f"""
        Bonjour. Bienvenue chez Studi, l'école 100% en ligne !
        Je suis l'assistant virtuel Stud'IA, je prends le relais lorsque nos conseillers en formation ne sont pas présents.
        """
        tts_provider = get_text_to_speech_provider(self.TEMP_DIR)
        audio_file_path = tts_provider.synthesize_speech(text)
        await self.send_audio_to_twilio(ws, stream_sid, audio_file_path)

        # Initialize audio processing variables
        audio_buffer, silence_counter_bytes, current_stream, params = self._init_stream_vars()
        self.logger.info(f"WebSocket handler started for {ws.client.host}:{ws.client.port}")

        try:            
            while True:
                try:
                    msg = await ws.receive_text()
                    data = self._decode_json(msg)
                    if data is None:
                        continue
                except WebSocketDisconnect as disconnect_err:
                    self.logger.info(f"WebSocket disconnected: {ws.client.host}:{ws.client.port} - Code: {disconnect_err.code}")
                    break
                    
                event = data.get("event")
                if event == "connected":
                    self._handle_connected_event(ws)
                elif event == "start":
                    current_stream = await self._handle_start_event(ws, data.get("start", {}))
                elif event == "media":
                    if not current_stream:
                        self.logger.warning("Received media before start event")
                        continue
                    audio_buffer, silence_counter_bytes = await self._handle_media_event(
                        ws, data, audio_buffer, silence_counter_bytes, params, current_stream
                    )
                elif event == "stop":
                    await self._handle_stop_event(ws, current_stream)
                    return
                elif event == "mark":
                    self._handle_mark_event(data, current_stream)
                else:
                    self.logger.warning(f"Received unknown event type: {event}")

        except Exception as e:
            self.logger.error(f"Unhandled error in WebSocket handler: {e}", exc_info=True)
        finally:
            if current_stream and current_stream in self.stream_states:
                self.logger.warning(f"Cleaning up state for stream {current_stream} due to handler exit/error.")
                del self.stream_states[current_stream]
            self.logger.info(f"WebSocket handler finished for {ws.client.host}:{ws.client.port} (Stream: {current_stream})" )
    
    async def _handle_media_event(self, ws, data, audio_buffer, silence_counter_bytes, params, current_stream):
        # 1. Decode audio chunk
        chunk = self._decode_audio_chunk(data, params["sample_width"])
        if chunk is None: return audio_buffer, silence_counter_bytes
        
        audio_buffer += chunk

        # 2. Silence detection
        silence_counter_bytes = self._update_silence_counter(
            chunk,
            silence_counter_bytes,
            params["sample_width"],
            params["silence_threshold"]
        )

        # 3. Process audio if: prolonged silence & buffer is large enough
        if silence_counter_bytes >= params["max_silence_bytes"] and len(audio_buffer) > params["min_audio_bytes_for_processing"]:
            self.logger.info(f"Silence detected for stream {current_stream}, processing audio (buffer: {len(audio_buffer)} bytes).")
            buffer_to_process = audio_buffer
            audio_buffer = b""
            silence_counter_bytes = 0

            transcript = self._transcribe_buffer(buffer_to_process)
            if transcript is None:
                return audio_buffer, silence_counter_bytes

            # 4. Orchestrate the conversation graph and generate a response
            response_text = await self._process_conversation(ws, current_stream, transcript)
            if response_text:
                await self._speak_and_send(ws, response_text, current_stream)
        return audio_buffer, silence_counter_bytes
   
    def _decode_audio_chunk(self, data, sample_width):
        media_data = data.get("media", {})
        payload = media_data.get("payload")
        if not payload:
            self.logger.warning("Received media event without payload")
            return None
        try:
            return audioop.ulaw2lin(base64.b64decode(payload), sample_width)
        except Exception as decode_err:
            self.logger.error(f"Error decoding/converting audio chunk: {decode_err}")
            return None

    def _update_silence_counter(self, chunk, silence_counter_bytes, sample_width, silence_threshold):
        rms: int = audioop.rms(chunk, sample_width)
        if rms < silence_threshold:
            return silence_counter_bytes + len(chunk)
        else:
            return 0

    def _transcribe_buffer(self, buffer_to_process):
        try:
            wav_path = self.save_wav(buffer_to_process)
            transcript: str = self.transcribe_audio(wav_path)
            self.logger.info(f"Transcript: {transcript}")
            os.remove(wav_path)
            return transcript
        except Exception as speech_err:
            self.logger.error(f"Error during transcription: {speech_err}", exc_info=True)
            return None
    
    async def _process_conversation(self, ws, current_stream, transcript):
        """Process user input through the conversation graph and get a response."""
        response_text = "Désolé, une erreur interne s'est produite."
        
        if current_stream in self.stream_states:
            # Get current state and update with user input
            current_state = self.stream_states[current_stream]
            current_state['user_input'] = transcript
            
            try:
                # Log the conversation for debugging
                self.logger.info(f"User [{current_stream[:8]}]: '{transcript[:50]}...'")
                
                # Invoke the graph with the updated state
                updated_state: ConversationState = await self.compiled_graph.ainvoke(
                    current_state,
                    {"recursion_limit": 15}  # Prevent infinite loops
                )
                
                # Save the updated state
                self.stream_states[current_stream] = updated_state
                
                # Extract the AI response from history
                if updated_state.get('history') and updated_state['history'][-1][0] == 'AI':
                    response_text = updated_state['history'][-1][1]
                    self.logger.info(f"AI [{current_stream[:8]}]: '{response_text[:50]}...'")
                else:
                    self.logger.warning(f"No AI response found in history after graph invocation.")
            except Exception as graph_err:
                self.logger.error(f"Error invoking graph: {graph_err}", exc_info=True)
            
            return response_text
        else:
            self.logger.error(f"Stream {current_stream} not found in states, cannot invoke graph.")
            return None

    async def _speak_and_send(self, ws, response_text, current_stream):
        try:
            tts_provider = get_text_to_speech_provider()
            path: str = tts_provider.synthesize_speech(response_text)
            await self.send_audio_to_twilio(ws, path, current_stream)
            self.logger.info(f"Sent graph response to stream {current_stream}: '{response_text[:50]}...'")
        except Exception as e:
            self.logger.error(f"Error sending graph response for stream {current_stream}: {e}", exc_info=True)

    async def _handle_stop_event(self, ws, current_stream):
        self.logger.info(f"Received stop event for stream: {current_stream}")
        if current_stream in self.stream_states:
            del self.stream_states[current_stream]
            self.logger.info(f"Cleaned up state for stream {current_stream}")
        else:
            self.logger.warning(f"Received stop for unknown or already cleaned stream: {current_stream}")
        await ws.close()

    def _handle_mark_event(self, data, current_stream):
        mark_name = data.get("mark", {}).get("name")
        self.logger.debug(f"Received mark event: {mark_name} for stream {current_stream}")
    
    def save_pcm_as_file(self, pcm_data: bytes, path: str):
        """Save PCM data (16-bit, 8kHz, mono) to a WAV file at the specified path."""
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(8000)
            wav_file.writeframes(pcm_data)
    
    def transcribe_audio(self, wav_path: str, language_code: str = "fr-FR") -> str:
        """Transcribe audio file using Google Cloud Speech-to-Text API."""
        try:
            # First try with OpenAI Whisper if available
            if self.OPENAI_API_KEY:
                try:
                    with open(wav_path, "rb") as audio_file:
                        response = self.openai_client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="fr"
                        )
                        return response.text
                except Exception as whisper_err:
                    self.logger.warning(f"Error with Whisper transcription, falling back to Google: {whisper_err}")
            
            # Fallback to Google Speech-to-Text
            client = speech.SpeechClient()
            with open(wav_path, "rb") as audio_file:
                content = audio_file.read()

            audio = speech.RecognitionAudio(content=content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=8000,
                language_code=language_code,
            )

            response = client.recognize(config=config, audio=audio)

            transcript = ""
            for result in response.results:
                transcript += result.alternatives[0].transcript

            return transcript
        except Exception as e:
            self.logger.error(f"Error transcribing audio: {e}", exc_info=True)
            return ""
    
    async def send_audio_to_twilio(self, ws: WebSocket, stream_sid: str, audio_bytes: bytes):
        """Convert mp3 to μ-law and send to Twilio over WebSocket."""
        msg = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": audio_bytes
                    }
                }

        await ws.send_text(json.dumps(msg))
        return True
        try:
            # Load audio and convert to appropriate format for Twilio (8kHz μ-law)
            audio = AudioSegment.from_raw(io.BytesIO(audio_bytes), frame_rate=8000, sample_width=2, channels=1)
            pcm_data = audio.raw_data
            ulaw_data = audioop.lin2ulaw(pcm_data, 2)  # 2 = 16 bits

            # Send in chunks with slight delay to simulate real-time streaming
            chunk_size = 320  # ~20ms at 8kHz
            for i in range(0, len(ulaw_data), chunk_size):
                chunk = ulaw_data[i:i + chunk_size]
                payload = base64.b64encode(chunk).decode()

                msg = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": payload
                    }
                }

                await ws.send_text(json.dumps(msg))
                await asyncio.sleep(0.02)  # 20ms for real-time simulation

            # Send mark to indicate end of message
            mark_msg = {
                "event": "mark",
                "streamSid": stream_sid,
                "mark": {
                    "name": "msg_retour"
                }
            }
            await ws.send_text(json.dumps(mark_msg))

            self.logger.info(f"Audio sent to Twilio for stream {stream_sid}")
            return True
        except Exception as e:
            self.logger.error(f"Error sending audio to Twilio: {e}", exc_info=True)
            return False