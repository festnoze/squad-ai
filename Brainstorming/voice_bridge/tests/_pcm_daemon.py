"""Stand-in for the Pocket TTS daemon: streams recognizable PCM per request.

Each character becomes a run of identical samples keyed to that character, so a
test can prove the chunks arrived complete, in order, and with nothing dropped
at the seams. The run is long enough that a request is worth seconds of audio,
which is what the start decision needs to have anything to weigh.

    python _pcm_daemon.py <port> [--fail-after N]
"""

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RATE = 24000
# The real voice fits about 19 characters into a second of speech.
SAMPLES_PER_CHAR = RATE // 19


def pcm_for(text: str) -> bytes:
    """16-bit mono PCM whose every sample says which character produced it."""
    return b"".join(bytes([ord(c) % 256, 1]) * SAMPLES_PER_CHAR for c in text)


def main() -> None:
    port = int(sys.argv[1])
    fail_after = int(sys.argv[3]) if "--fail-after" in sys.argv else -1
    served = 0

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

        def do_POST(self) -> None:
            nonlocal served
            length = int(self.headers.get("Content-Length") or 0)
            text = self.rfile.read(length).decode("utf-8")
            if fail_after >= 0 and served >= fail_after:
                self.send_response(500)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            served += 1

            pcm = pcm_for(text)
            self.send_response(200)
            self.send_header("Content-Type", "audio/L16")
            self.send_header("X-Sample-Rate", str(RATE))
            self.send_header("Content-Length", str(len(pcm)))
            self.end_headers()
            self.wfile.write(pcm)

    ThreadingHTTPServer.daemon_threads = True
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("ready", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
