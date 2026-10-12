"""Owned localhost ingress for a control port in an existing NETNONE runtime.

No container adoption, remote host, arbitrary program or model-facing API.
The namespace owner remains responsible for the product and browser lifetime.
"""
from __future__ import annotations

import re
import socketserver
import threading

from .isolated_validation import RuntimeSession
from .sandbox import _unavailable


class OwnedControlTunnel:
    def __init__(self, runtime: RuntimeSession, target_port: int, *, timeout=600):
        if not isinstance(runtime, RuntimeSession):
            raise _unavailable("control ingress requires an actual supervisor runtime capability")
        if type(target_port) is not int or not 1 <= target_port <= 65535 or target_port == runtime.port:
            raise _unavailable("distinct bounded container-local control port required")
        if not 1 <= timeout <= 1800:
            raise _unavailable("bounded control ingress lifetime required")
        self.runtime = runtime
        self.identifier = runtime._assert_owned()
        if not re.fullmatch(r"[a-f0-9]{64}", self.identifier):
            raise _unavailable("immutable parent container identity required")
        self.docker, self.ecosystem = runtime.docker, runtime.ecosystem
        self.port, self.timeout = target_port, timeout
        self.lock, self.operation_lock = threading.Lock(), threading.RLock()
        self.clients, self.sockets = set(), set()
        self.capacity = threading.BoundedSemaphore(16)
        self.closed, self.transition, self.persistent_database = False, False, False
        self.thread = None
        self._assert_owned()  # refuse external networking before opening ingress
        session = self
        class Handler(socketserver.BaseRequestHandler):
            def handle(self): session._forward(self.request)
        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = False
        self.server = Server(("127.0.0.1", 0), Handler)
        self.host_port = self.server.server_address[1]

    def _assert_owned(self):
        if self.closed or self.runtime._assert_owned() != self.identifier:
            raise _unavailable("control tunnel parent changed or is closed")
        value = self.runtime.inspect_configuration()
        if (value["container_id"] != self.identifier or value["network_mode"] != "none"
                or value["running"] is not True or value["published_ports"]):
            raise _unavailable("control namespace must be the exact active unpublished NETNONE runtime")
        return self.identifier

    # Reuse the already reviewed immutable-ID docker exec stdio forwarding.
    # Python uses the isolated base interpreter (-I), not product imports.
    _forward = RuntimeSession._forward
    _disconnect = RuntimeSession._disconnect

    def __enter__(self):
        with self.operation_lock:
            if self.closed or self.thread is not None:
                raise _unavailable("control tunnel is closed or already started")
            self._assert_owned()
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            return self

    def close(self):
        with self.operation_lock:
            if self.closed: return
            self.closed = True
            self._disconnect()
        if self.thread is not None:
            self.server.shutdown()
            self.thread.join(timeout=2)
            self.thread = None
        self.server.server_close()
        # Never stop/remove the parent or another container from this helper.

    def __exit__(self, *_): self.close()
