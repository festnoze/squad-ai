from abc import ABC, abstractmethod
import logging
import os

class SpeechToTextProvider(ABC):
    client: any = None
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
        self.client = self.speech.SpeechClient()
        self.temp_dir = temp_dir

    def transcribe_audio(self, file_name: str, language_code: str = "fr-FR") -> str:
        """Transcribe audio file using Google Cloud Speech-to-Text API."""
        try:
            with open(os.path.join(self.temp_dir, file_name), "rb") as audio_file:
                content = audio_file.read()

            audio = self.speech.RecognitionAudio(content=content)
            config = self.speech.RecognitionConfig(
                encoding=self.speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=8000,
                language_code=language_code,
            )

            response = self.client.recognize(config=config, audio=audio)

            transcript = ""
            for result in response.results:
                transcript += result.alternatives[0].transcript

            return transcript
        except Exception as e:
            self.logger.error(f"Error transcribing audio with Google: {e}", exc_info=True)
            return ""

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
        try:
            if not self.openai_client:
                raise ValueError("OpenAI client not initialized - missing API key")
                
            with open(os.path.join(self.temp_dir, file_name), "rb") as audio_file:
                response = self.openai_client.audio.transcriptions.create(
                    model="gpt-4o-transcribe",
                    file=audio_file,
                    language="fr"
                )
            return response.text
        except Exception as e:
            self.logger.error(f"Error transcribing audio with OpenAI model: {e}", exc_info=True)
            return ""

class HybridSTTProvider(SpeechToTextProvider):
    def __init__(self, temp_dir: str):
        from google.cloud import speech
        from openai import OpenAI
        
        self.speech = speech
        self.logger = logging.getLogger(__name__)
        self.speech_client = self.speech.SpeechClient()
        self.temp_dir = temp_dir
        
        if self.openai_api_key:
            self.openai_client = OpenAI(api_key=self.openai_api_key)
        else:
            self.openai_client = None
            self.logger.warning("OPENAI_API_KEY not set, OpenAI transcription will not be available.")

    def transcribe_audio(self, file_name: str, language_code: str = "fr-FR") -> str:
        """Transcribe audio file using Google Cloud Speech-to-Text API."""
        try:
            # First try with OpenAI Whisper if available
            if self.openai_api_key and self.openai_client:
                try:
                    with open(os.path.join(self.temp_dir, file_name), "rb") as audio_file:
                        response = self.openai_client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="fr"
                        )
                        return response.text
                except Exception as whisper_err:
                    self.logger.warning(f"Error with Whisper transcription, falling back to Google: {whisper_err}")
            
            # Fallback to Google Speech-to-Text
            with open(os.path.join(self.temp_dir, file_name), "rb") as audio_file:
                content = audio_file.read()

            audio = self.speech.RecognitionAudio(content=content)
            config = self.speech.RecognitionConfig(
                encoding=self.speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=8000,
                language_code=language_code,
            )

            response = self.speech_client.recognize(config=config, audio=audio)

            transcript = ""
            for result in response.results:
                transcript += result.alternatives[0].transcript

            return transcript
        except Exception as e:
            self.logger.error(f"Error transcribing audio: {e}", exc_info=True)
            return ""

def get_speech_to_text_provider(temp_dir: str, provider_name: str = "openai") -> SpeechToTextProvider:
    """Factory function to get the appropriate speech-to-text provider"""
    if provider_name == "google": return GoogleSTTProvider(temp_dir)
    if provider_name == "openai": return OpenAISTTProvider(temp_dir)
    #if provider_name == "hybrid": return HybridSTTProvider(temp_dir)
    raise ValueError(f"Invalid STT provider: {provider_name}")