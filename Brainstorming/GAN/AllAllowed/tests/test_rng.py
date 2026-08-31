"""Tests for the named random tree (W0, CONTRACTS section 3.1).

Why these: determinism (AC-1) rests entirely on the RngTree. If a substream stopped being a pure
function of ``(seed, name)``, or if an unregistered name were silently tolerated, a stray source of
entropy could leak into the engine and break byte-reproducibility without any obvious symptom.
"""

from __future__ import annotations

import pytest

from ala.errors import RngError
from ala.rng import RngTree


def _draws(rng, n: int = 8) -> list[float]:
    return [rng.random() for _ in range(n)]


def test_same_seed_and_name_give_the_same_sequence() -> None:
    a = RngTree(42).substream("world")
    b = RngTree(42).substream("world")
    assert _draws(a) == _draws(b)


def test_different_names_diverge() -> None:
    tree = RngTree(42)
    world = _draws(tree.substream("world"))
    tasks = _draws(tree.substream("tasks"))
    assert world != tasks


def test_different_seeds_diverge() -> None:
    a = RngTree(42).substream("world")
    b = RngTree(43).substream("world")
    assert _draws(a) != _draws(b)


def test_substream_is_cached_and_stateful() -> None:
    """A second request for the same name returns the same object, so draws keep advancing rather than
    restarting; that is what makes a whole match consume one coherent stream per name."""
    tree = RngTree(42)
    first = tree.substream("world")
    same = tree.substream("world")
    assert first is same
    a = first.random()
    b = same.random()
    assert a != b  # the stream advanced; it did not reset


def test_unregistered_name_raises() -> None:
    tree = RngTree(42)
    with pytest.raises(RngError):
        tree.substream("not_a_real_stream")


def test_agent_prefix_is_accepted() -> None:
    tree = RngTree(42)
    rng = tree.substream("agent:seat-03")
    # Deterministic against a fresh tree with the same seat name.
    assert _draws(rng) == _draws(RngTree(42).substream("agent:seat-03"))


def test_registered_names_all_resolve() -> None:
    tree = RngTree(7)
    for name in ("world", "tasks", "sudoers_defect", "clone_mutation"):
        assert tree.substream(name) is not None


def test_seed_is_exposed_and_normalized() -> None:
    assert RngTree(42).seed == 42
