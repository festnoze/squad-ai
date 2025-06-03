import logging
import asyncio
from fastapi import WebSocket
#
from app.speech.text_queue_manager import TextQueueManager
from app.speech.text_processing import ProcessText
from app.speech.twilio_audio_sender import TwilioAudioSender
from app.speech.text_to_speech import TextToSpeechProvider
from app.speech.outgoing_manager import OutgoingManager

class OutgoingAudioManager(OutgoingManager):
    """
    Manages the complete audio streaming process using a text-based approach.
    Text is queued, then processed into speech in small chunks for better responsiveness.
    """
    def __init__(self, websocket: any, tts_provider: TextToSpeechProvider, streamSid: str = None, min_chunk_interval: float = 0.05, min_chars_for_interruptible_speech: int = 15, sample_width=1, frame_rate=8000, channels=1):
        self.text_queue_manager = TextQueueManager()
        self.audio_sender : TwilioAudioSender = TwilioAudioSender(websocket, streamSid=streamSid, min_chunk_interval=min_chunk_interval)
        self.logger = logging.getLogger(__name__)
        self.tts_provider : TextToSpeechProvider = tts_provider  # Text-to-speech provider for converting text to audio
        self.sender_task = None
        self.frame_rate = frame_rate   # mu-law in 8/16kHz
        self.sample_width = sample_width    # mu-law in 8/16 bits
        self.channels = channels
        self.max_words_by_stream_chunk = 10
        self.max_chars_by_stream_chunk = 100
        self.ask_to_stop_streaming_worker = False
        self.websocket = websocket
        self.min_chars_for_interruptible_speech = min_chars_for_interruptible_speech

    def set_websocket(self, websocket: WebSocket):
        self.websocket = websocket
        self.audio_sender.websocket = websocket

    def update_stream_sid(self, streamSid: str) -> None:
        """
        Updates the stream SID when it changes (e.g., when a new call starts or ends)
        Allows setting to None when resetting after a call ends
        """
        self.audio_sender.streamSid = streamSid
        if not streamSid:
            self.logger.info("Reset stream SID to None")
        else:
            self.logger.info(f"Updated stream SID to: {streamSid}")
        return
         
    async def _background_streaming_worker(self):
        """Background worker that continuously processes texts from the queue and sends audio to the websocket"""
        self.logger.info("Background TTS and audio streaming worker started")
        text_chunks_processed = 0
        errors = 0
        streamSid_wait_count = 0
        max_streamSid_wait = 20  # Maximum number of attempts to wait for streamSid
        last_chunk_end_time = 0  # Track timing for natural speech flow (in ms)
        
        while True:
            if self.ask_to_stop_streaming_worker:
                self.logger.info("Stopping audio streaming worker asked")
                break
            
            if not self.is_sending_speech():
                await asyncio.sleep(0.1)
                continue

            try:
                if not self.audio_sender.streamSid:
                    streamSid_wait_count += 1
                    if streamSid_wait_count <= max_streamSid_wait:
                        self.logger.warning(f"Waiting for StreamSid initialization ({streamSid_wait_count}/{max_streamSid_wait})...")
                    else:
                        self.logger.error(f"No StreamSid set after {streamSid_wait_count} attempts, audio transmission may fail")
                    
                    await asyncio.sleep(0.2)
                    continue
                    
                if streamSid_wait_count > 0:
                    self.logger.info(f"StreamSid now available after {streamSid_wait_count} attempts: {self.audio_sender.streamSid}")
                    streamSid_wait_count = 0
                
                # Process this text into optimal chunks for natural speech
                speech_chunk = await self.text_queue_manager.get_next_text_chunk()
                                
                if not speech_chunk:
                    continue

                # Calculate timing for this chunk
                start_time, end_time = ProcessText.calculate_speech_timing(
                    speech_chunk, 
                    previous_chunk_end_time=last_chunk_end_time,
                    min_gap=0.05  # 50ms minimum gap between chunks
                )
                
                text_chunks_processed += 1
                chunk_len = len(speech_chunk)
                self.logger.debug(f"Processing speech chunk #{text_chunks_processed}: '{speech_chunk}' ({chunk_len} chars)")
                
                try:
                    # Synthesize speech from this chunk (returns MP3 format)
                    speech_bytes = self.tts_provider.synthesize_speech_to_bytes(speech_chunk)
                    
                    # Send the converted PCM audio to Twilio
                    result = await self.audio_sender.send_audio_chunk(speech_bytes)
                    
                    if result:
                        self.logger.debug(f"Successfully sent text chunk #{text_chunks_processed} as audio")
                    else:
                        self.logger.warning(f"Failed to send audio for text chunk #{text_chunks_processed}")
                        errors += 1
                        
                        if errors > 5 and errors % 5 == 0:
                            self.logger.error(f"Multiple audio sending errors: {errors} chunks failed")
                    
                    # Update the last chunk end time
                    last_chunk_end_time = end_time
                    
                    # Log progress periodically
                    if text_chunks_processed % 10 == 0:
                        self.logger.debug(
                            f"Processed {text_chunks_processed} chunks, total duration: {last_chunk_end_time/1000:.2f} seconds"
                        )
                except Exception as e:
                    self.logger.error(f"Error synthesizing or sending speech: {e}")
                    errors += 1
                    continue
                
                # Wait for a natural pause between chunks (helps create more natural rhythm)
                await asyncio.sleep(0.05)
                    
            except Exception as e:
                self.logger.error(f"Error in streaming worker: {e}", exc_info=True)
                errors += 1
                await asyncio.sleep(0.5)  # Sleep a bit longer on error
                       
    def run_background_streaming_worker(self) -> None:
        """
        Starts the streaming process in a background task
        """
        if self.audio_sender.is_sending or self.sender_task is not None:
            self.logger.error("Streaming is already running")
            return
            
        self.ask_to_stop_streaming_worker = False
        self.sender_task = asyncio.create_task(self._background_streaming_worker())
        self.logger.info("Audio streaming started")
        
    async def stop_background_streaming_worker_async(self) -> None:
        """
        Stops the streaming process and clears the text queue
        """
        self.audio_sender.is_sending = False
        await self.text_queue_manager.clear_queue()

        # Stop the background streaming worker
        if self.sender_task:
            try:
                self.ask_to_stop_streaming_worker = True
                await asyncio.wait_for(self.sender_task, timeout=2.0)
            except asyncio.TimeoutError:
                self.logger.warning("Streaming worker did not stop in time, cancelling")
                self.sender_task.cancel()
            except Exception as e:
                self.logger.error(f"Error stopping streaming worker: {e}")
            finally:
                self.sender_task = None

        self.logger.info("Audio streaming worker stopped")
        
    async def enqueue_text(self, text: str) -> bool:
        """
        Adds text to the queue for speech synthesis and streaming.
        """
        return await self.text_queue_manager.enqueue_text(text)
        
    async def clear_text_queue(self) -> None:
        await self.text_queue_manager.clear_queue()
        self.logger.info("Text queue cleared for interruption")
        
    def is_sending_speech(self) -> bool:
        """Check if the audio stream manager is actively sending audio or has significant text queued."""
        has_significant_text_queued = (
            not self.text_queue_manager.is_empty() and
            len(self.text_queue_manager.text_queue) > self.min_chars_for_interruptible_speech
        )
        return has_significant_text_queued or self.audio_sender.is_sending
        
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
            'is_sending_speech': self.is_sending_speech()
        }