from fastapi import WebSocket
from speech.twilio_audio_sender import TwilioAudioSender
from speech.telnyx_audio_sender import TelnyxAudioSender
from utils.envvar import EnvHelper


def create_audio_sender(
    websocket: WebSocket,
    stream_id: str = None,
    sample_rate: int = 8000,
    min_chunk_interval: float = 0.02,
    provider: str = None
):
    """Factory function to create appropriate audio sender based on provider"""
    if provider is None:
        provider = EnvHelper.get_phone_provider()
    
    if provider == "telnyx":
        return TelnyxAudioSender(
            websocket=websocket,
            stream_id=stream_id,
            sample_rate=sample_rate,
            min_chunk_interval=min_chunk_interval
        )
    else:
        # Default to Twilio for backwards compatibility
        return TwilioAudioSender(
            websocket=websocket,
            stream_sid=stream_id,  # Twilio uses stream_sid
            sample_rate=sample_rate,
            min_chunk_interval=min_chunk_interval
        )