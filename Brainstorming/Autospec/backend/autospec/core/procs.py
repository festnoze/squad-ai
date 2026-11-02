"""Run a child process with a hard wall-clock cap and kill its whole tree.

Windows does not kill grandchildren when a parent dies (uv -> python -> uvicorn,
npm -> node -> vite), so every timeout or stop goes through ``kill_tree``.
Only processes this module started are ever killed.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_TAIL = 20_000


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
    """Start a process in its own group so ``kill_tree`` can reach every descendant.

    Python descendants are forced to UTF-8 I/O: on Windows they would otherwise
    decode our UTF-8 pipes with the ANSI code page and mangle accented text.
    """
    env = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", **(os.environ if env is None else env)}
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(argv, cwd=cwd, env=env, stdin=stdin, stdout=stdout,
                            stderr=stderr, encoding="utf-8", errors="replace", **kwargs)


def run_capped(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
               timeout_s: float = 600.0, input_text: str | None = None) -> ProcResult:
    """Blocking run. Output is drained by threads so a full pipe never stalls the child.

    ``input_text`` is written to the child's stdin, which is then closed.
    """
    started = time.monotonic()
    proc = popen(argv, cwd=cwd, env=env,
                 stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL)
    chunks: dict[str, list[str]] = {"out": [], "err": []}

    def feed() -> None:
        try:
            proc.stdin.write(input_text)
            proc.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass

    if input_text is not None:
        threading.Thread(target=feed, daemon=True).start()

    def drain(stream, key: str) -> None:
        for line in iter(stream.readline, ""):
            chunks[key].append(line)
        stream.close()

    readers = [threading.Thread(target=drain, args=(proc.stdout, "out"), daemon=True),
               threading.Thread(target=drain, args=(proc.stderr, "err"), daemon=True)]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_tree(proc)
    for reader in readers:
        # A grandchild that inherited the pipe can keep it open: never wait forever.
        reader.join(timeout=5)
    return ProcResult(
        returncode=None if timed_out else proc.returncode,
        stdout="".join(chunks["out"]),
        stderr="".join(chunks["err"])[-_TAIL:],
        timed_out=timed_out,
        duration_s=round(time.monotonic() - started, 3),
    )
