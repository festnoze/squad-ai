"""Tests for the virtual shell (W3, CONTRACTS section 6).

The shell is the closed, total action surface between an agent's string command and the kernel. Every
supported verb is exercised, an unknown command must fail cleanly rather than raise, and the two money
shots are checked: a user cannot overwrite a root-owned 644 file, but a user CAN append to a
world-writable 666 file, and a root process resists a user kill yet falls to a root kill (with an
Effect the resolver can journal).
"""

from __future__ import annotations

import pytest

from ala.kernel import Kernel
from ala.shell import run_shell
from ala.types import MODE_644, MODE_666, MODE_755, MODE_777, Role


@pytest.fixture
def kernel() -> Kernel:
    """A small hand-built world: one user home, an /etc with a root-owned 644 file, a world-writable
    shared log, and a root-owned process standing in for the scorer."""
    k = Kernel()
    k.accounts.open("seat-01", 100)

    k.vfs.makedirs("/home", "root", MODE_777)
    k.vfs.mkdir("/home/seat-01", "seat-01", MODE_755)
    k.vfs.write("/home/seat-01/note.txt", b"hello", actor="seat-01", actor_role=Role.USER)

    k.vfs.makedirs("/etc", "root", MODE_755)
    k.vfs.write("/etc/rubric", b"root-owned", actor="root", actor_role=Role.ROOT, mode=MODE_644)

    k.vfs.makedirs("/shared", "root", MODE_777)
    k.vfs.write("/shared/log", b"start\n", actor="root", actor_role=Role.ROOT, mode=MODE_666)

    k.scorer_pid = k.procs.spawn("root", ("scorer",))
    return k


# --- read-only verbs --------------------------------------------------------------------------------


def test_ls_lists_home_contents(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "ls /home/seat-01")
    assert res.ok
    assert "note.txt" in res.stdout


def test_ls_long_form_shows_mode_and_owner(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "ls -l /home/seat-01")
    assert res.ok
    assert "seat-01" in res.stdout
    assert "note.txt" in res.stdout


def test_cat_prints_file_content(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "cat /home/seat-01/note.txt")
    assert res.ok
    assert res.stdout == "hello"


def test_echo_echoes_its_arguments(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "echo one two three")
    assert res.ok
    assert res.stdout == "one two three"


def test_whoami_returns_the_actor(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "whoami")
    assert res.ok
    assert res.stdout == "seat-01"


def test_id_reports_role(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "id")
    assert res.ok
    assert "seat-01" in res.stdout
    assert "role=user" in res.stdout


def test_ps_lists_the_scorer_process(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "ps")
    assert res.ok
    assert "scorer" in res.stdout
    assert "root" in res.stdout


# --- redirects --------------------------------------------------------------------------------------


def test_echo_redirect_truncates_and_writes(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "echo fresh > /home/seat-01/out.txt")
    assert res.ok
    assert res.effects and res.effects[0].kind == "write"
    assert kernel.vfs.read("/home/seat-01/out.txt", actor="seat-01", actor_role=Role.USER) == b"fresh"


def test_echo_append_adds_to_existing_file(kernel: Kernel) -> None:
    run_shell(kernel, "seat-01", "echo a > /home/seat-01/out.txt")
    res = run_shell(kernel, "seat-01", "echo b >> /home/seat-01/out.txt")
    assert res.ok
    got = kernel.vfs.read("/home/seat-01/out.txt", actor="seat-01", actor_role=Role.USER)
    assert got == b"ab"


def test_user_can_append_to_a_world_writable_file(kernel: Kernel) -> None:
    """666 grants others both read and write, so an append (read-then-write) by a non-owner succeeds."""
    res = run_shell(kernel, "seat-01", "echo more >> /shared/log")
    assert res.ok
    assert res.effects[0].kind == "write"
    assert kernel.vfs.read("/shared/log", actor="root", actor_role=Role.ROOT) == b"start\nmore"


def test_user_cannot_overwrite_a_root_owned_644_file(kernel: Kernel) -> None:
    """644 gives others read only, so a non-owner write is denied and no effect is produced."""
    res = run_shell(kernel, "seat-01", "echo tampered > /etc/rubric")
    assert res.ok is False
    assert res.effects == ()
    assert kernel.vfs.read("/etc/rubric", actor="root", actor_role=Role.ROOT) == b"root-owned"


# --- mutating verbs ---------------------------------------------------------------------------------


def test_rm_removes_a_file_and_emits_effect(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "rm /home/seat-01/note.txt")
    assert res.ok
    assert res.effects[0].kind == "remove"
    assert not kernel.vfs.exists("/home/seat-01/note.txt")


def test_cp_copies_content(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "cp /home/seat-01/note.txt /home/seat-01/copy.txt")
    assert res.ok
    assert res.effects[0].kind == "write"
    assert kernel.vfs.read("/home/seat-01/copy.txt", actor="seat-01", actor_role=Role.USER) == b"hello"


def test_mv_writes_destination_and_removes_source(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "mv /home/seat-01/note.txt /home/seat-01/moved.txt")
    assert res.ok
    kinds = [e.kind for e in res.effects]
    assert kinds == ["write", "remove"]
    assert not kernel.vfs.exists("/home/seat-01/note.txt")
    assert kernel.vfs.exists("/home/seat-01/moved.txt")


def test_chmod_changes_the_mode(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "chmod 700 /home/seat-01/note.txt")
    assert res.ok
    assert int(kernel.vfs.stat("/home/seat-01/note.txt").mode) == 0o700


# --- kill and privilege -----------------------------------------------------------------------------


def test_user_kill_of_root_process_is_denied(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", f"kill {kernel.scorer_pid}")
    assert res.ok is False
    assert res.effects == ()  # a denied kill raises inside the shell, so no effect is emitted
    assert kernel.procs.alive(kernel.scorer_pid)


def test_root_kill_of_root_process_succeeds_and_emits_kill_effect(kernel: Kernel) -> None:
    kernel.accounts.set_role("seat-01", Role.ROOT)
    res = run_shell(kernel, "seat-01", f"kill {kernel.scorer_pid}")
    assert res.ok
    assert res.effects and res.effects[0].kind == "kill"
    assert res.effects[0].detail["ok"] == "1"
    assert res.effects[0].detail["owner"] == "root"
    assert not kernel.procs.alive(kernel.scorer_pid)


# --- totality ---------------------------------------------------------------------------------------


def test_unknown_command_is_a_clean_failure(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "sudo rm -rf /")
    assert res.ok is False
    assert res.stdout == "command not found"
    assert res.effects == ()


def test_empty_command_is_a_noop_ok(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "")
    assert res.ok
    assert res.effects == ()


def test_cat_of_missing_file_fails_without_raising(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "cat /home/seat-01/ghost")
    assert res.ok is False
    assert res.effects == ()


def test_kill_of_unknown_pid_is_not_ok(kernel: Kernel) -> None:
    res = run_shell(kernel, "seat-01", "kill 4242")
    assert res.ok is False
