"""Keep a Piper voice resident in memory and synthesize over HTTP.

Loading the ONNX model costs ~4 s, which is fine once and unacceptable per
answer. This daemon pays it at startup; each request then runs at RTF ~0.1.

Run it with the interpreter that has piper-tts installed:
    <uv tools>/piper-tts/Scripts/python.exe piper_server.py --port 5111

POST / with the raw UTF-8 text, get a WAV back. GET /health to probe it.
"""

from __future__ import annotations

import argparse
import io
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from piper import PiperVoice

VOICE: PiperVoice | None = None
VERBOSE = False
MAX_BODY = 64 * 1024

# ONNX Runtime lays out its intra-op thread pool on the first Run. Letting that
# happen inside a request thread costs ~4 s per call instead of ~0.4 s, and it
# never recovers, so the first synthesis has to be a main-thread warm-up and
# every later one has to queue behind the same lock.
SYNTH_LOCK = threading.Lock()


def opt_out_of_power_throttling() -> None:
    """Windows EcoQoS throttles windowless background processes onto the slow
    cores. Measured here: 0.4 s of synthesis became 3.5 s once the daemon ran
    hidden. Opting out puts it back at full speed."""
    import ctypes
    from ctypes import wintypes

    class PowerThrottlingState(ctypes.Structure):
        _fields_ = [
            ("Version", wintypes.ULONG),
            ("ControlMask", wintypes.ULONG),
            ("StateMask", wintypes.ULONG),
        ]

    PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
    PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
    PROCESS_INFORMATION_CLASS_POWER_THROTTLING = 4

    state = PowerThrottlingState(
        Version=PROCESS_POWER_THROTTLING_CURRENT_VERSION,
        ControlMask=PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
        StateMask=0,  # 0 = throttling off
    )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetProcessInformation(
        kernel32.GetCurrentProcess(),
        PROCESS_INFORMATION_CLASS_POWER_THROTTLING,
        ctypes.byref(state),
        ctypes.sizeof(state),
    )


def synthesize(text: str) -> bytes:
    assert VOICE is not None
    buffer = io.BytesIO()
    with SYNTH_LOCK, wave.open(buffer, "wb") as wav:
        VOICE.synthesize_wav(text, wav)
    return buffer.getvalue()


class Server(ThreadingHTTPServer):
    # Windows honours SO_REUSEADDR literally: with the stdlib default a second
    # daemon binds the same port without error and the stale one keeps serving.
    # Refusing reuse turns that silent mix-up into an "address in use" crash.
    allow_reuse_address = False
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - base signature
        pass  # keep the console quiet

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, b"ok", "text/plain")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send(400, b"bad length", "text/plain")
            return
        text = self.rfile.read(length).decode("utf-8", errors="replace").strip()
        if not text:
            self._send(400, b"empty", "text/plain")
            return
        try:
            started = time.perf_counter()
            wav = synthesize(text)
            synth_ms = (time.perf_counter() - started) * 1000
            self._send(200, wav, "audio/wav")
            if VERBOSE:
                sent_ms = (time.perf_counter() - started) * 1000 - synth_ms
                print(
                    f"{len(text)} car -> {len(wav)} o | synth {synth_ms:.0f} ms"
                    f" | envoi {sent_ms:.0f} ms",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001 - never take the daemon down
            self._send(500, str(exc).encode("utf-8", "replace"), "text/plain")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        type=Path,
        default=Path(__file__).resolve().parent / "voices" / "fr_FR-siwis-medium.onnx",
    )
    parser.add_argument("--port", type=int, default=5111)
    parser.add_argument("--verbose", action="store_true", help="Log per-request timings.")
    args = parser.parse_args()

    global VOICE, VERBOSE
    VERBOSE = args.verbose
    opt_out_of_power_throttling()
    print(f"chargement de {args.model.name}...", flush=True)
    VOICE = PiperVoice.load(str(args.model))
    started = time.perf_counter()
    synthesize("Prechauffage.")
    warm_ms = (time.perf_counter() - started) * 1000
    print(
        f"piper_server pret sur http://127.0.0.1:{args.port}"
        f" (prechauffage {warm_ms:.0f} ms)",
        flush=True,
    )

    Server(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
