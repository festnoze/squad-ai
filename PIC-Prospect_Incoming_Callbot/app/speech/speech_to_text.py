import logging
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any
from uuid import UUID

from google.api_core.exceptions import PermissionDenied
from openai import AsyncOpenAI
from utils.envvar import EnvHelper
from utils.latency_decorator import measure_latency
from utils.latency_metric import OperationType

if TYPE_CHECKING:
    from api_client.conversation_persistence_interface import ConversationPersistenceInterface


class SpeechToTextProvider(ABC):
    google_client: any
    logger: logging.Logger
    temp_dir: str = ""
    language_code: str = "fr-FR"
    frame_rate: int = 8000
    conversation_persistence: "ConversationPersistenceInterface | None" = None

    @abstractmethod
    @measure_latency(OperationType.STT)
    async def transcribe_audio_async(
        self,
        file_name: str,
        call_sid: str | None = None,
        stream_sid: str | None = None,
        phone_number: str | None = None,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
    ) -> str:
        """Transcribe audio file to text using the specified provider"""
        pass


class GoogleSTTProvider(SpeechToTextProvider):
    def __init__(
        self,
        language_code: str = "fr-FR",
        frame_rate: int = 8000,
        temp_dir: str = "static/incoming_audio",
        conversation_persistence: "ConversationPersistenceInterface | None" = None,
    ):
        from google.cloud import speech
        self.speech = speech
        self.logger = logging.getLogger(__name__)
        self.google_async_client = self.speech.SpeechAsyncClient()
        self.language_code = language_code
        self.frame_rate = frame_rate
        self.temp_dir = temp_dir
        self.conversation_persistence = conversation_persistence

    @measure_latency(OperationType.STT, provider="google")
    async def transcribe_audio_async(
        self,
        file_name: str,
        call_sid: str | None = None,
        stream_sid: str | None = None,
        phone_number: str | None = None,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
    ) -> str:
        """Transcribe audio file using Google STT API."""
        try:
            return await GoogleSTTProvider.transcribe_audio_static_async(
                self.temp_dir, self.speech, self.google_async_client, file_name,
                self.language_code, self.frame_rate, self.conversation_persistence,
                call_sid, stream_sid, phone_number, conversation_id, message_id
            )
        except Exception as e:
            self.logger.error(f"Error transcribing audio with Google: {e}", exc_info=True)
            return e.message if isinstance(e, PermissionDenied) else ""

    @staticmethod
    async def transcribe_audio_static_async(
        temp_dir: str,
        speech: any,
        async_client: any,
        file_name: str,
        language_code: str,
        frame_rate: int,
        conversation_persistence: "ConversationPersistenceInterface | None" = None,
        call_sid: str | None = None,
        stream_sid: str | None = None,
        phone_number: str | None = None,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
    ) -> str:
        """Transcribe audio file using Google Cloud Speech-to-Text API asynchronously."""
        import os

        with open(os.path.join(temp_dir, file_name), "rb") as audio_file:
            content = audio_file.read()

        # Calculate audio duration and cost
        audio_duration_seconds = len(content) / (frame_rate * 2)  # 16-bit = 2 bytes per sample
        audio_duration_minutes = audio_duration_seconds / 60
        # Google STT pricing: $0.024 per minute for enhanced model
        price_per_minute = 0.024
        estimated_cost_usd = audio_duration_minutes * price_per_minute

        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=frame_rate,
            language_code=language_code,
            use_enhanced=True,
            model="phone_call",
        )

        # Use the native async recognize method
        response = await async_client.recognize(config=config, audio=audio)

        transcript = ""
        for result in response.results:
            transcript += result.alternatives[0].transcript

        # Log cost to database via conversation persistence
        if conversation_persistence:
            await conversation_persistence.add_llm_operation_async(
                operation_type_name="STT",
                provider="google",
                model="phone_call",
                tokens_or_duration=audio_duration_seconds,
                price_per_unit=price_per_minute / 60,  # Convert to price per second
                cost_usd=estimated_cost_usd,
                conversation_id=conversation_id,
                message_id=message_id,
                stream_id=stream_sid,
                call_sid=call_sid,
                phone_number=phone_number,
            )

        return transcript


class OpenAISTTProvider(SpeechToTextProvider):
    def __init__(
        self,
        language_code: str = "fr-FR",
        frame_rate: int = 8000,
        temp_dir: str = "static/incoming_audio",
        conversation_persistence: "ConversationPersistenceInterface | None" = None,
    ):
        self.logger = logging.getLogger(__name__)
        self.language_code = language_code
        self.frame_rate = frame_rate
        self.temp_dir = temp_dir
        self.conversation_persistence = conversation_persistence
        self.openai_client = AsyncOpenAI(api_key=EnvHelper.get_openai_api_key())

    @measure_latency(OperationType.STT, provider="openai")
    async def transcribe_audio_async(
        self,
        file_name: str,
        call_sid: str | None = None,
        stream_sid: str | None = None,
        phone_number: str | None = None,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
    ) -> str:
        """Transcribe audio file using OpenAI STT API."""
        try:
            return await OpenAISTTProvider.transcribe_audio_static_async(
                self.openai_client, self.temp_dir, file_name,
                self.language_code, self.frame_rate, self.conversation_persistence,
                call_sid, stream_sid, phone_number, conversation_id, message_id
            )
        except Exception as e:
            self.logger.error(f"Error transcribing audio with OpenAI: {e}", exc_info=True)
            return ""

    @staticmethod
    async def transcribe_audio_static_async(
        openai_client: AsyncOpenAI,
        temp_dir: str,
        file_name: str,
        language_code: str,
        frame_rate: int,
        conversation_persistence: "ConversationPersistenceInterface | None" = None,
        call_sid: str | None = None,
        stream_sid: str | None = None,
        phone_number: str | None = None,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
    ) -> str:
        """Transcribe audio file using OpenAI STT API."""
        if not openai_client:
            raise ValueError("OpenAI client not initialized - missing API key")

        # Get file size for cost estimation
        file_path = os.path.join(temp_dir, file_name)
        file_size_bytes = os.path.getsize(file_path)
        audio_duration_seconds = file_size_bytes / (frame_rate * 2)  # 16-bit = 2 bytes per sample
        audio_duration_minutes = audio_duration_seconds / 60
        # OpenAI GPT-4o-transcribe pricing: $0.006 per minute
        price_per_minute = 0.006
        estimated_cost_usd = audio_duration_minutes * price_per_minute

        with open(file_path, "rb") as audio_file:
            response = await openai_client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=audio_file,
                language=language_code.split("-")[0] if language_code else "fr",
            )

        # Log cost to database via conversation persistence
        if conversation_persistence:
            await conversation_persistence.add_llm_operation_async(
                operation_type_name="STT",
                provider="openai",
                model="gpt-4o-transcribe",
                tokens_or_duration=audio_duration_seconds,
                price_per_unit=price_per_minute / 60,  # Convert to price per second
                cost_usd=estimated_cost_usd,
                conversation_id=conversation_id,
                message_id=message_id,
                stream_id=stream_sid,
                call_sid=call_sid,
                phone_number=phone_number,
            )

        return response.text


class HybridSTTProvider(SpeechToTextProvider):
    def __init__(
        self,
        language_code: str = "fr-FR",
        frame_rate: int = 8000,
        temp_dir: str = "static/incoming_audio",
        conversation_persistence: "ConversationPersistenceInterface | None" = None,
    ):
        from google.cloud import speech
        self.google_speech = speech
        self.logger = logging.getLogger(__name__)
        self.google_async_client = self.google_speech.SpeechAsyncClient()
        self.openai_client = AsyncOpenAI(api_key=EnvHelper.get_openai_api_key())
        self.language_code = language_code
        self.frame_rate = frame_rate
        self.temp_dir = temp_dir
        self.conversation_persistence = conversation_persistence

    @measure_latency(OperationType.STT, provider="hybrid")
    async def transcribe_audio_async(
        self,
        file_name: str,
        call_sid: str | None = None,
        stream_sid: str | None = None,
        phone_number: str | None = None,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
    ) -> str:
        try:
            return await HybridSTTProvider.transcribe_audio_static_async(
                self.openai_client,
                self.google_speech,
                self.google_async_client,
                self.temp_dir,
                file_name,
                self.language_code,
                self.frame_rate,
                self.conversation_persistence,
                call_sid,
                stream_sid,
                phone_number,
                conversation_id,
                message_id,
            )
        except Exception as e:
            self.logger.error(f"Error transcribing audio with HybridSTTProvider: {e}", exc_info=True)
            return ""

    @staticmethod
    async def transcribe_audio_static_async(
        openai_client: AsyncOpenAI,
        speech: any,
        client: any,
        temp_dir: str,
        file_name: str,
        language_code: str,
        frame_rate: int,
        conversation_persistence: "ConversationPersistenceInterface | None" = None,
        call_sid: str | None = None,
        stream_sid: str | None = None,
        phone_number: str | None = None,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
    ) -> str:
        """Transcribe audio file using OpenAI STT API, fallback to Google Cloud Speech-to-Text API."""
        # Try Google transcription first
        transcript = await GoogleSTTProvider.transcribe_audio_static_async(
            temp_dir, speech, client, file_name, language_code, frame_rate,
            conversation_persistence, call_sid, stream_sid, phone_number, conversation_id, message_id
        )
        if transcript:
            return transcript

        # Fallback to OpenAI transcription
        if openai_client:
            transcript = await OpenAISTTProvider.transcribe_audio_static_async(
                openai_client, temp_dir, file_name, language_code, frame_rate,
                conversation_persistence, call_sid, stream_sid, phone_number, conversation_id, message_id
            )
            return transcript
        return ""

        # # Run both transcriptions in parallel
        # transcript_google = GoogleSTTProvider.transcribe_audio_static(temp_dir, speech, client, file_name, language_code, frame_rate)
        # transcript_openai = await OpenAISTTProvider.transcribe_audio_static_async(openai_client, temp_dir, file_name, language_code, frame_rate)

        # if len(transcript_google) == 0 or len(transcript_openai) == 0:
        #     return ""

        # if len(transcript_google) > len(transcript_openai):
        #     return transcript_google
        # return transcript_openai


def get_speech_to_text_provider(
    stt_provider_name: str = "openai",
    language_code: str = "fr-FR",
    frame_rate: int = 8000,
    temp_dir: str = "static/incoming_audio",
    conversation_persistence: "ConversationPersistenceInterface | None" = None,
) -> SpeechToTextProvider:
    """Factory function to get the appropriate speech-to-text provider"""
    if stt_provider_name.lower() == "hybrid":
        return HybridSTTProvider(
            language_code=language_code,
            frame_rate=frame_rate,
            temp_dir=temp_dir,
            conversation_persistence=conversation_persistence,
        )
    if stt_provider_name.lower() == "google":
        return GoogleSTTProvider(
            language_code=language_code,
            frame_rate=frame_rate,
            temp_dir=temp_dir,
            conversation_persistence=conversation_persistence,
        )
    if stt_provider_name.lower() == "openai":
        return OpenAISTTProvider(
            language_code=language_code,
            frame_rate=frame_rate,
            temp_dir=temp_dir,
            conversation_persistence=conversation_persistence,
        )
    raise ValueError(f"Invalid STT provider: {stt_provider_name}")
