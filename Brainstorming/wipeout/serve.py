"""Tiny static server for VELOCITRON.

Plain `python -m http.server` works too, but Chrome then caches the ES modules
and you keep playing an old build after an edit. This one sends no-store on
everything, so a refresh always picks up the latest code.

    python serve.py [port]
"""

import functools
import http.server
import os
import socketserver
import sys

DEFAULT_PORT = 8093


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, format, *args):  # noqa: A002 - name fixed by the base class
        # keep the console readable: only report failures
        if len(args) > 1 and str(args[1]).startswith(("4", "5")):
            super().log_message(format, *args)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    root = os.path.dirname(os.path.abspath(__file__))
    handler = functools.partial(NoCacheHandler, directory=root)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        print(f"VELOCITRON served from {root}")
        print(f"Open http://localhost:{port}/index.html")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
