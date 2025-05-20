import logging
import asyncio
from app.speech.text_queue_manager import TextQueueManager
from app.speech.text_processing import ProcessText
from app.speech.twilio_audio_sender import TwilioAudioSender
from typing import Optional, Tuple

class AudioStreamManager:


    """
    Manages the complete audio streaming process using a text-based approach.
    Text is queued, then processed into speech in small chunks for better responsiveness.
    """
    def __init__(self, websocket: any, tts_provider: any, streamSid: str = None, min_chunk_interval: float = 0.05):
        self.logger = logging.getLogger(__name__)
        self.text_queue_manager = TextQueueManager()
        self.audio_sender = TwilioAudioSender(websocket, streamSid=streamSid, min_chunk_interval=min_chunk_interval)
        self.tts_provider = tts_provider  # Text-to-speech provider for converting text to audio
        self.sender_task = None
        self.frame_rate = 24000  # Default frame rate, can be updated as needed
        self.sample_width = 2    # Default sample width, can be updated as needed
        
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
        
    def start_streaming(self) -> None:
        """
        Starts the streaming process in a background task
        """
        if self.audio_sender.is_sending:
            self.logger.warning("Streaming is already running")
            return
            
        self.sender_task = asyncio.create_task(self._streaming_worker())
        self.logger.info("Audio streaming started")
        
    async def stop_streaming(self) -> None:
        """
        Stops the streaming process and clears the text queue
        """
        self.audio_sender.is_sending = False
        if self.sender_task:
            try:
                # Wait for the task to complete with a timeout
                await asyncio.wait_for(self.sender_task, timeout=2.0)
            except asyncio.TimeoutError:
                self.logger.warning("Streaming worker did not stop in time, cancelling")
                self.sender_task.cancel()
            except Exception as e:
                self.logger.error(f"Error stopping streaming worker: {e}")
        
        # Clear the text queue asynchronously
        await self.text_queue_manager.clear_queue()
        self.logger.info("Text-to-speech streaming stopped")
        
    async def enqueue_text(self, text: str) -> bool:
        """
        Adds text to the queue for speech synthesis and streaming.
        Returns True if the text was successfully enqueued.
        """
        return await self.text_queue_manager.enqueue_text(text)
        
    async def clear_text_queue(self) -> None:
        """
        Clears the text queue without stopping the streaming worker.
        Used for interruption handling to immediately stop processing text.
        """
        # Clear the queue asynchronously
        await self.text_queue_manager.clear_queue()
        self.logger.info("Text queue cleared for interruption")
        
    def is_actively_sending(self) -> bool:
        """
        Check if the audio stream manager is actively sending audio
        """
        # Consider both the text queue and the audio sender status
        return not self.text_queue_manager.is_empty() or self.audio_sender.is_sending
        
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
            'is_running': self.audio_sender.is_sending,
            'is_actively_sending': self.is_actively_sending()
        }
        
    async def _streaming_worker(self):
        """Worker that processes texts from the queue and sends audio to the websocket"""
        self.logger.info("Text-to-speech streaming worker started")
        text_chunks_processed = 0
        errors = 0
        streamSid_wait_count = 0
        max_streamSid_wait = 20  # Maximum number of attempts to wait for streamSid
        last_chunk_end_time = 0  # Track timing for natural speech flow (in ms)
        
        while self.audio_sender.is_sending:
            try:
                # Check if we have a valid streamSid before processing
                if not self.audio_sender.streamSid:
                    streamSid_wait_count += 1
                    if streamSid_wait_count <= max_streamSid_wait:
                        self.logger.warning(f"Waiting for StreamSid initialization ({streamSid_wait_count}/{max_streamSid_wait})...")
                    else:
                        self.logger.error(f"No StreamSid set after {streamSid_wait_count} attempts, audio transmission may fail")
                    
                    # Short wait to check again
                    await asyncio.sleep(0.2)
                    continue
                    
                # Reset counter if we now have a valid streamSid
                if streamSid_wait_count > 0:
                    self.logger.info(f"StreamSid now available after {streamSid_wait_count} attempts: {self.audio_sender.streamSid}")
                    streamSid_wait_count = 0
                
                # Get a chunk of text from the queue
                text_chunk, estimated_duration = await self.text_queue_manager.get_text_chunk()
                
                if text_chunk:
                    # Process this text into optimal chunks for natural speech
                    speech_chunks = ProcessText.chunk_text_by_sized_sentences(text_chunk, max_words_by_sentence=25, max_chars_by_sentence=150)
                    
                    for chunk in speech_chunks:
                        # Skip empty chunks
                        if not chunk:
                            continue
                            
                        # Check if we should stop
                        if not self.audio_sender.is_sending:
                            break
                            
                        # Calculate timing for this chunk
                        start_time, end_time = ProcessText.calculate_speech_timing(
                            chunk, 
                            previous_chunk_end_time=last_chunk_end_time,
                            min_gap=0.05  # 50ms minimum gap between chunks
                        )
                        
                        text_chunks_processed += 1
                        chunk_len = len(chunk)
                        self.logger.debug(f"Processing speech chunk #{text_chunks_processed}: '{chunk}' ({chunk_len} chars)")
                        
                        try:
                            # Synthesize speech from this chunk
                            audio_bytes = self.tts_provider.synthesize_speech_to_bytes(chunk)
                            
                            # Send the audio to Twilio
                            result = await self.audio_sender.send_audio_chunk(audio_bytes)
                            
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
                else:
                    # No text to process, sleep a bit to reduce CPU usage
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                self.logger.error(f"Error in streaming worker: {e}", exc_info=True)
                errors += 1
                await asyncio.sleep(0.5)  # Sleep a bit longer on error
                
        self.logger.info(f"Text-to-speech streaming worker stopped. Processed {text_chunks_processed} chunks with {errors} errors.")
        
    def get_streaming_stats(self) -> dict[str, any]:
        """
        Returns statistics about the streaming process for monitoring
        """
        queue_stats = self.text_queue_manager.get_queue_stats()
        sender_stats = self.audio_sender.get_sending_stats()
        
        return {
            "text_queue": queue_stats,
            "audio_sender": sender_stats,
            "running": self.audio_sender.is_sending
        }
