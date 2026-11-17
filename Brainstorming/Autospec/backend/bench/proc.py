"""Child processes with a hard wall-clock cap and whole-tree kill.

The bench keeps its own copy of these few helpers on purpose: it must not
depend on the code of the factories it measures.

Output goes to files, never to pipes: a grandchild that inherits a pipe
(uv -> python -> uvicorn) can keep it open after its parent died and stall the
reader forever.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_TAIL_CHARS = 200_000


@dataclass
class Result:
    returncode: int | None  # None when killed on timeout
    stdout: str
    stderr: str
    timed_out: bool
    duration_s: float


def popen(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL) -> subprocess.Popen:
    """Start a process in its own group so ``kill_tree`` reaches every descendant."""
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen([str(a) for a in argv], cwd=str(cwd) if cwd else None, env=env,
                            stdin=stdin, stdout=stdout, stderr=stderr, **kwargs)


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill ``proc`` and all its descendants (only processes the bench started)."""
    if proc.poll() is None:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def _read(handle) -> str:
    handle.flush()
    handle.seek(0)
    data = handle.read().decode("utf-8", errors="replace")
    return data[-_TAIL_CHARS:]


def run(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
        timeout_s: float = 60.0, input_text: str | None = None,
        stdout_path: Path | None = None, stderr_path: Path | None = None) -> Result:
    """Blocking run capped at ``timeout_s``; the whole tree is killed on timeout.

    ``stdout_path`` / ``stderr_path`` keep the streams on disk (long factory
    runs); otherwise anonymous temporary files are used.
    """
    started = time.monotonic()
    out = open(stdout_path, "w+b") if stdout_path else tempfile.TemporaryFile()
    err = open(stderr_path, "w+b") if stderr_path else tempfile.TemporaryFile()
    try:
        proc = popen(argv, cwd=cwd, env=env,
                     stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                     stdout=out, stderr=err)
        if input_text is not None:
            def feed() -> None:
                try:
                    proc.stdin.write(input_text.encode("utf-8"))
                    proc.stdin.close()
                except (BrokenPipeError, OSError, ValueError):
                    pass
            threading.Thread(target=feed, daemon=True).start()
        timed_out = False
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(proc)
        return Result(
            returncode=None if timed_out else proc.returncode,
            stdout=_read(out),
            stderr=_read(err),
            timed_out=timed_out,
            duration_s=round(time.monotonic() - started, 3),
        )
    except OSError as exc:  # executable not found, permission denied
        return Result(returncode=None, stdout="", stderr=f"{type(exc).__name__}: {exc}",
                      timed_out=False, duration_s=round(time.monotonic() - started, 3))
    finally:
        out.close()
        err.close()


def free_port() -> int:
    """A TCP port free on the loopback right now (best effort, may race)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def tail(text: str, limit: int = 1500) -> str:
    text = text or ""
    return text if len(text) <= limit else "..." + text[-limit:]
