"""Browser access boundary for the trusted factory, not product authentication.

AUTOSPEC_CONTROL_ORIGINS and AUTOSPEC_CONTROL_HOSTS are optional JSON arrays.
They explicitly configure browser origins and network-facing authorities;
no wildcard, suffix matching, forwarded-header trust or test-host exception.
Remote/LAN opening needs an explicit authority. It is NOT an authentication
system: a configured remote CLI without Origin remains an operator decision.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse


DEV_ORIGINS = ("http://localhost:5183", "http://127.0.0.1:5183")
METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
HEADERS = ("Content-Type", "Last-Event-ID")
_DNS = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*")


def _authority(value: str) -> tuple[str, int | None]:
    if (not isinstance(value, str) or not value or len(value) > 512 or
        any(ord(char) <= 32 or ord(char) >= 127 for char in value) or
        any(char in value for char in "@/\\?#%")):
        raise ValueError("literal bounded control authority required")
    parsed = urlsplit("http://" + value)
    host = parsed.hostname
    port = parsed.port  # Also rejects malformed/unbounded port syntax.
    if not host or port is not None and not 1 <= port <= 65535:
        raise ValueError("control authority host/port invalid")
    try:
        address = ipaddress.ip_address(host)
        if host != address.compressed:
            raise ValueError("canonical IP authority required")
    except ValueError:
        if not _DNS.fullmatch(host) or len(host) > 253 or re.fullmatch(r"[0-9.]+", host):
            raise ValueError("literal canonical control hostname required")
    if value.lower() != _render_authority(host, port):
        raise ValueError("ambiguous control authority refused")
    return host, port


def _render_authority(host: str, port: int | None = None) -> str:
    literal = "[" + host + "]" if ":" in host else host
    return literal + (":" + str(port) if port is not None else "")


def _origin(value: str) -> tuple[str, str, int]:
    if not isinstance(value, str) or len(value) > 1024:
        raise ValueError("bounded literal control origin required")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("control origin must be an exact HTTP(S) origin")
    host, port = _authority(parsed.netloc)
    effective = port if port is not None else (443 if parsed.scheme == "https" else 80)
    canonical_port = None if effective == (443 if parsed.scheme == "https" else 80) else effective
    if value != parsed.scheme + "://" + _render_authority(host, canonical_port):
        raise ValueError("canonical exact control origin required")
    return parsed.scheme, host, effective


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
        mapped = getattr(address, "ipv4_mapped", None)
        return address.is_loopback or bool(mapped and mapped.is_loopback)
    except ValueError:
        return False


def _array(name: str) -> tuple[str, ...]:
    value = os.environ.get(name)
    if value is None:
        return ()
    if len(value) > 16_384:
        raise ValueError(name + " exceeds configuration bound")
    try:
        result = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(name + " needs a JSON array") from exc
    if (not isinstance(result, list) or len(result) > 32 or
        any(not isinstance(item, str) for item in result) or len(set(result)) != len(result)):
        raise ValueError(name + " needs unique bounded literal entries")
    return tuple(result)


@dataclass(frozen=True)
class ControlPolicy:
    origins: tuple[str, ...] = DEV_ORIGINS
    authorities: tuple[str, ...] = ()

    def __post_init__(self):
        for values in (self.origins, self.authorities):
            if (not isinstance(values, tuple) or len(values) > 34 or
                any(not isinstance(value, str) for value in values) or len(set(values)) != len(values)):
                raise ValueError("unique bounded control policy tuples required")
        for origin in self.origins:
            _origin(origin)
        for authority in self.authorities:
            host, port = _authority(authority)
            if authority != _render_authority(host, port):
                raise ValueError("canonical configured authority required")

    @classmethod
    def from_environment(cls):
        # Explicit JSON [] removes the dev defaults for served-GUI-only setups.
        origins = _array("AUTOSPEC_CONTROL_ORIGINS") if "AUTOSPEC_CONTROL_ORIGINS" in os.environ else DEV_ORIGINS
        return cls(origins, _array("AUTOSPEC_CONTROL_HOSTS"))

    def permits(self, scope) -> bool:
        try:
            headers = scope.get("headers", ())
            hosts = [value.decode("ascii") for key, value in headers if key.lower() == b"host"]
            origins = [value.decode("ascii") for key, value in headers if key.lower() == b"origin"]
            if len(hosts) != 1 or len(origins) > 1:
                return False
            host, port = _authority(hosts[0])
            scheme = {"ws":"http", "wss":"https"}.get(scope.get("scheme"), scope.get("scheme"))
            if scheme not in {"http", "https"}:
                return False
            effective = port if port is not None else (443 if scheme == "https" else 80)
            server = scope.get("server")
            if not isinstance(server, (tuple, list)) or len(server) != 2:
                return False
            server_port = server[1] if server[1] is not None else (443 if scheme == "https" else 80)
            if type(server_port) is not int or not 1 <= server_port <= 65535:
                return False
            configured = any(config_host == host and config_port in {None, effective}
                             for config_host, config_port in map(_authority, self.authorities))
            # Vite forwards the trusted frontend Host, rather than changing it
            # to the upstream API port. Only approved exact GUI authorities
            # receive this exception; arbitrary loopback ports never do.
            gui_authority = any(_origin(value)[1:] == (host, effective) for value in self.origins)
            local_authority = _loopback(host) and (effective == server_port or gui_authority)
            if not (local_authority or configured):
                return False
            client = scope.get("client")
            if not configured and (not client or not _loopback(client[0]) or client[0] == "localhost"):
                return False
            if not origins:
                return True  # Local CLI; not a browser authentication bypass.
            origin = origins[0]
            origin_scheme, origin_host, origin_port = _origin(origin)
            same_server = (_loopback(host) and effective == server_port and
                           (origin_scheme, origin_host, origin_port) == (scheme, host, effective))
            return origin in self.origins or same_server
        except (TypeError, ValueError, UnicodeError, KeyError, IndexError):
            return False


class FactoryControlBoundary:
    """Reject hostile Host/Origin BEFORE routing, including simple POSTs."""
    def __init__(self, app, *, policy: ControlPolicy | None = None):
        self.app = app
        self.policy = policy if policy is not None else ControlPolicy.from_environment()

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        if not self.policy.permits(scope):
            if scope["type"] == "websocket":
                return await send({"type":"websocket.close", "code":1008})
            return await JSONResponse({"detail":"CONTROL_ORIGIN_OR_HOST_REFUSED"}, status_code=403)(scope, receive, send)
        if scope["type"] == "websocket":
            return await self.app(scope, receive, send)
        origins = [value.decode("ascii") for key, value in scope["headers"] if key.lower() == b"origin"]
        if not origins:
            return await self.app(scope, receive, send)
        # Per-request exact CORS scope, never a wildcard or shared mutable
        # allowlist. This also supports the served GUI's actual loopback port.
        cors = CORSMiddleware(self.app, allow_origins=origins, allow_methods=METHODS,
                              allow_headers=HEADERS, allow_credentials=False)
        return await cors(scope, receive, send)
