import io
import os
import wave
import base64
import random
import logging
import webrtcvad
import audioop
import time
import uuid
from uuid import UUID
from datetime import datetime
from pydub import AudioSegment
from pydub.effects import normalize
from openai import OpenAI
from fastapi import WebSocket
#
from app.api_client.request_models.user_request_model import UserRequestModel, DeviceInfoRequestModel
from app.api_client.request_models.conversation_request_model import ConversationRequestModel
from app.api_client.request_models.query_asking_request_model import QueryAskingRequestModel
from app.agents.conversation_state_model import ConversationState
from app.speech.outgoing_audio_manager import OutgoingAudioManager
from app.speech.text_to_speech import TextToSpeechProvider
from app.speech.speech_to_text import SpeechToTextProvider
from app.api_client.studi_rag_inference_api_client import StudiRAGInferenceApiClient
from app.agents.agents_graph import AgentsGraph

class IncomingAudioManager:
    """Audio processing utilities for improving speech recognition quality and handling Twilio events"""
    
    # Voice settings
    VOICE_ID = "alloy"
    
    # Temporary directory for audio files
    TEMP_DIR = "./static/audio"
    
    def __init__(self, websocket: any, studi_rag_inference_api_client : StudiRAGInferenceApiClient, tts_provider: TextToSpeechProvider, stt_provider: SpeechToTextProvider, streamSid: str = None, min_chunk_interval: float = 0.05, sample_width=2, frame_rate=8000, channels=1, vad_aggressiveness=3):
        self.logger = logging.getLogger(__name__)
        self.studi_rag_inference_api_client = studi_rag_inference_api_client
        self.audio_stream_manager : OutgoingAudioManager = OutgoingAudioManager(websocket, tts_provider, streamSid, min_chunk_interval, sample_width, frame_rate, channels)
        self.sample_width = sample_width
        self.frame_rate = frame_rate
        self.channels = channels
        self.vad = webrtcvad.Vad(vad_aggressiveness)
        self.logger.info(f"Initialized IncomingAudioProcessing with VAD aggressiveness {vad_aggressiveness}")
        
        # State tracking
        self.start_time = None
        self.current_stream = None
        self.conversation_id = None
        self.stream_states = {}
        self.phones = {}  # Map call_sid to phone numbers
        self.compiled_graph : AgentsGraph = None
        self.openai_client = None
        self.stt_provider = stt_provider
        self.rag_interrupt_flag = {"interrupted": False}
        self.is_speaking = False
        
        # Audio processing parameters
        self.audio_buffer = b""
        self.consecutive_silence_duration_ms = 0.0
        self.speech_threshold = 250  # RMS threshold for speech detection
        self.required_silence_ms_to_answer = 1000  # ms of silence to trigger transcript
        self.min_audio_bytes_for_processing = 1000  # Minimum buffer size to process
        self.max_audio_bytes_for_processing = 200000  # Maximum buffer size to process
        
        # Create temp directory if it doesn't exist
        os.makedirs(self.TEMP_DIR, exist_ok=True)

    def run_background_streaming_worker(self) -> None:
        """Start the audio output streaming worker"""
        self.audio_stream_manager.run_background_streaming_worker()

    async def stop_background_streaming_worker_async(self) -> None:
        """Stop the audio output streaming worker"""
        await self.audio_stream_manager.stop_background_streaming_worker_async()

    def set_websocket(self, websocket: WebSocket):
        self.websocket = websocket
        self.audio_stream_manager.set_websocket(websocket)

    def set_stream_sid(self, stream_sid: str) -> None:
        self.audio_stream_manager.update_stream_sid(stream_sid)
    
    def is_speech(self, audio_chunk: bytes, frame_duration_ms=30) -> bool:
        """
        Determine if audio chunk contains speech using WebRTC VAD
        
        Args:
            audio_chunk: Raw PCM audio bytes
            frame_duration_ms: Frame duration in milliseconds
        
        Returns:
            True if speech is detected, False otherwise
        """
        # WebRTC VAD only accepts 10, 20, or 30 ms frames
        if frame_duration_ms not in (10, 20, 30):
            frame_duration_ms = 30
            
        # Calculate frame size and ensure audio chunk is the right length
        frame_size = int(self.frame_rate * frame_duration_ms / 1000) * self.sample_width * self.channels
        
        # If chunk is too small, return False
        if len(audio_chunk) < frame_size:
            return False
            
        # If chunk is too large, only use the beginning
        if len(audio_chunk) > frame_size:
            audio_chunk = audio_chunk[:frame_size]
            
        try:
            return self.vad.is_speech(audio_chunk, self.frame_rate)
        except Exception as e:
            self.logger.error(f"VAD error: {e}")
            # Fallback to RMS-based detection
            rms = audioop.rms(audio_chunk, self.sample_width)
            return rms > 250  # Default threshold
    
    def preprocess_audio(self, audio_data: bytes) -> bytes:
        """
        Preprocess audio data to improve speech recognition quality
        
        Args:
            audio_data: Raw PCM audio bytes
            
        Returns:
            Processed audio bytes
        """
        try:
            # Convert bytes to AudioSegment via WAV
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.sample_width)
                wf.setframerate(self.frame_rate)
                wf.writeframes(audio_data)
            
            buffer.seek(0)
            audio = AudioSegment.from_wav(buffer)
            
            # Step 1: Normalize audio (adjust volume to optimal level)
            audio = normalize(audio)
            
            # Step 2: Apply high-pass filter to remove low-frequency noise
            audio = audio.high_pass_filter(80)
            
            # Convert back to bytes
            output = io.BytesIO()
            audio.export(output, format="wav")
            output.seek(0)
            
            # Extract raw PCM data from WAV
            with wave.open(output, 'rb') as wf:
                processed_audio = wf.readframes(wf.getnframes())
                
            return processed_audio
        except Exception as e:
            self.logger.error(f"Audio preprocessing error: {e}")
            # Return original data if processing fails
            return audio_data
    
    def detect_silence_speech(self, audio_data: bytes, threshold=250) -> tuple[bool, int]:
        """
        Detect silence vs speech using both VAD and RMS
        
        Args:
            audio_data: Raw PCM audio bytes
            threshold: RMS threshold for silence detection
            
        Returns:
            Tuple of (is_silence, speech_to_noise_ratio)
        """
        # Get RMS value (volume)
        speech_to_noise_ratio = audioop.rms(audio_data, self.sample_width)
        
        # Check using VAD (more accurate but may not work on all chunks)
        try:
            frame_size = len(audio_data)
            if frame_size >= 480:  # At least 30ms at 8kHz, 16-bit mono
                vad_result = self.is_speech(audio_data)
                if vad_result:
                    return False, speech_to_noise_ratio  # VAD detected speech
        except Exception:
            pass  # Fall back to RMS method
            
        # RMS-based detection (fallback)
        is_silence = speech_to_noise_ratio < threshold
        return is_silence, speech_to_noise_ratio
        
    async def handle_incoming_websocket_start_event_async(self, call_sid: str, stream_sid: str) -> str:
        """Handle the 'start' event from Twilio which begins a new call."""
        
        self.start_time = time.time()
        self.logger.info(f"Call started - CallSid: {call_sid}, StreamSid: {stream_sid}")
        
        # Set the current stream so the audio functions know which stream to use
        self.current_stream = stream_sid
        
        self.audio_stream_manager.update_stream_sid(stream_sid)
        self.logger.info(f"Updated OutgoingAudioManager with stream SID: {stream_sid}")
                
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
        
        # Store the initial state for this stream (used by graph and other handlers)
        self.stream_states[stream_sid] = initial_state
        
        try:
            
            # Then invoke the graph with initial state to get the AI-generated welcome message
            updated_state = await self.compiled_graph.ainvoke(initial_state)
            self.stream_states[stream_sid] = updated_state
            
            # If there's an AI message from the graph, send it after the welcome message
            if updated_state.get('history') and updated_state['history'][0][0] == 'AI':
                ai_message = updated_state['history'][0][1]
                if ai_message and ai_message.strip() != welcome_text.strip():
                    await self.speak_and_send_text(ai_message)
                    await self.studi_rag_inference_api_client.add_external_ai_message_to_conversation(self.conversation_id, ai_message)
        
        except Exception as e:
            self.logger.error(f"Error in initial graph invocation: {e}", exc_info=True)
            # If there was an error with the graph, we already sent our welcome message,
            # so we don't need to send a fallback
        
        return stream_sid

    async def handle_incoming_websocket_media_event_async(self, audio_data: dict) -> None:        
        if not self.current_stream:
            self.logger.error("/!\\ 'media event' received before the 'start event'")
            return
        
        # 1. Decode audio chunk
        chunk = self._decode_audio_chunk(audio_data)
        if chunk is None: 
            self.logger.warning("Received media event without valid audio chunk")
            return
                        
        # First, update the speaking state based on the queue status
        await self.update_is_speaking_state_async()
        
        # Check for speech while system is speaking (interruption detection)
        if self.is_speaking:
            # Check if this chunk contains speech - use a lower threshold to detect speech earlier
            is_silence, speech_to_noise_ratio = self.detect_silence_speech(
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
        is_silence, speech_to_noise_ratio = self.detect_silence_speech(
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
                response = self.studi_rag_inference_api_client.rag_query_stream_async(rag_query_RM, timeout=60, interrupt_flag=self.rag_interrupt_flag)
                # Use enhanced text-to-speech method for acknowledgment
                acknowledgment_text = f"OK. Vous avez demandé : {user_query_transcript}. Laissez-moi un instant pour rechercher des informations à ce sujet."
                await self.audio_stream_manager.enqueue_text(acknowledgment_text)
                
                full_answer = ""
                was_interrupted = False
                async for chunk in response:
                    # Vérifier si on a été interrompu entre les chunks
                    if was_interrupted:
                        self.logger.info("Speech interrupted while processing RAG response")
                        break
                        
                    full_answer += chunk
                    self.logger.debug(f"Received chunk: {chunk}")
                    print(f"<< ... {chunk} ... >>")
                    
                    # Sauvegarder l'état de parole avant de parler
                    speaking_before = self.is_speaking
                    
                    # Use the enhanced text processing for better speech quality
                    # Using smaller chunks for RAG responses to be more responsive
                    await self.audio_stream_manager.enqueue_text(chunk)
                    
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
                    self.logger.info(f"Full answer received from RAG API in {end_time - self.start_time:.2f}s: {full_answer[:100]}...")
                else:
                    self.logger.warning(f"Empty response received from RAG API")
                
            except Exception as e:
                error_message = f"Je suis désolé, une erreur s'est produite lors de la communication avec le service."
                self.logger.error(f"Error in RAG API communication: {str(e)}")
                # Use enhanced text-to-speech for error messages too
                await self.audio_stream_manager.enqueue_text(error_message)

            # 5 bis. Process user's query through conversation graph
            #response_text = await self._process_conversation(transcript)

        return
    
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
            user = await self.studi_rag_inference_api_client.create_or_retrieve_user(user_RM)
            user_id = user['id']
            
            # Convert user_id to UUID if it's a string
            if isinstance(user_id, str): user_id = UUID(user_id)
                
            # Create empty messages list
            messages = []
            
            # Create the conversation request model
            conversation_model = ConversationRequestModel(user_id=user_id, messages=messages)
            
            self.logger.info(f"Creating new conversation for user: {user_id}")
            new_conversation = await self.studi_rag_inference_api_client.create_new_conversation(conversation_model)
            return new_conversation['id']

        except Exception as e:
            self.logger.error(f"Error creating conversation: {str(e)}")
            return str(uuid.uuid4())

    def _decode_audio_chunk(self, data : dict):
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
        is_audio_file_to_delete = False
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
            processed_audio = self.preprocess_audio(audio_data)
            self.logger.info(f"Audio preprocessing complete. Original size: {len(audio_data)} bytes, Processed size: {len(processed_audio)} bytes")
                
            # Save the processed audio to a file
            wav_audio_filename = self.save_as_wav_file(processed_audio)
            is_audio_file_to_delete = False #True
            
            # Transcribe using the hybrid STT provider
            self.logger.info("Transcribing audio with hybrid STT provider...")
            transcript: str = self.stt_provider.transcribe_audio(wav_audio_filename)
            self.logger.info(f">> Speech to text transcription: '{transcript}'")
            
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
        finally:
            if is_audio_file_to_delete:
                self._delete_temp_file(wav_audio_filename)
    
    def _delete_temp_file(self, file_name: str):
        try:
            os.remove(os.path.join(self.TEMP_DIR, file_name))
        except Exception as e:
            self.logger.error(f"Error deleting temp file {file_name}: {e}")

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
    
    def save_as_wav_file(self, audio_data: bytes):
        """Save PCM data (16-bit, 8kHz, mono) to a WAV file at the specified path."""
        file_name = f"{uuid.uuid4()}.wav"
        with wave.open(os.path.join(self.TEMP_DIR, file_name), "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(self.sample_width)  # 16-bit
            wav_file.setframerate(self.frame_rate)
            wav_file.writeframes(audio_data)
        return file_name
            
    async def update_is_speaking_state_async(self):
        """
        Updates the speaking state based on the text queue status
        This provides a more accurate representation of when audio is actually being sent
        """
        is_sending_audio = self.audio_stream_manager.is_sending_speech()
        if is_sending_audio != self.is_speaking:
            if is_sending_audio:
                self.is_speaking = True
                # Log more detailed stats about the text queue
                stats = self.audio_stream_manager.get_streaming_stats()
                text_stats = stats['text_queue']
                self.logger.debug(f"Speaking started - Text queue: {text_stats['current_size_chars']} chars, " +
                                f"{text_stats['total_chars_processed']} chars processed so far")
            else:
                self.is_speaking = False
                self.logger.debug("Speaking stopped - Text queue empty")
    
    async def stop_speaking_async(self):
        """Stop any ongoing speech and clear text queue and interrupt RAG streaming"""
        if self.is_speaking:
            # Interrupt RAG streaming with its tag if it's active
            if hasattr(self, 'rag_interrupt_flag'):
                self.rag_interrupt_flag["interrupted"] = True
                self.logger.info("RAG streaming interrupted due to speech interruption")
                
            await self.audio_stream_manager.clear_text_queue()
            self.logger.info("Cleared text queue due to speech interruption")
            self.is_speaking = False
            return True  # Speech was stopped
        return False  # No speech was ongoing
