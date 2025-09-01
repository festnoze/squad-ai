import asyncio
import audioop
import base64
import io
import logging
import os
import random
import time
import uuid
import wave

import webrtcvad
from agents.agents_graph import AgentsGraph
from agents.phone_conversation_state_model import ConversationState, PhoneConversationState
from agents.text_registry import AgentTexts
from api_client.conversation_persistence_interface import ConversationPersistenceInterface
from api_client.studi_rag_inference_api_client import StudiRAGInferenceApiClient
from fastapi import WebSocket
from pydub import AudioSegment
from pydub.effects import normalize
from speech.speech_to_text import SpeechToTextProvider

#
from utils.envvar import EnvHelper

from database.conversation_persistence_local_service import ConversationPersistenceLocalService
from database.conversation_persistence_service_fake import ConversationPersistenceServiceFake
from managers.incoming_manager import IncomingManager
from managers.outgoing_audio_manager import OutgoingManager


class IncomingAudioManager(IncomingManager):
    """Audio processing utilities for improving speech recognition quality and handling Twilio events"""

    # Tmp directory for incoming audio files
    incoming_speech_dir = "./static/incoming_audio"

    def __init__(
        self,
        websocket: WebSocket,
        stt_provider: SpeechToTextProvider,
        outgoing_manager: OutgoingManager,
        agents_graph: AgentsGraph,
        conversation_persistence: ConversationPersistenceInterface = None,
        sample_width=2,
        frame_rate=8000,
        channels=1,
        vad_aggressiveness=3,
    ):
        self.logger = logging.getLogger(__name__)
        self.websocket: WebSocket = websocket
        self.stt_provider: SpeechToTextProvider = stt_provider
        self.outgoing_manager: OutgoingManager = outgoing_manager
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
        self.stream_states: dict[str, ConversationState] = {}
        self.phones_by_call_sid = {}  # Map call_sid to phone numbers
        self.average_noise_by_stream_sid: dict[str, int] = {}  # List already etalonnated stream_sid
        self.speech_to_noise_ratio_samples_by_stream_sid: dict[
            str, list[int]
        ] = {}  # Map stream_sid with noise calibration data
        self.agents_graph: AgentsGraph = agents_graph
        self.openai_client = None
        self.rag_interrupt_flag: dict = {"interrupted": False}
        self.is_speaking: bool = False
        self.interuption_asked: bool = False
        self.removed_text_to_speak: str | None = None
        self.speak_anew_on_long_silence: bool = EnvHelper.get_speak_anew_on_long_silence()
        self.max_silence_duration_before_reasking: int = (
            EnvHelper.get_max_silence_duration_before_reasking()
        )  # ms of silence before reasking

        # Audio processing parameters
        self.audio_buffer = b""
        self.consecutive_silence_duration_ms = 0.0
        self.speech_threshold_base = EnvHelper.get_speech_threshold()
        self.speech_threshold = (
            self.speech_threshold_base + 300
        )  # Add 300 as default background noise value on startup (to be calibrated later)
        self.required_silence_ms_to_answer = (
            EnvHelper.get_required_silence_ms_to_answer()
        )  # ms of silence to trigger transcript
        self.min_audio_bytes_for_processing = (
            EnvHelper.get_min_audio_bytes_for_processing()
        )  # Minimum buffer size to process
        self.max_audio_bytes_for_processing = (
            EnvHelper.get_max_audio_bytes_for_processing()
        )  # Maximum buffer size to process
        self.max_silence_duration_before_hangup = (
            EnvHelper.get_max_silence_duration_before_hangup()
        )  # ms of silence before hanging up the call
        self.do_audio_preprocessing = EnvHelper.get_do_audio_preprocessing()
        self.perform_background_noise_calibration = EnvHelper.get_perform_background_noise_calibration()
        self.keep_audio_file = EnvHelper.get_keep_audio_files()

        # Create temp directory if it doesn't exist
        os.makedirs(self.incoming_speech_dir, exist_ok=True)

        # Who handles conversation history persistence? local/ studi_rag/ desactivated (fake)
        self.conversation_persistence: ConversationPersistenceInterface | None = None
        if conversation_persistence:
            self.conversation_persistence = conversation_persistence
        else:
            conversation_persistence_type = EnvHelper.get_conversation_persistence_type()
            if conversation_persistence_type == "local":
                self.conversation_persistence = ConversationPersistenceLocalService()
            elif conversation_persistence_type == "studi_rag":
                self.conversation_persistence = StudiRAGInferenceApiClient()
            else:
                self.conversation_persistence = ConversationPersistenceServiceFake()

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

    def _is_speech(self, audio_chunk: bytes, frame_duration_ms=20) -> bool:
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
            frame_duration_ms = 20

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
            return rms > self.speech_threshold  # Default threshold

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
            with wave.open(buffer, "wb") as wf:
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
            with wave.open(output, "rb") as wf:
                processed_audio = wf.readframes(wf.getnframes())

            return processed_audio
        except Exception as e:
            self.logger.error(f"/!\\ Audio preprocessing error: {e}")
            # Return original data if processing fails
            return audio_data

    def analyse_speech_for_silence(self, audio_data: bytes) -> tuple[bool, int]:
        """
        Detect silence vs speech using both VAD and RMS
        Args: audio_data: Raw PCM audio bytes
        Returns: Tuple of (is_silence, speech_to_noise_ratio)
        """
        # Get RMS value (volume)
        speech_to_noise_ratio = audioop.rms(audio_data, self.sample_width)

        # Check using VAD (more accurate but may not work on all chunks)
        try:
            if len(audio_data) >= 320:  # At least 20ms at 8kHz, 16-bit mono
                is_speech = speech_to_noise_ratio > self.speech_threshold and self._is_speech(audio_data)
                return not is_speech, speech_to_noise_ratio  # VAD detected speech
        except Exception:
            pass  # Fall back to RMS method
        return True, speech_to_noise_ratio

    async def init_conversation_async(self, call_sid: str, stream_sid: str) -> None:
        """Handle the 'start' event from Twilio which begins a new call."""
        self.set_call_sid(call_sid)
        self.set_stream_sid(stream_sid)
        phone_number = self.phones_by_call_sid.get(call_sid, None)
        if phone_number is None:
            self.logger.error(f"Phone number not found for call SID: {call_sid}")
            return None
        self.logger.info(
            f"--- Call started --- \nPhone number: {phone_number}, CallSid: {call_sid}, StreamSid: {stream_sid}."
        )

        # Get or Create the state for the graph
        if stream_sid in self.stream_states:
            current_state = self.stream_states[stream_sid]
        else:
            current_state: PhoneConversationState = PhoneConversationState(
                call_sid=call_sid, caller_phone=phone_number, user_input="", history=[], agent_scratchpad={}
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

        # 1- Update the speaking state based on the queue status
        await self.update_is_speaking_state_async()

        # 2. Decode audio chunk
        chunk = self._decode_audio_chunk(audio_data)
        if chunk is None:
            self.logger.warning("Received media event without valid audio chunk")
            return

        # 3- Perform speech detection (using WebRTC VAD)
        is_silence, speech_to_noise_ratio = self.analyse_speech_for_silence(chunk)
        # self.logger.info(f"Speech detection: {'speech' if not is_silence else 'silence'}, S/N ratio: {speech_to_noise_ratio:.2f}")

        # 4- Perform background noise calibration (at call start)
        if self.perform_background_noise_calibration:
            self._perform_background_noise_calibration(self.stream_sid, speech_to_noise_ratio)

        # 5- Skip handling incoming speech if system is speaking - and interruption isn't allowed
        if not self.outgoing_manager.can_speech_be_interupted and (
            self.is_speaking or self.outgoing_manager.has_text_to_be_sent()
        ):
            return

        # 6- If user is speaking while system is speaking, stop system speech
        if (
            self.is_speaking
            and not is_silence
            and self.outgoing_manager.can_speech_be_interupted
            and not self.interuption_asked
        ):
            self.removed_text_to_speak = await self.stop_speaking_async(speech_to_noise_ratio)

            # Log the interruption (but only the first time)
            if self.consecutive_silence_duration_ms > 0:
                self.logger.info(
                    f"\r>>> USER INTERRUPTION - Incoming speech while system was speaking ({speech_to_noise_ratio:.2f})"
                )
            self.consecutive_silence_duration_ms = 0.0

        # 7- Silence detection consecutive to user speech beginning
        has_speech_began = len(self.audio_buffer) > 0

        # Count consecutive silence (if system is not speaking)
        if is_silence and not self.is_speaking:
            chunk_duration_ms = (len(chunk) / self.sample_width) / self.frame_rate * 1000
            self.consecutive_silence_duration_ms += chunk_duration_ms

        # Add chunk to buffer if speech has begun or this is a speech chunk
        if has_speech_began or not is_silence:
            self.audio_buffer += chunk

            # Only reset silence counter if the current chunk contains speech
            if not is_silence:
                self.consecutive_silence_duration_ms = 0.0

            if random.randint(0, 100) < 1:  # Log every 1%
                self.logger.debug(
                    f"\nSpeech detected - RMS: {speech_to_noise_ratio:.2f} / {self.speech_threshold:.2f}, "
                    f"Buffer size: {len(self.audio_buffer)} bytes"
                )

        # 8- Speak anew if the user remains silent for long enough
        if (
            self.speak_anew_on_long_silence
            and self.consecutive_silence_duration_ms >= self.max_silence_duration_before_reasking
            and self.consecutive_silence_duration_ms % self.max_silence_duration_before_reasking <= 10
        ):
            self.logger.info(
                f">>> User silence duration of {self.consecutive_silence_duration_ms:.1f}ms exceeded max. silence before speaking anew: {self.max_silence_duration_before_reasking:.1f}ms."
            )
            await self.outgoing_manager.enqueue_text_async(
                "Comment puis-je vous aider ? Je peux répondre à vos questions concernant nos formations, ou prendre rendez-vous avec un conseiller."
            )
            await asyncio.sleep(0.05)
            return

        # 9- Hangup the call if the user remains silent for too long
        if self.consecutive_silence_duration_ms >= self.max_silence_duration_before_hangup:
            self.logger.info(
                f">>> User silence duration of {self.consecutive_silence_duration_ms:.1f}ms exceeded max. allowed silence of {self.max_silence_duration_before_hangup:.1f}ms."
            )
            await self._hangup_call_async()
            return

        is_long_silence_after_speech = (
            has_speech_began and self.consecutive_silence_duration_ms >= self.required_silence_ms_to_answer
        )
        has_reach_min_speech_length = len(self.audio_buffer) >= self.min_audio_bytes_for_processing
        is_speech_too_long = len(self.audio_buffer) > self.max_audio_bytes_for_processing

        # 10- Process audio
        # Conditions: if buffer large enough followed by a prolonged silence, or if buffer is too large
        if (is_long_silence_after_speech and has_reach_min_speech_length) or is_speech_too_long:
            audio_data = self.audio_buffer
            self.audio_buffer = b""
            self.consecutive_silence_duration_ms = 0.0
            if is_speech_too_long:
                self.logger.info(
                    f"\nProcess incoming audio: [Buffer size limit reached]. (buffer size: {len(self.audio_buffer)} bytes).\n"
                )
            else:
                self.logger.info(
                    f"\nProcess incoming audio: [Silence after speech detected]. (buffer size: {len(self.audio_buffer)} bytes).\n"
                )
            if self.interuption_asked:
                self.interuption_asked = False

            # Acknowledgement message
            if EnvHelper.get_do_acknowledge_user_speech():
                acknowledge_text = random.choice(["Très bien", "Compris", "D'accord", "Entendu", "Parfait"])
                if EnvHelper.get_long_acknowledgement():
                    acknowledge_text += ", " + random.choice([
                        "un instant s'il vous plait",
                        "je vous demande un instant",
                        "merci de patienter",
                        "laissez-moi un moment",
                        "une petite seconde",
                    ])
                acknowledge_text += "."
                await self.outgoing_manager.enqueue_text_async(acknowledge_text)

            # 11- Transcribe speech to text
            user_query_transcript = await self._perform_speech_to_text_transcription_async(audio_data)
            self.logger.info(f'>>> Transcription finished. Heard text: "{user_query_transcript}"')

            if EnvHelper.get_repeat_user_input():
                feedback_text = f' Vous avez dit : "{user_query_transcript}".'
                await self.outgoing_manager.enqueue_text_async(feedback_text)

            # 12- Send user query to the agents graph (for processing and response)
            if user_query_transcript:
                self.removed_text_to_speak = None
                await self.send_user_query_to_agents_graph_async(user_query_transcript)

            # 13- If transcript of user query is empty (no speech detected), enqueue back the text to speak previously removed
            if not user_query_transcript:
                if self.removed_text_to_speak:
                    await self.outgoing_manager.enqueue_text_async(self.removed_text_to_speak)
                    self.logger.info(
                        f'>>> Empty transcript. Enqueued back originaly removed text to speak: "{self.removed_text_to_speak}"'
                    )
                    self.removed_text_to_speak = None
                else:
                    await self.outgoing_manager.enqueue_text_async(AgentTexts.ask_to_repeat_text)
                    self.logger.info(">>> Empty transcript.")

        # await asyncio.sleep(0.1) # Pause incoming process to let others processes breathe
        return

    async def send_user_query_to_agents_graph_async(self, user_query: str):
        try:
            self.logger.info(f"Sending incoming user query to agents graph. Transcription: '{user_query}'")

            if self.stream_sid in self.stream_states:
                current_state: PhoneConversationState = self.stream_states[self.stream_sid]
                current_state["user_input"] = user_query
            else:
                current_state: PhoneConversationState = {
                    "call_sid": self.call_sid,
                    "caller_phone": self.phones_by_call_sid[self.call_sid],
                    "user_input": user_query,
                    "history": [],
                    "agent_scratchpad": {},
                }
                self.stream_states[self.stream_sid] = current_state

            # Persist user query
            conv_id = current_state["agent_scratchpad"].get("conversation_id", None)
            current_state["history"].append(("user", user_query))
            await self.conversation_persistence.add_message_to_conversation_async(conv_id, user_query, "user")

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

    def _perform_background_noise_calibration(
        self, stream_sid, speech_to_noise_ratio, samples_count_to_average=600, min_noise_level=10
    ):
        if stream_sid in self.average_noise_by_stream_sid:
            return

        if stream_sid not in self.speech_to_noise_ratio_samples_by_stream_sid:
            self.speech_to_noise_ratio_samples_by_stream_sid[stream_sid] = []
        if len(self.speech_to_noise_ratio_samples_by_stream_sid[stream_sid]) < samples_count_to_average:
            self.speech_to_noise_ratio_samples_by_stream_sid[stream_sid].append(speech_to_noise_ratio)

        # Calculate the speech to noise ratio average when we reach samples count
        if len(self.speech_to_noise_ratio_samples_by_stream_sid[stream_sid]) >= samples_count_to_average:
            calibration_data = self.speech_to_noise_ratio_samples_by_stream_sid[stream_sid]
            calibration_data = [x for x in calibration_data if x >= min_noise_level]  # Exclude no noise samples
            if not any(calibration_data):
                calibration_data = [min_noise_level]
            average_noise = int(round(sum(calibration_data) / len(calibration_data)))
            self.logger.info(
                f"Noise calibration completed for stream {stream_sid}. Average noise level: {average_noise:.2f}"
            )
            # Replace list with the calculated average for memory efficiency
            self.average_noise_by_stream_sid[stream_sid] = average_noise
            del self.speech_to_noise_ratio_samples_by_stream_sid[stream_sid]
            self.speech_threshold = max(self.speech_threshold_base * 1.3, average_noise * 1.5)

    def _decode_audio_chunk(self, data: dict):
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

    async def _perform_speech_to_text_transcription_async(self, audio_data: bytes):
        try:
            wav_audio_filename = None
            # Check if the audio buffer has a high enough speech to noise ratio
            speech_to_noise_ratio = audioop.rms(audio_data, self.sample_width)
            if speech_to_noise_ratio < self.speech_threshold:
                if random.random() < 0.1:  # log 1/10 of the time
                    self.logger.info(
                        f"[Silence/Noise] Low speech/noise ratio detected: {speech_to_noise_ratio}. Transcription skipped"
                    )
                return None

            self.logger.info(
                f"[Speech] High speech/noise ratio detected: {speech_to_noise_ratio}. Processing transcription."
            )

            # Apply audio preprocessing to improve quality
            self.logger.info("Applying audio preprocessing...")
            processed_audio = (
                self.perform_audio_preprocessing(audio_data) if self.do_audio_preprocessing else audio_data
            )
            self.logger.info(
                f"Audio preprocessing complete. Original size: {len(audio_data)} bytes, Processed size: {len(processed_audio)} bytes"
            )

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
                "c'est la fin de la vidéo",
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
            if not self.keep_audio_file and wav_audio_filename:
                self._delete_temp_file(wav_audio_filename)

    def _delete_temp_file(self, file_name: str):
        try:
            os.remove(os.path.join(self.incoming_speech_dir, file_name))
        except Exception as e:
            self.logger.error(f"Error deleting temp file {file_name}: {e}")

    async def speak_and_send_ask_for_feedback_async(self, transcript):
        response_text = (
            "Instructions : Fait un feedback reformulé de façon synthétique de la demande utilisateur suivante, afin de t'assurer de ta bonne comphéhension de celle-ci : "
            + transcript
        )
        response = self.openai_client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": response_text}], stream=True
        )
        if response:
            spoken_text = await self.speak_and_send_stream_async(response)
            self.logger.info(f"<< Response text: '{spoken_text}'")
            return spoken_text
        return ""

    async def _hangup_call_async(self):
        if self.websocket:
            self.logger.info("### HANGING UP ### Make phone call ends.")

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
            wav_file.setframerate(self.frame_rate)  # 8kHz
            wav_file.writeframes(audio_data)  # PCM data
        return file_name

    async def update_is_speaking_state_async(self):
        """
        Updates the speaking state based on the text queue status
        This provides a more accurate representation of when audio is actually being sent
        """
        is_sending_audio = self.outgoing_manager.is_sending()
        if is_sending_audio != self.is_speaking and not self.interuption_asked:
            self.is_speaking = is_sending_audio

    async def stop_speaking_async(self, speech_to_noise_ratio) -> str:
        """Stop any ongoing speech and clear text queue and interrupt RAG streaming"""
        self.logger.info(f"Speech interruption detected (level: {speech_to_noise_ratio}), stopping system speech")
        self.interuption_asked = True
        # Interrupt RAG streaming with its tag if it's active
        if hasattr(self, "rag_interrupt_flag"):
            self.rag_interrupt_flag["interrupted"] = True
            self.logger.info("RAG streaming interrupted due to speech interruption")

        removed_text = await self.outgoing_manager.clear_text_queue_async()
        self.logger.info(f"Cleared queued text due to speech interruption: '{removed_text}'")
        self.is_speaking = False
        # Reset buffer to clear any previous speech before interruption
        self.audio_buffer = b""
        return removed_text
