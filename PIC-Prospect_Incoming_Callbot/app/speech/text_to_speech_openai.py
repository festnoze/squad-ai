from pathlib import Path
from typing import Literal
from openai import OpenAI
from pydub import AudioSegment
import io
import os

TTSModel        = Literal["gpt-4o-mini-tts", "gpt-4o-tts", "tts-1", "tts-1-hd"]
VoicePreset     = Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
ResponseFormat  = Literal["mp3", "opus", "aac", "flac", "wav", "pcm"]
OutputType      = Literal["stream", "file", "audio_bytes"]

class TTS_OpenAI:    
    openai_client: any = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    @staticmethod
    def generate_speech(
            model: TTSModel,
            text: str,
            voice: VoicePreset = "nova",
            instructions: str = "",
            speed: float = 1.0,
            response_format: ResponseFormat = "pcm",
            pcm_rate: int | None = None) -> bytes:
        resp: any = TTS_OpenAI.openai_client.audio.speech.create(
                model=model,
                input=text,
                voice=voice,
                instructions=instructions,
                speed=speed,
                response_format=response_format,
        )
        raw: bytes = resp.read()
        if response_format == "pcm" and pcm_rate and pcm_rate != 24000:
                audio = AudioSegment.from_raw(io.BytesIO(raw), sample_width=2, frame_rate=24000, channels=1)
                audio = audio.set_frame_rate(pcm_rate)
                buf = io.BytesIO()
                audio.export(buf, format="raw")
                raw = buf.getvalue()
        return raw
    
    @staticmethod
    def tts_playback(
            text: str,
            model: TTSModel = "tts-1",
            voice: VoicePreset = "nova",
            instructions: str = "Speak in a cheerful and positive tone.",
            speed: float = 1.0,
            response_format: ResponseFormat = "pcm",
            output_type: OutputType = "stream",
            output_path: Path = Path("speech.pcm")) -> any:
        import pyaudio
        if output_type == "stream":
                pa: any = pyaudio.PyAudio()
                stream_out: any = pa.open(format=pyaudio.paInt16, channels=1, rate=24_000, output=True)
                with TTS_OpenAI.openai_client.audio.speech.with_streaming_response.create(
                        model=model,
                        input=text,
                        voice=voice,
                        instructions=instructions,
                        speed=speed,
                        response_format="pcm",
                ) as resp:
                        for chunk in resp.iter_bytes():
                                stream_out.write(chunk)
                stream_out.stop_stream()
                stream_out.close()
                pa.terminate()
        elif output_type == "audio_bytes":
                with TTS_OpenAI.openai_client.audio.speech.with_streaming_response.create(
                        model=model,
                        input=text,
                        voice=voice,
                        instructions=instructions,
                        speed=speed,
                        response_format=response_format,
                ) as resp:
                        return b"".join(resp.iter_bytes())
        else:  # file
                with TTS_OpenAI.openai_client.audio.speech.with_streaming_response.create(
                        model=model,
                        input=text,
                        voice=voice,
                        instructions=instructions,
                        speed=speed,
                        response_format=response_format,
                ) as resp:
                        resp.stream_to_file(output_path)
                        return output_path