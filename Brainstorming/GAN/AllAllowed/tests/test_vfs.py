"""Tests for the virtual filesystem (W2, CONTRACTS section 5.1).

The vfs is the whole point of the scenario: a 700 home must be private, world-readable files must be
reachable only through a traversable path, and ``root`` must bypass every check. These tests pin those
guarantees down because an escalation attack only means something if the walls are real first.
"""

from __future__ import annotations

import pytest

from ala.errors import PathNotFound, PermissionDenied
from ala.kernel.vfs import Vfs
from ala.types import MODE_644, MODE_700, MODE_755, MODE_777, Perm, Role


def _fresh() -> Vfs:
    """A vfs with a world-writable ``/home`` so an owner can create its own home under it."""
    vfs = Vfs()
    vfs.makedirs("/home", "root", MODE_777)
    return vfs


# --- basic operations -------------------------------------------------------------------------------


def test_mkdir_then_listdir_shows_child() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_755)
    assert "seat-01" in vfs.listdir("/home", actor="seat-01", actor_role=Role.USER)


def test_write_then_read_roundtrip() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_755)
    vfs.write("/home/seat-01/note.txt", b"hello", actor="seat-01", actor_role=Role.USER)
    assert vfs.read("/home/seat-01/note.txt", actor="seat-01", actor_role=Role.USER) == b"hello"


def test_write_overwrites_existing_content() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_755)
    vfs.write("/home/seat-01/f", b"one", actor="seat-01", actor_role=Role.USER)
    vfs.write("/home/seat-01/f", b"two", actor="seat-01", actor_role=Role.USER)
    assert vfs.read("/home/seat-01/f", actor="seat-01", actor_role=Role.USER) == b"two"


def test_remove_deletes_the_file() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_755)
    vfs.write("/home/seat-01/f", b"x", actor="seat-01", actor_role=Role.USER)
    vfs.remove("/home/seat-01/f", actor="seat-01", actor_role=Role.USER)
    assert not vfs.exists("/home/seat-01/f")


def test_remove_missing_path_raises() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_755)
    with pytest.raises(PathNotFound):
        vfs.remove("/home/seat-01/ghost", actor="seat-01", actor_role=Role.USER)


def test_chmod_changes_mode_and_owner_may_do_it() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_755)
    vfs.write("/home/seat-01/f", b"x", actor="seat-01", actor_role=Role.USER)
    vfs.chmod("/home/seat-01/f", Perm(0o600), actor="seat-01", actor_role=Role.USER)
    assert vfs.stat("/home/seat-01/f").mode == Perm(0o600)


def test_listdir_is_sorted() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_755)
    for name in ("c", "a", "b"):
        vfs.write(f"/home/seat-01/{name}", b"", actor="seat-01", actor_role=Role.USER)
    assert vfs.listdir("/home/seat-01", actor="seat-01", actor_role=Role.USER) == ("a", "b", "c")


def test_exists_and_stat_do_not_require_permission() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_700)
    vfs.write("/home/seat-01/secret", b"x", actor="seat-01", actor_role=Role.USER)
    # An outsider cannot read it, but metadata reads never check permission.
    assert vfs.exists("/home/seat-01/secret")
    assert vfs.stat("/home/seat-01/secret").owner == "seat-01"


# --- permission denial ------------------------------------------------------------------------------


def test_non_owner_cannot_read_a_700_file() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_755)
    vfs.write("/home/seat-01/f", b"x", actor="seat-01", actor_role=Role.USER, mode=MODE_700)
    with pytest.raises(PermissionDenied):
        vfs.read("/home/seat-01/f", actor="seat-02", actor_role=Role.USER)


def test_non_owner_cannot_write_a_700_file() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_755)
    vfs.write("/home/seat-01/f", b"x", actor="seat-01", actor_role=Role.USER, mode=MODE_700)
    with pytest.raises(PermissionDenied):
        vfs.write("/home/seat-01/f", b"y", actor="seat-02", actor_role=Role.USER)


def test_non_owner_cannot_chmod() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_755)
    vfs.write("/home/seat-01/f", b"x", actor="seat-01", actor_role=Role.USER)
    with pytest.raises(PermissionDenied):
        vfs.chmod("/home/seat-01/f", Perm(0o777), actor="seat-02", actor_role=Role.USER)


def test_non_owner_cannot_create_under_a_700_dir() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_700)
    with pytest.raises(PermissionDenied):
        vfs.write("/home/seat-01/new", b"x", actor="seat-02", actor_role=Role.USER)


# --- directory traversal ----------------------------------------------------------------------------


def test_700_home_blocks_outsider_even_from_a_world_readable_file() -> None:
    """The core privacy guarantee: a world-readable file inside a 700 home is still unreachable to an
    outsider, because the outsider cannot traverse (execute) the private directory to get to it."""
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_700)
    vfs.write("/home/seat-01/open", b"public", actor="seat-01", actor_role=Role.USER, mode=MODE_777)
    with pytest.raises(PermissionDenied):
        vfs.read("/home/seat-01/open", actor="seat-02", actor_role=Role.USER)


def test_traversable_dir_lets_outsider_reach_a_readable_file() -> None:
    """The contrast case: with the execute bit on the directory, the world-readable file is reachable,
    proving traversal is what the 700 test actually blocks."""
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_755)
    vfs.write("/home/seat-01/open", b"public", actor="seat-01", actor_role=Role.USER, mode=MODE_777)
    assert vfs.read("/home/seat-01/open", actor="seat-02", actor_role=Role.USER) == b"public"


def test_listdir_of_a_700_dir_denied_to_outsider() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_700)
    with pytest.raises(PermissionDenied):
        vfs.listdir("/home/seat-01", actor="seat-02", actor_role=Role.USER)


# --- root bypass ------------------------------------------------------------------------------------


def test_root_reads_through_a_700_home() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_700)
    vfs.write("/home/seat-01/secret", b"top", actor="seat-01", actor_role=Role.USER)
    assert vfs.read("/home/seat-01/secret", actor="root", actor_role=Role.ROOT) == b"top"


def test_root_writes_a_file_it_does_not_own() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_700)
    vfs.write("/home/seat-01/f", b"x", actor="seat-01", actor_role=Role.USER, mode=MODE_644)
    vfs.write("/home/seat-01/f", b"edited", actor="root", actor_role=Role.ROOT)
    assert vfs.stat("/home/seat-01/f").content == b"edited"


def test_root_chmods_any_file() -> None:
    vfs = _fresh()
    vfs.mkdir("/home/seat-01", "seat-01", MODE_700)
    vfs.write("/home/seat-01/f", b"x", actor="seat-01", actor_role=Role.USER)
    vfs.chmod("/home/seat-01/f", Perm(0o777), actor="root", actor_role=Role.ROOT)
    assert vfs.stat("/home/seat-01/f").mode == Perm(0o777)


# --- path shape -------------------------------------------------------------------------------------


def test_relative_path_rejected() -> None:
    vfs = _fresh()
    with pytest.raises(PathNotFound):
        vfs.read("home/seat-01/f", actor="seat-01", actor_role=Role.USER)


def test_read_of_missing_file_raises() -> None:
    vfs = _fresh()
    with pytest.raises(PathNotFound):
        vfs.read("/home/seat-01/nope", actor="seat-01", actor_role=Role.USER)
