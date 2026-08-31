"""Safety proof: the simulated kernel never reaches the real OS (AC-9, CONTRACTS section 15).

The whole engine (kernel, shell, tools, scorer, scenario, scripted agents, runner) is meant to be a pure
in-memory simulation. The only legitimate real-world side effect during a scripted match is the journal
file the runner appends to, which is plain file I/O. Everything else - opening a real outbound network
connection, spawning a subprocess, shelling out - would be a contract breach that could touch the host.

Strategy: arm traps that explode if any of those real-world entry points is called, then run a full
scripted match built exactly like ``conftest.run_tiny_match`` and assert it completes untouched. We do
NOT patch ``builtins.open`` because the journal legitimately writes a real file; instead we guard the
channels the engine must never use - real network egress, subprocesses, and ``os.system``. Each trap
below documents what it guards against.

Note on the network trap: the runner drives ``asyncio.run`` for the ACT phase, and on Windows the
event loop's own self-pipe calls ``socket.socketpair()`` on the loopback interface. That is asyncio
plumbing, not the engine touching the network, so we trap ``socket.connect`` for non-loopback targets
only. A real outbound connection (any non-loopback host) still explodes; the loop's loopback pipe does
not. This keeps the trap precise: "no real network" means "no connection to anything off this host".
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
from collections.abc import Callable
from typing import Any, NoReturn

import pytest


class RealWorldEscape(RuntimeError):
    """Raised by a trap when engine code reaches for a real OS resource it must never touch."""


# Hosts that are on this machine, never the real network. asyncio's Windows self-pipe uses 127.0.0.1.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0", ""})


def _trap(name: str) -> Callable[..., NoReturn]:
    """Build a trap that raises ``RealWorldEscape`` naming the forbidden call it intercepted."""

    def _explode(*_args: Any, **_kwargs: Any) -> NoReturn:
        raise RealWorldEscape(f"engine reached the real OS via {name}")

    return _explode


async def _atrap_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> NoReturn:
    """Async twin of ``_trap`` for ``asyncio.create_subprocess_exec`` (an async function)."""
    raise RealWorldEscape("engine reached the real OS via asyncio.create_subprocess_exec")


def _host_of(address: Any) -> str:
    """Extract the host string from a socket address tuple, for the loopback allowlist check."""
    if isinstance(address, tuple) and address:
        return str(address[0])
    return str(address)


@pytest.fixture
def armed_traps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every real-world entry point the engine must never use with an exploding stub.

    - ``socket.socket.connect`` / ``connect_ex``: guard against a real outbound network connection.
      Loopback targets are allowed because asyncio's own event-loop self-pipe needs them; any
      non-loopback host explodes, so the engine cannot reach the real network.
    - ``subprocess.Popen``: guards against spawning a real child process synchronously.
    - ``asyncio.create_subprocess_exec``: guards the async subprocess path the LLM gateway would use;
      a scripted match must never take it.
    - ``os.system``: guards against shelling out through the C library.

    ``builtins.open`` is deliberately left alone: the runner's journal is a legitimate real file, so an
    open trap would be too broad. The channels above have no legitimate use in a scripted match.
    """
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guarded_connect(self: socket.socket, address: Any) -> Any:
        if _host_of(address) not in _LOOPBACK_HOSTS:
            raise RealWorldEscape(f"engine opened a real network connection to {address!r}")
        return real_connect(self, address)

    def guarded_connect_ex(self: socket.socket, address: Any) -> Any:
        if _host_of(address) not in _LOOPBACK_HOSTS:
            raise RealWorldEscape(f"engine opened a real network connection to {address!r}")
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(subprocess, "Popen", _trap("subprocess.Popen"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _atrap_create_subprocess_exec)
    monkeypatch.setattr(os, "system", _trap("os.system"))


def test_traps_are_actually_armed(armed_traps: None) -> None:
    """Sanity check: prove the traps really raise, so a green safety test cannot be a silent no-op."""
    with pytest.raises(RealWorldEscape):
        # A non-loopback target must explode before any real packet leaves the machine.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(("203.0.113.1", 80))
        finally:
            sock.close()
    with pytest.raises(RealWorldEscape):
        subprocess.Popen(["true"])
    with pytest.raises(RealWorldEscape):
        os.system("true")


def test_scripted_match_never_touches_real_os(
    armed_traps: None,
    run_tiny_match: Callable[..., Any],
) -> None:
    """Run a full scripted match with the traps armed; it must complete without tripping any of them.

    If any tool, the kernel, the scorer, or the runner opened a real outbound connection, spawned a
    subprocess, or called ``os.system`` the match would raise ``RealWorldEscape`` and this test would
    fail. Completion proves the simulated kernel stays in memory and the only real side effect is the
    journal file itself.
    """
    result, journal_path, projection = run_tiny_match()

    # The match ran to the end and produced a real journal (the one allowed real-world effect).
    assert result.ticks > 0
    assert journal_path.exists()
    assert result.journal_hash
    # The projection replays from that journal alone, confirming the run produced a usable event stream.
    assert projection.all_agents()
