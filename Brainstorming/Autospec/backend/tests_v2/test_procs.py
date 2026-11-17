import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from autospec.core import procs
from autospec.core.procs import arun_capped, run_capped
from bench import proc as bench_proc

SLEEP_60 = [sys.executable, "-c", "import time; time.sleep(60)"]
# Writes "<child pid> <grandchild pid>" to argv[1], then both sleep: a plain kill of the
# child would leave the grandchild running.
WITH_GRANDCHILD = ("import os, subprocess, sys, time\n"
                   "grandchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                   "with open(sys.argv[1] + '.tmp', 'w') as handle:\n"
                   "    handle.write(f'{os.getpid()} {grandchild.pid}')\n"
                   "os.replace(sys.argv[1] + '.tmp', sys.argv[1])\n"
                   "time.sleep(120)\n")


def is_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def await_pids(path: Path, timeout_s: float = 30) -> list[int]:
    deadline = time.monotonic() + timeout_s
    while not path.is_file():
        assert time.monotonic() < deadline, f"{path} never appeared"
        await asyncio.sleep(0.1)
    return [int(pid) for pid in path.read_text(encoding="utf-8").split()]


def survivors(pids: list[int], within_s: float = 10) -> list[int]:
    """The pids still alive after ``within_s`` seconds (polled, returns as soon as all died)."""
    deadline = time.monotonic() + within_s
    while (alive := [pid for pid in pids if is_alive(pid)]) and time.monotonic() < deadline:
        time.sleep(0.2)
    return alive


def sleep_after(seconds: float, *, jump_s: float = 3600):
    """A wall clock on which the machine sleeps ``jump_s`` seconds, ``seconds`` from now."""
    wake = time.monotonic() + seconds
    real = time.time
    return lambda: real() + (jump_s if time.monotonic() >= wake else 0.0)


def test_captures_output_and_exit_code():
    result = run_capped([sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"],
                        timeout_s=30)
    assert result.returncode == 3
    assert result.stdout.strip() == "out"
    assert "err" in result.stderr
    assert not result.timed_out


def test_stdin_is_fed_then_closed():
    result = run_capped([sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
                        input_text="héllo\nworld", timeout_s=30)
    assert result.stdout.strip() == "HÉLLO\nWORLD"


def test_stdin_reaches_the_child_as_utf8_bytes_with_lf_newlines():
    """A text-mode stdin turned every LF into CRLF on Windows before it reached the CLI."""
    result = run_capped([sys.executable, "-c", "import sys; print(sys.stdin.buffer.read().hex())"],
                        input_text="é\nline 2\n", timeout_s=30)
    assert bytes.fromhex(result.stdout.strip()) == "é\nline 2\n".encode("utf-8")


def test_timeout_kills_the_whole_tree_quickly():
    # The child spawns a grandchild that would outlive a plain kill of its parent.
    code = ("import subprocess, sys, time;"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
            "time.sleep(60)")
    started = time.monotonic()
    result = run_capped([sys.executable, "-c", code], timeout_s=2)
    assert result.timed_out and result.returncode is None
    assert time.monotonic() - started < 20


def test_large_output_does_not_deadlock():
    result = run_capped([sys.executable, "-c", "print('x' * 2_000_000)"], timeout_s=30)
    assert len(result.stdout.strip()) == 2_000_000


def test_the_cap_is_wall_clock_time_a_machine_sleep_counts(monkeypatch):
    """Windows does not count sleep in Popen.wait timeouts: a 90 min cap never fired over 2.7 h."""
    monkeypatch.setattr(procs, "_now", sleep_after(1.0))
    started = time.monotonic()
    result = run_capped(SLEEP_60, timeout_s=600)
    assert result.timed_out and result.returncode is None
    assert time.monotonic() - started < 15
    assert result.duration_s >= 3600  # the wall-clock duration, sleep included


def test_wait_until_waits_for_the_deadline_without_a_clock_jump():
    child = subprocess.Popen(SLEEP_60)
    try:
        started = time.monotonic()
        assert not procs.wait_until(child, time.time() + 1.5)
        assert 1.4 <= time.monotonic() - started < 5
    finally:
        procs.kill_tree(child)
    assert procs.wait_until(child, time.time() + 5)  # already exited: True at once


# --------------------------------------------------------------------------- async + cancellation


async def test_arun_capped_behaves_like_run_capped():
    result = await arun_capped([sys.executable, "-c", "import sys; print(sys.stdin.read()[::-1]); sys.exit(4)"],
                               input_text="abc", timeout_s=30)
    assert (result.returncode, result.stdout.strip(), result.timed_out) == (4, "cba", False)
    timed_out = await arun_capped(SLEEP_60, timeout_s=1)
    assert timed_out.timed_out and timed_out.returncode is None


async def test_cancelling_arun_capped_kills_child_and_grandchild_at_once(tmp_path):
    pids_file = tmp_path / "pids.txt"
    task = asyncio.create_task(arun_capped([sys.executable, "-c", WITH_GRANDCHILD, str(pids_file)],
                                           timeout_s=600))
    pids = await await_pids(pids_file)
    started = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert survivors(pids) == [], "a cancelled run left its process tree running"
    assert time.monotonic() - started < 10


def interrupted_once_started(pids_file: Path):
    """A ``wait_until`` stand-in: Ctrl-C arrives once the child wrote its pids file."""
    def wait_until(proc, deadline):
        limit = time.monotonic() + 30
        while not pids_file.is_file() and time.monotonic() < limit:
            time.sleep(0.1)
        raise KeyboardInterrupt
    return wait_until


def test_an_interrupt_during_a_blocking_run_kills_the_tree(tmp_path, monkeypatch):
    """Ctrl-C reaching a blocking run_capped (scaffold, git) must not orphan its tree either."""
    pids_file = tmp_path / "pids.txt"
    monkeypatch.setattr(procs, "wait_until", interrupted_once_started(pids_file))
    with pytest.raises(KeyboardInterrupt):
        run_capped([sys.executable, "-c", WITH_GRANDCHILD, str(pids_file)], timeout_s=600)
    pids = [int(pid) for pid in pids_file.read_text(encoding="utf-8").split()]
    assert survivors(pids) == [], "an interrupted run left its process tree running"


async def test_a_missing_executable_still_raises_oserror():
    with pytest.raises(OSError):
        await arun_capped(["no-such-executable-7c1e"], timeout_s=5)


# --------------------------------------------------------------------------- bench copy


def test_bench_cap_is_wall_clock_time_too(monkeypatch):
    """The real case: a 90 min bench cap, the machine asleep for hours in the middle."""
    monkeypatch.setattr(bench_proc, "_now", sleep_after(1.0, jump_s=3 * 3600))
    started = time.monotonic()
    result = bench_proc.run(SLEEP_60, timeout_s=90 * 60)
    assert result.timed_out and result.returncode is None
    assert time.monotonic() - started < 20


def test_an_interrupt_during_a_bench_run_kills_the_tree(tmp_path, monkeypatch):
    """Ctrl-C on the bench must not orphan the factory: its own process group never sees it."""
    pids_file = tmp_path / "pids.txt"
    monkeypatch.setattr(bench_proc, "wait_until", interrupted_once_started(pids_file))
    with pytest.raises(KeyboardInterrupt):
        bench_proc.run([sys.executable, "-c", WITH_GRANDCHILD, str(pids_file)], timeout_s=600)
    pids = [int(pid) for pid in pids_file.read_text(encoding="utf-8").split()]
    assert survivors(pids) == [], "an interrupted bench run left its process tree running"


def test_bench_run_without_a_clock_jump_completes():
    result = bench_proc.run([sys.executable, "-c", "import sys; print(sys.stdin.read())"],
                            input_text="a\nb", timeout_s=30)
    assert not result.timed_out and result.returncode == 0
    assert result.stdout.replace("\r\n", "\n").strip() == "a\nb"
