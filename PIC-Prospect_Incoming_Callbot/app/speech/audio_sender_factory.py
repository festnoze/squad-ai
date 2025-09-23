from fastapi import WebSocket
from speech.telnyx_audio_sender import TelnyxAudioSender
from speech.twilio_audio_sender import TwilioAudioSender
from utils.phone_provider_type import PhoneProviderType


def create_audio_sender(websocket: WebSocket, phone_provider: PhoneProviderType | str, stream_id: str = None, sample_rate: int = 8000, min_chunk_interval: float = 0.02):
    """Factory function to create appropriate audio sender based on provider"""
    # Support both enum and string for backwards compatibility
    if isinstance(phone_provider, PhoneProviderType):
        provider_type = phone_provider
    else:
        # Convert string to enum for backwards compatibility
        provider_type = PhoneProviderType.TELNYX if phone_provider == "telnyx" else PhoneProviderType.TWILIO

    if provider_type == PhoneProviderType.TELNYX:
        return TelnyxAudioSender(websocket=websocket, stream_id=stream_id, sample_rate=sample_rate, min_chunk_interval=min_chunk_interval)
    else:
        # Default to Twilio for backwards compatibility
        return TwilioAudioSender(
            websocket=websocket,
            stream_sid=stream_id,  # Twilio uses stream_sid
            sample_rate=sample_rate,
            min_chunk_interval=min_chunk_interval,
        )
