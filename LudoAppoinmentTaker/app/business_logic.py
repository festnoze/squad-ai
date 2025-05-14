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
from pydub.silence import detect_nonsilent
from google.cloud import speech, texttospeech
from openai import OpenAI, Stream
from typing import Dict, Optional
from fastapi import WebSocket, WebSocketDisconnect
#
from agents_graph import AgentsGraph
from app.agents.conversation_state_model import ConversationState
from app.api_client.studi_rag_inference_client import StudiRAGInferenceClient
from app.api_client.request_models.user_request_model import UserRequestModel, DeviceInfoRequestModel
from app.api_client.request_models.conversation_request_model import ConversationRequestModel
from app.api_client.request_models.query_asking_request_model import QueryAskingRequestModel
from app.text_to_speech import get_text_to_speech_provider
from app.speech_to_text import get_speech_to_text_provider
from app.audio_processing import AudioProcessor

class BusinessLogic:
    # Class variables shared across instances
    compiled_graph = None # LangGraph workflow compilation
    phones: Dict[str, str] = {}  # Map call_sid to phone numbers
    
    def __init__(self, websocket: WebSocket = None):
        # Instance variables
        self.websocket = websocket
        self.logger = logging.getLogger(__name__)
        self.logger.info("BusinessLogic logger started")
        
        # State tracking for this instance
        self.openai_client = None
        self.stream_states = {}
        self.active_streams = {}
        self.active_calls = {}
        
        # Set audio processing parameters as instance variables
        self.frame_rate = 8000  # Sample rate in Hz (8kHz is standard for telephony)
        self.sample_width = 2    # 16-bit PCM
        self.speech_threshold = 250  # Threshold for silence vs. speech
        self.min_audio_bytes_for_processing = 6400  # Minimum buffer size = ~400ms at 8kHz
        self.max_audio_bytes_for_processing = 150000  # Maximum buffer size = ~15s at 8kHz
        self.consecutive_silence_duration_ms = 0.0  # Count consecutive silence duration in milliseconds
        self.required_silence_ms_to_answer = 800  # Require 800ms of silence to process audio
        
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
            self.logger.warning(f"/!\\ Warning: Google calendar credentials file not found at {self.google_calendar_credentials_path}")

        self.tts_provider = get_text_to_speech_provider(self.TEMP_DIR)
        self.stt_provider = get_speech_to_text_provider(self.TEMP_DIR, provider="hybrid")
        
        # Initialize audio processor for better quality
        self.audio_processor = AudioProcessor(sample_width=self.sample_width, frame_rate=self.frame_rate, vad_aggressiveness=3)

        self.studi_rag_inference_client = StudiRAGInferenceClient()

        # Initialize API clients
        if self.openai_client is None:
            self.openai_client = OpenAI(api_key=self.OPENAI_API_KEY)

        if not self.compiled_graph:
            self.compiled_graph = AgentsGraph().graph

        self.logger.info("BusinessLogic initialized successfully.")
    
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
        
        self.start_time = datetime.now()
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

        self.conversation_id = await self.init_user_and_conversation(phone_number, call_sid)
        
        # Set the current stream so the audio functions know which stream to use
        self.current_stream = stream_sid
        
        # Store the state
        self.stream_states[stream_sid] = initial_state
        
        # Send a welcome message immediately to let the user know they're connected
        welcome_text = f"""
        Bonjour! Et bienvenue chez Studi, l'école 100% en ligne !
        Je suis l'assistant virtuel Stud'IA, je prends le relais lorsque nos conseillers en formation ne sont pas présents.
        Souhaitez-vous prendre rendez-vous avec un conseiller ou que je vous aide à trouver quelle formation pourrait vous intéresser ?
        """
        welcome_text = "Salut !"

        try:
            # First, send our welcome message
            await self._speak_and_send_from_text(welcome_text)
            await self.studi_rag_inference_client.add_message_to_conversation(self.conversation_id, welcome_text)
            
            # Then invoke the graph with initial state to get the AI-generated welcome message
            updated_state = await self.compiled_graph.ainvoke(initial_state)
            self.stream_states[stream_sid] = updated_state
            
            # If there's an AI message from the graph, send it after the welcome message
            if updated_state.get('history') and updated_state['history'][0][0] == 'AI':
                ai_message = updated_state['history'][0][1]
                if ai_message and ai_message.strip() != welcome_text.strip():
                    await self._speak_and_send_from_text(ai_message)
                    await self.studi_rag_inference_client.add_message_to_conversation(self.conversation_id, ai_message)
        
        except Exception as e:
            self.logger.error(f"Error in initial graph invocation: {e}", exc_info=True)
            # If there was an error with the graph, we already sent our welcome message,
            # so we don't need to send a fallback
        
        return stream_sid

    async def init_user_and_conversation(self, calling_phone_number: str, call_sid: str):
        """ Initialize the user session: create user and conversation and send a welcome message """
        # Ensure user_name and IP are valid strings
        user_name_val = "Twilio incoming call " + (calling_phone_number or "Unknown User")
        ip_val = calling_phone_number or "Unknown IP"
        user_RM = UserRequestModel(
            user_id=None,
            user_name=user_name_val,
            IP=ip_val,
            device_info=DeviceInfoRequestModel(user_agent="twilio", platform="phone", app_version="", os="", browser="", is_mobile=True)
        )
        try:
            user = await self.studi_rag_inference_client.create_or_retrieve_user(user_RM)
            user_id = user['id']
            
            # Convert user_id to UUID if it's a string
            if isinstance(user_id, str): user_id = UUID(user_id)
                
            # Create empty messages list
            from app.api_client.request_models.conversation_request_model import MessageRequestModel
            messages = []
            
            # Create the conversation request model
            conversation_model = ConversationRequestModel(user_id=user_id, messages=messages)
            
            self.logger.info(f"Creating new conversation for user: {user_id}")
            new_conversation = await self.studi_rag_inference_client.create_new_conversation(conversation_model)
            return new_conversation['id']

        except Exception as e:
            self.logger.error(f"Error creating conversation: {str(e)}")
            return str(uuid.uuid4())

    async def websocket_handler(self, calling_phone_number: str, call_sid: str) -> None:
        """Main WebSocket handler for Twilio streams."""
        if not self.websocket:
            self.logger.error("WebSocket not set, cannot handle WebSocket connection.")
            return
        
        if not self.compiled_graph:
            self.logger.error("Graph not compiled, cannot handle WebSocket connection.")
            await self.websocket.close(code=1011, reason="Server configuration error")
            return

        self.logger.info(f"WebSocket handler started for {self.websocket.client.host}:{self.websocket.client.port}")
        
        # Store the caller's phone number and call SID so we can retrieve them later
        self.phones[call_sid] = calling_phone_number

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
                    await self._handle_start_event(data.get("start", {}))
                elif event == "media":
                    if not self.current_stream:
                        self.logger.warning("/!\\ Error: media event received before the start event")
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
        if chunk is None: 
            self.logger.warning("Received media event without valid audio chunk")
            return
        
        # Use WebRTC VAD for better speech detection
        is_silence, speech_to_noise_ratio = self.audio_processor.detect_silence_speech(
            chunk, threshold=self.speech_threshold
        )

        # 2. Silence detection before adding to buffer
        has_speech_began = len(self.audio_buffer) > 0

        # Count consecutive silence chunks in milliseconds
        if is_silence:
            # Calculate duration in milliseconds: (chunk_bytes / bytes_per_sample) / samples_per_second * 1000
            chunk_duration_ms = (len(chunk) / self.sample_width) / self.frame_rate * 1000
            self.consecutive_silence_duration_ms += chunk_duration_ms
            print(f"\rSilent chunk - Duration: {self.consecutive_silence_duration_ms:.1f}ms - Speech/noise: {speech_to_noise_ratio:04d} (size: {len(chunk)}B) ", end="", flush=True)

        # Add speech chunk to buffer
        if has_speech_began or not is_silence:
            self.audio_buffer += chunk
            self.consecutive_silence_duration_ms = 0.0

            self.logger.debug(
                f"Speech detected - RMS: {speech_to_noise_ratio}/{self.speech_threshold}, "
                f"Buffer size: {len(self.audio_buffer)} bytes"
            )

        is_long_silence_after_speech = has_speech_began and self.consecutive_silence_duration_ms >= self.required_silence_ms_to_answer 
        has_reach_min_speech_length = len(self.audio_buffer) >= self.min_audio_bytes_for_processing
        is_speech_too_long = len(self.audio_buffer) > self.max_audio_bytes_for_processing
        
        # 3. Process audio
        # Conditions: if buffer large enough followed by a prolonged silence, or if buffer is too large
        if (is_long_silence_after_speech and has_reach_min_speech_length) or is_speech_too_long:
            if is_speech_too_long:
                self.logger.info(f"Processing audio for stream {self.current_stream}: Buffer size limit reached. (buffer size: {len(self.audio_buffer)} bytes).")
            else:
                self.logger.info(f"Processing audio for stream {self.current_stream}: Silence after speech detected. (buffer size: {len(self.audio_buffer)} bytes).")
            
            audio_data = self.audio_buffer
            self.audio_buffer = b""
            self.consecutive_silence_duration_ms = 0.0

            # 4. Transcribe speech to text
            user_query_transcript = self._perform_speech_to_text_transcription(audio_data)
            if user_query_transcript is None:
                return
            
            # 5. Feedback the request to the user
            #spoken_text = await self.send_ask_feedback(transcript)
            request = QueryAskingRequestModel(
                conversation_id=self.conversation_id,
                user_query_content= user_query_transcript,
                display_waiting_message=False
            )
            try:
                self.logger.info(f"Sending request to RAG API for stream: {self.current_stream}")
                start_time = time.time()
                response = self.studi_rag_inference_client.rag_query_stream_async(request, timeout=60)
                full_answer = ""
                async for chunk in response:
                    full_answer += chunk
                    self.logger.debug(f"Received chunk: {chunk}")
                    print(f">> RAG API response: {full_answer}", end="", flush=True)
                    await self._speak_and_send_from_text(chunk)
                end_time = time.time()
                if full_answer:
                    self.logger.info(f"Full answer gotten from RAG API in {end_time - start_time:.2f}s. : {full_answer}")
                else:
                    self.logger.warning(f"Empty response received from RAG API")
            except Exception as e:
                error_message = f"Je suis désolé, une erreur s'est produite lors de la communication avec le service."
                self.logger.error(f"Error in RAG API communication: {str(e)}")
                await self._speak_and_send_from_text(error_message)

            # 5. Process user's query through conversation graph
            #response_text = await self._process_conversation(transcript)

        return

    async def send_ask_feedback(self, transcript):
        response_text = "Instructions : Fait un feedback reformulé de façon synthétique de la demande utilisateur suivante, afin de t'assurer de ta bonne comphéhension de celle-ci : " + transcript 
        response = self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": response_text}
            ],
            stream=True
        )
        if response:
            spoken_text = await self._speak_and_send_from_stream(response)
            self.logger.info(f"<< Response text: '{spoken_text}'")
            return spoken_text
        return ""
   
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

    def _perform_speech_to_text_transcription(self, audio_data: bytes):
        try:
            # Check if the audio buffer has a high enough speech to noise ratio
            speech_to_noise_ratio = audioop.rms(audio_data, self.sample_width)
            if speech_to_noise_ratio < self.speech_threshold:
                if random.random() < 0.1: # log 1/10 of the time
                    self.logger.info(f"[Silence/Noise] Low speech/noise ratio detected: {speech_to_noise_ratio}. Transcription skipped")
                return None
                
            self.logger.info(f"[Speech] High speech/noise ratio detected: {speech_to_noise_ratio}. Processing transcription.")
            
            # Apply audio preprocessing to improve quality
            self.logger.info("Applying audio preprocessing...")
            processed_audio = self.audio_processor.preprocess_audio(audio_data)
            self.logger.info(f"Audio preprocessing complete. Original size: {len(audio_data)} bytes, Processed size: {len(processed_audio)} bytes")
                
            # Save the processed audio to a file
            wav_file_name = self.save_as_wav_file(processed_audio)
            
            # Transcribe using the hybrid STT provider
            self.logger.info("Transcribing audio with hybrid STT provider...")
            transcript: str = self.stt_provider.transcribe_audio(wav_file_name)
            self.logger.info(f">> Speech to text transcription: '{transcript}'")
            #self.delete_temp_file(wav_file_name)
            
            # Filter out known watermark text that appears during silences
            known_watermarks = [
                "Sous-titres réalisés para la communauté d'Amara.org",
                "Sous-titres réalisés par la communauté d'Amara.org",
                "Sous-titres réalisés",
                "Sous-titres",
                "Amara.org",
                "❤️ par SousTitreur.com...",
                "SousTitreur.com",
                "Merci d'avoir regardé cette vidéo, n'hésitez pas à vous abonner à la chaîne pour ne manquer aucune de mes prochaines vidéos.",
                "Merci d'avoir regardé cette vidéo",
                "Merci à tous et à la prochaine",
                "c'est la fin de la vidéo"
            ]
            
            # Check if transcript contains any of the known watermarks
            if any(watermark.lower() in transcript.lower() for watermark in known_watermarks):
                self.logger.warning(f"!!! Detected watermark in transcript, ignoring: '{transcript}'")
                return None
                
            # If transcript is too short, it might be noise
            if len(transcript.strip()) < 2:
                self.logger.info(f"Transcript too short, ignoring: '{transcript}'")
                return None
                
            return transcript
            
        except Exception as speech_err:
            self.logger.error(f"Error during transcription: {speech_err}", exc_info=True)
            return None
    
    def delete_temp_file(self, file_name: str):
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
                updated_state: ConversationState = await self.compiled_graph.ainvoke(
                    current_state,
                    {"recursion_limit": 15}  # Prevent infinite loops
                )
                
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

    async def _speak_and_send_from_stream(self, answer_stream: Stream):
        """Synthesize speech from text and send to Twilio"""
        try:
            full_text = ""
            text_buffer = ""
            for chunk in answer_stream:
                if chunk.choices:
                    delta_content = chunk.choices[0].delta.content
                    if delta_content is not None:
                        text_buffer += delta_content
                        # Check if we should send this segment (after punctuation or if long enough)
                        if len(text_buffer) > 1 and (any(punct in delta_content for punct in [".", ",", ":", "!", "?"]) or len(text_buffer.split()) > 20):
                            await self._speak_and_send_from_text(text_buffer)
                            full_text += text_buffer
                            text_buffer = ""
            
            # Send any remaining text after the loop completes
            if text_buffer:
                await self._speak_and_send_from_text(text_buffer)
                full_text += text_buffer
            
            return full_text
        except Exception as e:
            self.logger.error(f"/!\\ Error sending audio to Twilio in {self._speak_and_send_from_stream.__name__}: {e}", exc_info=True)
            return ""

    async def _speak_and_send_from_text(self, text_buffer: str):
        audio_bytes = self.tts_provider.synthesize_speech_to_bytes(text_buffer)
        await self.send_audio_to_twilio(audio_bytes= audio_bytes)

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
    
    def save_as_wav_file(self, audio_data: bytes):
        """Save PCM data (16-bit, 8kHz, mono) to a WAV file at the specified path."""
        file_name = f"{uuid.uuid4()}.wav"
        with wave.open(os.path.join(self.TEMP_DIR, file_name), "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(self.sample_width)  # 16-bit
            wav_file.setframerate(self.frame_rate)
            wav_file.writeframes(audio_data)
        return file_name
    
    def _prepare_voice_stream(self, file_path: str=None, audio_bytes: bytes=None, frame_rate: int=None, channels: int=1, sample_width: int=None, convert_to_mulaw: bool = False):
        # Use instance defaults if not specified
        frame_rate = frame_rate or self.frame_rate
        sample_width = sample_width or self.sample_width
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
    
    async def send_audio_to_twilio_old(self, mp3_path):
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
            audio = AudioSegment.from_file(mp3_path).set_frame_rate(self.frame_rate).set_channels(1).set_sample_width(self.sample_width)
            pcm_data = audio.raw_data

            # Convertir en μ-law
            ulaw_data = audioop.lin2ulaw(pcm_data, self.sample_width)  # 2 = 16 bits

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

    async def send_audio_to_twilio(self, file_path: str=None, audio_bytes: bytes=None, frame_rate: int=None, channels: int=1, sample_width: int=None, convert_to_mulaw: bool = False):
        # Use instance defaults if not specified
        frame_rate = frame_rate or self.frame_rate
        sample_width = sample_width or self.sample_width
        """Convert mp3 to μ-law and send to Twilio over WebSocket."""
        if not self.websocket:
            self.logger.error("WebSocket not set, cannot send audio")
            return False
            
        try:
            # Load audio and convert to appropriate format for Twilio (8kHz μ-law)
            ulaw_data = self._prepare_voice_stream(file_path=file_path, audio_bytes=audio_bytes, frame_rate=frame_rate, channels=channels, sample_width=sample_width, convert_to_mulaw=True)
            if file_path:
                self.delete_temp_file(file_path)
            
            chunk_size = 6400  # 0.4s at 8kHz
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