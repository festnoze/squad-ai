import logging
import asyncio
from fastapi import WebSocket
#
from app.speech.text_queue_manager import TextQueueManager
from app.speech.text_processing import ProcessText
from app.speech.twilio_audio_sender import TwilioAudioSender
from app.speech.text_to_speech import TextToSpeechProvider
from app.managers.outgoing_manager import OutgoingManager
#
from app.utils.async_call_wrapper import AsyncCallWrapper

class OutgoingAudioManager(OutgoingManager):
    """
    Manages the complete audio streaming process using a text-based approach.
    Text is queued, then processed into speech in small chunks for better responsiveness.
    """
    def __init__(
            self,
            websocket: any,
            tts_provider: TextToSpeechProvider,
            stream_sid: str = None,
            min_chunk_interval: float = 0.05,  # 50ms~
            min_chars_for_interruptible_speech: int = 15,
            sample_width: int = 1,
            frame_rate: int = 8000,
            channels: int = 1,
            loop_interval: float = 0.05, # 50ms~
            pause_between_chunks: float = 0.05, # 50ms~
            max_words_by_stream_chunk: int = 20,
            max_chars_by_stream_chunk: int = 100
        ):

        self.text_queue_manager = TextQueueManager()
        self.audio_sender : TwilioAudioSender = TwilioAudioSender(websocket, stream_sid=stream_sid, min_chunk_interval=min_chunk_interval)
        self.logger = logging.getLogger(__name__)
        self.tts_provider : TextToSpeechProvider = tts_provider  # Text-to-speech provider for converting text to audio
        self.sender_task = None
        self.frame_rate = frame_rate   # mu-law in 8/16kHz
        self.sample_width = sample_width    # mu-law in 8/16 bits
        self.channels = channels
        self.streaming_interuption_asked = False
        self.ask_to_stop_streaming_worker = False
        self.websocket = websocket
        self.min_chars_for_interruptible_speech = min_chars_for_interruptible_speech
        self.loop_interval = loop_interval
        self.pause_between_chunks = pause_between_chunks
        self.max_words_by_stream_chunk = max_words_by_stream_chunk
        self.max_chars_by_stream_chunk = max_chars_by_stream_chunk

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

    def synthesize_next_audio_chunk(self):
        """
        Gets the next text chunk and synthesizes it to audio bytes.
        Returns None if no text is available or tuple (speech_chunk, speech_bytes) if successful.
        """
        try:
            # Process this text into optimal chunks for natural speech
            if self.text_queue_manager.is_empty():
                return None
            speech_chunk = self.text_queue_manager.get_next_text_chunk_sync()
            if not speech_chunk:
                return None
            
            speech_bytes = self.tts_provider.synthesize_speech_to_bytes(speech_chunk)
            if not speech_bytes:
                self.logger.warning(f"Failed to synthesize speech for chunk: '{speech_chunk}'")
                return None
                
            return (speech_chunk, speech_bytes)
        except Exception as e:
            self.logger.error(f"Error in synthesize_next_audio_chunk: {e}")
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
        next_chunk_data = None  # Will store (speech_chunk, speech_bytes)
        
        # Helper function to safely cancel and clean up the pre-synthesis task
        def cleanup_pre_synthesis():
            nonlocal pre_synthesis_task, next_chunk_data
            if pre_synthesis_task:
                try:
                    if not pre_synthesis_task.done():
                        # We can't directly cancel a thread, but we'll reset the reference
                        pass
                except Exception as e:
                    self.logger.error(f"Error cleaning up pre-synthesis task: {e}")
                pre_synthesis_task = None
            next_chunk_data = None

        # Create a helper function to create a task for async.to_thread-like behavior
        async def create_synthesis_task():
            nonlocal pre_synthesis_task
            if not pre_synthesis_task or pre_synthesis_task.done():
                pre_synthesis_task = asyncio.create_task(asyncio.to_thread(
                    self.synthesize_next_audio_chunk
                ))
            return pre_synthesis_task

        while True:
            if self.ask_to_stop_streaming_worker:
                self.logger.info("Stopping audio streaming worker asked")
                cleanup_pre_synthesis()
                break

            if self.streaming_interuption_asked:
                self.logger.info("Streaming interruption asked")
                self.audio_sender.streaming_interuption_asked = True
                self.audio_sender.is_sending = False
                self.streaming_interuption_asked = False
                cleanup_pre_synthesis()
                continue
            
            if not self.is_sending_speech():
                await asyncio.sleep(self.loop_interval)
                continue
            
            await asyncio.sleep(self.loop_interval) # Pause outgoing loop process to let others processes breathe

            try:
                if not self.audio_sender.stream_sid:
                    streamSid_wait_count += 1
                    if streamSid_wait_count <= max_streamSid_wait:
                        self.logger.warning(f"Waiting for StreamSid initialization ({streamSid_wait_count}/{max_streamSid_wait})...")
                    else:
                        self.logger.error(f"No StreamSid set after {streamSid_wait_count} attempts, audio transmission may fail")
                    
                    await asyncio.sleep(0.2)
                    continue
                    
                if streamSid_wait_count > 0:
                    self.logger.info(f"StreamSid now available after {streamSid_wait_count} attempts: {self.audio_sender.stream_sid}")
                    streamSid_wait_count = 0
                
                # Start pre-synthesis for the first chunk
                if not pre_synthesis_task:
                    self.logger.debug("Starting initial speech synthesis")
                    pre_synthesis_task = asyncio.create_task(asyncio.to_thread(
                        self.synthesize_next_audio_chunk
                    ))
                
                # Wait for synthesis to complete if it's running
                if not pre_synthesis_task.done():
                    try:
                        # Wait with timeout to allow for interruption checks
                        await asyncio.wait_for(asyncio.shield(pre_synthesis_task), 0.5)
                    except asyncio.TimeoutError:
                        # Keep waiting in the next loop iteration
                        continue
                    except Exception as e:
                        self.logger.error(f"Error waiting for pre-synthesis: {e}")
                        pre_synthesis_task = None
                        continue
                
                # Get the result of the synthesis
                try:
                    next_chunk_data = pre_synthesis_task.result()
                    pre_synthesis_task = None
                    
                    if not next_chunk_data:
                        self.logger.debug("No speech chunk available, waiting...")
                        await asyncio.sleep(0.1)
                        continue
                    
                    speech_chunk, speech_bytes = next_chunk_data
                    text_chunks_processed += 1
                    self.logger.debug(f"- Processing speech chunk #{text_chunks_processed}: '{speech_chunk}' ({len(speech_chunk)} chars)")
                    
                    # Send the current audio
                    send_task = asyncio.create_task(self.audio_sender.send_audio_chunk(speech_bytes))
                    
                    # Start pre-synthesis for the next chunk in parallel
                    pre_synthesis_task = asyncio.create_task(asyncio.to_thread(
                        self.synthesize_next_audio_chunk
                    ))

                    # Wait for the send to complete, but check for completion of next synthesis as well
                    while not send_task.done():
                        await asyncio.sleep(0.05)
                    
                    result = send_task.result()
                    
                    if result:
                        self.logger.debug(f"Successfully sent text chunk #{text_chunks_processed} as audio")
                    else:
                        self.logger.warning(f"Failed to send audio for text chunk #{text_chunks_processed}")
                        errors += 1
                        
                        if errors > 5 and errors % 5 == 0:
                            self.logger.error(f"Multiple audio sending errors: {errors} chunks failed")
                
                except asyncio.CancelledError:
                    self.logger.info("Pre-synthesis task was cancelled")
                    pre_synthesis_task = None
                    continue
                except Exception as e:
                    self.logger.error(f"Error processing or sending speech: {e}")
                    errors += 1
                    pre_synthesis_task = None
                    await asyncio.sleep(0.2)  # Sleep briefly before retrying
                    continue
                    
            except asyncio.CancelledError:
                self.logger.info("Streaming worker task was cancelled")
                cleanup_pre_synthesis()
                break
                
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
        self.sender_task = asyncio.create_task(self._background_streaming_worker_async())
        self.logger.info("Audio background streaming worker started")
        
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
                await asyncio.wait_for(self.sender_task, timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.warning("Streaming audio worker did not stop in time, cancelling")
                self.sender_task.cancel()
            except Exception as e:
                self.logger.error(f"Error stopping streaming worker: {e}")
            finally:
                self.sender_task = None

        self.logger.info("Audio background streaming worker stopped")
        
    async def enqueue_text(self, text: str) -> bool:
        """
        Adds text to the queue for speech synthesis and streaming.
        """
        return await self.text_queue_manager.enqueue_text(text)
        
    async def clear_text_queue(self) -> None:
        await self.text_queue_manager.clear_queue()
        self.streaming_interuption_asked = True
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