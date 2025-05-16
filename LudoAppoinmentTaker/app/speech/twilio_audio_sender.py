import time
import logging
import threading
import asyncio
import json
import base64

class TwilioAudioSender:
    """
    Handles sending audio to Twilio with rate limiting to prevent connection issues.
    """
    def __init__(self, websocket: any, streamSid: str = None, min_chunk_interval: float = 0.02):
        self.logger = logging.getLogger(__name__)
        self.websocket = websocket
        self.streamSid = streamSid
        self.min_chunk_interval = min_chunk_interval  # Minimum time between chunks (in seconds)
        self.last_send_time = time.time()
        self.is_sending = False
        self.send_lock = threading.Lock()
        self.total_bytes_sent = 0
        self.chunks_sent = 0
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        
    async def send_audio_chunk(self, audio_chunk: bytes) -> bool:
        """
        Sends an audio chunk to Twilio with optimized rate limiting.
        Returns True if successful, False otherwise.
        """
        if not audio_chunk:
            return False
            
        if not self.streamSid:
            self.logger.error("No streamSid provided, cannot send audio to Twilio")
            return False
            
        if not self.websocket:
            self.logger.error("WebSocket is not available")
            return False
            
        # Apply minimal rate limiting - only if we're sending too quickly
        now = time.time()
        time_since_last = now - self.last_send_time
        
        if time_since_last < self.min_chunk_interval:
            # Calculate sleep time but use a shorter delay to reduce latency
            sleep_time = max(0.005, self.min_chunk_interval - time_since_last)
            await asyncio.sleep(sleep_time)
        
        # Only one thread should send at a time
        with self.send_lock:
            try:
                self.is_sending = True
                
                # Pre-calculate the message size to detect large payloads
                chunk_size = len(audio_chunk)
                if chunk_size > 8192:  # If chunk is unusually large
                    self.logger.warning(f"Large audio chunk detected: {chunk_size} bytes")
                
                # Encode the chunk for Twilio using base64
                payload = base64.b64encode(audio_chunk).decode('utf-8')
                
                # Create Media message for Twilio with the correct streamSid
                media_message = {
                    "event": "media",
                    "streamSid": self.streamSid,
                    "media": {
                        "payload": payload
                    }
                }
                
                # Send the audio chunk to Twilio via WebSocket
                json_message = json.dumps(media_message)
                await self.websocket.send_text(json_message)
                
                # Update metrics
                self.last_send_time = time.time()
                self.total_bytes_sent += chunk_size
                self.chunks_sent += 1
                
                # Reset error counter on success
                if self.consecutive_errors > 0:
                    self.logger.info(f"Successfully sent after {self.consecutive_errors} errors")
                    self.consecutive_errors = 0
                
                return True
                
            except Exception as e:
                self.consecutive_errors += 1
                self.logger.error(f"Error sending audio to Twilio: {e}")
                
                if self.consecutive_errors >= self.max_consecutive_errors:
                    self.logger.critical(f"Too many consecutive errors ({self.consecutive_errors}), "
                                        f"Twilio connection may be broken")
                    
                # Implement retry with increasing backoff for transient errors
                if self.consecutive_errors < 3:
                    await asyncio.sleep(0.1 * self.consecutive_errors)  # Progressive backoff
                    # We could implement retries here if needed
                
                return False
            finally:
                self.is_sending = False
                
    def get_sending_stats(self) -> dict[str, any]:
        """
        Returns statistics about the audio sending for monitoring
        """
        return {
            "total_bytes_sent": self.total_bytes_sent,
            "chunks_sent": self.chunks_sent,
            "consecutive_errors": self.consecutive_errors,
            "is_sending": self.is_sending,
            "last_send_time": self.last_send_time
        }

