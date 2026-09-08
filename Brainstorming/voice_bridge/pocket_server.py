"""Keep a Kyutai Pocket TTS voice resident and synthesize French over HTTP.

Same shape as piper_server.py, different engine: Pocket TTS is a 2026 model
from Kyutai at 24 kHz, where Piper is a 2022 VITS at 22.05 kHz driven by
rule-based espeak phonemization. It sounds markedly more natural in French and
costs more CPU: RTF ~0.8 against ~0.1.

Run it with the interpreter of .venv-pocket:
    .venv-pocket/Scripts/python.exe pocket_server.py --port 5112

POST / with the raw UTF-8 text, get a WAV back. GET /health returns the voice.
"""

from __future__ import annotations

import argparse
import io
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import torch
from pocket_tts import TTSModel

MODEL: TTSModel | None = None
VOICE_STATE = None
VOICE_NAME = ""
LANGUAGE = "french_24l"
VERBOSE = False
MAX_BODY = 64 * 1024

# Same lesson as the Piper daemon: the first inference has to happen in the
# main thread, and inferences must not overlap.
SYNTH_LOCK = threading.Lock()


def to_wav(audio: torch.Tensor, sample_rate: int) -> bytes:
    samples = np.clip(audio.numpy(), -1.0, 1.0)
    pcm = (samples * 32767.0).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


def synthesize(text: str) -> bytes:
    assert MODEL is not None
    with SYNTH_LOCK:
        # copy_state keeps the conditioning intact between requests.
        audio = MODEL.generate_audio(VOICE_STATE, text, copy_state=True)
    return to_wav(audio, MODEL.sample_rate)


class Server(ThreadingHTTPServer):
    # Windows would otherwise let a second daemon bind the same port silently.
    allow_reuse_address = False
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - base signature
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, VOICE_NAME.encode("utf-8"), "text/plain")
        else:
            self._send(404, b"not found", "text/plain")

    def _stream(self, text: str) -> None:
        """Send raw PCM as it is generated.

        Generation runs at RTF ~0.8, so waiting for the whole clip costs ~3.5 s
        of silence. Streaming puts the first sound out in ~340 ms, and since
        generation outruns playback the speakers never starve.
        """
        assert MODEL is not None
        self.send_response(200)
        self.send_header("Content-Type", "audio/L16")
        self.send_header("X-Sample-Rate", str(MODEL.sample_rate))
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        with SYNTH_LOCK:
            for chunk in MODEL.generate_audio_stream(VOICE_STATE, text, copy_state=True):
                pcm = (np.clip(chunk.numpy(), -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
                self.wfile.write(f"{len(pcm):X}\r\n".encode("ascii") + pcm + b"\r\n")
                self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")

    def do_POST(self) -> None:
        wanted = self.headers.get("X-Voice")
        if wanted and wanted != VOICE_NAME:
            self._send(409, VOICE_NAME.encode("utf-8"), "text/plain")
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send(400, b"bad length", "text/plain")
            return
        text = self.rfile.read(length).decode("utf-8", errors="replace").strip()
        if not text:
            self._send(400, b"empty", "text/plain")
            return

        if self.path.rstrip("/").endswith("stream"):
            try:
                self._stream(text)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the listener hit --stop; nothing to report
            return

        try:
            started = time.perf_counter()
            wav = synthesize(text)
            synth_ms = (time.perf_counter() - started) * 1000
            self._send(200, wav, "audio/wav")
            if VERBOSE:
                print(f"{len(text)} car -> {len(wav)} o | synth {synth_ms:.0f} ms", flush=True)
        except Exception as exc:  # noqa: BLE001 - never take the daemon down
            self._send(500, str(exc).encode("utf-8", "replace"), "text/plain")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", default="estelle", help="Voice name, or a wav path to clone.")
    parser.add_argument("--language", default="french_24l")
    parser.add_argument("--port", type=int, default=5112)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    global MODEL, VOICE_STATE, VOICE_NAME, LANGUAGE, VERBOSE
    VERBOSE = args.verbose
    VOICE_NAME = args.voice
    LANGUAGE = args.language

    print(f"chargement de pocket-tts ({LANGUAGE})...", flush=True)
    MODEL = TTSModel.load_model(language=LANGUAGE)
    VOICE_STATE = MODEL.get_state_for_audio_prompt(args.voice)

    started = time.perf_counter()
    synthesize("Prechauffage.")
    warm_ms = (time.perf_counter() - started) * 1000
    print(
        f"pocket_server pret sur http://127.0.0.1:{args.port}"
        f" | voix {VOICE_NAME} | {MODEL.sample_rate} Hz | prechauffage {warm_ms:.0f} ms",
        flush=True,
    )

    Server(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
