from abc import ABC, abstractmethod
import logging
import os
import uuid

class TextToSpeechProvider(ABC):
    client: any = None
    logger: logging.Logger = None
    temp_dir: str = None
    
    @abstractmethod
    def synthesize_speech_to_file(self, text: str) -> str:
        """Speech-to-text using specified the provider, and save it to the outputed file in temp directory"""
        pass

    @abstractmethod
    def synthesize_speech_to_bytes(self, text: str) -> bytes:
        """Speech-to-text using specified the provider, and return it as bytes"""
        pass

    def save_raw_audio_stream(self, raw_audio_data: bytes):
        # Sauvegarder le fichier MP3 temporairement
        filename = f"{uuid.uuid4()}.mp3"
        filepath = os.path.join(self.temp_dir, filename)
        # Sauvegarder le fichier audio (MP3)
        with open(filepath, "wb") as out:
            out.write(raw_audio_data)
        return filepath

class GoogleTTSProvider(TextToSpeechProvider):
    def __init__(self, temp_dir: str):
        from google.cloud import texttospeech as google_tts
        self.google_tts = google_tts
        self.logger = logging.getLogger(__name__)
        self.client = self.google_tts.TextToSpeechClient()
        self.temp_dir = temp_dir

    def synthesize_speech_to_file(self, text: str) -> str:
        """Synthesize speech using Google Cloud Text-to-Speech API."""
        audio_bytes = self.synthesize_speech_to_bytes(text)
        return self.save_raw_audio_stream(audio_bytes)
    
    def synthesize_speech_to_bytes(self, text: str) -> bytes:
        try:
            synthesis_input = self.google_tts.SynthesisInput(text=text)
            voice = self.google_tts.VoiceSelectionParams(language_code="fr-FR", ssml_gender=self.google_tts.SsmlVoiceGender.FEMALE)
            audio_config = self.google_tts.AudioConfig(audio_encoding=self.google_tts.AudioEncoding.MP3)

            response = self.client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
            return response.audio_content

        except Exception as google_error:
            self.logger.error(f"Google TTS failed: {google_error}.", exc_info=True)
            return b""
            

class OpenAITTSProvider(TextToSpeechProvider):
    def __init__(self, temp_dir: str):
        from openai import OpenAI
        self.logger = logging.getLogger(__name__)
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.temp_dir = temp_dir

    def synthesize_speech_to_file(self, text: str) -> str:
        audio_bytes = self.synthesize_speech_to_bytes(text)
        return self.save_raw_audio_stream(audio_bytes)

    def synthesize_speech_to_bytes(self, text: str) -> bytes:
        try:            
            resp: any = self.client.audio.speech.create(
                model="tts-1",
                voice="nova",  # Better for french: fable, nova, shimmer, onyx
                # All OpenAI TTS voices: alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer
                input=text
            )
            audio_bytes = resp.read()
            return audio_bytes

        except Exception as openai_error:
            self.logger.error(f"OpenAI TTS failed: {openai_error}.", exc_info=True)
            return b""

def get_text_to_speech_provider(temp_dir: str, provider: str = "openai") -> TextToSpeechProvider:
    if provider == "google": return GoogleTTSProvider(temp_dir)
    if provider == "openai": return OpenAITTSProvider(temp_dir)
    raise ValueError(f"Invalid TTS provider: {provider}")
