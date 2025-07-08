from abc import ABC, abstractmethod
import logging
import audioop
from utils.envvar import EnvHelper

class TextToSpeechProvider(ABC):
    client: any = None
    logger: logging.Logger = None
    temp_dir: str = None
    frame_rate: int = None # default: 8kHz sample rate (required by Twilio Voice)
    channels: int = None # default: 1 = Mono channel
    sample_width: int = None # default: 2 (x bytes = x*8 bits per sample) = 16-bit signed PCM (little-endian)
    
    @abstractmethod
    def synthesize_speech_to_bytes(self, text: str) -> bytes:
        """Speech-to-text using specified the provider, and return it as bytes"""
        pass

    def convert_to_PCM_UTF_with_frame_rate(self, audio_bytes: bytes, frame_rate: int) -> bytes:
        if not audio_bytes:
            self.logger.warning("No audio bytes provided to convert")
            return b""

        if frame_rate == self.frame_rate:
            return audio_bytes
        
        try:
            # Use audioop to resample.
            converted_audio, _ = audioop.ratecv(audio_bytes, self.sample_width, self.channels, frame_rate, self.frame_rate, None)
            self.logger.debug(f"Successfully resampled audio from {frame_rate}Hz to {self.frame_rate}Hz")
            return converted_audio
        except audioop.error as e:
            self.logger.error(f"Error resampling audio with audioop: {e}", exc_info=True)
            return b""


class GoogleTTSProvider(TextToSpeechProvider):
    def __init__(self, temp_dir: str, frame_rate: int = 8000, channels: int = 1, sample_width: int = 2):
        from google.cloud import texttospeech as google_tts
        self.google_tts = google_tts
        self.logger = logging.getLogger(__name__)
        self.client = self.google_tts.TextToSpeechClient()
        self.temp_dir = temp_dir
        self.frame_rate = frame_rate
        self.channels = channels
        self.sample_width = sample_width

    def synthesize_speech_to_bytes(self, text: str) -> bytes:
        try:
            synthesis_input = self.google_tts.SynthesisInput(text=text)
            voice = self.google_tts.VoiceSelectionParams(language_code="fr-FR", ssml_gender=self.google_tts.SsmlVoiceGender.FEMALE)
            audio_config = self.google_tts.AudioConfig(
                audio_encoding=self.google_tts.AudioEncoding.LINEAR16,
                sample_rate_hertz=self.frame_rate
            )

            response = self.client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
            return response.audio_content

        except Exception as google_error:
            self.logger.error(f"Google TTS failed: {google_error}.", exc_info=True)
            return b""

class OpenAITTSProvider(TextToSpeechProvider):
    def __init__(self, temp_dir: str, frame_rate: int = 8000, channels: int = 1, sample_width: int = 2, openai_api_key: str = None):
        from openai import OpenAI
        self.logger = logging.getLogger(__name__)
        api_key = openai_api_key if openai_api_key else EnvHelper.get_openai_api_key()
        self.client = OpenAI(api_key=api_key)
        self.temp_dir = temp_dir
        self.frame_rate = frame_rate
        self.channels = channels
        self.sample_width = sample_width

    def synthesize_speech_to_bytes(self, text: str) -> bytes:
        try:            
            resp: any = self.client.audio.speech.create(
                model="tts-1-hd",
                response_format="pcm",
                voice="nova",  # Better for french: fable, nova, shimmer
                # All OpenAI TTS voices: alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer
                input=text,
                #instructions="Parle d'une voix calme, positive, avec une diction rapide et claire",
                speed=1.0
            )
            audio_bytes = resp.read()
            return self.convert_to_PCM_UTF_with_frame_rate(audio_bytes, frame_rate=24000)

        except Exception as openai_error:
            self.logger.error(f"OpenAI TTS failed: {openai_error}.", exc_info=True)
            return b""

def get_text_to_speech_provider(temp_dir: str, provider_name: str = "openai", frame_rate: int = 8000, channels: int = 1, sample_width: int = 2) -> TextToSpeechProvider:
    if provider_name.lower() == "google": return GoogleTTSProvider(temp_dir, frame_rate=frame_rate, channels=channels, sample_width=sample_width)
    if provider_name.lower() == "openai": return OpenAITTSProvider(temp_dir, frame_rate=frame_rate, channels=channels, sample_width=sample_width)
    raise ValueError(f"Invalid TTS provider: {provider_name}")
