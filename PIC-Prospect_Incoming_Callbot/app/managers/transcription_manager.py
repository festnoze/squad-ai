import base64
import logging

from speech.speech_to_text import SpeechToTextProvider, get_speech_to_text_provider

logger = logging.getLogger(__name__)


class TranscriptionManager:
    """Manages the transcription of inbound and outbound audio streams."""

    def __init__(self, stt_provider_name: str = "openai", frame_rate: int = 8000, language_code: str = "fr-FR"):
        """Initializes the TranscriptionManager with separate STT providers for each track."""
        logger.info("Initializing TranscriptionManager...")
        # Assumption: SpeechToText can be instantiated without arguments or with necessary config.
        self.inbound_stt: SpeechToTextProvider = get_speech_to_text_provider(
            provider_name=stt_provider_name, language_code=language_code, frame_rate=frame_rate
        )
        self.outbound_stt: SpeechToTextProvider = get_speech_to_text_provider(
            provider_name=stt_provider_name, language_code=language_code, frame_rate=frame_rate
        )
        logger.info("TranscriptionManager initialized with separate STT handlers for inbound and outbound tracks.")

    async def process_media_event_async(self, media_data: dict) -> None:
        """Processes a 'media' event from Twilio, routing it to the correct STT handler."""
        try:
            track = media_data.get("media", {}).get("track")
            payload = media_data.get("media", {}).get("payload")

            if not track or not payload:
                logger.warning("Received media event with missing track or payload.")
                return

            audio_chunk = base64.b64decode(payload)

            if track == "inbound":
                transcription = await self.inbound_stt.transcribe_audio_chunk_async(audio_chunk)
                if transcription:
                    logger.info(f"[TRANSCRIPTION - INBOUND]: {transcription}")
            elif track == "outbound":
                transcription = await self.outbound_stt.transcribe_audio_chunk_async(audio_chunk)
                if transcription:
                    logger.info(f"[TRANSCRIPTION - OUTBOUND]: {transcription}")
        except Exception as e:
            logger.error(f"Error processing media event in TranscriptionManager: {e}", exc_info=True)
