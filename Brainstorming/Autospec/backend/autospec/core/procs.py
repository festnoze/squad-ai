"""Run a child process with a hard wall-clock cap and kill its whole tree.

Windows does not kill grandchildren when a parent dies (uv -> python -> uvicorn,
npm -> node -> vite), so every timeout, cancellation or interrupt goes through ``kill_tree``.
Only processes this module started are ever killed. Caps are wall-clock deadlines checked
every ``WAIT_SLICE_S``: on Windows a ``Popen.wait`` timeout does not count a machine sleep
(a 90 min cap once never fired over a 2.7 h run).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_TAIL = 20_000
WAIT_SLICE_S = 0.5


def _now() -> float:
    """Wall-clock seconds, the clock of every cap (tests patch it to simulate a sleep)."""
    return time.time()


@dataclass
class ProcResult:
    returncode: int | None  # None when killed on timeout
    stdout: str
    stderr: str
    timed_out: bool
    duration_s: float


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def popen(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE) -> subprocess.Popen:
    """Start a process in its own group so ``kill_tree`` can reach every descendant. Pipes are
    binary (a text-mode stdin turns every LF into CRLF on Windows); Python descendants are forced
    to UTF-8 I/O, or on Windows they would decode our UTF-8 pipes with the ANSI code page."""
    env = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", **(os.environ if env is None else env)}
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(argv, cwd=cwd, env=env, stdin=stdin, stdout=stdout, stderr=stderr, **kwargs)


def wait_until(proc: subprocess.Popen, deadline: float) -> bool:
    """Wait for ``proc`` until the wall-clock ``deadline`` (``time.time``); True when it exited."""
    while (remaining := deadline - _now()) > 0:
        try:
            proc.wait(timeout=min(remaining, WAIT_SLICE_S))
            return True
        except subprocess.TimeoutExpired:
            pass
    return proc.poll() is not None


class _Child:
    """A started process whose outputs are drained by threads, so a full pipe never stalls it."""

    def __init__(self, argv: list[str], cwd: Path | None, env: dict[str, str] | None,
                 input_text: str | None):
        self.started = _now()
        self.proc = popen(argv, cwd=cwd, env=env,
                          stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL)
        self.chunks: dict[str, list[str]] = {"out": [], "err": []}
        if input_text is not None:
            threading.Thread(target=self._feed, args=(input_text.encode("utf-8"),), daemon=True).start()
        self.readers = [threading.Thread(target=self._drain, args=(self.proc.stdout, "out"), daemon=True),
                        threading.Thread(target=self._drain, args=(self.proc.stderr, "err"), daemon=True)]
        for reader in self.readers:
            reader.start()

    def _feed(self, data: bytes) -> None:
        with contextlib.suppress(OSError, ValueError):  # the child may exit without reading
            self.proc.stdin.write(data)
            self.proc.stdin.close()

    def _drain(self, stream, key: str) -> None:
        with io.TextIOWrapper(stream, encoding="utf-8", errors="replace") as text:  # universal newlines
            for line in text:
                self.chunks[key].append(line)

    def finish(self, timeout_s: float) -> ProcResult:
        timed_out = True
        try:
            timed_out = not wait_until(self.proc, self.started + timeout_s)
        finally:  # a timeout, or Ctrl-C in a blocking caller: never leave the tree behind
            if timed_out:
                kill_tree(self.proc)
        for reader in self.readers:
            # A grandchild that inherited the pipe can keep it open: never wait forever.
            reader.join(timeout=5)
        return ProcResult(
            returncode=None if timed_out else self.proc.returncode,
            stdout="".join(self.chunks["out"]),
            stderr="".join(self.chunks["err"])[-_TAIL:],
            timed_out=timed_out,
            duration_s=round(_now() - self.started, 3),
        )


def run_capped(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
               timeout_s: float = 600.0, input_text: str | None = None) -> ProcResult:
    """Blocking run capped at ``timeout_s`` of wall-clock time; the tree is killed on timeout.
    ``input_text`` goes to the child's stdin as UTF-8 bytes, then stdin is closed."""
    return _Child(argv, cwd, env, input_text).finish(timeout_s)


async def arun_capped(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
                      timeout_s: float = 600.0, input_text: str | None = None) -> ProcResult:
    """``run_capped`` for coroutines: cancelling the awaiting task (an API stop, Ctrl-C) kills
    the whole tree at once, instead of leaving it running until its timeout, then re-raises."""
    child = _Child(argv, cwd, env, input_text)
    try:
        return await asyncio.to_thread(child.finish, timeout_s)
    except asyncio.CancelledError:
        # Synchronous on purpose: a second cancellation or a busy thread pool cannot stop it.
        kill_tree(child.proc)
        raise
