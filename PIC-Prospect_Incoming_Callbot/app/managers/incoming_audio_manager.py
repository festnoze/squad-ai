import io
import os
import wave
import base64
import random
import logging
import webrtcvad
import audioop
import uuid
import logging
import time
import asyncio
from pydub import AudioSegment
from pydub.effects import normalize
from fastapi import WebSocket
#
from utils.envvar import EnvHelper
from agents.phone_conversation_state_model import ConversationState, PhoneConversationState
from speech.speech_to_text import SpeechToTextProvider
from agents.agents_graph import AgentsGraph
from managers.incoming_manager import IncomingManager
from managers.outgoing_audio_manager import OutgoingManager

class IncomingAudioManager(IncomingManager):
    """Audio processing utilities for improving speech recognition quality and handling Twilio events"""
    
    # Tmp directory for incoming audio files
    incoming_speech_dir = "./static/incoming_audio"   

    def __init__(self, websocket: WebSocket, stt_provider: SpeechToTextProvider,outgoing_manager: OutgoingManager, agents_graph : AgentsGraph, sample_width=2, frame_rate=8000, channels=1, vad_aggressiveness=3):
        self.logger = logging.getLogger(__name__)
        self.websocket : WebSocket = websocket
        self.stt_provider : SpeechToTextProvider = stt_provider
        self.outgoing_manager : OutgoingManager = outgoing_manager
        self.sample_width = sample_width
        self.frame_rate = frame_rate
        self.channels = channels
        self.vad = webrtcvad.Vad(vad_aggressiveness)
        self.logger.info(f"Initialized IncomingAudioProcessing with VAD aggressiveness {vad_aggressiveness}")
        self.stream_sid = None

        # State tracking
        self.start_time = None
        self.conversation_id = None
        self.websocket_creation_time = None
        self.stream_states : dict[str, ConversationState] = {}
        self.phones_by_call_sid = {}  # Map call_sid to phone numbers
        self.agents_graph : AgentsGraph = agents_graph
        self.openai_client = None
        self.rag_interrupt_flag = {"interrupted": False}
        self.is_speaking = False
        self.speak_anew_on_long_silence = False
        
        # Audio processing parameters
        self.audio_buffer = b""
        self.consecutive_silence_duration_ms = 0.0
        self.speech_threshold = 950  # RMS threshold for speech detection
        self.required_silence_ms_to_answer = 700  # ms of silence to trigger transcript
        self.min_audio_bytes_for_processing = 1000  # Minimum buffer size to process
        self.max_audio_bytes_for_processing = 200000  # Maximum buffer size to process
        self.max_silence_duration_before_reasking = 15 * 1000  # ms of silence before reasking
        self.max_silence_duration_before_hangup = 70 * 1000  # ms of silence before hanging up the call
        self.do_audio_preprocessing = EnvHelper.get_do_audio_preprocessing()
        
        # Create temp directory if it doesn't exist
        os.makedirs(self.incoming_speech_dir, exist_ok=True)

    def set_websocket(self, websocket: WebSocket):
        self.websocket = websocket
    
    def set_websocket_creation_time(self, creation_time: float):
        self.websocket_creation_time = creation_time

    def set_call_sid(self, call_sid: str) -> None:
        self.call_sid = call_sid      
        self.logger.info(f"Updated Incoming / Outgoing AudioManagers to call SID: {call_sid}")

    def set_stream_sid(self, stream_sid: str) -> None:
        self.stream_sid = stream_sid
        self.outgoing_manager.update_stream_sid(stream_sid)  
        self.logger.info(f"Updated Incoming / Outgoing AudioManagers to stream SID: {stream_sid}")

    def set_phone_number(self, phone_number: str, call_sid: str) -> None:
        self.phones_by_call_sid[call_sid] = phone_number

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
            self.logger.error(f"/!\\ VAD error: {e}")
            # Fallback to RMS-based detection
            rms = audioop.rms(audio_chunk, self.sample_width)
            return rms > 250  # Default threshold
    
    def perform_audio_preprocessing(self, audio_data: bytes) -> bytes:
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
            self.logger.error(f"/!\\ Audio preprocessing error: {e}")
            # Return original data if processing fails
            return audio_data
    
    def analyse_speech_for_silence(self, audio_data: bytes, threshold=400) -> tuple[bool, int]:
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
        
    async def init_conversation_async(self, call_sid: str, stream_sid: str) -> None:
        """Handle the 'start' event from Twilio which begins a new call."""
        self.set_call_sid(call_sid)
        self.set_stream_sid(stream_sid)
        phone_number = self.phones_by_call_sid.get(call_sid, None)
        if phone_number is None:
            self.logger.error(f"Phone number not found for call SID: {call_sid}")
            return None
        self.logger.info(f"--- Call started --- \nPhone number: {phone_number}, CallSid: {call_sid}, StreamSid: {stream_sid}.")
        
        # Get or Create the state for the graph
        if stream_sid in self.stream_states:
            current_state = self.stream_states[stream_sid]
        else:
            current_state: PhoneConversationState = PhoneConversationState(
                call_sid=call_sid,
                caller_phone=phone_number,
                user_input="",
                history=[],
                agent_scratchpad={}
            )
        
        # Store the initial state for this stream (used by graph and other handlers)
        self.stream_states[stream_sid] = current_state
        
        # Then invoke the graph with initial state to get the AI-generated welcome message
        try:            
            updated_state = await self.agents_graph.ainvoke(current_state)
            self.stream_states[stream_sid] = updated_state

        except Exception as e:
            self.logger.error(f"Error in initial graph invocation: {e}", exc_info=True)


    async def process_incoming_data_async(self, audio_data: dict) -> None:
        if not self.stream_sid:
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
        if self.is_speaking and not self.outgoing_manager.can_speech_be_interupted:
            return

        removed_text_to_speak = ""
        if self.is_speaking and self.outgoing_manager.can_speech_be_interupted:
            # Check if this chunk contains speech - use a lower threshold to detect speech earlier
            is_silence, speech_to_noise_ratio = self.analyse_speech_for_silence(chunk, threshold=self.speech_threshold * 2.5)  # Less sensitive detection while speaking
                
            # If user is speaking while system is speaking, stop system speech, but only if user speak loud
            if not is_silence:
                self.logger.info(f"Speech interruption detected (level: {speech_to_noise_ratio}), stopping system speech")
                removed_text_to_speak = await self.stop_speaking_async()
                # Reset buffer to clear any previous speech before interruption
                self.audio_buffer = b""
                
                # Log the interruption (but only the first time)
                if self.consecutive_silence_duration_ms > 0:
                    self.logger.info(f"\r>>> USER INTERRUPTION - Incoming speech while system was speaking ({speech_to_noise_ratio})")
                self.consecutive_silence_duration_ms = 0.0
        else:
            # Use WebRTC VAD for better speech detection
            is_silence, speech_to_noise_ratio = self.analyse_speech_for_silence(chunk, threshold=self.speech_threshold)

        # 2a. Silence detection before adding to buffer
        has_speech_began = len(self.audio_buffer) > 0

        # Count consecutive silence (while system is not speaking only)
        if is_silence and not self.is_speaking:
            chunk_duration_ms = (len(chunk) / self.sample_width) / self.frame_rate * 1000
            self.consecutive_silence_duration_ms += chunk_duration_ms

        # Add chunk to buffer if speech has begun or this is a speech chunk
        if has_speech_began or not is_silence:
            self.audio_buffer += chunk
            
            # Only reset silence counter if the current chunk contains speech
            if not is_silence:
                self.consecutive_silence_duration_ms = 0.0

            if(random.randint(0, 100) < 1): # Log every 1%
                self.logger.debug(
                    f"\nSpeech detected - RMS: {speech_to_noise_ratio}/{self.speech_threshold}, "
                    f"Buffer size: {len(self.audio_buffer)} bytes")

        # 2b. Speak anew if the user remains silent for long enough
        if (self.speak_anew_on_long_silence 
        and self.consecutive_silence_duration_ms >= self.max_silence_duration_before_reasking 
        and self.consecutive_silence_duration_ms % self.max_silence_duration_before_reasking <= 10):
            self.logger.info(f">>> User silence duration of {self.consecutive_silence_duration_ms:.1f}ms exceeded max. silence before speaking anew: {self.max_silence_duration_before_reasking:.1f}ms.")
            await self.outgoing_manager.enqueue_text_async("Comment puis-je vous aider ? Je peux répondre à vos questions concernant nos formations, ou prendre rendez-vous avec un conseiller.")
            await asyncio.sleep(0.05)
            return

        # 2c. Hangup the call if the user remains silent for too long
        if self.consecutive_silence_duration_ms >= self.max_silence_duration_before_hangup:
            self.logger.info(f">>> User silence duration of {self.consecutive_silence_duration_ms:.1f}ms exceeded max. allowed silence of {self.max_silence_duration_before_hangup:.1f}ms.")
            await self._hangup_call_async()
            return
        
        is_long_silence_after_speech = has_speech_began and self.consecutive_silence_duration_ms >= self.required_silence_ms_to_answer 
        has_reach_min_speech_length = len(self.audio_buffer) >= self.min_audio_bytes_for_processing
        is_speech_too_long = len(self.audio_buffer) > self.max_audio_bytes_for_processing
        
        # 3. Process audio
        # Conditions: if buffer large enough followed by a prolonged silence, or if buffer is too large
        if (is_long_silence_after_speech and has_reach_min_speech_length) or is_speech_too_long:
            if is_speech_too_long:
                self.logger.info(f"\nProcess incoming audio: [Buffer size limit reached]. (buffer size: {len(self.audio_buffer)} bytes).\n")
            else:
                self.logger.info(f"\nProcess incoming audio: [Silence after speech detected]. (buffer size: {len(self.audio_buffer)} bytes).\n")
            
            audio_data = self.audio_buffer
            self.audio_buffer = b""
            self.consecutive_silence_duration_ms = 0.0

            # Waiting message
            #await self.outgoing_manager.enqueue_text(random.choice(["Très bien, je vous demande un instant.", "Merci de patienter.", "Laissez-moi y réfléchir.", "Une petite seconde."]))
            acknowledge_text = random.choice(["Très bien, ", "Compris, ", "D'accord, ", "Entendu, ", "Parfait, "])
            acknowledge_text += random.choice(["un instant s'il vous plait.", "je vous demande un instant.", "merci de patienter.", "laissez-moi y réfléchir.", "une petite seconde."])
            await self.outgoing_manager.enqueue_text_async(acknowledge_text)
            
            # 4. Transcribe speech to text
            user_query_transcript = await self._perform_speech_to_text_transcription_async(audio_data, keep_audio_file=EnvHelper.get_keep_audio_files())
            self.logger.info(f">>> Transcription finished. Heard text: \"{user_query_transcript}\"")
            
            # repeat_user_input = EnvHelper.get_repeat_user_input()
            # if repeat_user_input : 
            #     feedback_text = f" Vous avez dit : \"{user_query_transcript}\"."
            #     await self.outgoing_manager.enqueue_text_async(feedback_text)
            
            # 5. Send user query to the agents graph (for processing and response)
            if user_query_transcript:
                await self.send_user_query_to_agents_graph_async(user_query_transcript)
            
            # If no user query transcript, enqueue back the text to speak previously removed
            if not user_query_transcript:
                if removed_text_to_speak:
                    await self.outgoing_manager.enqueue_text_async(removed_text_to_speak)
                    self.logger.info(f">>> Empty transcript. Enqueued back originaly removed text to speak: \"{removed_text_to_speak}\"")
                else:
                    await self.outgoing_manager.enqueue_text_async(AgentsGraph.other_text)
                    self.logger.info(">>> Empty transcript.")

        #await asyncio.sleep(0.1) # Pause incoming process to let others processes breathe
        return

    async def send_user_query_to_agents_graph_async(self, user_query : str):
        try:
            self.logger.info(f"Sending incoming user query to agents graph. Transcription: '{user_query}'")  

            if self.stream_sid in self.stream_states:
                current_state : PhoneConversationState= self.stream_states[self.stream_sid]
                current_state["user_input"] = user_query
            else:
                current_state : PhoneConversationState = {
                    "call_sid": self.call_sid,
                    "caller_phone": self.phones_by_call_sid[self.call_sid],
                    "user_input": user_query,
                    "history": [],
                    "agent_scratchpad": {}
                }
                self.stream_states[self.stream_sid] = current_state
                        
            # Invoke the graph with current state to get the AI-generated welcome message
            updated_state = await self.agents_graph.ainvoke(current_state)
            self.stream_states[self.stream_sid] = updated_state

            # If the agents graph response ends with "au revoir.", do hang-up
            if updated_state["history"][-1][1].endswith("au revoir."):
                self.logger.info(">>> Agents graph response ends with 'au revoir.', hanging up the call.")
                while self.outgoing_manager.has_text_to_be_sent() or self.outgoing_manager.is_sending():
                    await asyncio.sleep(0.3)
                await self._hangup_call_async()

        except Exception as e:
            self.logger.error(f"Error in user query to agents graph: {e}", exc_info=True)

    def _decode_audio_chunk(self, data : dict):
        try:
            media_data = data.get("media", {})
            payload = media_data.get("payload", None)
            if not payload:
                self.logger.warning("Received media event without payload")
                return None
            return audioop.ulaw2lin(base64.b64decode(payload), self.sample_width)
        except Exception as decode_err:
            self.logger.error(f"Error decoding/converting audio chunk: {decode_err}")
            return None

    async def _perform_speech_to_text_transcription_async(self, audio_data: bytes, keep_audio_file : bool = False):
        try:
            wav_audio_filename = None
            # Check if the audio buffer has a high enough speech to noise ratio
            speech_to_noise_ratio = audioop.rms(audio_data, self.sample_width)
            if speech_to_noise_ratio < self.speech_threshold:
                if random.random() < 0.1: # log 1/10 of the time
                    self.logger.info(f"[Silence/Noise] Low speech/noise ratio detected: {speech_to_noise_ratio}. Transcription skipped")
                return None
                
            self.logger.info(f"[Speech] High speech/noise ratio detected: {speech_to_noise_ratio}. Processing transcription.")
            
            # Apply audio preprocessing to improve quality
            self.logger.info("Applying audio preprocessing...")
            processed_audio = self.perform_audio_preprocessing(audio_data) if self.do_audio_preprocessing else audio_data
            self.logger.info(f"Audio preprocessing complete. Original size: {len(audio_data)} bytes, Processed size: {len(processed_audio)} bytes")
                
            # Save the processed audio to a file
            wav_audio_filename = self.save_as_wav_file(processed_audio)
            
            # Transcribe using the hybrid STT provider
            self.logger.info("Transcribing audio with hybrid STT provider...")
            transcript: str = await self.stt_provider.transcribe_audio_async(wav_audio_filename)
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
            if not keep_audio_file and wav_audio_filename:
                self._delete_temp_file(wav_audio_filename)
    
    def _delete_temp_file(self, file_name: str):
        try:
            os.remove(os.path.join(self.incoming_speech_dir, file_name))
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
        
    async def _hangup_call_async(self):
        if self.websocket:
            self.logger.info(f"### HANGING UP ### Make phone call ends.")
            
            # Speak out "Au revoir" to the user first
            self.outgoing_manager.enqueue_text_async("Au revoir")
            time.sleep(1)
            # Close the websocket first
            try:
                await self.websocket.close(code=1000)
            except Exception as e:
                self.logger.error(f"Error closing websocket: {e}")
            self.websocket = None

            # Hang-up Twilio phone call
            try:
                twilio_sid = EnvHelper.get_twilio_sid()
                twilio_auth = EnvHelper.get_twilio_auth()
                if twilio_sid and twilio_auth and getattr(self, "call_sid", None):
                    from twilio.rest import Client
                    client = Client(twilio_sid, twilio_auth)
                    client.calls(self.call_sid).update(status="completed")
                    self.logger.info(f"Call {self.call_sid} hung up via Twilio")
                else:
                    if not twilio_sid or not twilio_auth:
                        self.logger.error("/!\\ Twilio credentials not configured")
                    else:
                        self.logger.error("/!\\ call_sid not set; unable to hang up Twilio phone call")
            except Exception as e:
                self.logger.error(f"/!\\ Error hanging up call via Twilio: {e}", exc_info=True)

    def save_as_wav_file(self, audio_data: bytes):
        """Save PCM data (16-bit, 8kHz, mono) to a WAV file at the specified path."""
        # Calculate milliseconds elapsed since websocket creation
        elapsed_ms = 0
        if self.websocket_creation_time:
            elapsed_ms = int((time.time() - self.websocket_creation_time) * 1000)
        
        file_name = f"{uuid.uuid4()}-{elapsed_ms}.wav"
        with wave.open(os.path.join(self.incoming_speech_dir, file_name), "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(self.sample_width)  # 16-bit
            wav_file.setframerate(self.frame_rate) # 8kHz
            wav_file.writeframes(audio_data) # PCM data
        return file_name
            
    async def update_is_speaking_state_async(self):
        """
        Updates the speaking state based on the text queue status
        This provides a more accurate representation of when audio is actually being sent
        """
        is_sending_audio = self.outgoing_manager.is_sending()
        if is_sending_audio != self.is_speaking:
            if is_sending_audio:
                self.is_speaking = True
                # Log more detailed stats about the text queue
                stats = self.outgoing_manager.get_streaming_stats()
                text_stats = stats['text_queue']
                self.logger.debug(f"Speaking started - Text queue: {text_stats['current_size_chars']} chars, " +
                                f"{text_stats['total_chars_processed']} chars processed so far")
            else:
                self.is_speaking = False
                self.logger.debug("Speaking stopped - Text queue empty")
    
    async def stop_speaking_async(self) -> str:
        """Stop any ongoing speech and clear text queue and interrupt RAG streaming"""
        if self.is_speaking:
            # Interrupt RAG streaming with its tag if it's active
            if hasattr(self, 'rag_interrupt_flag'):
                self.rag_interrupt_flag["interrupted"] = True
                self.logger.info("RAG streaming interrupted due to speech interruption")
                
            removed_text = await self.outgoing_manager.clear_text_queue_async()
            self.logger.info("Cleared text queue due to speech interruption")
            self.is_speaking = False
            return removed_text
        return ""