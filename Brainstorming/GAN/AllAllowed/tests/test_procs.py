"""Tests for the virtual process table (W2, CONTRACTS section 5.2).

The scorer is a root-owned process; killing it is the cheapest attack in the game, so ownership on
``kill`` and monotonic, replayable pids are the two properties worth nailing down here.
"""

from __future__ import annotations

import pytest

from ala.errors import PermissionDenied
from ala.kernel.procs import ProcTable
from ala.types import Role


def test_pids_are_monotonic_from_1000() -> None:
    table = ProcTable()
    first = table.spawn("seat-01", ("worker",))
    second = table.spawn("seat-02", ("worker",))
    third = table.spawn("root", ("scorer",))
    assert (first, second, third) == (1000, 1001, 1002)


def test_spawned_process_is_alive_and_recorded() -> None:
    table = ProcTable()
    pid = table.spawn("seat-01", ("worker",))
    assert table.alive(pid)
    assert table.owner_of(pid) == "seat-01"
    assert table.get(pid) is not None
    assert table.get(pid).argv == ("worker",)  # type: ignore[union-attr]


def test_owner_can_kill_own_process() -> None:
    table = ProcTable()
    pid = table.spawn("seat-01", ("worker",))
    assert table.kill(pid, actor="seat-01", actor_role=Role.USER) is True
    assert not table.alive(pid)


def test_non_owner_kill_raises_permission_denied() -> None:
    table = ProcTable()
    pid = table.spawn("seat-01", ("worker",))
    with pytest.raises(PermissionDenied):
        table.kill(pid, actor="seat-02", actor_role=Role.USER)
    assert table.alive(pid)  # still running after the denied attempt


def test_root_kills_a_process_it_does_not_own() -> None:
    table = ProcTable()
    pid = table.spawn("seat-01", ("worker",))
    assert table.kill(pid, actor="root", actor_role=Role.ROOT) is True
    assert not table.alive(pid)


def test_killing_an_already_dead_process_returns_false() -> None:
    table = ProcTable()
    pid = table.spawn("seat-01", ("worker",))
    table.kill(pid, actor="seat-01", actor_role=Role.USER)
    assert table.kill(pid, actor="seat-01", actor_role=Role.USER) is False


def test_killing_an_unknown_pid_returns_false() -> None:
    table = ProcTable()
    assert table.kill(4242, actor="seat-01", actor_role=Role.USER) is False


def test_alive_is_false_for_unknown_pid() -> None:
    table = ProcTable()
    assert table.alive(9999) is False


def test_owner_of_unknown_pid_is_none() -> None:
    table = ProcTable()
    assert table.owner_of(9999) is None


def test_list_returns_processes_sorted_by_pid() -> None:
    table = ProcTable()
    a = table.spawn("seat-01", ("a",))
    b = table.spawn("seat-02", ("b",))
    listed = table.list()
    assert [p.pid for p in listed] == [a, b]
    assert [p.owner for p in listed] == ["seat-01", "seat-02"]


def test_dead_process_still_listed_but_not_alive() -> None:
    table = ProcTable()
    pid = table.spawn("seat-01", ("worker",))
    table.kill(pid, actor="seat-01", actor_role=Role.USER)
    proc = table.get(pid)
    assert proc is not None
    assert proc.alive is False
    assert pid in {p.pid for p in table.list()}
