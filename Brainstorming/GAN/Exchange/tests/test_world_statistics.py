"""FR-5.2.2 and FR-5.2.1 statistics of the world generator (A03).

Every test here is marked ``statistical`` and uses fixed seeds, so it is
deterministic: it either passes on every machine or fails on every machine. The
tolerances are stated in a comment next to the assertion, as CONTRACTS section
10 requires.

**These tests are built to be able to fail.** Two mechanisms:

* a *biased control*. The convergence check is factored into
  :func:`_max_absolute_deviation_ppm`, and the test applies it twice: once to
  the real generator, where it must pass, and once to a deliberately biased
  counter (the second half of :func:`_reference_and_biased`, which shifts every
  probability by ``BIAS_PPM`` before flipping the coin) where it must fail on
  every market.
  A tolerance wide enough to swallow the bias, or a comparison against a
  constant "roughly one half", would make the first assertion vacuous and the
  second one impossible.
* a *discrimination guard*. The reference the frequencies are compared to must
  itself be spread out (:data:`MIN_REFERENCE_SPREAD_PPM`), otherwise
  "frequency equals latent probability" would also hold for a generator that
  ignored the latent process and flipped a fair coin on every market.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence

import pytest

from pxe.rng import RngTree, randint
from pxe.types import Outcome
from pxe.world.generator import World, generate_world, outcome_frequency

pytestmark = pytest.mark.statistical

#: FR-5.2.2 says ten thousand draws, so the headline test draws ten thousand.
DRAWS = 10_000

#: Draws of the two secondary templates. The claim is the same, the sample is
#: smaller and the tolerance below is widened accordingly, which keeps the whole
#: file inside a few seconds.
SECONDARY_DRAWS = 1_200

#: Convergence tolerance of the headline test, in ppm. The standard error of a
#: Bernoulli mean over 10 000 draws is at most 0.5 / sqrt(10 000) = 5 000 ppm,
#: so 22 000 ppm is about 4.4 standard errors: tight enough that the 150 000 ppm
#: bias of the control fails it by a factor of seven, wide enough that no seed
#: flakes.
TOLERANCE_PPM = 22_000

#: Same reasoning at 1 200 draws: the standard error is 14 400 ppm and the
#: tolerance is about 3.5 of them.
SECONDARY_TOLERANCE_PPM = 50_000

#: The reference probabilities must span at least this much, or the comparison
#: has no discriminating power (see the module docstring).
MIN_REFERENCE_SPREAD_PPM = 120_000

#: Shift applied by the biased control. It is deliberately much larger than the
#: tolerance and much smaller than one, so the biased generator is still a
#: perfectly plausible looking world generator.
BIAS_PPM = 150_000

#: The reference is averaged over every fourth seed of the same sequence. The
#: mean of the latent probability has a standard error of
#: sd(p) / sqrt(2 500) = 150 000 / 50 = 3 000 ppm, an order of magnitude under
#: the tolerance, so sampling the reference costs nothing in rigour and saves
#: three quarters of the run time.
REFERENCE_STRIDE = 4


def _increments(world: World, latent_key: str) -> list[float]:
    """Return the per tick latent increments of one key, as floats.

    Args:
        world: The world holding the process.
        latent_key: Latent variable name.

    Returns:
        ``T`` increments, oldest first.
    """
    row = world.latent.values_milli[world.latent.keys.index(latent_key)]
    return [float(row[tick] - row[tick - 1]) for tick in range(1, len(row))]


def _reference_and_biased(
    template_id: str,
    *,
    seeds: Sequence[int],
    n_markets: int,
) -> tuple[dict[str, int], dict[str, int]]:
    """Return the mean latent probability and the biased YES frequency, per market.

    Both are computed in one pass over the same worlds, which is what keeps the
    statistical file fast enough to stay in the default suite.

    Args:
        template_id: Template under test.
        seeds: Seeds to draw, a subsequence of the ones ``outcome_frequency``
            used (documented in its docstring as ``base_seed + i``).
        n_markets: Number of markets per world.

    Returns:
        ``(mean_probability_ppm, biased_frequency_ppm)``, both keyed by market
        id, both non empty.
    """
    totals: dict[str, int] = {}
    biased_counts: dict[str, int] = {}
    for seed in seeds:
        world = generate_world(template_id=template_id, seed=seed, n_markets=n_markets)
        # A registered "test.*" substream (CONTRACTS section 3.3), so the control
        # cannot collide with any engine stream.
        control = RngTree(seed).fresh_substream("test.biased_control")
        for market in world.scenario.markets:
            probability = world.latent.probability_ppm(market.latent_key, market.resolution_tick)
            totals[market.market_id] = totals.get(market.market_id, 0) + probability
            biased = min(999_999, max(1, probability + BIAS_PPM))
            if randint(control, 0, 999_999) < biased:
                biased_counts[market.market_id] = biased_counts.get(market.market_id, 0) + 1
    count = len(seeds)
    reference = {market_id: total // count for market_id, total in totals.items()}
    biased_frequency = {
        market_id: (2 * biased_counts.get(market_id, 0) * 1_000_000 + count) // (2 * count) for market_id in totals
    }
    return reference, biased_frequency


def _max_absolute_deviation_ppm(frequency: Mapping[str, int], reference: Mapping[str, int]) -> int:
    """Return the largest absolute gap between a frequency and its reference.

    Args:
        frequency: Measured YES frequency in ppm, per market.
        reference: Mean latent probability in ppm, per market.

    Returns:
        The largest absolute difference, in ppm.

    Raises:
        AssertionError: If either mapping is empty or they disagree on the
            market set. That is the anti-vacuous guard: with no market the
            "maximum deviation" of an empty sequence would be zero and every
            convergence claim below would hold for free.
    """
    assert frequency, "no frequency was measured"
    assert reference, "no reference was computed"
    assert sorted(frequency) == sorted(reference), "frequency and reference cover different markets"
    return max(abs(frequency[market_id] - reference[market_id]) for market_id in sorted(frequency))


def test_frequency_converges() -> None:
    """FR-5.2.2: over 10 000 draws the YES frequency converges to the latent probability."""
    frequency = outcome_frequency("election", draws=DRAWS, base_seed=0, n_markets=5)
    assert frequency, "outcome_frequency returned nothing"
    assert len(frequency) == 5
    assert all(0 <= value <= 1_000_000 for value in frequency.values())

    seeds = range(0, DRAWS, REFERENCE_STRIDE)
    reference, biased = _reference_and_biased("election", seeds=list(seeds), n_markets=5)
    assert len(reference) == len(frequency)

    # Discrimination guard: the markets must not all sit at one half, or the
    # convergence claim would be satisfied by a fair coin.
    spread = max(reference.values()) - min(reference.values())
    assert spread >= MIN_REFERENCE_SPREAD_PPM, f"the reference is flat ({spread} ppm)"

    deviation = _max_absolute_deviation_ppm(frequency, reference)
    assert deviation <= TOLERANCE_PPM, f"frequency is {deviation} ppm off the latent probability"

    # The same check must reject a generator whose coin is biased by 150 000 ppm,
    # market by market. If this loop ever passes, the tolerance above stopped
    # measuring anything.
    biased_deviation = _max_absolute_deviation_ppm(biased, reference)
    assert biased_deviation > 4 * TOLERANCE_PPM, "the biased control was not detected at all"
    for market_id in sorted(reference):
        gap = abs(biased[market_id] - reference[market_id])
        assert gap > TOLERANCE_PPM, f"the biased control passed on {market_id} ({gap} ppm)"


@pytest.mark.parametrize(("template_id", "n_markets"), [("harvest", 4), ("league", 6)])
def test_frequency_converges_for_every_template(template_id: str, n_markets: int) -> None:
    """The same claim on the other two templates, at a smaller sample size."""
    frequency = outcome_frequency(template_id, draws=SECONDARY_DRAWS, base_seed=0, n_markets=n_markets)
    assert frequency, "outcome_frequency returned nothing"
    assert len(frequency) == n_markets

    reference, biased = _reference_and_biased(template_id, seeds=list(range(SECONDARY_DRAWS)), n_markets=n_markets)
    spread = max(reference.values()) - min(reference.values())
    assert spread >= MIN_REFERENCE_SPREAD_PPM, f"{template_id} reference is flat ({spread} ppm)"

    deviation = _max_absolute_deviation_ppm(frequency, reference)
    assert deviation <= SECONDARY_TOLERANCE_PPM, f"{template_id} is {deviation} ppm off"
    assert _max_absolute_deviation_ppm(biased, reference) > 2 * SECONDARY_TOLERANCE_PPM


def test_correlated_markets_resolve_together() -> None:
    """FR-5.2.1: a correlated group is correlated in its outcomes, not only in its prices."""
    draws = 1_500
    outcomes: dict[str, list[int]] = {}
    groups: dict[str, str] = {}
    for seed in range(draws):
        world = generate_world(template_id="election", seed=seed, n_markets=5)
        for market in world.scenario.markets:
            outcomes.setdefault(market.market_id, []).append(1 if world.outcome(market.market_id) is Outcome.YES else 0)
            groups[market.market_id] = market.correlation_group
    assert outcomes, "no outcome was drawn"
    assert all(len(series) == draws for series in outcomes.values())
    assert any(0 < sum(series) < draws for series in outcomes.values()), "every outcome is constant"

    market_ids = sorted(outcomes, key=lambda market_id: int(market_id[1:]))
    grouped: list[float] = []
    crossed: list[float] = []
    for position, left in enumerate(market_ids):
        for right in market_ids[position + 1 :]:
            correlation = statistics.correlation(
                [float(value) for value in outcomes[left]],
                [float(value) for value in outcomes[right]],
            )
            if groups[left] and groups[left] == groups[right]:
                grouped.append(correlation)
            else:
                crossed.append(correlation)
    assert grouped, "the world has no correlated pair"
    assert crossed, "the world has no independent pair to compare against"
    # Tolerance: measured over 1 500 draws the grouped pairs land near 0.27 and
    # the independent ones inside plus or minus 0.06 (the standard error of a
    # correlation over 1 500 points is about 0.026). Independent draws per
    # market would put every grouped pair in the crossed band, which is the
    # failure this test exists to catch.
    for correlation in grouped:
        assert correlation > 0.12, f"a correlated pair resolved independently ({correlation:.3f})"
    for correlation in crossed:
        assert abs(correlation) < 0.10, f"an independent pair is correlated ({correlation:.3f})"
    assert min(grouped) > max(crossed)


def test_declared_rho_matches_the_generated_paths() -> None:
    """The rho written into ``ScenarioSpec.correlations`` is the rho actually used."""
    deviations: list[float] = []
    for seed in range(1_000, 1_040):
        world = generate_world(template_id="league", seed=seed, n_markets=6)
        assert world.scenario.correlations, "no declared correlation"
        left, right, rho_milli = world.scenario.correlations[0]
        key_of = {market.market_id: market.latent_key for market in world.scenario.markets}
        measured = statistics.correlation(_increments(world, key_of[left]), _increments(world, key_of[right]))
        deviations.append(measured - rho_milli / 1000.0)
    assert len(deviations) == 40, "the sweep measured nothing"
    # Tolerance: one world gives 48 increments, so a single measurement has a
    # standard error near 0.09; the mean of forty is accurate to about 0.014.
    # A declared rho that was decorative rather than used would show up here as
    # a systematic offset of the size of rho itself.
    mean_deviation = statistics.mean(deviations)
    assert abs(mean_deviation) < 0.05, f"declared and measured rho disagree by {mean_deviation:.3f}"
