import asyncio
import audioop
import base64
import json
import logging
import time


class TelnyxAudioSender:
    """
    Handles sending audio to Telnyx with RTP payload format and rate limiting to prevent connection issues.
    """

    def __init__(
        self, websocket: any, stream_id: str = None, sample_rate: int = 8000, min_chunk_interval: float = 0.02
    ):
        self.logger = logging.getLogger(__name__)
        self.websocket = websocket
        self.stream_id = stream_id
        self.sample_rate = sample_rate
        self.min_chunk_interval = min_chunk_interval  # Minimum time between chunks (in seconds)
        self.last_send_time = time.time()
        self.is_sending = False
        self.streaming_interruption_asked = False
        self.send_lock = asyncio.Lock()
        self.total_bytes_sent = 0
        self.bytes_sent = 0  # Alias for total_bytes_sent for consistency with stats API
        self.chunks_sent = 0
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.last_chunk_time = 0
        self.avg_chunk_size = 0
        self.start_time = time.time()
        self.total_send_duration = 0

    async def send_audio_chunk_async(
        self, audio_chunk: bytes, progressive_volume_increase_duration: float = 0.0, sending_start_delay: float = 0.0
    ) -> bool:
        """
        Sends an audio chunk to Telnyx by breaking it into smaller segments with RTP payload format,
        with proportional delays and interruption support.
        The input audio_chunk is expected to be 16-bit linear PCM.
        Returns True if at least one segment was successfully sent, False otherwise.
        """
        if not audio_chunk:
            self.logger.warning("send_audio_chunk called with empty audio_chunk.")
            return False

        if not self.stream_id:
            self.logger.error("No stream_id provided, cannot send audio to Telnyx.")
            return False

        if not self.websocket:
            self.logger.error("WebSocket is not set in TelnyxAudioSender (None).")
            return False

        try:
            if hasattr(self.websocket, "closed") and self.websocket.closed:
                self.logger.error("WebSocket is closed.")
                return False
        except Exception as e:
            self.logger.error(f"Error checking WebSocket state: {e}")
            return False

        try:
            # Ensure audio_chunk has an even number of bytes for 16-bit PCM
            # Each 16-bit sample requires 2 bytes
            if len(audio_chunk) % 2 != 0:
                # Pad with a zero byte to make it even
                audio_chunk = audio_chunk + b"\x00"
                self.logger.debug(f"Padded PCM chunk from {len(audio_chunk) - 1} to {len(audio_chunk)} bytes")

            # Apply progressive volume increase if requested
            if progressive_volume_increase_duration > 0.0:
                chunk_duration = 0.1  # 100ms chunks
                chunk_size = int(self.sample_rate * chunk_duration * 2)  # for 8kHz mono 16-bit = 2x8bits
                processed_chunks = []

                # Add silent chunks if any sending_start_delay
                if sending_start_delay > 0.0:
                    silent_chunks_count = int(sending_start_delay / chunk_duration)
                    silent_chunk = b"\x00" * chunk_size  # Silent chunk (zeros for 16-bit PCM)
                    for _ in range(silent_chunks_count):
                        processed_chunks.append(silent_chunk)

                # Process original audio chunks with adjusted timing
                for i in range(0, len(audio_chunk), chunk_size):
                    chunk = audio_chunk[i : i + chunk_size]
                    chunk_index = i // chunk_size
                    # Adjust timing to account for silent pre-chunks
                    chunk_time = (chunk_index * chunk_duration) + sending_start_delay
                    volume_factor = min(
                        1.0, max(0.0, (chunk_time - sending_start_delay) / progressive_volume_increase_duration)
                    )

                    # Apply volume scaling to this chunk (16-bit PCM, sample width = 2)
                    scaled_chunk = audioop.mul(chunk, 2, volume_factor)
                    processed_chunks.append(scaled_chunk)

                # Concatenate all processed chunks back into a single audio bytes object
                audio_chunk = b"".join(processed_chunks)

            # For Telnyx, we can send PCM directly as RTP payload or convert to μ-law
            # Telnyx supports PCMU (μ-law), so let's convert to μ-law like Twilio for compatibility
            # Convert the entire 16-bit PCM audio_chunk to 8-bit μ-law.
            # Sample width is 2 for 16-bit PCM.
            full_mulaw_audio = audioop.lin2ulaw(audio_chunk, 2)
        except audioop.error as e:
            self.logger.error(f"Error converting PCM to μ-law: {e}. PCM chunk len: {len(audio_chunk)}")
            return False

        segment_size_mulaw = 512  # μ-law bytes per segment (1024 bytes PCM -> 512 bytes μ-law)
        sent_any_segment = False
        original_pcm_chunk_size = len(audio_chunk)

        async with self.send_lock:
            self.is_sending = True
            try:
                for i in range(0, len(full_mulaw_audio), segment_size_mulaw):
                    if self.streaming_interruption_asked:
                        self.logger.info(
                            "~~ Streaming interruption asked by flag, stopping sending for this audio_chunk.~~"
                        )
                        break

                    segment_mulaw = full_mulaw_audio[i : i + segment_size_mulaw]
                    if not segment_mulaw:
                        continue

                    try:
                        payload = base64.b64encode(segment_mulaw).decode("utf-8")
                        # Telnyx uses stream_id instead of streamSid
                        media_message = {
                            "event": "media",
                            "stream_id": self.stream_id,
                            "media": {"payload": payload}
                        }
                        json_message = json.dumps(media_message)

                        await self.websocket.send_text(json_message)
                        sent_any_segment = True

                        # Proportional delay: µ-law is 8000 samples/sec, 1 byte/sample (8000 bytes/sec)
                        delay_duration = len(segment_mulaw) / self.sample_rate
                        await asyncio.sleep(delay_duration - 0.01)

                        if self.consecutive_errors > 0:
                            self.logger.debug(
                                f"Successfully sent a segment after {self.consecutive_errors} prior errors."
                            )
                            self.consecutive_errors = 0

                    except Exception as e:
                        self.consecutive_errors += 1
                        self.logger.error(
                            f"Error sending audio segment to Telnyx: {e} (Consecutive error {self.consecutive_errors})"
                        )
                        if self.consecutive_errors >= self.max_consecutive_errors:
                            self.logger.critical(
                                f"Max consecutive errors ({self.max_consecutive_errors}) reached while sending segment. "
                                f"Stopping processing for current audio_chunk."
                            )
                            break
                        break  # Stop processing this chunk on segment error for safety

                if sent_any_segment:
                    current_time = time.time()
                    self.last_send_time = current_time
                    self.last_chunk_time = current_time

                    self.total_bytes_sent += original_pcm_chunk_size
                    self.bytes_sent = self.total_bytes_sent
                    self.chunks_sent += 1

                    if self.chunks_sent > 0:
                        self.avg_chunk_size = self.total_bytes_sent / self.chunks_sent

                    self.total_send_duration = current_time - self.start_time

                    if self.chunks_sent % 10 == 0:
                        self.logger.debug(
                            f"Audio metrics: {self.chunks_sent} send_audio_chunk calls processed, "
                            f"{self.total_bytes_sent / 1024:.1f} KB total PCM sent, "
                            f"{self.avg_chunk_size:.1f} bytes avg PCM size per call."
                        )
            finally:
                self.is_sending = False
                # Reset interruption flag after sending is complete
                if self.streaming_interruption_asked:
                    self.streaming_interruption_asked = False

        return sent_any_segment

    def get_sender_stats(self) -> dict:
        """
        Get comprehensive statistics about the audio sending process.

        Returns:
            Dictionary with detailed statistics about audio chunks sent
        """
        now = time.time()
        return {
            "chunks_sent": self.chunks_sent,
            "bytes_sent": self.total_bytes_sent,
            "bytes_sent_kb": round(self.total_bytes_sent / 1024, 2),
            "avg_chunk_size": round(self.avg_chunk_size, 2),
            "consecutive_errors": self.consecutive_errors,
            "is_sending": self.is_sending,
            "last_chunk_time": self.last_chunk_time,
            "time_since_last_chunk": round(now - self.last_chunk_time, 3) if self.last_chunk_time > 0 else 0,
            "total_duration": round(now - self.start_time, 2),
            "send_duration": round(self.total_send_duration, 2),
            "stream_id": self.stream_id or "None",
        }

    def get_sending_stats(self) -> dict[str, any]:
        """
        Returns statistics about the audio sending for monitoring
        """
        return {
            "total_bytes_sent": self.total_bytes_sent,
            "chunks_sent": self.chunks_sent,
            "consecutive_errors": self.consecutive_errors,
            "is_sending": self.is_sending,
            "last_send_time": self.last_send_time,
        }