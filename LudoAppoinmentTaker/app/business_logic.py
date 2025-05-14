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
        self.required_silence_ms_to_answer = 500  # Require 800ms of silence to process audio
        self.speech_chunk_duration_ms = 400  # Duration of each audio chunk in milliseconds
        
        self.audio_buffer = b""
        self.current_stream = None
        self.start_time = None
        
        # Audio streaming queue system
        self.audio_queue = asyncio.Queue()
        self.stream_worker_task = None
        self.is_streaming = False
        self.chunk_lock = asyncio.Lock()  # Lock to prevent concurrent WebSocket operations         

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
    
    async def _handle_connected_event(self):
        """Handle the 'connected' event from Twilio."""
        self.logger.info("Twilio WebSocket connected")
        
        # Start the streaming worker if it's not already running
        if not self.is_streaming and not self.stream_worker_task:
            self.is_streaming = True
            self.stream_worker_task = asyncio.create_task(self._streaming_worker())
            self.logger.info("Started audio streaming worker task")
            
    async def _streaming_worker(self):
        """Background worker that processes the audio queue and sends to Twilio.
        Uses cooperative yielding to avoid blocking the event loop.
        """
        self.logger.info("Audio streaming worker started")
        
        try:
            while self.is_streaming:
                try:
                    # Check if there are items in the queue before waiting
                    if self.audio_queue.empty():
                        # Yield control to other tasks using a short sleep
                        await asyncio.sleep(0.01)  # 10ms yield
                        continue
                        
                    # Get item without blocking indefinitely
                    audio_item = self.audio_queue.get_nowait()
                    
                    # Process the queue item
                    success = await self._process_audio_queue_item(audio_item)
                    
                    # Mark the task as done regardless of success
                    self.audio_queue.task_done()
                    
                    if not success:
                        self.logger.warning("Error processing queue item, but continuing worker")
                    
                    # Yield control briefly after processing each item
                    # This is critical to prevent blocking the event loop
                    await asyncio.sleep(0)  # Yield control but resume immediately
                    
                except asyncio.QueueEmpty:
                    # Queue was empty after all, just yield and continue
                    await asyncio.sleep(0.01)  # 10ms yield
                except Exception as e:
                    self.logger.error(f"Error in streaming worker: {e}", exc_info=True)
                    # Brief pause to avoid tight loop in error conditions
                    await asyncio.sleep(0.01)  # 10ms yield
        except asyncio.CancelledError:
            self.logger.info("Audio streaming worker cancelled")
        except Exception as e:
            self.logger.error(f"Unexpected error in streaming worker: {e}", exc_info=True)
        finally:
            self.logger.info("Audio streaming worker stopped")
            self.is_streaming = False
            
    async def _process_audio_queue_item(self, item):
        """Process a single audio queue item and send it to Twilio."""
        if not item or 'type' not in item:
            self.logger.warning("Invalid queue item")
            return False
            
        # Acquire the lock to prevent concurrent access to the WebSocket
        async with self.chunk_lock:
            # Check websocket is still connected before starting
            if not self._is_websocket_connected():
                self.logger.warning("WebSocket disconnected - dropping queue item")
                return False
                
            try:
                if item['type'] == 'audio_chunk':
                    # Process audio chunk
                    chunk = item.get('data')
                    stream_sid = item.get('stream_sid')
                    
                    # Skip if missing required data
                    if not chunk or not stream_sid:
                        return False
                        
                    # Confirm stream_sid matches current stream
                    if stream_sid != self.current_stream:
                        self.logger.warning(f"Stream mismatch: queued {stream_sid} vs current {self.current_stream}")
                        return False
                        
                    # Send the audio data chunk
                    payload = base64.b64encode(chunk).decode()
                    msg = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": payload
                        }
                    }
                    
                    # Send with brief timeout
                    await asyncio.wait_for(self.websocket.send_text(json.dumps(msg)), timeout=1.0)
                    return True
                    
                elif item['type'] == 'mark':
                    # Process mark event
                    mark_name = item.get('name', 'segment')
                    stream_sid = item.get('stream_sid')
                    
                    if not stream_sid:
                        return False
                        
                    # Send the mark event
                    mark_msg = {
                        "event": "mark",
                        "streamSid": stream_sid,
                        "mark": {
                            "name": mark_name
                        }
                    }
                    
                    await asyncio.wait_for(self.websocket.send_text(json.dumps(mark_msg)), timeout=1.0)
                    return True
                    
                elif item['type'] == 'pause':
                    # Just a pause, no need to send anything
                    duration = item.get('duration', 0.2)
                    await asyncio.sleep(duration)
                    return True
                    
                else:
                    self.logger.warning(f"Unknown queue item type: {item['type']}")
                    return False
                    
            except asyncio.TimeoutError:
                self.logger.error("Timeout sending to Twilio WebSocket")
                return False
            except Exception as e:
                self.logger.error(f"Error processing queue item: {e}")
                return False
    
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
            await self.speak_and_send_text(welcome_text)
            await self.studi_rag_inference_client.add_message_to_conversation(self.conversation_id, welcome_text)
            
            # Then invoke the graph with initial state to get the AI-generated welcome message
            updated_state = await self.compiled_graph.ainvoke(initial_state)
            self.stream_states[stream_sid] = updated_state
            
            # If there's an AI message from the graph, send it after the welcome message
            if updated_state.get('history') and updated_state['history'][0][0] == 'AI':
                ai_message = updated_state['history'][0][1]
                if ai_message and ai_message.strip() != welcome_text.strip():
                    await self.speak_and_send_text(ai_message)
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
        """Main WebSocket handler for Twilio streams with enhanced logging."""
        if not self.websocket:
            self.logger.error("WebSocket not set, cannot handle WebSocket connection.")
            return
        
        if not self.compiled_graph:
            self.logger.error("Graph not compiled, cannot handle WebSocket connection.")
            await self.websocket.close(code=1011, reason="Server configuration error")
            return

        start_time = time.time()
        remote_addr = f"{self.websocket.client.host}:{self.websocket.client.port}"
        self.logger.info(f"WebSocket handler started for {remote_addr}")
        
        # Log initial WebSocket state and attributes
        try:
            ws_attrs = {attr: getattr(self.websocket, attr) for attr in dir(self.websocket) 
                       if not attr.startswith('_') and not callable(getattr(self.websocket, attr))}
            self.logger.debug(f"Initial WebSocket state: {ws_attrs}")
        except Exception as attr_err:
            self.logger.debug(f"Could not log WebSocket attributes: {attr_err}")
        
        # Store the caller's phone number and call SID so we can retrieve them later
        self.phones[call_sid] = calling_phone_number

        # Track activity for diagnostics
        last_activity = time.time()
        message_count = 0

        try:            
            while True:
                # Check if the WebSocket is still connected before trying to receive
                if not self._is_websocket_connected():
                    self.logger.warning(f"WebSocket connectivity check failed before receive_text()")
                    # Try to get more info about what happened
                    idle_time = time.time() - last_activity
                    self.logger.info(f"Connection stats: {message_count} messages processed, {idle_time:.2f}s since last activity")
                    break
                    
                try:
                    # Set a reasonable timeout for receiving messages - prevents indefinite hanging
                    # Use wait_for with a timeout of 30 seconds
                    msg = await asyncio.wait_for(self.websocket.receive_text(), timeout=30.0)
                    last_activity = time.time()
                    message_count += 1
                    
                    # Process the message
                    data = self._decode_json(msg)
                    if data is None:
                        continue
                        
                except asyncio.TimeoutError:
                    idle_time = time.time() - last_activity
                    self.logger.warning(f"No WebSocket activity for {idle_time:.2f}s - checking connection")
                    # Don't break - just log and let the loop continue
                    continue
                    
                except WebSocketDisconnect as disconnect_err:
                    session_time = time.time() - start_time
                    self.logger.info(f"WebSocket disconnected: {remote_addr} - Code: {disconnect_err.code} after {session_time:.2f}s")
                    self.logger.info(f"Connection stats at disconnect: {message_count} messages processed")
                    break
                    
                except RuntimeError as rt_err:
                    # This catches specific errors like "WebSocket is not connected"
                    self.logger.error(f"WebSocket runtime error: {rt_err}")
                    self.logger.info(f"Connection stats at error: {message_count} messages, {time.time() - last_activity:.2f}s since activity")
                    break
                    
                except Exception as recv_err:
                    # Something else went wrong during receive
                    self.logger.error(f"Unexpected error receiving WebSocket message: {recv_err}", exc_info=True)
                    break
                
                # Process the event
                try:    
                    event = data.get("event")
                    if event == "connected":
                        self._handle_connected_event()
                    elif event == "start":
                        await self._handle_start_event(data.get("start", {}))
                    elif event == "media":
                        if not self.current_stream:
                            self.logger.warning("/!\ Error: media event received before the start event")
                            continue
                        await self._handle_media_event(data)
                    elif event == "stop":
                        await self._handle_stop_event()
                    else:
                        self.logger.warning(f"Unknown event: {event}")
                except Exception as event_err:
                    self.logger.error(f"Error processing event '{data.get('event')}': {event_err}", exc_info=True)
        except Exception as outer_err:
            # Catch any errors in the main handler loop
            self.logger.error(f"Unhandled error in WebSocket main loop: {outer_err}", exc_info=True)
        finally:
            # Log session information on exit
            session_duration = time.time() - start_time
            remote_addr = f"{self.websocket.client.host}:{self.websocket.client.port}"
            self.logger.info(f"WebSocket handler finished for {remote_addr} (Stream: {self.current_stream})")
            self.logger.info(f"Session stats: Duration {session_duration:.2f}s, {message_count} messages processed")
            
            # Clean up the stream state if it wasn't already done by a stop event
            if self.current_stream and self.current_stream in self.stream_states:
                self.logger.warning(f"Cleaning up state for stream {self.current_stream} due to handler exit/error.")
                self._clean_stream_state(self.current_stream)
            
            self.logger.info(f"WebSocket endpoint finished for: {remote_addr} (Stream: {self.current_stream})")
    
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
                display_waiting_message=True
            )
            try:
                self.logger.info(f"Sending request to RAG API for stream: {self.current_stream}")
                start_time = time.time()
                response = self.studi_rag_inference_client.rag_query_stream_async(request, timeout=60)
                full_answer = ""
                async for chunk in response:
                    full_answer += chunk
                    self.logger.debug(f"Received chunk: {chunk}")
                    self.logger.info(f'"" RAG API response\'s chunk: ... {chunk} ... ""')
                    await self.speak_and_send_text(chunk)
                end_time = time.time()
                if full_answer:
                    self.logger.info(f"Full answer gotten from RAG API in {end_time - start_time:.2f}s. : {full_answer}")
                else:
                    self.logger.warning(f"Empty response received from RAG API")
            except Exception as e:
                error_message = f"Je suis désolé, une erreur s'est produite lors de la communication avec le service."
                self.logger.error(f"Error in RAG API communication: {str(e)}")
                await self.speak_and_send_text(error_message)

            # 5. Process user's query through conversation graph
            #response_text = await self._process_conversation(transcript)

        return

    async def speak_and_send_ask_for_feedback(self, transcript):
        response_text = "Instructions : Fait un feedback reformulé de façon synthétique de la demande utilisateur suivante, afin de t'assurer de ta bonne comphéhension de celle-ci : " + transcript 
        response = self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": response_text}
            ],
            stream=True
        )
        if response:
            spoken_text = await self.speak_and_send_stream(response)
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
            self.delete_temp_file(wav_file_name)
            
            # Filter out known watermark text that appears during silences
            known_watermarks = [
                "communauté d'Amara.org",
                "Sous-titres réalisés",
                "Amara.org",
                "SousTitreur.com",
                "n'hésitez pas à vous abonner",
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
        try:
            os.remove(os.path.join(self.TEMP_DIR, file_name))
        except Exception as e:
            self.logger.error(f"Error deleting temp file {file_name}: {e}")
            
    def _is_websocket_connected(self) -> bool:
        """Check if the websocket is still connected with enhanced monitoring"""
        if not self.websocket:
            self.logger.debug("No websocket object available")
            return False
            
        try:
            # Check for common disconnection indicators
            # 1. Check if the connection was explicitly closed
            if hasattr(self.websocket, 'closed') and self.websocket.closed:
                self.logger.debug("WebSocket reports closed=True")
                return False
                
            # 2. Check for client_state attribute in Starlette/FastAPI WebSockets
            if hasattr(self.websocket, 'client_state'):
                state_str = str(self.websocket.client_state)
                self.logger.debug(f"WebSocket client_state: {state_str}")
                
                # If client_state is an enum with CONNECTED attribute (Starlette) 
                if hasattr(self.websocket.client_state, 'CONNECTED'):
                    is_connected = (self.websocket.client_state == self.websocket.client_state.CONNECTED)
                    self.logger.debug(f"WebSocket CONNECTED enum check: {is_connected}")
                    return is_connected
                    
                # If client_state is a string, check for 'connect' substring
                if isinstance(self.websocket.client_state, str):
                    is_connected = 'connect' in state_str.lower() and 'disconnect' not in state_str.lower()
                    self.logger.debug(f"WebSocket string state check: {is_connected} (state='{state_str}')")
                    return is_connected
            
            # 3. For Twilio-specific WebSocket implementations, try additional checks
            if hasattr(self.websocket, 'application_state'):
                self.logger.debug(f"WebSocket application_state: {self.websocket.application_state}")
            
            # 4. Check transport-level connection if available
            if hasattr(self.websocket, 'transport') and hasattr(self.websocket.transport, 'is_closing'):
                if self.websocket.transport.is_closing():
                    self.logger.debug("WebSocket transport is closing")
                    return False
            
            # If we've made it this far without a definitive answer, try a very basic check
            # This may not be 100% reliable but is a good fallback
            if hasattr(self.websocket, '_send_lock'):
                # Presence of a _send_lock often indicates an active connection
                self.logger.debug("WebSocket has _send_lock, assuming connected")
                return True
                
            # Default to assuming it's connected if we can't definitively determine state
            self.logger.debug("No definitive connection state found, assuming connected")
            return True
            
        except Exception as e:
            self.logger.warning(f"Error checking websocket connection: {e}")
            # Log WebSocket attributes for debugging
            self.logger.debug(f"WebSocket attributes: {[attr for attr in dir(self.websocket) if not attr.startswith('_')]}")
            # For safety, if we had an exception checking, assume connected
            return True
    
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

    async def speak_and_send_stream(self, answer_stream: Stream):
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
                            await self.speak_and_send_text(text_buffer)
                            full_text += text_buffer
                            text_buffer = ""
            
            # Send any remaining text after the loop completes
            if text_buffer:
                await self.speak_and_send_text(text_buffer)
                full_text += text_buffer
                # Add a small pause between chunks (100-200ms)
                await asyncio.sleep(0.15)
            
            return full_text
        except Exception as e:
            self.logger.error(f"/!\\ Error sending audio to Twilio in {self.speak_and_send_stream.__name__}: {e}", exc_info=True)
            return ""

    async def speak_and_send_text(self, text_buffer: str):
        audio_bytes = self.tts_provider.synthesize_speech_to_bytes(text_buffer)
        await self.enqueue_send_audio_to_twilio(audio_bytes= audio_bytes, frame_rate=self.frame_rate, sample_width=self.sample_width)

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
            
    async def enqueue_send_audio_to_twilio(self, file_path: str=None, audio_bytes: bytes=None, frame_rate: int=None, channels: int=1, sample_width: int=None, convert_to_mulaw: bool = False):
        """Enqueue audio delivery to Twilio via the streaming worker task.
        This decouples audio generation from WebSocket transmission for more reliable streaming.
        Ensures non-blocking behavior by creating a separate task for queue filling.
        """
        # Use instance defaults if not specified
        frame_rate = frame_rate or self.frame_rate
        sample_width = sample_width or self.sample_width
        
        # Basic validation
        if not self.current_stream:
            self.logger.error("No active stream, cannot send audio")
            return False
            
        # Start a separate task to fill the queue to avoid blocking
        enqueue_task = asyncio.create_task(
            self._fill_audio_queue(
                file_path=file_path, 
                audio_bytes=audio_bytes,
                frame_rate=frame_rate, 
                channels=channels,
                sample_width=sample_width, 
                convert_to_mulaw=convert_to_mulaw
            )
        )
        
        # We don't await the task - this allows it to run concurrently
        self.logger.debug("Started audio enqueuing task")
        return True
        
    async def _fill_audio_queue(self, file_path: str=None, audio_bytes: bytes=None, frame_rate: int=None, 
                               channels: int=1, sample_width: int=None, convert_to_mulaw: bool = False):
        """Helper method to fill the audio queue in a separate task."""
        start_time = time.time()
        
        try:
            # Load audio and convert to appropriate format
            ulaw_data = self._prepare_voice_stream(file_path=file_path, audio_bytes=audio_bytes, 
                                                 frame_rate=frame_rate, channels=channels, 
                                                 sample_width=sample_width, convert_to_mulaw=True)
            if file_path:
                self.delete_temp_file(file_path)
            
            # Calculate chunk size based on duration
            chunk_size = int((self.speech_chunk_duration_ms / 1000) * frame_rate * sample_width)
            
            # Calculate total audio attributes
            total_audio_seconds = (len(ulaw_data) / (frame_rate * sample_width))
            total_chunks = len(ulaw_data) // chunk_size + (1 if len(ulaw_data) % chunk_size else 0)
            
            # Start the streaming worker if it's not already running
            if not self.is_streaming and not self.stream_worker_task:
                self.is_streaming = True
                self.stream_worker_task = asyncio.create_task(self._streaming_worker())
                self.logger.info("Started audio streaming worker task")
            
            # Break audio into small chunks for better handling
            # Smaller chunks process faster and allow more fine-grained control
            max_chunk_duration_ms = 500  # Maximum 500ms per chunk for better control
            chunks_per_group = max(1, int(max_chunk_duration_ms / self.speech_chunk_duration_ms))
            total_groups = (total_chunks + chunks_per_group - 1) // chunks_per_group
            
            self.logger.info(f"-> Queueing {total_audio_seconds:.2f}s of audio splitted in {total_chunks} chunks ({total_groups} groups)")
            
            # Queue all audio chunks with small pauses between groups
            chunks_queued = 0
            
            for group in range(total_groups):
                group_start = group * chunks_per_group * chunk_size
                group_end = min(group_start + (chunks_per_group * chunk_size), len(ulaw_data))
                group_data = ulaw_data[group_start:group_end]
                
                # Queue a small pause between groups to help Twilio connection
                if group > 0:
                    await self.audio_queue.put({
                        'type': 'pause',
                        'duration': 0.2,  # 200ms pause between groups
                        'stream_sid': self.current_stream
                    })
                
                # Process the audio group into individual chunks
                for i in range(0, len(group_data), chunk_size):
                    chunk = group_data[i:i + chunk_size]
                    
                    # Queue this chunk for processing
                    await self.audio_queue.put({
                        'type': 'audio_chunk',
                        'data': chunk,
                        'stream_sid': self.current_stream
                    })
                    chunks_queued += 1
                    
                    # Yield control after every chunk to prevent blocking
                    await asyncio.sleep(0)
                    
                    # Every N chunks, add a tiny pause (if not the last chunk)
                    if chunks_queued % 3 == 0 and chunks_queued < total_chunks:
                        await self.audio_queue.put({
                            'type': 'pause',
                            'duration': 0.05,  # 50ms mini-pause after every 3 chunks
                            'stream_sid': self.current_stream
                        })
            
            # Queue a mark after all chunks to indicate the end of this audio segment
            await self.audio_queue.put({
                'type': 'mark',
                'name': 'msg_retour',
                'stream_sid': self.current_stream
            })
            
            # Log queue statistics
            self.logger.info(f"Successfully queued {chunks_queued} audio chunks (~{total_audio_seconds:.2f}s)")
            return True
            
        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(f"Error preparing audio for queue: {elapsed:.2f}s elapsed: {e}", exc_info=True)
            return False