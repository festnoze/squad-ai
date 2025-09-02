import audioop
import logging
from abc import ABC, abstractmethod

from speech.text_to_speech_openai import TTS_OpenAI
from utils.envvar import EnvHelper
from utils.latency_decorator import measure_latency
from utils.latency_metric import OperationType


class TextToSpeechProvider(ABC):
    client: any = None
    logger: logging.Logger = None
    frame_rate: int = None  # default: 8kHz sample rate (required by Twilio Voice)
    channels: int = None  # default: 1 = Mono channel
    sample_width: int = None  # default: 2 (x bytes = x*8 bits per sample) = 16-bit signed PCM (little-endian)
    temp_dir: str = None

    @abstractmethod
    @measure_latency(OperationType.TTS)
    async def synthesize_speech_to_bytes_async(self, text: str) -> bytes:
        """Speech-to-text using specified the provider, and return it as bytes"""
        pass

    def convert_PCM_frame_rate_w_audioop(self, audio_bytes: bytes, from_frame_rate: int, to_frame_rate: int) -> bytes:
        if not audio_bytes:
            self.logger.warning("No audio bytes provided to convert")
            return b""

        audio_bytes = self.strip_wav_header(audio_bytes)

        if from_frame_rate == to_frame_rate:
            return audio_bytes

        try:
            # Use audioop to resample.
            converted_audio, _ = audioop.ratecv(
                audio_bytes, self.sample_width, self.channels, from_frame_rate, to_frame_rate, None
            )
            self.logger.debug(f"Successfully resampled audio from {from_frame_rate}Hz to {to_frame_rate}Hz")
            return converted_audio
        except audioop.error as e:
            self.logger.error(f"Error resampling audio with audioop: {e}", exc_info=True)
            return b""

    def strip_wav_header(self, audio_bytes: bytes) -> bytes:
        if audio_bytes[:4] == b"RIFF":
            return audio_bytes[44:]
        else:
            return audio_bytes


class GoogleTTSProvider(TextToSpeechProvider):
    def __init__(
        self, frame_rate: int = 8000, channels: int = 1, sample_width: int = 2, temp_dir: str = "static/outgoing_audio"
    ):
        from google.cloud import texttospeech as google_tts

        self.google_tts = google_tts
        self.logger = logging.getLogger(__name__)
        self.client = self.google_tts.TextToSpeechClient()
        self.frame_rate = frame_rate
        self.channels = channels
        self.sample_width = sample_width
        self.temp_dir = temp_dir
        self.voice = EnvHelper.get_text_to_speech_voice() or "fr-FR-Chirp3-HD-Charon"
        self.voice_params = self.google_tts.VoiceSelectionParams(
            language_code="fr-FR", ssml_gender=self.google_tts.SsmlVoiceGender.FEMALE, name=self.voice
        )
        self.audio_config = self.google_tts.AudioConfig(
            audio_encoding=self.google_tts.AudioEncoding.LINEAR16, sample_rate_hertz=16000
        )

    @measure_latency(OperationType.TTS, provider="google")
    async def synthesize_speech_to_bytes_async(self, text: str) -> bytes:
        try:
            synthesis_input = self.google_tts.SynthesisInput(text=text)
            response = self.client.synthesize_speech(
                input=synthesis_input, voice=self.voice_params, audio_config=self.audio_config
            )
            audio_bytes = response.audio_content
            return self.convert_PCM_frame_rate_w_audioop(
                audio_bytes, from_frame_rate=16000, to_frame_rate=self.frame_rate
            )

        except Exception as google_error:
            self.logger.error(f"Google TTS failed: {google_error}.", exc_info=True)
            return b""


class OpenAITTSProvider(TextToSpeechProvider):
    def __init__(
        self,
        frame_rate: int = 8000,
        channels: int = 1,
        sample_width: int = 2,
        temp_dir: str = "static/outgoing_audio",
        openai_api_key: str = None,
    ):
        from openai import OpenAI

        self.logger = logging.getLogger(__name__)
        api_key = openai_api_key if openai_api_key else EnvHelper.get_openai_api_key()
        self.client = OpenAI(api_key=api_key)
        self.frame_rate = frame_rate
        self.channels = channels
        self.sample_width = sample_width
        self.temp_dir = temp_dir
        self.voice = EnvHelper.get_text_to_speech_voice() or "nova"
        self.instructions = (
            EnvHelper.get_text_to_speech_instructions()
            or "Parle d'une voix calme mais positive, avec une diction rapide mais claire"
        )
        self.model = EnvHelper.get_text_to_speech_model() or "tts-1"

    @measure_latency(OperationType.TTS, provider="openai")
    async def synthesize_speech_to_bytes_async(self, text: str) -> bytes:
        try:
            audio_bytes = await TTS_OpenAI.generate_speech_async(
                model=self.model,
                response_format="pcm",
                voice=self.voice,
                text=text,
                instructions=self.instructions,
                speed=1.0,
            )
            return self.convert_PCM_frame_rate_w_audioop(
                audio_bytes, from_frame_rate=24000, to_frame_rate=self.frame_rate
            )

        except Exception as openai_error:
            self.logger.error(f"OpenAI TTS failed: {openai_error}.", exc_info=True)
            return b""


def get_text_to_speech_provider(
    provider_name: str = "openai",
    frame_rate: int = 8000,
    channels: int = 1,
    sample_width: int = 2,
    temp_dir: str = "static/outgoing_audio",
) -> TextToSpeechProvider:
    if provider_name.lower() == "google":
        return GoogleTTSProvider(frame_rate=frame_rate, channels=channels, sample_width=sample_width, temp_dir=temp_dir)
    if provider_name.lower() == "openai":
        return OpenAITTSProvider(frame_rate=frame_rate, channels=channels, sample_width=sample_width, temp_dir=temp_dir)
    raise ValueError(f"Invalid TTS provider: {provider_name}")
