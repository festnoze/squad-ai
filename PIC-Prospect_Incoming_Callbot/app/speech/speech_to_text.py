import logging
import os
from abc import ABC, abstractmethod

from openai import AsyncOpenAI
from utils.envvar import EnvHelper
from utils.latency_decorator import measure_latency
from utils.latency_metric import OperationType


class SpeechToTextProvider(ABC):
    google_client: any = None
    logger: logging.Logger = None
    temp_dir: str = ""
    language_code: str = "fr-FR"
    frame_rate: int = 8000

    @abstractmethod
    @measure_latency(OperationType.STT)
    async def transcribe_audio_async(self, file_name: str, call_sid: str = None, stream_sid: str = None, phone_number: str = None) -> str:
        """Transcribe audio file to text using the specified provider"""
        pass


class GoogleSTTProvider(SpeechToTextProvider):
    def __init__(self, language_code: str = "fr-FR", frame_rate: int = 8000, temp_dir: str = "static/incoming_audio"):
        from google.cloud import speech

        self.speech = speech
        self.logger = logging.getLogger(__name__)
        self.google_client = self.speech.SpeechClient()
        self.language_code = language_code
        self.frame_rate = frame_rate
        self.temp_dir = temp_dir

    @measure_latency(OperationType.STT, provider="google")
    async def transcribe_audio_async(self, file_name: str, call_sid: str = None, stream_sid: str = None, phone_number: str = None) -> str:
        """Transcribe audio file using Google STT API."""
        try:
            return GoogleSTTProvider.transcribe_audio_static(self.temp_dir, self.speech, self.google_client, file_name, self.language_code, self.frame_rate)
        except Exception as e:
            self.logger.error(f"Error transcribing audio with Google: {e}", exc_info=True)
            return ""

    @staticmethod
    def transcribe_audio_static(temp_dir: str, speech: any, client: any, file_name: str, language_code: str, frame_rate: int) -> str:
        """Transcribe audio file using Google Cloud Speech-to-Text API."""

        with open(os.path.join(temp_dir, file_name), "rb") as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=frame_rate,
            language_code=language_code,
            use_enhanced=True,
            model="phone_call",  # Specialized model for phone audio
        )

        response = client.recognize(config=config, audio=audio)

        transcript = ""
        for result in response.results:
            transcript += result.alternatives[0].transcript

        return transcript


class OpenAISTTProvider(SpeechToTextProvider):
    def __init__(self, language_code: str = "fr-FR", frame_rate: int = 8000, temp_dir: str = "static/incoming_audio"):
        from openai import AsyncOpenAI

        self.logger = logging.getLogger(__name__)
        self.language_code = language_code
        self.frame_rate = frame_rate
        self.temp_dir = temp_dir
        self.openai_client = AsyncOpenAI(api_key=EnvHelper.get_openai_api_key())

    @measure_latency(OperationType.STT, provider="openai")
    async def transcribe_audio_async(self, file_name: str, call_sid: str | None = None, stream_sid: str | None = None, phone_number: str | None = None) -> str:
        """Transcribe audio file using OpenAI STT API."""
        try:
            return await OpenAISTTProvider.transcribe_audio_static_async(self.openai_client, self.temp_dir, file_name, self.language_code, self.frame_rate)
        except Exception as e:
            self.logger.error(f"Error transcribing audio with OpenAI: {e}", exc_info=True)
            return ""

    @staticmethod
    async def transcribe_audio_static_async(openai_client: AsyncOpenAI, temp_dir: str, file_name: str, language_code: str, frame_rate: int) -> str:
        """Transcribe audio file using OpenAI STT API."""
        if not openai_client:
            raise ValueError("OpenAI client not initialized - missing API key")
        with open(os.path.join(temp_dir, file_name), "rb") as audio_file:
            response = await openai_client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=audio_file,
                language=language_code.split("-")[0] if language_code else "fr",
            )
        return response.text


class HybridSTTProvider(SpeechToTextProvider):
    def __init__(self, language_code: str = "fr-FR", frame_rate: int = 8000, temp_dir: str = "static/incoming_audio"):
        from google.cloud import speech
        from openai import OpenAI

        self.google_speech = speech
        self.logger = logging.getLogger(__name__)
        self.google_client = self.google_speech.SpeechClient()
        self.openai_client = OpenAI(api_key=EnvHelper.get_openai_api_key())
        self.language_code = language_code
        self.frame_rate = frame_rate
        self.temp_dir = temp_dir

    @measure_latency(OperationType.STT, provider="hybrid")
    async def transcribe_audio_async(self, file_name: str, call_sid: str | None = None, stream_sid: str | None = None, phone_number: str | None = None) -> str:
        try:
            return await HybridSTTProvider.transcribe_audio_static_async(
                self.openai_client,
                self.google_speech,
                self.google_client,
                self.temp_dir,
                file_name,
                self.language_code,
                self.frame_rate,
            )
        except Exception as e:
            self.logger.error(f"Error transcribing audio with HybridSTTProvider: {e}", exc_info=True)
            return ""

    @staticmethod
    async def transcribe_audio_static_async(openai_client: AsyncOpenAI, speech: any, client: any, temp_dir: str, file_name: str, language_code: str, frame_rate: int) -> str:
        """Transcribe audio file using OpenAI STT API, fallback to Google Cloud Speech-to-Text API."""
        # Try Google transcription first
        transcript = GoogleSTTProvider.transcribe_audio_static(temp_dir, speech, client, file_name, language_code, frame_rate)
        if transcript:
            return transcript

        # Fallback to OpenAI transcription
        if openai_client:
            transcript = await OpenAISTTProvider.transcribe_audio_static_async(openai_client, temp_dir, file_name, language_code, frame_rate)
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
    provider_name: str = "openai",
    language_code: str = "fr-FR",
    frame_rate: int = 8000,
    temp_dir: str = "static/incoming_audio",
) -> SpeechToTextProvider:
    """Factory function to get the appropriate speech-to-text provider"""
    if provider_name.lower() == "hybrid":
        return HybridSTTProvider(language_code=language_code, frame_rate=frame_rate, temp_dir=temp_dir)
    if provider_name.lower() == "google":
        return GoogleSTTProvider(language_code=language_code, frame_rate=frame_rate, temp_dir=temp_dir)
    if provider_name.lower() == "openai":
        return OpenAISTTProvider(language_code=language_code, frame_rate=frame_rate, temp_dir=temp_dir)
    raise ValueError(f"Invalid STT provider: {provider_name}")
