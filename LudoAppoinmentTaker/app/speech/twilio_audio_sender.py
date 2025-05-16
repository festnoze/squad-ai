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
    def __init__(self, websocket: any, streamSid: str = None, min_chunk_interval: float = 0.05):
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
        Sends an audio chunk to Twilio with rate limiting.
        Returns True if successful, False otherwise.
        """
        if not audio_chunk:
            return False
            
        if not self.streamSid:
            self.logger.error("No streamSid provided, cannot send audio to Twilio")
            return False
            
        # Apply rate limiting
        now = time.time()
        time_since_last = now - self.last_send_time
        
        if time_since_last < self.min_chunk_interval:
            await asyncio.sleep(self.min_chunk_interval - time_since_last)
        
        # Only one thread should send at a time
        with self.send_lock:
            try:
                if not self.websocket:
                    self.logger.error("WebSocket is not available")
                    return False
                    
                self.is_sending = True
                
                # Encode the chunk for Twilio
                # If it's already µ-law encoded, we can just base64 encode it
                payload = base64.b64encode(audio_chunk).decode('utf-8')
                
                # Create Media message for Twilio with the correct streamSid
                media_message = {
                    "event": "media",
                    "streamSid": self.streamSid,  # Use the actual Twilio stream SID
                    "media": {
                        "payload": payload
                    }
                }
                
                # Send the audio chunk to Twilio via WebSocket as a JSON string
                await self.websocket.send_text(json.dumps(media_message))
                
                # Update metrics
                self.last_send_time = time.time()
                self.total_bytes_sent += len(audio_chunk)
                self.chunks_sent += 1
                self.consecutive_errors = 0
                return True
                
            except Exception as e:
                self.consecutive_errors += 1
                self.logger.error(f"Error sending audio to Twilio: {e}")
                
                if self.consecutive_errors >= self.max_consecutive_errors:
                    self.logger.critical(f"Too many consecutive errors ({self.consecutive_errors}), "
                                        f"Twilio connection may be broken")
                
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

