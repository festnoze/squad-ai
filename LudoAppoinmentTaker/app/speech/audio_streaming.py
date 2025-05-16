import logging
import asyncio
from app.speech.audio_queue_manager import AudioQueueManager
from app.speech.twilio_audio_sender import TwilioAudioSender

class AudioStreamManager:
    """
    Manages the complete audio streaming process, combining queue management and sending.
    """
    def __init__(self, websocket: any, streamSid: str = None, max_queue_size: int = 20, min_chunk_interval: float = 0.05):
        self.logger = logging.getLogger(__name__)
        self.queue_manager = AudioQueueManager(max_queue_size=max_queue_size)
        self.audio_sender = TwilioAudioSender(websocket, streamSid=streamSid, min_chunk_interval=min_chunk_interval)
        self.running = False
        self.sender_task = None
        
    def update_stream_sid(self, streamSid: str) -> None:
        """
        Updates the stream SID when it changes (e.g., when a new call starts)
        """
        if not streamSid:
            self.logger.warning("Attempted to update streamSid with None or empty value")
            return
            
        self.audio_sender.streamSid = streamSid
        self.logger.info(f"Updated stream SID to: {streamSid}")
        return
        
    def start_streaming(self) -> None:
        """
        Starts the streaming process in a background task
        """
        if self.running:
            self.logger.warning("Streaming is already running")
            return
            
        self.running = True
        self.sender_task = asyncio.create_task(self._streaming_worker())
        self.logger.info("Audio streaming started")
        
    async def stop_streaming(self) -> None:
        """
        Stops the streaming process
        """
        self.running = False
        if self.sender_task:
            try:
                # Wait for the task to complete with a timeout
                await asyncio.wait_for(self.sender_task, timeout=2.0)
            except asyncio.TimeoutError:
                self.logger.warning("Streaming worker did not stop in time, cancelling")
                self.sender_task.cancel()
            except Exception as e:
                self.logger.error(f"Error stopping streaming worker: {e}")
                
        self.queue_manager.clear_queue()
        self.logger.info("Audio streaming stopped")
        
    def enqueue_audio(self, audio_chunk: bytes) -> bool:
        """
        Adds audio to the queue for streaming
        """
        return self.queue_manager.enqueue_audio(audio_chunk)
        
    async def _streaming_worker(self) -> None:
        """
        Background task that pulls audio from the queue and sends it to Twilio
        """
        self.logger.info("Streaming worker started")
        chunks_processed = 0
        errors = 0
        
        while self.running:
            try:
                # Check if we have a valid streamSid before processing
                if not self.audio_sender.streamSid:
                    self.logger.warning("No StreamSid set in audio sender, audio won't be sent")
                    await asyncio.sleep(0.5)
                    continue
                    
                # Get audio chunk from queue (with timeout to check if we should stop)
                audio_chunk = self.queue_manager.get_audio_chunk(block=True, timeout=0.1)
                
                if audio_chunk:
                    chunks_processed += 1
                    chunk_size = len(audio_chunk)
                    self.logger.debug(f"Processing audio chunk #{chunks_processed}, size: {chunk_size} bytes")
                    
                    # Send the chunk to Twilio
                    result = await self.audio_sender.send_audio_chunk(audio_chunk)
                    
                    if result:
                        self.logger.debug(f"Successfully sent audio chunk #{chunks_processed} ({chunk_size} bytes)")
                    else:
                        self.logger.warning(f"Failed to send audio chunk #{chunks_processed} ({chunk_size} bytes)")
                        errors += 1
                        
                        if errors > 5 and errors % 5 == 0:
                            self.logger.error(f"Multiple audio sending errors: {errors} chunks failed")
                else:
                    # No audio to send, sleep a bit to reduce CPU usage
                    await asyncio.sleep(0.01)
                    
            except Exception as e:
                self.logger.error(f"Error in streaming worker: {e}", exc_info=True)
                errors += 1
                await asyncio.sleep(0.5)  # Sleep a bit longer on error
                
        self.logger.info(f"Streaming worker stopped. Processed {chunks_processed} chunks with {errors} errors.")
        
    def get_streaming_stats(self) -> dict[str, any]:
        """
        Returns statistics about the streaming process for monitoring
        """
        queue_stats = self.queue_manager.get_queue_stats()
        sender_stats = self.audio_sender.get_sending_stats()
        
        return {
            "queue": queue_stats,
            "sender": sender_stats,
            "running": self.running
        }
