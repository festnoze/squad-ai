import asyncio
import logging
import os
import time
import uuid
import wave

from fastapi import WebSocket

#
from speech.text_queue_manager import TextQueueManager
from speech.text_to_speech import TextToSpeechProvider
from speech.audio_sender_factory import create_audio_sender

#
from utils.audio_mixer import AudioMixer
from utils.envvar import EnvHelper

from managers.outgoing_manager import OutgoingManager


class OutgoingAudioManager(OutgoingManager):
    """
    Manages the complete audio streaming process using a text-based approach.
    Text is queued, then processed into speech in small chunks for better responsiveness.
    """

    # Tmp directory for outgoing audio files
    outgoing_speech_dir = "./static/outgoing_audio"

    # Speech synthesis cache: {text: (audio_bytes, timestamp)}
    _synthesized_audio_cache: dict[str, tuple[bytes, float]] = {}

    def __init__(
        self,
        websocket: any,
        tts_provider: TextToSpeechProvider,
        stream_sid: str = None,
        min_chunk_interval: float = 0.05,  # 50ms~
        can_speech_be_interupted: bool = False,
        min_chars_for_interruptible_speech: int = 2,
        sample_width: int = 1,
        frame_rate: int = 8000,
        channels: int = 1,
        loop_interval: float = 0.05,  # 50ms~
        max_words_by_stream_chunk: int = 20,
        max_chars_by_stream_chunk: int = 100,
        cache_ttl_minutes: int = 5,
        provider: str = None,
    ):
        self.logger = logging.getLogger(__name__)
        super().__init__(output_channel="audio", can_speech_be_interupted=can_speech_be_interupted)
        self.text_queue_manager = TextQueueManager()
        self.audio_sender = create_audio_sender(
            websocket=websocket, 
            stream_id=stream_sid, 
            sample_rate=frame_rate, 
            min_chunk_interval=min_chunk_interval,
            provider=provider
        )

        self.tts_provider: TextToSpeechProvider = tts_provider  # Text-to-speech provider for converting text to audio
        self.sender_task = None
        self.keep_outgoing_audio_file = EnvHelper.get_keep_outgoing_audio_file()
        self.frame_rate = frame_rate  # mu-law in 8/16kHz
        self.sample_width = sample_width  # mu-law in 8/16 bits
        self.channels = channels
        self.streaming_interuption_asked = False
        self.ask_to_stop_streaming_worker = False
        self.websocket = websocket
        self.min_chars_for_interruptible_speech = min_chars_for_interruptible_speech
        self.loop_interval = loop_interval
        self.max_words_by_stream_chunk = max_words_by_stream_chunk
        self.max_chars_by_stream_chunk = max_chars_by_stream_chunk
        self.cache_ttl_seconds = cache_ttl_minutes * 60

        # Background noise configuration
        self.background_noise_enabled = EnvHelper.get_background_noise_enabled()
        self.background_noise_volume = EnvHelper.get_background_noise_volume()
        self.audio_mixer = None

        # Initialize audio mixer if background noise is enabled
        if self.background_noise_enabled:
            self.audio_mixer = AudioMixer(sample_width=sample_width, frame_rate=frame_rate, channels=channels)

        # Create temp directory if it doesn't exist
        os.makedirs(self.outgoing_speech_dir, exist_ok=True)

        # Initialize latency tracking attributes
        self.call_sid = None
        self.phone_number = None

    def set_websocket(self, websocket: WebSocket):
        self.websocket = websocket
        self.audio_sender.websocket = websocket

    def update_stream_sid(self, stream_sid: str) -> None:
        """
        Updates the stream SID when it changes (e.g., when a new call starts or ends)
        Allows setting to None when resetting after a call ends
        """
        # Handle different attribute names for different providers
        if hasattr(self.audio_sender, 'stream_sid'):
            self.audio_sender.stream_sid = stream_sid
        elif hasattr(self.audio_sender, 'stream_id'):
            self.audio_sender.stream_id = stream_sid
        
        if not stream_sid:
            self.logger.info("Reset stream ID to None")
        else:
            self.logger.info(f"Updated stream SID to: {stream_sid}")
        return

    def set_call_sid(self, call_sid: str) -> None:
        """Set the call SID for latency tracking"""
        self.call_sid = call_sid

    def set_phone_number(self, phone_number: str) -> None:
        """Set the phone number for latency tracking"""
        self.phone_number = phone_number

    def get_synthesized_audio_from_cache(self, text: str, allow_partial: bool = False) -> bytes | None:
        """
        Get cached synthesis result if available and not expired.
        Permanent entries (timestamp = -1) never expire.

        Args:
            text: The text to search for in cache
            allow_partial: If True, allows partial matching using _find_partial_cached_audio

        Returns:
            Audio bytes if found (complete or combined from parts), None otherwise
        """
        # First try exact match (existing behavior)
        if text in self._synthesized_audio_cache:
            audio_bytes, timestamp = self._synthesized_audio_cache[text]

            # Permanent entries never expire (timestamp = -1)
            if timestamp == -1:
                return audio_bytes

            current_time = time.time()
            if current_time - timestamp <= self.cache_ttl_seconds:
                return audio_bytes
            else:
                # Cache expired, remove entry
                del self._synthesized_audio_cache[text]

        # If exact match not found and partial matching is allowed
        if allow_partial:
            try:
                audio_parts_found, remaining_text, parts_used = self._find_partial_cached_audio(text)

                if audio_parts_found and not remaining_text.strip():
                    # All text was found in cache parts
                    combined_audio = self._combine_audio_parts(audio_parts_found)
                    if combined_audio:
                        self.logger.info(
                            f">>>>>> Using combined cached parts for: '{text}' (parts: {[p[:30] + '...' for p in parts_used]})"
                        )

                        # Cache the combined result for future use (store clean audio without background noise)
                        self.add_synthesized_audio_to_cache(text, combined_audio)
                        return combined_audio

            except Exception as e:
                self.logger.error(f"Error in partial cache search for '{text[:50]}...': {e}")

        return None

    @staticmethod
    def add_synthesized_audio_to_cache(text: str, audio_bytes: bytes, permanent: bool = False) -> None:
        """
        Cache synthesis result with current timestamp or as permanent entry.

        Args:
            text: The text that was synthesized
            audio_bytes: The synthesized audio data
            permanent: If True, cache permanently (never expires)
        """
        timestamp = -1 if permanent else time.time()
        OutgoingAudioManager._synthesized_audio_cache[text] = (audio_bytes, timestamp)

    def _combine_audio_parts(self, audio_parts: list[bytes]) -> bytes:
        """
        Combine multiple PCM audio parts into a single audio stream.

        Args:
            audio_parts: List of PCM audio byte arrays to combine

        Returns:
            Combined audio bytes, or empty bytes if combination fails
        """
        if not audio_parts:
            return b""

        if len(audio_parts) == 1:
            return audio_parts[0]

        try:
            # For PCM audio, we can simply concatenate the byte arrays
            combined_audio = b"".join(audio_parts)
            self.logger.debug(f"Combined {len(audio_parts)} audio parts into {len(combined_audio)} bytes")
            return combined_audio
        except Exception as e:
            self.logger.error(f"Failed to combine audio parts: {e}")
            return b""

    def _find_partial_cached_audio(self, text: str, max_recursion_depth: int = 5) -> tuple[list[bytes], str, list[str]]:
        """
        Recursively find cached audio parts for the beginning of the text.

        Args:
            text: The text to search for cached parts
            max_recursion_depth: Maximum recursion depth to prevent infinite loops

        Returns:
            Tuple of (audio_parts_found, remaining_text, parts_used)
            - audio_parts_found: List of audio bytes found in cache
            - remaining_text: Text that still needs to be synthesized
            - parts_used: List of text parts that were found in cache
        """
        if not text.strip() or max_recursion_depth <= 0:
            return [], text, []

        text = text.strip()
        audio_parts_found = []
        parts_used = []

        # First, try to find the complete text in cache
        complete_audio = self.get_synthesized_audio_from_cache(text)
        if complete_audio:
            return [complete_audio], "", [text]

        # Split text into potential prefix parts (by sentences, then by words)
        text_separators = [". ", "! ", "? ", ", ", " "]
        potential_prefixes = []

        # Generate potential prefixes by different separators
        for separator in text_separators:
            parts = text.split(separator)
            if len(parts) > 1:
                for i in range(1, len(parts)):
                    prefix = separator.join(parts[:i])
                    if separator != " ":  # Add back the separator except for spaces
                        prefix += separator
                    if prefix.strip() and len(prefix.strip()) >= 3:  # Minimum length
                        potential_prefixes.append(prefix.strip())

        # Sort by length (longest first) to find the best match
        potential_prefixes = sorted(set(potential_prefixes), key=len, reverse=True)

        # Try to find the longest prefix in cache
        for prefix in potential_prefixes:
            cached_audio = self.get_synthesized_audio_from_cache(prefix)
            if cached_audio:
                audio_parts_found.append(cached_audio)
                parts_used.append(prefix)

                # Calculate remaining text
                remaining_text = text[len(prefix) :].strip()

                if remaining_text:
                    # Recursively search for more parts in the remaining text
                    more_audio_parts, final_remaining, more_parts = self._find_partial_cached_audio(
                        remaining_text, max_recursion_depth - 1
                    )
                    audio_parts_found.extend(more_audio_parts)
                    parts_used.extend(more_parts)
                    remaining_text = final_remaining

                break

        # If no prefixes found, return the original text as remaining
        if not audio_parts_found:
            remaining_text = text
        else:
            remaining_text = remaining_text if "remaining_text" in locals() else ""

        return audio_parts_found, remaining_text, parts_used

    def _apply_background_noise_if_any(self, audio_data: bytes) -> bytes:
        "Apply background noise to audio data if background noise is enabled."
        if not audio_data:
            return audio_data

        if self.background_noise_enabled and self.audio_mixer and self.audio_mixer.has_background_noise_loaded():
            try:
                mixed_audio = self.audio_mixer.mix_audio_with_background(audio_data, self.background_noise_volume)
                return mixed_audio
            except Exception as e:
                self.logger.error(f"Failed to apply background noise: {e}")
                return audio_data

        return audio_data

    async def synthesize_next_audio_chunk_async(self) -> bytes | None:
        """
        Gets the next text chunk and synthesizes it to audio bytes with intelligent caching.
        Uses partial cache matching to combine cached parts with newly synthesized audio.
        Returns None if no text is available or audio bytes if successful.
        """
        try:
            # Get next sentence to speak
            speech_chunk = await self.text_queue_manager.get_next_text_chunk_async()
            if not speech_chunk:
                return None

            speech_chunk = speech_chunk.strip()

            # Step 1: Try exact cache match first (fastest path)
            cached_bytes = self.get_synthesized_audio_from_cache(speech_chunk, allow_partial=False)
            if cached_bytes:
                self.logger.info(f">>>>>> Using exact cached synthesis for: '{speech_chunk}'")
                return self._apply_background_noise_if_any(cached_bytes)

            # Step 2: Try partial cache matching with intelligent combination
            try:
                audio_parts_found, remaining_text, parts_used = self._find_partial_cached_audio(speech_chunk)

                if audio_parts_found or remaining_text.strip():
                    final_audio_parts = []
                    synthesis_info = []

                    # Add cached parts to final audio
                    if audio_parts_found:
                        final_audio_parts.extend(audio_parts_found)
                        synthesis_info.extend([f"cached({part[:25]}...)" for part in parts_used])

                    # Synthesize remaining text if any
                    if remaining_text.strip():
                        self.logger.info(f">>>>>> Synthesizing remaining text: '{remaining_text}'")
                        remaining_audio = await self.tts_provider.synthesize_speech_to_bytes_async(
                            remaining_text,
                            call_sid=self.call_sid,
                            stream_sid=self.audio_sender.stream_sid,
                            phone_number=self.phone_number,
                        )

                        if remaining_audio:
                            final_audio_parts.append(remaining_audio)
                            synthesis_info.append(f"synthesized({remaining_text[:25]}...)")

                            # Cache the remaining part for future use
                            OutgoingAudioManager.add_synthesized_audio_to_cache(remaining_text.strip(), remaining_audio)
                        else:
                            self.logger.error(f"/!\\ Failed to synthesize remaining text: '{remaining_text}'")

                            # If partial synthesis fails, fall back to complete synthesis
                            return await self._fallback_complete_synthesis(speech_chunk)

                    # Combine all parts if we have multiple parts
                    if len(final_audio_parts) > 1:
                        combined_audio = self._combine_audio_parts(final_audio_parts)
                        if combined_audio:
                            self.logger.info(f">>>>>> Combined audio from: {synthesis_info}")

                            # Cache the complete combined result (without background noise)
                            OutgoingAudioManager.add_synthesized_audio_to_cache(speech_chunk, combined_audio)
                            return self._apply_background_noise_if_any(combined_audio)
                        else:
                            self.logger.warning("Failed to combine audio parts, falling back to complete synthesis")
                            return await self._fallback_complete_synthesis(speech_chunk)

                    elif len(final_audio_parts) == 1:
                        # Only one part (either cached or synthesized)
                        audio_result = final_audio_parts[0]
                        self.logger.info(f">>>>>> Using single audio part: {synthesis_info[0]}")

                        # Cache if this was synthesized (not cached) - store without background noise
                        if not audio_parts_found:  # This means it was synthesized
                            OutgoingAudioManager.add_synthesized_audio_to_cache(speech_chunk, audio_result)

                        return self._apply_background_noise_if_any(audio_result)

            except Exception as e:
                self.logger.error(f"Error in partial synthesis for '{speech_chunk[:50]}...': {e}")
                # Fall back to complete synthesis on error
                return await self._fallback_complete_synthesis(speech_chunk)

            # Step 3: Fall back to complete synthesis if no parts found
            return await self._fallback_complete_synthesis(speech_chunk)

        except Exception as e:
            self.logger.error(f"Error in synthesize_next_audio_chunk_async: {e}")
            return None

    async def _fallback_complete_synthesis(self, text: str) -> bytes | None:
        """
        Fallback method to synthesize complete text when partial synthesis fails.

        Args:
            text: Complete text to synthesize

        Returns:
            Synthesized audio bytes or None if synthesis fails
        """
        try:
            self.logger.info(f">>>>>> Fallback: Synthesizing complete text: '{text}'")
            speech_bytes = await self.tts_provider.synthesize_speech_to_bytes_async(
                text, call_sid=self.call_sid, stream_sid=self.audio_sender.stream_sid, phone_number=self.phone_number
            )

            if speech_bytes:
                # Cache the complete synthesis (without background noise)
                OutgoingAudioManager.add_synthesized_audio_to_cache(text, speech_bytes)
                return self._apply_background_noise_if_any(speech_bytes)
            else:
                self.logger.error(f"/!\\ Failed to synthesize complete text: '{text}'")
                return None

        except Exception as e:
            self.logger.error(f"Error in fallback synthesis for '{text[:50]}...': {e}")
            return None

    async def _background_streaming_worker_async(self) -> None:
        """Background worker that continuously processes texts from the queue and sends audio to the websocket"""
        self.logger.info("Background TTS and audio streaming worker started")
        text_chunks_processed = 0
        errors = 0
        streamSid_wait_count = 0
        max_streamSid_wait = 20  # Maximum number of attempts to wait for streamSid
        last_chunk_end_time = 0  # Track timing for natural speech flow (in ms)
        pre_synthesis_task = None

        while True:
            if self.ask_to_stop_streaming_worker:
                self.logger.info("Stopping audio streaming worker asked")
                pre_synthesis_task = None
                break

            if self.streaming_interuption_asked:
                self.logger.info("Streaming interruption asked")
                self.audio_sender.streaming_interuption_asked = True
                self.audio_sender.is_sending = False
                self.streaming_interuption_asked = False
                pre_synthesis_task = None
                continue

            await asyncio.sleep(self.loop_interval)  # Pause outgoing loop process to let others processes breathe

            if self.is_sending():
                continue

            if not self.has_text_to_be_sent() and not pre_synthesis_task:
                continue

            if not self.audio_sender.stream_sid:
                streamSid_wait_count += 1
                if streamSid_wait_count > max_streamSid_wait:
                    self.logger.error(
                        f"No StreamSid set after {streamSid_wait_count} attempts, audio transmission may fail"
                    )
                await asyncio.sleep(0.2)
                continue

            # Handle the next text chunk to be sent
            try:
                if not pre_synthesis_task and self.has_text_to_be_sent():
                    pre_synthesis_task = asyncio.create_task(self.synthesize_next_audio_chunk_async())

                if not pre_synthesis_task:
                    continue

                while not pre_synthesis_task.done():
                    await asyncio.sleep(self.loop_interval)

                speech_bytes = pre_synthesis_task.result()
                pre_synthesis_task = None

                if not speech_bytes:
                    self.logger.debug("No speech chunk available, waiting...")
                    await asyncio.sleep(0.1)
                    continue

                text_chunks_processed += 1

                if self.keep_outgoing_audio_file:
                    self._save_as_wav_file(speech_bytes)

                # Send the current audio
                send_audio_chunk_task = asyncio.create_task(self.audio_sender.send_audio_chunk_async(speech_bytes))

                # Start pre-synthesis for the next chunk in parallel of sending the current chunk
                pre_synthesis_task = None
                if self.has_text_to_be_sent():
                    pre_synthesis_task = asyncio.create_task(self.synthesize_next_audio_chunk_async())

                # Wait for the send to complete, but check for completion of next synthesis as well
                while not send_audio_chunk_task.done():
                    await asyncio.sleep(self.loop_interval)

            except asyncio.CancelledError:
                self.logger.info("Streaming worker task was cancelled")
                pre_synthesis_task = None
                break

            except Exception as e:
                self.logger.error(f"Error in streaming worker: {e}", exc_info=True)
                errors += 1
                await asyncio.sleep(0.5)  # Sleep a bit longer on error

    def _save_as_wav_file(self, audio_data: bytes, file_name: str | None = None):
        """Save PCM data (16-bit, 8kHz, mono) to a WAV file at the specified path."""
        if not file_name:
            file_name = f"{uuid.uuid4()}.wav"
        with wave.open(os.path.join(self.outgoing_speech_dir, file_name), "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(self.sample_width)  # 16-bit
            wav_file.setframerate(self.frame_rate)  # 8kHz
            wav_file.writeframes(audio_data)  # PCM data
        return file_name

    def run_background_streaming_worker(self) -> None:
        """
        Starts the streaming process in a background task
        """
        if self.is_sending() or self.sender_task is not None:
            self.logger.error("Streaming is already running")
            return

        self.ask_to_stop_streaming_worker = False
        self.sender_task = asyncio.create_task(self._background_streaming_worker_async())
        self.logger.info("Audio background streaming worker started")

    async def stop_background_streaming_worker_async(self) -> None:
        """
        Stops the streaming process and clears the text queue
        """
        self.audio_sender.is_sending = False
        await self.text_queue_manager.clear_queue_async()

        # Stop the background streaming worker
        if self.sender_task:
            try:
                self.ask_to_stop_streaming_worker = True
                await asyncio.wait_for(self.sender_task, timeout=5.0)
            except TimeoutError:
                self.logger.warning("Streaming audio worker did not stop in time, cancelling")
                self.sender_task.cancel()
            except Exception as e:
                self.logger.error(f"Error stopping streaming worker: {e}")
            finally:
                self.sender_task = None

        self.logger.info("Audio background streaming worker stopped")

    async def enqueue_text_async(self, text: str) -> bool:
        """
        Adds text to the queue for speech synthesis and streaming.
        """
        return await self.text_queue_manager.enqueue_text_async(text)

    async def clear_text_queue_async(self) -> str:
        if self.can_speech_be_interupted:
            removed_text = ""
            if self.text_queue_manager.last_text_chunk:
                removed_text += self.text_queue_manager.last_text_chunk + " "
            removed_text += self.text_queue_manager.text_queue
            await self.text_queue_manager.clear_queue_async()
            self.streaming_interuption_asked = True
            self.logger.info("Text queue cleared for interruption")
            return removed_text

    def has_text_to_be_sent(self) -> bool:
        """Check if the audio stream manager has text to send."""
        has_significant_text_queued = (
            not self.text_queue_manager.is_empty()
            and len(self.text_queue_manager.text_queue) > self.min_chars_for_interruptible_speech
        )
        return has_significant_text_queued

    def is_sending(self) -> bool:
        """Returns True if an audio stream is currently outgoing."""
        return self.audio_sender.is_sending

    def get_streaming_stats(self) -> dict:
        """
        Get comprehensive statistics about the text and audio streaming process.

        Returns:
            Dictionary with detailed statistics about text queue and audio processing
        """
        # Get text queue statistics
        text_queue_stats = self.text_queue_manager.get_queue_stats()

        # Get comprehensive audio sender statistics
        audio_sender_stats = self.audio_sender.get_sender_stats()

        # Aggregate statistics
        return {
            "text_queue": text_queue_stats,
            "audio_sender": audio_sender_stats,
            "is_sending_speech": self.has_text_to_be_sent(),
        }
