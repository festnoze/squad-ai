import os
import logging
import asyncio
import uuid
import time
import wave
from fastapi import WebSocket
#
from speech.text_queue_manager import TextQueueManager
from speech.twilio_audio_sender import TwilioAudioSender
from speech.text_to_speech import TextToSpeechProvider
from managers.outgoing_manager import OutgoingManager
from utils.envvar import EnvHelper
#
from utils.async_call_wrapper import AsyncCallWrapper

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
            can_speech_be_interupted: bool = True,
            min_chars_for_interruptible_speech: int = 5,
            sample_width: int = 1,
            frame_rate: int = 8000,
            channels: int = 1,
            loop_interval: float = 0.05, # 50ms~
            max_words_by_stream_chunk: int = 20,
            max_chars_by_stream_chunk: int = 100,
            cache_ttl_minutes: int = 5
        ):
        self.logger = logging.getLogger(__name__)
        super().__init__(output_channel = "audio", can_speech_be_interupted=can_speech_be_interupted)
        self.text_queue_manager = TextQueueManager()
        self.audio_sender : TwilioAudioSender = TwilioAudioSender(websocket, stream_sid=stream_sid, sample_rate=frame_rate, min_chunk_interval=min_chunk_interval)
        
        self.tts_provider : TextToSpeechProvider = tts_provider  # Text-to-speech provider for converting text to audio
        self.sender_task = None
        self.keep_audio_file = EnvHelper.get_keep_audio_files()
        self.frame_rate = frame_rate   # mu-law in 8/16kHz
        self.sample_width = sample_width    # mu-law in 8/16 bits
        self.channels = channels
        self.streaming_interuption_asked = False
        self.ask_to_stop_streaming_worker = False
        self.websocket = websocket
        self.min_chars_for_interruptible_speech = min_chars_for_interruptible_speech
        self.loop_interval = loop_interval
        self.max_words_by_stream_chunk = max_words_by_stream_chunk
        self.max_chars_by_stream_chunk = max_chars_by_stream_chunk
        self.cache_ttl_seconds = cache_ttl_minutes * 60
        
        # Create temp directory if it doesn't exist
        os.makedirs(self.outgoing_speech_dir, exist_ok=True)


    def set_websocket(self, websocket: WebSocket):
        self.websocket = websocket
        self.audio_sender.websocket = websocket

    def update_stream_sid(self, stream_sid: str) -> None:
        """
        Updates the stream SID when it changes (e.g., when a new call starts or ends)
        Allows setting to None when resetting after a call ends
        """
        self.audio_sender.stream_sid = stream_sid
        if not stream_sid:
            self.logger.info("Reset stream SID to None")
        else:
            self.logger.info(f"Updated stream SID to: {stream_sid}")
        return

    def get_synthesized_audio_from_cache(self, text: str) -> bytes | None:
        """
        Get cached synthesis result if available and not expired.
        Permanent entries (timestamp = -1) never expire.
        """
        if text not in self._synthesized_audio_cache:
            return None
            
        audio_bytes, timestamp = self._synthesized_audio_cache[text]
        
        # Permanent entries never expire (timestamp = -1)
        if timestamp == -1:
            return audio_bytes
        
        current_time = time.time()
        if current_time - timestamp > self.cache_ttl_seconds:
            # Cache expired, remove entry
            del self._synthesized_audio_cache[text]
            return None
            
        return audio_bytes
    
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

    async def synthesize_next_audio_chunk_async(self) -> bytes | None:
        """
        Gets the next text chunk and synthesizes it to audio bytes.
        Returns None if no text is available or tuple (speech_chunk, speech_bytes) if successful.
        Uses caching to avoid re-synthesizing the same text.
        """
        try:
            # Get next sentense to speak
            speech_chunk = await self.text_queue_manager.get_next_text_chunk_async()
            if not speech_chunk:
                return None
            
            # Search for the existing audio of the sentense from cache first
            cached_bytes = self.get_synthesized_audio_from_cache(speech_chunk)
            if cached_bytes:
                self.logger.info(f">>>>>> Using cached synthesis for chunk: '{speech_chunk}'")
                return cached_bytes
            
            # Else, synthesize the audio for the text
            speech_bytes = await self.tts_provider.synthesize_speech_to_bytes_async(speech_chunk)
            self.logger.info(f">>>>>> Synthesized speech for chunk: '{speech_chunk}'")
            if not speech_bytes:
                self.logger.error(f"/!\\ Failed to synthesize speech for chunk: '{speech_chunk}'")
                return None
            
            # Cache the synthesized audio for the text
            OutgoingAudioManager.add_synthesized_audio_to_cache(speech_chunk, speech_bytes)
                
            return speech_bytes

        except Exception as e:
            self.logger.error(f"Error in synthesize_next_audio_chunk_async: {e}")
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
            
            await asyncio.sleep(self.loop_interval) # Pause outgoing loop process to let others processes breathe

            if self.is_sending():
                continue

            if not self.has_text_to_be_sent() and not pre_synthesis_task:
                continue

            if not self.audio_sender.stream_sid:
                streamSid_wait_count += 1
                if streamSid_wait_count > max_streamSid_wait:
                    self.logger.error(f"No StreamSid set after {streamSid_wait_count} attempts, audio transmission may fail")
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

                if self.keep_audio_file:
                    self.save_as_wav_file(speech_bytes)
                
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
                
    def save_as_wav_file(self, audio_data: bytes):
        """Save PCM data (16-bit, 8kHz, mono) to a WAV file at the specified path."""
        file_name = f"{uuid.uuid4()}.wav"
        with wave.open(os.path.join(self.outgoing_speech_dir, file_name), "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(self.sample_width)  # 16-bit
            wav_file.setframerate(self.frame_rate) # 8kHz
            wav_file.writeframes(audio_data) # PCM data
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
            except asyncio.TimeoutError:
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
            text = await self.text_queue_manager.clear_queue_async()
            self.streaming_interuption_asked = True
            self.logger.info("Text queue cleared for interruption")
            return text
        
    def has_text_to_be_sent(self) -> bool:
        """Check if the audio stream manager has text to send."""
        has_significant_text_queued = (
            not self.text_queue_manager.is_empty() and
            len(self.text_queue_manager.text_queue) > self.min_chars_for_interruptible_speech
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
            'text_queue': text_queue_stats,
            'audio_sender': audio_sender_stats,
            'is_sending_speech': self.has_text_to_be_sent()
        }