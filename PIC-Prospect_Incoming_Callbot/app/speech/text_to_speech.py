from abc import ABC, abstractmethod
import logging
import os
import io
from pydub import AudioSegment
from speech.text_to_speech_openai import TTS_OpenAI

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

        
    def convert_to_PCM_UTF_8_bytes(self, mp3_bytes: bytes) -> bytes:
        if not mp3_bytes:
            self.logger.warning("No MP3 bytes provided to convert")
            return b""
        
        try:
            # Load MP3 from bytes
            audio = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
            
            # Convert to the format Twilio expects:
            # - 8kHz sample rate (required by Twilio Voice)
            # - Mono channel
            # - 16-bit signed PCM (little-endian)
            audio = audio.set_frame_rate(self.frame_rate).set_channels(self.channels).set_sample_width(self.sample_width)
            
            # Export as raw PCM bytes without any ffmpeg parameters
            # This automatically uses the configured format (8kHz, mono, 16-bit)
            buffer = io.BytesIO()
            audio.export(buffer, format="raw")
            
            # Get the raw PCM bytes
            buffer.seek(0)
            pcm_bytes = buffer.read()
            
            # Verify we got valid PCM data
            if len(pcm_bytes) == 0:
                self.logger.error("PCM conversion produced empty bytes")
                return b""
                
            self.logger.debug(f"Successfully converted {len(mp3_bytes)} bytes of MP3 to {len(pcm_bytes)} bytes of PCM")
            return pcm_bytes
            
        except Exception as e:
            self.logger.error(f"Error converting MP3 to PCM: {e}")
            # Return empty bytes on error
            return b""

    def convert_to_PCM_UTF_8_bytes_new(self, audio_bytes: bytes) -> bytes:
        if not audio_bytes:
            self.logger.warning("No audio bytes provided to convert")
            return b""
            
        try:
            # Load MP3 from bytes
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            # audio = AudioSegment.from_raw(io.BytesIO(audio_bytes), sample_width=2, frame_rate=24000, channels=1)
            # audio = audio.set_frame_rate(self.frame_rate).set_channels(self.channels).set_sample_width(self.sample_width)
            
            buffer = io.BytesIO()
            audio.export(buffer, format="raw")
            
            # Get the raw PCM bytes
            buffer.seek(0)
            pcm_bytes = buffer.read()
            return pcm_bytes
            
        except Exception as e:
            self.logger.error(f"Error converting MP3 to PCM: {e}")
            # Return empty bytes on error
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

class OpenAITTSProvider(TextToSpeechProvider):
    def __init__(self, temp_dir: str, frame_rate: int = 8000, channels: int = 1, sample_width: int = 2):
        from openai import OpenAI
        self.logger = logging.getLogger(__name__)
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.temp_dir = temp_dir
        self.frame_rate = frame_rate
        self.channels = channels
        self.sample_width = sample_width

    def synthesize_speech_to_bytes(self, text: str) -> bytes:
        try:            
            resp: any = self.client.audio.speech.create(
                model="tts-1",
                voice="nova",  # Better for french: fable, nova, shimmer
                # All OpenAI TTS voices: alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer
                input=text,
                #instructions="Parle d'une voix calme, positive, avec une diction rapide et claire",
                speed=1.0
            )
            audio_bytes = resp.read()
            return self.convert_to_PCM_UTF_8_bytes(audio_bytes)

        except Exception as openai_error:
            self.logger.error(f"OpenAI TTS failed: {openai_error}.", exc_info=True)
            return b""

def get_text_to_speech_provider(temp_dir: str, provider_name: str = "openai", frame_rate: int = 8000, channels: int = 1, sample_width: int = 2) -> TextToSpeechProvider:
    if provider_name.lower() == "google": return GoogleTTSProvider(temp_dir, frame_rate=frame_rate, channels=channels, sample_width=sample_width)
    if provider_name.lower() == "openai": return OpenAITTSProvider(temp_dir, frame_rate=frame_rate, channels=channels, sample_width=sample_width)
    raise ValueError(f"Invalid TTS provider: {provider_name}")
