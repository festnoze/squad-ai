import base64
import io
from typing import Literal

from openai import AsyncOpenAI
from openai._types import NOT_GIVEN
from utils.envvar import EnvHelper

TTSModel = Literal[
    "gpt-4o-realtime-preview",
    "gpt-4o-mini-realtime-preview",
    "gpt-4o-mini-tts",
    "tts-1",
    "tts-1-hd",
]
VoicePreset = Literal[
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "onyx",
    "nova",
    "sage",
    "shimmer",
]
ResponseFormat = Literal["pcm", "mp3", "wav", "flac", "opus", "aac"]


class TTS_OpenAI:
    _client: AsyncOpenAI = AsyncOpenAI(api_key=EnvHelper.get_openai_api_key())

    @staticmethod
    async def generate_speech_async(
        model: TTSModel,
        text: str,
        voice: VoicePreset = "nova",
        instructions: str = NOT_GIVEN,
        speed: float = 1.0,
        response_format: ResponseFormat = "pcm",
        convert_to_pcm_rate: int | None = None,
    ) -> bytes:
        if model in {"gpt-4o-realtime-preview", "gpt-4o-mini-realtime-preview"}:
            return await TTS_OpenAI._generate_realtime_bytes(model=model, text=text, voice=voice)
        if model.startswith("tts-1"):
            instructions = NOT_GIVEN
        resp = await TTS_OpenAI._client.audio.speech.create(
            model=model,
            input=text,
            voice=voice,
            instructions=instructions,
            speed=speed,
            response_format=response_format,
        )
        raw = resp.read()
        if response_format == "pcm" and convert_to_pcm_rate:
            raw = TTS_OpenAI._convert_rate(raw, 24000, convert_to_pcm_rate)
        return raw

    @staticmethod
    async def _generate_realtime_bytes(
        model: str,
        text: str,
        voice: VoicePreset,
    ) -> bytes:
        client = TTS_OpenAI._client
        pcm_chunks: list[bytes] = []
        async with client.beta.realtime.connect(model=model) as conn:
            await conn.session.update(
                session={
                    "modalities": ["audio"],
                    "output_audio_format": "pcm16",
                }
            )
            await conn.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                }
            )
            await conn.response.create(
                response={
                    "modalities": ["audio"],
                    "voice": voice,
                }
            )
            async for event in conn:
                if event.type == "response.audio.delta":
                    pcm_chunks.append(base64.b64decode(event.delta))
                elif event.type == "response.done":
                    break
        return b"".join(pcm_chunks)

    @staticmethod
    def _convert_rate(
        audio_bytes: bytes,
        from_rate: int,
        to_rate: int,
        sample_width: int = 2,
        channels: int = 1,
    ) -> bytes:
        from pydub import AudioSegment

        audio = AudioSegment.from_raw(
            io.BytesIO(audio_bytes),
            frame_rate=from_rate,
            sample_width=sample_width,
            channels=channels,
        )
        audio = audio.set_frame_rate(to_rate)
        buf = io.BytesIO()
        audio.export(buf, format="raw")
        return buf.getvalue()
