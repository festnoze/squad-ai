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

    async def init_user_and_new_conversation_upon_phone_call_async(self, calling_phone_number: str, call_sid: str):
        """ Initialize the user session: create user and conversation"""
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
            messages = []
            
            # Create the conversation request model
            conversation_model = ConversationRequestModel(user_id=user_id, messages=messages)
            
            self.logger.info(f"Creating new conversation for user: {user_id}")
            new_conversation = await self.studi_rag_inference_client.create_new_conversation(conversation_model)
            return new_conversation['id']

        except Exception as e:
            self.logger.error(f"Error creating conversation: {str(e)}")
            return str(uuid.uuid4())

    async def handle_ongoing_call_async(self, calling_phone_number: str, call_sid: str) -> None:
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
        self.audio_stream_manager.start_streaming()
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
        
        self.start_time = datetime.now()
        self.logger.info(f"Call started - CallSid: {call_sid}, StreamSid: {stream_sid}")
        
        # Set the current stream so the audio functions know which stream to use
        self.current_stream = stream_sid
        
        # Update the streamSid in the audio streaming manager
        if self.audio_stream_manager:
            # Update the streamSid in the audio sender
            self.audio_stream_manager.update_stream_sid(stream_sid)
            self.logger.info(f"Updated AudioStreamManager with stream SID: {stream_sid}")
        
        # Define the welcome message
        welcome_text = """
            Bienvenue chez Studi !
            Je suis l'assistant virtuel Stud'IA, je prends le relais lorsque nos conseillers ne sont pas présents.
            Puis-je vous aider à choisir votre formation ? Ou a prendre rendez-vous avec un conseiller en formation ?"""
        #welcome_text = "Salut !"

        # Play welcome message with enhanced text-to-speech
        self.logger.info(f"Playing welcome message with voice ID: {self.VOICE_ID}")
        await self.send_text_to_speak_to_twilio_async(welcome_text, max_words_per_chunk=10, max_chars_per_chunk=100)
        
        # Wait until the welcome message is finished playing
        # await asyncio.sleep(duration / 1000)
        # self.logger.info("Welcome message completed, now listening for user speech")

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
        # Now, initialize the user and conversation backend (this might take some time)
        self.conversation_id = await self.init_user_and_new_conversation_upon_phone_call_async(phone_number, call_sid)
        
        # Store the initial state for this stream (used by graph and other handlers)
        self.stream_states[stream_sid] = initial_state
        
        try:
            # Log the welcome message to our backend records
            await self.studi_rag_inference_client.add_external_ai_message_to_conversation(self.conversation_id, welcome_text)
            
            # # Then invoke the graph with initial state to get the AI-generated welcome message
            # updated_state = await self.compiled_graph.ainvoke(initial_state)
            # self.stream_states[stream_sid] = updated_state
            
            # # If there's an AI message from the graph, send it after the welcome message
            # if updated_state.get('history') and updated_state['history'][0][0] == 'AI':
            #     ai_message = updated_state['history'][0][1]
            #     if ai_message and ai_message.strip() != welcome_text.strip():
            #         await self.speak_and_send_text(ai_message)
            #         await self.studi_rag_inference_client.add_external_ai_message_to_conversation(self.conversation_id, ai_message)
        
        except Exception as e:
            self.logger.error(f"Error in initial graph invocation: {e}", exc_info=True)
            # If there was an error with the graph, we already sent our welcome message,
            # so we don't need to send a fallback
        
        return stream_sid

    async def _handle_media_event_async(self, data):
        
        if not self.current_stream:
            self.logger.error("/!\\ 'media event' received before the 'start event'")
            return
        
        # 1. Decode audio chunk
        chunk = self._decode_audio_chunk(data)
        if chunk is None: 
            self.logger.warning("Received media event without valid audio chunk")
            return
                        
        # First, update the speaking state based on the queue status
        await self.update_is_speaking_state_async()
        
        # Check for speech while system is speaking (interruption detection)
        if self.is_speaking:
            # Check if this chunk contains speech - use a lower threshold to detect speech earlier
            is_silence, speech_to_noise_ratio = self.incoming_audio.detect_silence_speech(
                chunk, threshold=self.speech_threshold * 0.8  # More sensitive detection while speaking
            )
            
            # If user is speaking while system is speaking, stop system speech
            # Use a lower threshold multiplier (1.2x instead of 1.5x) for quicker interruption
            if not is_silence and speech_to_noise_ratio > self.speech_threshold * 1.2:
                self.logger.info(f"Speech interruption detected (level: {speech_to_noise_ratio}), stopping system speech")
                await self.stop_speaking_async()
                # Reset buffer to clear any previous speech before interruption
                self.audio_buffer = b""
                self.consecutive_silence_duration_ms = 0.0
                # Add a message to the logs so we can track interruptions
                print(f"\r>>> USER INTERRUPTED - Speech detected while system was speaking ({speech_to_noise_ratio})")
        
        # Use WebRTC VAD for better speech detection
        is_silence, speech_to_noise_ratio = self.incoming_audio.detect_silence_speech(
            chunk, threshold=self.speech_threshold
        )

        # 2. Silence detection before adding to buffer
        has_speech_began = len(self.audio_buffer) > 0

        # Count consecutive silence chunks duration
        if is_silence:
            # Calculate duration
            chunk_duration_ms = (len(chunk) / self.sample_width) / self.frame_rate * 1000
            self.consecutive_silence_duration_ms += chunk_duration_ms
            msg = f"\rSilent chunk - Duration: {self.consecutive_silence_duration_ms:.1f}ms - Speech/noise: {speech_to_noise_ratio:04d} (size: {len(chunk)} bytes)."
            print(msg, end="", flush=True)

        # Add speech chunk to buffer
        if has_speech_began or not is_silence:
            self.audio_buffer += chunk
            self.consecutive_silence_duration_ms = 0.0

            if(random.randint(0, 100) < 1): # Log every 1%
                self.logger.debug(
                    f"Speech detected - RMS: {speech_to_noise_ratio}/{self.speech_threshold}, "
                    f"Buffer size: {len(self.audio_buffer)} bytes")

        is_long_silence_after_speech = has_speech_began and self.consecutive_silence_duration_ms >= self.required_silence_ms_to_answer 
        has_reach_min_speech_length = len(self.audio_buffer) >= self.min_audio_bytes_for_processing
        is_speech_too_long = len(self.audio_buffer) > self.max_audio_bytes_for_processing
        
        # 3. Process audio
        # Conditions: if buffer large enough followed by a prolonged silence, or if buffer is too large
        if (is_long_silence_after_speech and has_reach_min_speech_length) or is_speech_too_long:
            if is_speech_too_long:
                self.logger.info(f"Process incoming audio: Buffer size limit reached. (buffer size: {len(self.audio_buffer)} bytes).")
            else:
                self.logger.info(f"Process incoming audio: Silence after speech detected. (buffer size: {len(self.audio_buffer)} bytes).")
            
            audio_data = self.audio_buffer
            self.audio_buffer = b""
            self.consecutive_silence_duration_ms = 0.0

            # Waiting message
            #await self.speak_and_send_text("Très bien, je vais traiter votre demande.")

            # 4. Transcribe speech to text
            user_query_transcript = self._perform_speech_to_text_transcription(audio_data)
            if user_query_transcript is None:
                return
            
            # 5. Feedback the request to the user
            #spoken_text = await self.send_ask_feedback(transcript)
            try:
                self.logger.info(f"Sending request to RAG API for stream: {self.current_stream}")
                rag_query_RM = QueryAskingRequestModel(
                    conversation_id=self.conversation_id,
                    user_query_content= user_query_transcript,
                    display_waiting_message=False
                )
                self.rag_interrupt_flag = {"interrupted": False} # Reset the interrupt flag before starting new streaming
                response = self.studi_rag_inference_client.rag_query_stream_async(rag_query_RM, timeout=60, interrupt_flag=self.rag_interrupt_flag)
                # Use enhanced text-to-speech method for acknowledgment
                acknowledgment_text = f"OK. Vous avez demandé : {user_query_transcript}. Laissez-moi un instant pour rechercher des informations à ce sujet."
                await self.send_text_to_speak_to_twilio_async(acknowledgment_text, max_words_per_chunk=10, max_chars_per_chunk=100)
                
                full_answer = ""
                was_interrupted = False
                async for chunk in response:
                    # Vérifier si on a été interrompu entre les chunks
                    if not self.is_speaking:
                        was_interrupted = True
                        self.logger.info("Speech interrupted while processing RAG response")
                        break
                        
                    full_answer += chunk
                    self.logger.debug(f"Received chunk: {chunk}")
                    print(f"<< ... {chunk} ... >>")
                    
                    # Sauvegarder l'état de parole avant de parler
                    speaking_before = self.is_speaking
                    
                    # Use the enhanced text processing for better speech quality
                    # Using smaller chunks for RAG responses to be more responsive
                    await self.send_text_to_speak_to_twilio_async(chunk, max_words_per_chunk=6, max_chars_per_chunk=75)
                    
                    # Vérifier si on a été interrompu pendant qu'on parlait
                    if speaking_before and not self.is_speaking:
                        was_interrupted = True
                        self.logger.info("Speech interrupted during RAG response chunk")
                        break
                
                # Loguer les résultats du traitement RAG
                end_time = time.time()
                if was_interrupted:
                    self.logger.info(f"RAG streaming was interrupted")
                elif full_answer:
                    self.logger.info(f"Full answer received from RAG API in {end_time - start_time:.2f}s: {full_answer[:100]}...")
                else:
                    self.logger.warning(f"Empty response received from RAG API")
                
            except Exception as e:
                error_message = f"Je suis désolé, une erreur s'est produite lors de la communication avec le service."
                self.logger.error(f"Error in RAG API communication: {str(e)}")
                # Use enhanced text-to-speech for error messages too
                await self.send_text_to_speak_to_twilio_async(error_message, max_words_per_chunk=8, max_chars_per_chunk=100)

            # 5. Process user's query through conversation graph
            #response_text = await self._process_conversation(transcript)

        return

    async def speak_and_send_ask_for_feedback_async(self, transcript):
        response_text = "Instructions : Fait un feedback reformulé de façon synthétique de la demande utilisateur suivante, afin de t'assurer de ta bonne comphéhension de celle-ci : " + transcript 
        response = self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": response_text}
            ],
            stream=True
        )
        if response:
            spoken_text = await self.speak_and_send_stream_async(response)
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
            processed_audio = self.incoming_audio.preprocess_audio(audio_data)
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
                " par SousTitreur.com...",
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
        try:
            os.remove(os.path.join(self.TEMP_DIR, file_name))
        except Exception as e:
            self.logger.error(f"Error deleting temp file {file_name}: {e}")
            
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
    
    async def speak_and_send_stream_async(self, answer_stream):
        """Synthesize speech from text and send to Twilio"""
        try:
            # Mark the start of speech activity
            self.is_speaking = True
            self.logger.info("Starting streaming speech generation")
            
            full_text = ""
            text_buffer = ""
            # Flag to track if speech was interrupted
            was_interrupted = False
            
            for chunk in answer_stream:
                # Check if we've been interrupted - if so, stop processing further chunks
                if was_interrupted or self.is_speaking:
                    self.logger.info("Stream processing stopped due to interruption")
                    break
                    
                if chunk.choices:
                    delta_content = chunk.choices[0].delta.content
                    if delta_content is not None:
                        text_buffer += delta_content
                        # Send segment at sentence ends or max length
                        if len(text_buffer) > 1 and (any(punct in delta_content for punct in [".", ",", ":", "!", "?"]) or len(text_buffer.split()) > 20):
                            # If speaking is interrupted during this call, remember that
                            speaking_before = self.is_speaking
                            
                            # Use our enhanced text-to-speech method for better speech quality
                            await self.send_text_to_speak_to_twilio_async(text_buffer, max_words_per_chunk=8, max_chars_per_chunk=80)
                            
                            if speaking_before and not self.is_speaking:
                                # Speech was interrupted during this segment
                                was_interrupted = True
                                self.logger.info("Speech was interrupted during streaming, stopping further processing")
                                break
                                
                            full_text += text_buffer
                            text_buffer = ""
            
            # Only send remaining text if we weren't interrupted
            if text_buffer and not was_interrupted:
                self.logger.info(f"Processing final text chunk in stream: {len(text_buffer)} chars")
                await self.send_text_to_speak_to_twilio_async(text_buffer, max_words_per_chunk=8, max_chars_per_chunk=80)
                full_text += text_buffer
                
                # Log timing stats if audio stream manager is available
                if self.audio_stream_manager:
                    stats = self.audio_stream_manager.get_streaming_stats()
                    self.logger.info(f"Stream complete - Text stats: {stats['text_queue']['current_size_chars']} chars queued, " +
                                    f"chunks processed: {stats['audio_sender']['chunks_sent']}")
            
            return full_text
        except Exception as e:
            self.logger.error(f"/!\\ Error sending audio to Twilio in {self.speak_and_send_stream_async.__name__}: {e}", exc_info=True)
            return ""

    async def update_is_speaking_state_async(self):
        """
        Updates the speaking state based on the text queue status
        This provides a more accurate representation of when audio is actually being sent
        """
        if hasattr(self, 'audio_stream_manager') and self.audio_stream_manager:
            is_sending_audio = self.audio_stream_manager.is_actively_sending()
            if is_sending_audio != self.is_speaking:
                if is_sending_audio:
                    self.is_speaking = True
                    # Log more detailed stats about the text queue
                    stats = self.audio_stream_manager.get_streaming_stats()
                    text_stats = stats['text_queue']
                    self.logger.debug(f"Speaking started - Text queue: {text_stats['current_size_chars']} chars, " +
                                     f"{text_stats['total_chars_processed']} chars processed so far")

    async def send_text_to_speak_to_twilio_async(self, text_buffer: str, max_words_per_chunk: int = 15, max_chars_per_chunk: int = 150) -> float:
        """
        Enhanced version that processes text more intelligently for speech synthesis and streaming.
        Uses advanced text chunking and timing optimization for more natural speech.
        
        Args:
            text_buffer: The text to synthesize and send
            max_words_per_chunk: Maximum words per chunk for processing
            max_chars_per_chunk: Maximum characters per chunk
            
        Returns:
            Estimated total duration in milliseconds
        """
        if not text_buffer:
            self.logger.warning("Empty text buffer provided to send_text_to_speak_to_twilio")
            return 0
            
        self.is_speaking = True
        total_duration_ms = 0
        
        # Use the text chunking utilities for better speech chunking
        text_chunks = ProcessText.chunk_text_by_sized_sentences(text_buffer, max_words_per_chunk, max_chars_per_chunk)
        
        # Optimize timing between chunks for more natural speech
        timed_chunks = ProcessText.optimize_speech_timing(text_chunks)
        
        self.logger.info(f"Processing text into {len(text_chunks)} optimized chunks for speech")
        
        # Check if audio stream manager is initialized
        if not self.audio_stream_manager:
            self.logger.warning("Audio stream manager not initialized, using direct synthesis fallback")
            
            # Process each chunk with appropriate timing
            for chunk_text, start_time, end_time in timed_chunks:
                audio_bytes = self.tts_provider.synthesize_speech_to_bytes(chunk_text)
                await self.send_audio_to_twilio_async(audio_bytes=audio_bytes, frame_rate=self.frame_rate, sample_width=self.sample_width)
                
                # Use the exact timing from our optimization
                chunk_duration = end_time - start_time
                total_duration_ms += chunk_duration
                
                # Add a small natural pause between chunks
                await asyncio.sleep(0.1)
                
            return total_duration_ms
        
        # Use streaming approach with audio stream manager
        for chunk_text, _, end_time in timed_chunks:
            result = await self.audio_stream_manager.enqueue_text(chunk_text)
            
            if result:
                # Update total duration based on optimized timing
                total_duration_ms = end_time  # Last chunk's end time is the total duration
                self.logger.debug(f"Enqueued chunk: '{chunk_text[:20]}...' ({len(chunk_text)} chars)")
            else:
                self.logger.error(f"Failed to enqueue text chunk: '{chunk_text[:20]}...'")
                # Don't try to enqueue more if one fails
                break
                
        if total_duration_ms > 0:
            self.logger.info(f"Successfully enqueued {len(text_chunks)} chunks for streaming, estimated duration: {total_duration_ms/1000:.2f} seconds")
        else:
            self.logger.error("Failed to enqueue any text chunks for streaming")
            
        return total_duration_ms
        
    async def speak_and_send_text_async(self, text_buffer: str):
        """
        Legacy method that now uses the enhanced send_text_to_speak_to_twilio method.
        Kept for backward compatibility.
        
        Args:
            text_buffer: The text to synthesize and send
            
        Returns:
            Estimated duration in milliseconds
        """
        self.logger.debug(f"Using enhanced text processing for '{text_buffer[:30]}...'")
        
        # Use our enhanced method with default parameters
        return await self.send_text_to_speak_to_twilio_async(
            text_buffer=text_buffer,
            max_words_per_chunk=15,
            max_chars_per_chunk=150
        )

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
    
    async def stop_speaking_async(self):
        """Stop any ongoing speech and clear text queue and interrupt RAG streaming"""
        if self.is_speaking:
            # Interrupt RAG streaming if it's active
            if hasattr(self, 'rag_interrupt_flag'):
                self.rag_interrupt_flag["interrupted"] = True
                self.logger.info("RAG streaming interrupted due to speech interruption")
                
            if self.audio_stream_manager:
                await self.audio_stream_manager.clear_text_queue()
                self.logger.info("Cleared text queue due to speech interruption")
            self.is_speaking = False
            return True  # Speech was stopped
        return False  # No speech was ongoing
    
    async def send_audio_to_twilio_async(self, file_path: str=None, audio_bytes: bytes=None, frame_rate: int=None, channels: int=1, sample_width: int=None, convert_to_mulaw: bool = False):
        """Convert audio to μ-law and send to Twilio using throttled streaming to prevent disconnections."""
        # Use instance defaults if not specified
        frame_rate = frame_rate or self.frame_rate
        sample_width = sample_width or self.sample_width
        
        # Validate required parameters
        if not self.websocket:
            self.logger.error("WebSocket not set, cannot send audio")
            return False
            
        if not self.current_stream:
            self.logger.error("No active stream, cannot send audio")
            return False
        
        # Check connection state
        if not self._is_websocket_connected():
            self.logger.warning("WebSocket is not connected, cannot send audio")
            return False
        
        # Check if audio stream manager is initialized
        if not self.audio_stream_manager:
            self.logger.error("/!\\ Audio stream manager not initialized")
            return False
        
        # Start timing this operation
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
            
            # Log total audio being sent
            total_audio_ms = (len(ulaw_data) / (frame_rate * sample_width)) * 1000
            total_chunks = len(ulaw_data) // chunk_size + (1 if len(ulaw_data) % chunk_size else 0)
            
            self.logger.info(f"Sending {len(ulaw_data)} bytes of audio (~{total_audio_ms:.1f}ms) in {total_chunks} chunks using AudioStreamManager")
            
            # Split audio into chunks and queue them for throttled sending
            chunks_queued = 0
            for i in range(0, len(ulaw_data), chunk_size):
                chunk = ulaw_data[i:i + chunk_size]
                
                # Convert audio chunk directly to text for backward compatibility
                # This is needed during the transition period until all code is updated
                # to use the new text-based approach directly
                audio_text = f"<audio_binary:{len(chunk)}>"  # Placeholder text representing audio
                result = await self.audio_stream_manager.enqueue_text(audio_text)
                if result:
                    chunks_queued += 1
                
                # Log progress at regular intervals
                if chunks_queued % 10 == 0 or chunks_queued == total_chunks:
                    queue_stats = self.audio_stream_manager.get_streaming_stats()['text_queue']
                    elapsed = time.time() - start_time
                    progress_pct = (chunks_queued / total_chunks) * 100 if total_chunks > 0 else 0
                    self.logger.debug(f"Audio queued: {progress_pct:.1f}% - {chunks_queued}/{total_chunks} chunks - Queue size: {queue_stats['current_size_chars']} chars")
            
            # Try to send mark (but don't fail if it doesn't work)
            try:
                # Send mark to indicate end of message
                mark_msg = {
                    "event": "mark",
                    "streamSid": self.current_stream,
                    "mark": {
                        "name": "msg_retour"
                    }
                }
                await self.websocket.send_text(json.dumps(mark_msg))
            except Exception as mark_error:
                self.logger.warning(f"Could not send mark event: {mark_error}")
            
            # Final success logging
            total_time = time.time() - start_time
            self.logger.info(f"Audio queued: {chunks_queued}/{total_chunks} chunks, {total_audio_ms:.1f}ms audio in {total_time:.2f}s")
            return True
        
        except Exception as e:
            self.logger.error(f"Error sending audio to Twilio: {e}", exc_info=True)
            return False

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
    