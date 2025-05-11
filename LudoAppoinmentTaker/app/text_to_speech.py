from abc import ABC, abstractmethod
import logging
import os

class TextToSpeechProvider(ABC):
    client: any = None
    logger: logging.Logger = None
    
    @abstractmethod
    def synthesize_speech(self, text: str, language_code: str = "fr-FR") -> bytes:
        pass

class GoogleTTSProvider(TextToSpeechProvider):
    def __init__(self):
        from google.cloud import texttospeech as google_tts
        self.google_tts = google_tts
        self.logger = logging.getLogger(__name__)
        self.client = self.google_tts.TextToSpeechClient()

    def synthesize_speech(self, text: str, language_code: str = "fr-FR") -> bytes:
        """Synthesize speech using Google Cloud Text-to-Speech API."""
        try:
            synthesis_input = self.google_tts.SynthesisInput(text=text)
            voice = self.google_tts.VoiceSelectionParams(language_code=language_code, ssml_gender=self.google_tts.SsmlVoiceGender.FEMALE)
            audio_config = self.google_tts.AudioConfig(audio_encoding=self.google_tts.AudioEncoding.MP3)

            response = self.client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
            return response.audio_content

        except Exception as google_error:
            self.logger.error(f"Google TTS failed: {google_error}.", exc_info=True)
            return b""
            

class OpenAITTSProvider(TextToSpeechProvider):
    def __init__(self):
        from openai import OpenAI
        self.logger = logging.getLogger(__name__)
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def synthesize_speech(self, text: str, language_code: str = "fr-FR") -> bytes:
        try:
            resp: any = self.client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text,
            )
            audio_bytes = resp.read()
            return audio_bytes

        except Exception as openai_error:
            self.logger.error(f"OpenAI TTS failed: {openai_error}.", exc_info=True)
            return b""

def get_text_to_speech_provider(provider_name: str = "openai") -> TextToSpeechProvider:
    if provider_name == "google": return GoogleTTSProvider()
    if provider_name == "openai": return OpenAITTSProvider()
    raise ValueError(f"Invalid TTS provider: {provider_name}")
