"""Trusted harness ports shared by independent security/business/API probes.

No product imports, hidden login bypass, route remapping or debug endpoint.
Fixtures/commands are harness-owned and must target an isolated test database.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol
from urllib.parse import urlparse

import httpx


class AdapterUnavailable(RuntimeError):
    """A required external observation cannot be obtained (not product FAIL)."""


@dataclass(frozen=True)
class FixtureAccount:
    id: str
    email: str
    password: str = field(repr=False)
    role: str = "client"
    active: bool = True


@dataclass(frozen=True)
class FixtureManifest:
    accounts: dict[str, FixtureAccount] = field(default_factory=dict)
    tickets: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Proof:
    type: str
    path: str
    sha256: str
    snapshot_hash: str
    contract_hash: str
    checks: tuple[str, ...] = ()
    passed: bool = True
    detail: str = ""

    def intact(self, *, snapshot_hash: str, contract_hash: str) -> bool:
        path = Path(self.path)
        return (self.type in {"X", "R", "V"} and self.snapshot_hash == snapshot_hash and
                self.contract_hash == contract_hash and path.is_file() and
                hashlib.sha256(path.read_bytes()).hexdigest() == self.sha256)


class SupportAdapter(Protocol):
    base_url: str
    origin: str
    evidence_root: Path
    manifest: FixtureManifest

    async def prepare_case(self, case_id: str, **options) -> FixtureManifest: ...
    async def request(self, actor: str | None, method: str, path: str, *, json=None, params=None,
                      headers: dict[str, str | None] | None = None, ip: str = "127.0.0.1",
                      authenticate: bool = True) -> httpx.Response: ...
    async def login(self, actor: str, *, ip: str = "127.0.0.1") -> httpx.Response: ...
    async def observe(self, name: str, **params) -> Any: ...
    async def command(self, action: str, **params) -> dict: ...
    async def advance_clock(self, seconds: float) -> None: ...
    async def arm_race(self, point: str, parties: int = 2) -> None: ...
    async def proofs(self, requirement_id: str) -> list[Proof]: ...
    async def snapshot_hash(self) -> str: ...
    async def contract_hash(self) -> str: ...
    async def close(self) -> None: ...


AsyncPort = Callable[..., Awaitable[Any]]


class HttpxSupportAdapter:
    """Real HTTP/cookie clients and injectable trusted observation ports.

    Runtime transport defaults to real HTTP. Tests may supply a real ASGI app
    transport, not canned responses. IP is a source address, never forged XFF.
    Callback failures are explicit; no missing observation defaults to success.
    """

    def __init__(self, *, base_url: str, auth_path: str, origin: str, csrf_field: str,
                 evidence_root: Path, prepare: AsyncPort, observe: AsyncPort,
                 snapshot: AsyncPort, oracle: AsyncPort, command: AsyncPort | None = None,
                 clock: AsyncPort | None = None, proofs: AsyncPort | None = None,
                 race: AsyncPort | None = None, restart: AsyncPort | None = None,
                 fault: AsyncPort | None = None, db_connect: Callable | None = None,
                 transport_factory: Callable[[str], httpx.AsyncBaseTransport] | None = None,
                 allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "::1")):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in allowed_hosts:
            raise ValueError("explicit isolated HTTP origin required")
        self.base_url, self.auth_path, self.origin, self.csrf_field = base_url, auth_path, origin, csrf_field
        self.evidence_root = Path(evidence_root).resolve()
        self._ports = dict(prepare=prepare, observe=observe, snapshot=snapshot, oracle=oracle,
                           command=command, clock=clock, proofs=proofs, race=race,
                           restart=restart, fault=fault)
        self._db_connect = db_connect
        self._transport_factory = transport_factory
        self._clients: dict[tuple[str | None, str], httpx.AsyncClient] = {}
        self._csrf: dict[tuple[str | None, str], str] = {}
        self.manifest = FixtureManifest()

    async def _port(self, name: str, *args, **kwargs):
        callback = self._ports.get(name)
        if callback is None:
            raise AdapterUnavailable(f"required harness port unavailable: {name}")
        return await callback(*args, **kwargs)

    def _client(self, actor: str | None, ip: str) -> httpx.AsyncClient:
        key = (actor, ip)
        if key not in self._clients:
            transport = (self._transport_factory(ip) if self._transport_factory else
                         httpx.AsyncHTTPTransport(local_address=ip))
            self._clients[key] = httpx.AsyncClient(base_url=self.base_url, transport=transport,
                                                  timeout=15, follow_redirects=False)
        return self._clients[key]

    async def prepare_case(self, case_id: str, **options) -> FixtureManifest:
        await self.close()
        self.manifest = await self._port("prepare", case_id, **options)
        return self.manifest

    async def reset_fixture(self, name: str) -> FixtureManifest:
        return await self.prepare_case(name)

    async def login(self, actor: str, *, ip: str = "127.0.0.1") -> httpx.Response:
        if actor not in self.manifest.accounts:
            raise AdapterUnavailable("actor credentials absent from fixture manifest")
        account = self.manifest.accounts[actor]
        response = await self._client(actor, ip).post(self.auth_path,
            json={"email": account.email, "password": account.password}, headers={"Origin": self.origin})
        if response.status_code == 200:
            value = response.json().get(self.csrf_field)
            if isinstance(value, str):
                self._csrf[(actor, ip)] = value
        return response

    async def request(self, actor: str | None, method: str, path: str, *, json=None, params=None,
                      headers: dict[str, str | None] | None = None, ip: str = "127.0.0.1",
                      authenticate: bool = True) -> httpx.Response:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("request path must be same-origin and absolute-relative")
        key = (actor, ip)
        if actor is not None and authenticate and key not in self._clients:
            response = await self.login(actor, ip=ip)
            if response.status_code != 200:
                return response  # executed auth failure, no injected session
        client = self._client(actor, ip)
        selected = {"Origin": self.origin}
        if key in self._csrf:
            selected["X-CSRF-Token"] = self._csrf[key]
        for header, value in (headers or {}).items():
            selected = {k: v for k, v in selected.items() if k.casefold() != header.casefold()}
            if value is not None:
                selected[header] = value
        return await client.request(method, path, json=json, params=params, headers=selected)

    def session_cookie(self, actor: str, name: str, *, ip: str = "127.0.0.1") -> str:
        return self._client(actor, ip).cookies.get(name, "")

    def csrf_token(self, actor: str, *, ip: str = "127.0.0.1") -> str:
        return self._csrf.get((actor, ip), "")

    async def observe(self, name: str, **params):
        return await self._port("observe", name, **params)

    async def snapshot_db(self):
        return await self.observe("snapshot")

    def connect_db(self):
        if self._db_connect is None:
            raise AdapterUnavailable("distinct SQLite connection port unavailable")
        return self._db_connect()

    async def command(self, action: str, **params):
        return await self._port("command", action, **params)

    async def advance_clock(self, seconds: float):
        await self._port("clock", seconds)

    async def arm_race(self, point: str, parties: int = 2):
        await self._port("race", point, parties)

    async def set_fault(self, point: str, enabled: bool = True):
        await self._port("fault", point, enabled)

    async def restart(self):
        await self._port("restart")

    async def proofs(self, requirement_id: str) -> list[Proof]:
        callback = self._ports.get("proofs")
        return [] if callback is None else await callback(requirement_id)

    async def source_review(self, requirement_id: str) -> list[Proof]:
        return [p for p in await self.proofs(requirement_id) if p.type == "R"]

    async def browser_evidence(self, requirement_id: str) -> list[Proof]:
        return [p for p in await self.proofs(requirement_id) if p.type == "V"]

    async def snapshot_hash(self) -> str:
        return await self._port("snapshot")

    async def contract_hash(self) -> str:
        return await self._port("oracle")

    async def close(self):
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
        self._csrf.clear()
