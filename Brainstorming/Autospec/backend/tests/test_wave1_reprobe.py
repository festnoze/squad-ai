"""Tests for WORKFLOW_REVIEW P7: the resume wait re-probes the usage window.

``session_monitor.await_window`` sleeps until the estimated reset epoch, but
wakes every ``reprobe_s`` seconds to ask ccusage for a fresher estimate. The
conservative fallback (``RESUME_FALLBACK_MIN``) can therefore be cut short when
the window reopens earlier than feared, while a later or failing probe never
extends the wait.

The clock, the sleep and the probe are injected, so nothing here touches the
wall clock.
"""

import pytest
from autospec.orchestrator import session_monitor


class FakeClock:
    """Virtual clock: every awaited sleep advances it by the slept duration."""

    def __init__(self, start: float = 1_000_000.0):
        self.now = start
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    async def asleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay


def _probe_returning(*values):
    """Async probe replaying `values`; an Exception instance is raised."""
    queue = list(values)
    calls: list[int] = []

    async def _probe():
        calls.append(1)
        value = queue.pop(0) if queue else None
        if isinstance(value, Exception):
            raise value
        return value

    _probe.calls = calls
    return _probe


# ------------------------------------------------------------ no re-probing

async def test_await_window_without_reprobe_sleeps_once():
    clock = FakeClock()
    target = clock.now + 3600
    probe = _probe_returning(clock.now + 10)

    effective = await session_monitor.await_window(
        target, reprobe_s=0, clock=clock.time, sleep=clock.asleep, probe=probe
    )

    assert effective == target
    assert clock.sleeps == [3600]
    assert probe.calls == []  # re-probing disabled: ccusage is never called


async def test_await_window_negative_reprobe_also_disables():
    clock = FakeClock()
    target = clock.now + 120

    effective = await session_monitor.await_window(
        target, reprobe_s=-5, clock=clock.time, sleep=clock.asleep
    )

    assert effective == target
    assert clock.sleeps == [120]


# ------------------------------------------------------------ earlier window

async def test_await_window_shortens_on_closer_estimate():
    clock = FakeClock()
    start = clock.now
    target = start + 3600  # conservative fallback: one hour
    # First wake (t+600): ccusage says the block ends at t+900.
    probe = _probe_returning(start + 900, start + 900)

    effective = await session_monitor.await_window(
        target, reprobe_s=600, clock=clock.time, sleep=clock.asleep, probe=probe
    )

    assert effective == start + 900
    assert clock.sleeps == [600, 300]  # full slice, then the shortened remainder
    assert clock.now == start + 900
    assert len(probe.calls) == 1  # the last slice lands on the target: no probe


async def test_await_window_can_shorten_twice():
    clock = FakeClock()
    start = clock.now
    probe = _probe_returning(start + 1800, start + 700)

    effective = await session_monitor.await_window(
        start + 3600, reprobe_s=300, clock=clock.time, sleep=clock.asleep, probe=probe
    )

    assert effective == start + 700
    assert clock.sleeps == [300, 300, 100]
    assert clock.now == start + 700


# -------------------------------------------------- never extends / swallows

@pytest.mark.parametrize(
    "value",
    [
        7200.0,  # a LATER estimate (offset applied below)
        None,  # no active block
        0.0,  # probe knows nothing usable
        -10.0,  # an estimate already in the past
    ],
)
async def test_await_window_never_extends(value):
    clock = FakeClock()
    start = clock.now
    later = None if value is None else (start + value if value > 100 else value)
    probe = _probe_returning(later, later, later, later)

    effective = await session_monitor.await_window(
        start + 1200, reprobe_s=600, clock=clock.time, sleep=clock.asleep, probe=probe
    )

    assert effective == start + 1200
    assert clock.sleeps == [600, 600]
    assert clock.now == start + 1200


async def test_await_window_swallows_probe_errors():
    clock = FakeClock()
    start = clock.now
    probe = _probe_returning(RuntimeError("ccusage exploded"), start + 1500)

    effective = await session_monitor.await_window(
        start + 1800, reprobe_s=600, clock=clock.time, sleep=clock.asleep, probe=probe
    )

    # First probe raised (kept the target), second one shortened it.
    assert effective == start + 1500
    assert clock.sleeps == [600, 600, 300]
    assert len(probe.calls) == 2


async def test_await_window_stale_estimate_in_the_past_is_ignored():
    clock = FakeClock()
    start = clock.now
    # A probe answering "the window reopened 10 minutes ago" is not a future
    # estimate: it is stale data, so the target must stay untouched.
    probe = _probe_returning(start - 600, start - 600)

    effective = await session_monitor.await_window(
        start + 1200, reprobe_s=600, clock=clock.time, sleep=clock.asleep, probe=probe
    )

    assert effective == start + 1200
    assert clock.sleeps == [600, 600]


# ------------------------------------------------------------ already elapsed

async def test_await_window_returns_immediately_when_target_passed():
    clock = FakeClock()
    target = clock.now - 1

    effective = await session_monitor.await_window(
        target, reprobe_s=600, clock=clock.time, sleep=clock.asleep
    )

    assert effective == target
    assert clock.sleeps == []
    assert clock.now == 1_000_000.0


async def test_await_window_returns_immediately_at_exact_target():
    clock = FakeClock()
    effective = await session_monitor.await_window(
        clock.now, reprobe_s=0, clock=clock.time, sleep=clock.asleep
    )
    assert effective == clock.now
    assert clock.sleeps == []


# ------------------------------------------------------------ default probe

async def test_await_window_defaults_to_ccusage_probe(monkeypatch):
    clock = FakeClock()
    start = clock.now
    calls: list[int] = []

    async def _fake_block_reset():
        calls.append(1)
        return start + 800

    monkeypatch.setattr(session_monitor, "aget_block_reset", _fake_block_reset)

    effective = await session_monitor.await_window(
        start + 3600, reprobe_s=600, clock=clock.time, sleep=clock.asleep
    )

    assert effective == start + 800
    assert calls == [1]
    assert clock.sleeps == [600, 200]
