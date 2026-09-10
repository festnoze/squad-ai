"""The voice lock: one reader on the speakers at a time, across processes.

Run with:  python -m pytest tests -q   (from voice_bridge, any interpreter)
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
HOLDER = HERE / "_lock_holder.py"
sys.path.insert(0, str(HERE.parent))
import speak  # noqa: E402


_counter = 0


def launch(lock: Path, stamp: Path, hold: float, timeout: float, log: Path) -> subprocess.Popen:
    """Start a holder and return once it is about to queue for the lock."""
    global _counter
    _counter += 1
    name = str(_counter)
    proc = subprocess.Popen(
        [sys.executable, str(HOLDER), str(lock), str(stamp), str(hold), str(timeout), str(log), name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    ready = Path(f"{log}.ready.{name}")
    deadline = time.time() + 15
    while not ready.exists():
        assert time.time() < deadline, "holder never became ready"
        assert proc.poll() is None, proc.stderr.read().decode("utf-8", "replace")
        time.sleep(0.02)
    return proc


def read_log(log: Path) -> list[tuple[float, float, bool]]:
    rows = []
    for line in log.read_text(encoding="utf-8").splitlines():
        start, end, acquired = line.split()
        rows.append((float(start), float(end), acquired == "1"))
    return rows


def wait_all(procs: list[subprocess.Popen]) -> None:
    for proc in procs:
        _, err = proc.communicate(timeout=30)
        assert proc.returncode == 0, err.decode("utf-8", "replace")


def test_concurrent_readers_take_turns(tmp_path: Path) -> None:
    lock, stamp, log = tmp_path / "voice.lock", tmp_path / "stop.stamp", tmp_path / "log"
    procs = [launch(lock, stamp, hold=0.8, timeout=20, log=log) for _ in range(3)]
    wait_all(procs)

    rows = sorted(read_log(log))
    assert len(rows) == 3
    assert all(acquired for _, _, acquired in rows), "every reader got its turn"
    for (_, end_prev, _), (start_next, _, _) in zip(rows, rows[1:]):
        assert start_next >= end_prev - 0.05, "two holders overlapped"


def test_waiter_gives_up_after_timeout(tmp_path: Path) -> None:
    lock, stamp, log = tmp_path / "voice.lock", tmp_path / "stop.stamp", tmp_path / "log"
    first = launch(lock, stamp, hold=3.0, timeout=20, log=log)
    time.sleep(0.3)  # let the first one actually take the lock
    second = launch(lock, stamp, hold=0.1, timeout=0.5, log=log)
    wait_all([second])
    wait_all([first])

    rows = read_log(log)
    given_up = [row for row in rows if not row[2]]
    assert len(given_up) == 1, "the second reader gave up"
    assert given_up[0][1] < rows[-1][1] if rows[-1][2] else True


def test_zero_timeout_cancels_when_busy(tmp_path: Path) -> None:
    lock, stamp, log = tmp_path / "voice.lock", tmp_path / "stop.stamp", tmp_path / "log"
    first = launch(lock, stamp, hold=2.0, timeout=20, log=log)
    time.sleep(0.3)
    started = time.time()
    second = launch(lock, stamp, hold=0.1, timeout=0, log=log)
    wait_all([second])
    assert time.time() - started < 1.5, "a zero wait returns at once"
    wait_all([first])
    assert [row[2] for row in read_log(log)] == [False, True]


def test_stop_while_waiting_abandons_the_queue(tmp_path: Path) -> None:
    lock, stamp, log = tmp_path / "voice.lock", tmp_path / "stop.stamp", tmp_path / "log"
    first = launch(lock, stamp, hold=3.0, timeout=20, log=log)
    time.sleep(0.3)
    second = launch(lock, stamp, hold=0.1, timeout=20, log=log)
    time.sleep(0.3)  # the second one is now polling the lock
    stamp.touch()  # what --stop does
    wait_all([second])
    wait_all([first])

    rows = read_log(log)
    assert [row[2] for row in rows] == [False, True]
    assert rows[0][1] < rows[1][1], "the waiter left before the holder finished"


def test_lock_in_process_is_reentrant_per_file_handle(tmp_path: Path) -> None:
    """Two handles in one process still exclude each other (Windows semantics)."""
    lock = tmp_path / "voice.lock"
    speak.STOP_STAMP = tmp_path / "stop.stamp"
    first = speak.VoiceLock(lock)
    assert first.acquire(1)
    second = speak.VoiceLock(lock)
    assert not second.acquire(0.3)
    first.release()
    assert second.acquire(0.3)
    second.release()


def test_stop_stamp_is_touched_by_stop_playing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(speak, "STATE_DIR", tmp_path)
    monkeypatch.setattr(speak, "STOP_STAMP", tmp_path / "stop.stamp")
    monkeypatch.setattr(speak, "PID_FILE", tmp_path / "player.pid")
    monkeypatch.setattr(speak, "SEQ_FILE", tmp_path / "sequencer.pid")
    before = time.time() - 1
    speak.stop_playing()
    assert speak.stop_requested_since(before)
    assert not speak.stop_requested_since(time.time() + 1)
