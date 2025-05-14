from abc import ABC, abstractmethod
import logging
import os

class SpeechToTextProvider(ABC):
    google_client: any = None
    logger: logging.Logger = None
    openai_api_key: str = os.getenv("OPENAI_API_KEY")
    temp_dir: str = ""
    
    @abstractmethod
    def transcribe_audio(self, file_name: str, language_code: str = "fr-FR") -> str:
        """Transcribe audio file to text using the specified provider"""
        pass

class GoogleSTTProvider(SpeechToTextProvider):
    def __init__(self, temp_dir: str):
        from google.cloud import speech
        self.speech = speech
        self.logger = logging.getLogger(__name__)
        self.google_client = self.speech.SpeechClient()
        self.temp_dir = temp_dir

    def transcribe_audio(self, file_name: str, language_code: str = "fr-FR") -> str:
        """Transcribe audio file using Google STT API."""
        try:
            return GoogleSTTProvider.transcribe_audio_static(self.temp_dir, self.speech, self.google_client, file_name, language_code)
        except Exception as e:
            self.logger.error(f"Error transcribing audio with Google: {e}", exc_info=True)
            return ""
    
    @staticmethod
    def transcribe_audio_static(temp_dir: str, speech, client, file_name: str, language_code: str = "fr-FR") -> str:
        """Transcribe audio file using Google Cloud Speech-to-Text API."""
        
        with open(os.path.join(temp_dir, file_name), "rb") as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=8000,
            language_code=language_code,
        )

        response = client.recognize(config=config, audio=audio)

        transcript = ""
        for result in response.results:
            transcript += result.alternatives[0].transcript

        return transcript

class OpenAISTTProvider(SpeechToTextProvider):
    def __init__(self, temp_dir: str):
        from openai import OpenAI
        self.logger = logging.getLogger(__name__)
        self.temp_dir = temp_dir
        if self.openai_api_key:
            self.openai_client = OpenAI(api_key=self.openai_api_key)
        else:
            self.openai_client = None
            self.logger.warning("OPENAI_API_KEY not set, OpenAI transcription will not be available.")

    def transcribe_audio(self, file_name: str, language_code: str = "fr-FR") -> str:
        """Transcribe audio file using OpenAI STT API."""
        return OpenAISTTProvider.transcribe_audio_static(self.openai_client, self.temp_dir, file_name, language_code, self.logger)
    
    @staticmethod
    def transcribe_audio_static(openai_client, temp_dir: str, file_name: str, language_code: str = "fr-FR", logger=None) -> str:
        """Transcribe audio file using OpenAI STT API."""
        try:
            if not openai_client:
                raise ValueError("OpenAI client not initialized - missing API key")
            with open(os.path.join(temp_dir, file_name), "rb") as audio_file:
                response = openai_client.audio.transcriptions.create(
                    model="gpt-4o-transcribe",
                    file=audio_file,
                    language=language_code.split('-')[0] if language_code else "fr"
                )
            return response.text
        except Exception as e:
            if logger:
                logger.error(f"Error transcribing audio with OpenAI model: {e}", exc_info=True)
            return ""

class HybridSTTProvider(SpeechToTextProvider):
    def __init__(self, temp_dir: str):
        from google.cloud import speech
        from openai import OpenAI
        self.google_speech = speech
        self.logger = logging.getLogger(__name__)
        self.temp_dir = temp_dir
        self.google_client = self.google_speech.SpeechClient()
        self.openai_client = None
        if not self.openai_api_key:
            self.logger.warning("OPENAI_API_KEY not set, OpenAI transcription will not be available.")
        else:
            self.openai_client = OpenAI(api_key=self.openai_api_key)

    def transcribe_audio(self, file_name: str, language_code: str = "fr-FR") -> str:
        return HybridSTTProvider.transcribe_audio_static(self.openai_client, self.google_speech, self.google_client, self.temp_dir, file_name, language_code, self.logger)
    
    @staticmethod
    def transcribe_audio_static(openai_client, speech, client, temp_dir: str, file_name: str, language_code: str = "fr-FR", logger=None) -> str:
        """Transcribe audio file using OpenAI STT API, fallback to Google Cloud Speech-to-Text API."""
        try:
            # Try Google transcription first
            transcript = GoogleSTTProvider.transcribe_audio_static(temp_dir, speech, client, file_name, language_code, logger)
            if transcript:
                return transcript

            # Fallback to OpenAI transcription
            if openai_client:
                transcript = OpenAISTTProvider.transcribe_audio_static(openai_client, speech, client, temp_dir, file_name, language_code, logger)
                return transcript

            return ""
        except Exception as e:
            if logger:
                logger.error(f"Error transcribing audio with HybridSTTProvider: {e}", exc_info=True)
            return ""

def get_speech_to_text_provider(temp_dir: str, provider: str = "openai") -> SpeechToTextProvider:
    """Factory function to get the appropriate speech-to-text provider"""
    if provider == "hybrid": return HybridSTTProvider(temp_dir)
    if provider == "google": return GoogleSTTProvider(temp_dir)
    if provider == "openai": return OpenAISTTProvider(temp_dir)
    raise ValueError(f"Invalid STT provider: {provider}")