"""Anchor tests for :mod:`pxe.rng` (A01).

The point of these tests is not statistical quality, it is that the exact
values never move. Every draw helper is implemented inside ``pxe.rng`` on top of
``getrandbits`` precisely so it is ours to pin (section 3.2, decision 18). The
frozen vectors below are the tripwire: if a CPython upgrade, a refactor or a
"harmless" reordering changes one of them, every golden journal hash has already
moved and this test says so first.
"""

import math
import random

import pytest

from pxe.errors import UnknownSubstreamError
from pxe.rng import (
    RNG_ALGORITHM_VERSION,
    RngTree,
    _exp,
    _log,
    _norm_ppf,
    _randbelow,
    bernoulli,
    beta,
    choice,
    choices_weighted,
    derive_seed,
    is_registered_substream,
    lognormal,
    normal,
    randint,
    random_open_unit,
    random_unit,
    sample_without_replacement,
    shuffle_seeded,
    uniform,
)

_PIN_SEED = 20260827


def _pinned() -> random.Random:
    return RngTree(_PIN_SEED).fresh_substream("test.scratch")


# --------------------------------------------------------------------------
# Frozen draw vectors
# --------------------------------------------------------------------------
@pytest.mark.determinism
def test_algorithm_version_is_pinned() -> None:
    assert RNG_ALGORITHM_VERSION == "1.0.0"


@pytest.mark.determinism
def test_shuffle_vector_is_frozen() -> None:
    seats = [f"A{i}" for i in range(1, 9)]
    assert shuffle_seeded(_pinned(), seats) == ["A4", "A2", "A5", "A7", "A6", "A1", "A8", "A3"]


@pytest.mark.determinism
def test_draw_vectors_are_frozen() -> None:
    rng = _pinned()
    assert random_unit(rng) == 0.29847304170906597
    assert normal(rng) == -1.317856766985275
    assert lognormal(rng) == 0.2247539223338069
    assert uniform(rng, -1.0, 1.0) == -0.3775122737060088
    assert beta(rng, 2.0, 5.0) == 0.4569872063458788
    assert randint(rng, 1, 100) == 9
    assert bernoulli(rng, 0.5) is False
    assert choice(rng, ("a", "b", "c")) == "b"
    assert sample_without_replacement(rng, [1, 2, 3, 4, 5], 3) == [2, 3, 1]
    assert choices_weighted(rng, ["x", "y", "z"], [1.0, 2.0, 3.0], k=5) == ["z", "z", "z", "y", "z"]


@pytest.mark.determinism
def test_derive_seed_is_frozen() -> None:
    assert derive_seed(0, "world.latent") == derive_seed(0, "world.latent")
    assert derive_seed(1, "world.latent") != derive_seed(0, "world.latent")
    assert RngTree(_PIN_SEED).seed_for("world.latent") == (
        35418504157793144283584494709040790594282982360247173759859788546071099070460
    )


# --------------------------------------------------------------------------
# The standard library generator is only used through getrandbits
# --------------------------------------------------------------------------
@pytest.mark.determinism
def test_helpers_consume_only_getrandbits() -> None:
    """A helper reaching for random(), shuffle() or gauss() would move on a
    CPython upgrade. Poison every one of them and check nothing notices."""

    class BitsOnly(random.Random):
        def random(self) -> float:  # pragma: no cover - must never be called
            raise AssertionError("random() is banned, use random_unit")

        def shuffle(self, x, random=None) -> None:  # type: ignore[override]  # pragma: no cover
            raise AssertionError("shuffle() is banned, use shuffle_seeded")

        def randrange(self, *args, **kwargs):  # type: ignore[override]  # pragma: no cover
            raise AssertionError("randrange() is banned, use randint")

        def gauss(self, *args, **kwargs):  # type: ignore[override]  # pragma: no cover
            raise AssertionError("gauss() is banned, use normal")

        def betavariate(self, *args, **kwargs):  # type: ignore[override]  # pragma: no cover
            raise AssertionError("betavariate() is banned, use beta")

    rng = BitsOnly(1234)
    shuffle_seeded(rng, list(range(10)))
    normal(rng)
    lognormal(rng)
    beta(rng, 2.0, 3.0)
    uniform(rng)
    bernoulli(rng, 0.25)
    randint(rng, 0, 9)
    choice(rng, "abcdef")
    choices_weighted(rng, [1, 2, 3], [1.0, 1.0, 1.0], k=3)


# --------------------------------------------------------------------------
# The pinned transcendentals are accurate enough to be used
# --------------------------------------------------------------------------
def test_log_matches_libm_to_a_few_ulp() -> None:
    for i in range(1, 5000):
        x = i / 97.0
        assert math.isclose(_log(x), math.log(x), rel_tol=1e-14, abs_tol=1e-14)


def test_exp_matches_libm_to_a_few_ulp() -> None:
    for i in range(-3000, 3000):
        x = i / 101.0
        assert math.isclose(_exp(x), math.exp(x), rel_tol=1e-14)


def test_norm_ppf_inverts_the_normal_cdf() -> None:
    for i in range(1, 1000):
        p = i / 1000.0
        x = _norm_ppf(p)
        cdf = 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
        assert abs(cdf - p) < 1e-8


def test_randbelow_covers_its_range() -> None:
    rng = _pinned()
    seen = {_randbelow(rng, 7) for _ in range(500)}
    assert seen == set(range(7))
    assert _randbelow(rng, 1) == 0
    with pytest.raises(ValueError):
        _randbelow(rng, 0)


def test_open_unit_is_never_zero() -> None:
    rng = _pinned()
    for _ in range(10_000):
        u = random_open_unit(rng)
        assert 0.0 < u < 1.0


# --------------------------------------------------------------------------
# Substream registry
# --------------------------------------------------------------------------
def test_tick_shuffle_is_registered_and_agent_order_is_not() -> None:
    assert is_registered_substream("runner.tick_shuffle.17")
    assert not is_registered_substream("runner.agent_order")
    assert not is_registered_substream("runner.tick_shuffle")


def test_unregistered_substream_raises() -> None:
    tree = RngTree(1)
    with pytest.raises(UnknownSubstreamError):
        tree.substream("world.not_a_thing")


@pytest.mark.determinism
def test_fresh_substream_does_not_depend_on_history() -> None:
    """FR-5.1.5: the tick shuffle must depend on (seed, tick) alone."""
    tree = RngTree(99)
    first = shuffle_seeded(tree.fresh_substream("runner.tick_shuffle.5"), ["A1", "A2", "A3", "A4"])
    drained = tree.substream("runner.tick_shuffle.4")
    for _ in range(1000):
        drained.getrandbits(32)
    second = shuffle_seeded(tree.fresh_substream("runner.tick_shuffle.5"), ["A1", "A2", "A3", "A4"])
    assert first == second


@pytest.mark.determinism
def test_shuffle_of_full_list_then_filter_is_stable() -> None:
    """Section 3.4: filtering after the shuffle keeps the permutation a
    function of (seed, tick) alone, whatever the frozen set is."""
    tree = RngTree(7)
    seats = ["A1", "A2", "A3", "A4", "A5", "A6"]
    permutation = shuffle_seeded(tree.fresh_substream("runner.tick_shuffle.3"), seats)
    for frozen in ({"A2"}, {"A1", "A6"}, set(), {"A3", "A4", "A5"}):
        again = shuffle_seeded(tree.fresh_substream("runner.tick_shuffle.3"), seats)
        assert again == permutation
        filtered = [a for a in again if a not in frozen]
        assert filtered == [a for a in permutation if a not in frozen]


def test_child_namespaces_do_not_collide() -> None:
    tree = RngTree(5)
    assert tree.child("world").seed_for("world.latent") != tree.child("info").seed_for("world.latent")
