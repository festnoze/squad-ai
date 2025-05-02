import wave
import time
import queue
import numpy as np
import sounddevice as sd
from pathlib import Path
from openai import OpenAI
from models.form_agent_state import FormAgentState

class AgentAudio:
        def __init__(self) -> None:
                self.client: OpenAI = OpenAI()

        async def transcript_audio(self, state: FormAgentState) -> FormAgentState:
                audio_path: str | None = state.get("audio_path")
                if audio_path:
                        with open(audio_path, "rb") as f:
                                transcript: str = self.client.audio.transcriptions.create(
                                        model="gpt-4o-transcribe",
                                        file=f,
                                        response_format="text"
                                ).text
                        state["transcription"] = transcript
                return state

        async def speak_out(self, state: FormAgentState) -> FormAgentState:
                text: str | None = state.get("speak_text")
                if text:
                        resp = self.client.audio.speech.create(
                                model="gpt-4o-mini-tts",
                                voice="alloy",
                                input=text
                        )
                        out_path: Path = Path("outputs") / "speech.mp3"
                        resp.stream_to_file(out_path)
                        state["speech_file"] = str(out_path)
                return state

        def record_audio(self, output_path: str, threshold: float, silence_duration: float) -> None:
                q: queue.Queue[np.ndarray] = queue.Queue()
                fs: int = 16000
                channels: int = 1
                silent_chunks: int = 0
                chunk_duration: float = 0.1
                chunk_size: int = int(fs * chunk_duration)

                def callback(indata: np.ndarray, frames: int, time_info: any, status: any) -> None:
                        q.put(indata.copy())

                with sd.InputStream(samplerate=fs, channels=channels, blocksize=chunk_size, callback=callback):
                        frames: list[np.ndarray] = []
                        while True:
                                data: np.ndarray = q.get()
                                frames.append(data)
                                rms: float = np.sqrt(np.mean(data**2))
                                if rms < threshold:
                                        silent_chunks += 1
                                else:
                                        silent_chunks = 0
                                if silent_chunks * chunk_duration >= silence_duration:
                                        break

                wf = wave.open(output_path, "wb")
                wf.setnchannels(channels)
                wf.setsampwidth(2)
                wf.setframerate(fs)
                for chunk in frames:
                        wf.writeframes((chunk * 32767).astype(np.int16).tobytes())
                wf.close()
