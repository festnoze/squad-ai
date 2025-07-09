from typing import Literal
from openai import OpenAI
from openai._types import NOT_GIVEN
import io
from utils.envvar import EnvHelper

TTSModel        = Literal["gpt-4o-mini-tts", "gpt-4o-tts", "tts-1", "tts-1-hd"]
VoicePreset     = Literal["fable", "onyx", "nova", "shimmer", "alloy", "echo", "ash", "ballad", "coral", "sage" ]
                # Better for french: fable, nova, shimmer
                # All OpenAI TTS voices: alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer
ResponseFormat  = Literal["mp3", "opus", "aac", "flac", "wav", "pcm"]
OutputType      = Literal["stream", "file", "audio_bytes"]

class TTS_OpenAI:    
    openai_client: any = OpenAI(api_key=EnvHelper.get_openai_api_key())
    
    @staticmethod
    def generate_speech(
            model: TTSModel,
            text: str,
            voice: VoicePreset = "nova",
            instructions: str = NOT_GIVEN,
            speed: float = 1.0,
            response_format: ResponseFormat = "pcm",
            convert_to_pcm_rate: int | None = None) -> bytes:
        # 'tts-1*' models don't support instructions, only 'gpt-4o-*-tts' ones does.
        if model.startswith('tts-1'):
            instructions = NOT_GIVEN
        response: any = TTS_OpenAI.openai_client.audio.speech.create(
                model=model,
                input=text,
                voice=voice,
                instructions=instructions,
                speed=speed,
                response_format=response_format,
        )
        raw_response: bytes = response.read()
        if response_format == "pcm" and convert_to_pcm_rate:
            raw_response = TTS_OpenAI.convert_PCM_frame_rate_w_pydub(audio_bytes=raw_response, from_frame_rate=24000, to_frame_rate=convert_to_pcm_rate)
        return raw_response    
    
    def convert_PCM_frame_rate_w_pydub(self, audio_bytes: bytes, from_frame_rate: int, to_frame_rate: int, sample_width: int = 2, channels: int = 1) -> bytes:
        if not audio_bytes: return b""
        if from_frame_rate == to_frame_rate: return audio_bytes
        
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_raw(io.BytesIO(audio_bytes), sample_width=sample_width, frame_rate=from_frame_rate, channels=channels)
            audio = audio.set_frame_rate(to_frame_rate)
            buf = io.BytesIO()
            audio.export(buf, format="raw")
            return buf.getvalue()
        
        except Exception:
            return b""
        
    def convert_PCM_frame_rate_w_audioop(self, audio_bytes: bytes, from_frame_rate: int, to_frame_rate: int) -> bytes:
        if not audio_bytes: return b""
        if from_frame_rate == to_frame_rate: return audio_bytes
        
        try:
            import audioop
            converted_audio, _ = audioop.ratecv(audio_bytes, self.sample_width, self.channels, from_frame_rate, to_frame_rate, None)
            return converted_audio
        
        except audioop.error as e:
            return b""
    
    ## UN-USE: kept for streaming cases
    # @staticmethod
    # def tts_playback(
    #         text: str,
    #         model: TTSModel = "tts-1",
    #         voice: VoicePreset = "nova",
    #         instructions: str = "Speak in a cheerful and positive tone.",
    #         speed: float = 1.0,
    #         response_format: ResponseFormat = "pcm",
    #         output_type: OutputType = "stream",
    #         output_path: Path = Path("speech.pcm")) -> any:
    #     import pyaudio
    #     if output_type == "stream":
    #             pa: any = pyaudio.PyAudio()
    #             stream_out: any = pa.open(format=pyaudio.paInt16, channels=1, rate=24_000, output=True)
    #             with TTS_OpenAI.openai_client.audio.speech.with_streaming_response.create(
    #                     model=model,
    #                     input=text,
    #                     voice=voice,
    #                     instructions=instructions,
    #                     speed=speed,
    #                     response_format="pcm",
    #             ) as resp:
    #                     for chunk in resp.iter_bytes():
    #                             stream_out.write(chunk)
    #             stream_out.stop_stream()
    #             stream_out.close()
    #             pa.terminate()
    #     elif output_type == "audio_bytes":
    #             with TTS_OpenAI.openai_client.audio.speech.with_streaming_response.create(
    #                     model=model,
    #                     input=text,
    #                     voice=voice,
    #                     instructions=instructions,
    #                     speed=speed,
    #                     response_format=response_format,
    #             ) as resp:
    #                     return b"".join(resp.iter_bytes())
    #     else:  # file
    #             with TTS_OpenAI.openai_client.audio.speech.with_streaming_response.create(
    #                     model=model,
    #                     input=text,
    #                     voice=voice,
    #                     instructions=instructions,
    #                     speed=speed,
    #                     response_format=response_format,
    #             ) as resp:
    #                     resp.stream_to_file(output_path)
    #                     return output_path