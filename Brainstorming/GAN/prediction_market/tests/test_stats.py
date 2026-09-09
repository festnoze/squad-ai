"""E4: the block bootstrap, the paired bound, the permutation null and the candidate deflation.

What these tests are for, in the order of the package's done-when (PLAN_V2_WAVES, "E4 statistics") and of
CONTRACTS_V2 12.4:

* **A synthetic agent with a known skill gets an interval that contains it.** The agent here is built from
  a generating process whose population skill is arithmetic (state ``700_000`` on a market that resolves
  YES seven times in ten and the expected per-market skill is ``40_000`` micro), the outcomes are drawn
  from the run's own tree, and the assertion is coverage of that population number rather than of the
  sample mean the interval is centred on. A bound that could not contain the truth would be a bound
  nobody should claim with.
* **The shuffled null centres on zero.** Three agents make the statement sharp rather than approximate:
  the market follower, whose skill is exactly ``0`` on every market and under every shuffle, so the null
  is exactly ``0`` and the p-value exactly one; a coin-flip agent, whose observed mean sits in the middle
  of its own null; and a skilled agent, which no shuffle reaches (``p_value_ppm == 0``) and whose null
  lower bound is negative, which is part 4 of the bar in section 12.6.
* **Deflation widens with the candidate count.** Strictly, over five decades of ``K``, and the ``K = 1``
  case is pinned against ``statistics.NormalDist`` so the constant is the contract's and not a
  coincidence. The test that matters for PRD 2.6 is the last one: a positive undeflated bound turns
  negative once the family it was selected from is charged for.
* **Fewer than two blocks is the degenerate interval of ruling R68**, and an empty input is zeros rather
  than a ``ZeroDivisionError`` (the zero-denominator rule of section 12).
* **The block is the resample unit.** The same values grouped by week give a strictly wider interval than
  the same values one block per market: the interval that ignores correlation is the one that lies.
* **The continuous units of section 17.6 (ruling R190) permute realised signs, not scores**, inside a
  ``(block, bar key)`` group only: an unmatched forecast stays in place, a forecast in another block is
  never reachable, and the prices and the time weights of a binary call cannot change a continuous
  answer because neither enters the directional score.

Everything is offline, integer and deterministic: every draw comes from a ``pmx.rng`` substream, no test
reads a clock, and each interval is asserted twice from two trees built on one seed.
"""

from __future__ import annotations

from statistics import NormalDist

import pytest

from pmx.metrics.stats import (
    ALPHA_PPM,
    BOOTSTRAP_RESAMPLES,
    PERMUTATION_INNER_RESAMPLES,
    PERMUTATIONS,
    Interval,
    NullResult,
    _binary_skill_micro,
    block_key,
    bootstrap_lower_bound,
    deflated_lower_bound,
    iso_week_key,
    paired_lower_bound,
    permutation_null,
)
from pmx.rng import RngTree, bernoulli
from pmx.scoring import RANDOM_WALK_BRIER_MICRO as E3_RANDOM_WALK_BRIER_MICRO
from pmx.scoring import ForecastBar, bar_weights_ms, directional_brier_micro, skill_micro
from pmx.types import (
    MS_PER_DAY,
    MS_PER_HOUR,
    PPM_ONE,
    MarketMeta,
    brier_micro,
    ms_from_iso_date,
    ppm_from_bp,
    round_half_up,
)

SEED = 20_260_908

#: The random walk's Brier and the constant the follower's market states, both pinned by section 17.5.
RANDOM_WALK_BRIER_MICRO = 250_000
FIFTY_FIFTY_PPM = 500_000


def _tree() -> RngTree:
    """The statistics tree of a run: the same seed gives the same integers (section 6.4)."""
    return RngTree(SEED).child("stats")


def _meta(
    market_id: str,
    *,
    event_key: str | None = None,
    resolved_at_ms: int = 0,
    provider: str = "kalshi",
) -> MarketMeta:
    """A leak-free market projection with the three fields ``block_key`` reads and defaults elsewhere."""
    return MarketMeta(
        id=market_id,
        provider=provider,
        category="politics",
        tags=(),
        event_key=event_key,
        created_at_ms=0,
        close_at_ms=resolved_at_ms,
        resolved_at_ms=resolved_at_ms,
        resolution=1,
        interval_min=1_440,
        n_bars=10,
        hardness_tags=(),
        fee_schedule_id="demo-zero",
        fold="train",
    )


# --------------------------------------------------------------------------------------------------
# The declared constants and payload shapes
# --------------------------------------------------------------------------------------------------
def test_constants_are_the_contract_numbers() -> None:
    """Section 12.4's four numbers. A resample count that drifts moves every claim in the product."""
    assert BOOTSTRAP_RESAMPLES == 10_000
    assert PERMUTATIONS == 1_000
    assert PERMUTATION_INNER_RESAMPLES == 200
    assert ALPHA_PPM == 50_000


def test_the_directional_baseline_is_e3s_and_not_a_second_spelling() -> None:
    """Section 17.5 gives the continuous score one owner: ``pmx.scoring``. The statistics rescore a
    permutation, they never define a loss, so the constant this file pins from the contract and the one
    E4 rescores against have to be the same integer and the tie rule has to be E3's."""
    assert RANDOM_WALK_BRIER_MICRO == E3_RANDOM_WALK_BRIER_MICRO == 250_000
    assert directional_brier_micro(FIFTY_FIFTY_PPM, 0) == RANDOM_WALK_BRIER_MICRO
    assert directional_brier_micro(700_000, 1) == 90_000
    assert directional_brier_micro(700_000, -1) == 490_000
    assert directional_brier_micro(700_000, 0) == 290_000


def test_interval_to_dict_is_seven_integers() -> None:
    """The payload of a claim, a leaderboard row and a model card (section 12.11): no float anywhere."""
    interval = Interval(point=1, lower=-2, upper=3, sd=4, n=5, n_blocks=6, resamples=7)
    payload = interval.to_dict()
    assert payload == {"point": 1, "lower": -2, "upper": 3, "sd": 4, "n": 5, "n_blocks": 6, "resamples": 7}
    assert all(isinstance(value, int) and not isinstance(value, bool) for value in payload.values())


def test_null_result_to_dict_is_three_integers() -> None:
    """The ``null`` block of a claim file (section 12.8)."""
    payload = NullResult(null_lb_micro=-5, p_value_ppm=120_000, permutations=1_000).to_dict()
    assert payload == {"null_lb_micro": -5, "p_value_ppm": 120_000, "permutations": 1_000}
    assert all(isinstance(value, int) and not isinstance(value, bool) for value in payload.values())


# --------------------------------------------------------------------------------------------------
# The block key
# --------------------------------------------------------------------------------------------------
def test_iso_week_key_is_the_iso_week_and_not_the_calendar_year() -> None:
    """1 January 2027 falls in ISO week 53 of 2026, and a block key that read the calendar year would
    split one week into two blocks across the new year."""
    assert iso_week_key(ms_from_iso_date("2026-01-01")) == "w2026-01"
    assert iso_week_key(ms_from_iso_date("2026-06-15")) == "w2026-25"
    assert iso_week_key(ms_from_iso_date("2026-12-31")) == "w2026-53"
    assert iso_week_key(ms_from_iso_date("2027-01-01")) == "w2026-53"
    assert iso_week_key(ms_from_iso_date("2027-01-04")) == "w2027-01"


def test_iso_week_key_is_constant_inside_a_utc_day() -> None:
    """A block is a week, so the hour of the resolution never changes it."""
    monday = ms_from_iso_date("2026-06-15")
    assert {iso_week_key(monday + hour * MS_PER_HOUR) for hour in range(24)} == {"w2026-25"}


def test_block_key_falls_back_to_the_resolution_week() -> None:
    """No cluster and no event key: the week the market resolved in (section 12.4)."""
    market = _meta("kalshi-A", resolved_at_ms=ms_from_iso_date("2026-06-17"))
    assert block_key(market) == "w2026-25"


def test_block_key_prefers_the_event_key_to_the_week() -> None:
    """Two markets of one event are one draw even when they resolve in different weeks."""
    first = _meta("kalshi-A", event_key="KXSENATEGA-26", resolved_at_ms=ms_from_iso_date("2026-06-17"))
    second = _meta("kalshi-B", event_key="KXSENATEGA-26", resolved_at_ms=ms_from_iso_date("2026-06-24"))
    assert block_key(first) == block_key(second) == "KXSENATEGA-26"


def test_block_key_prefers_the_cluster_to_the_event_and_the_week() -> None:
    """Amendment C1's ruling R118: two venues quoting one event are one block, and the argument ships in
    wave 2 so that R1b only has to fill it in wave 7."""
    kalshi = _meta("kalshi-A", event_key="KXSENATEGA-26", resolved_at_ms=ms_from_iso_date("2026-06-17"))
    manifold = _meta("manifold-b", provider="manifold", resolved_at_ms=ms_from_iso_date("2026-07-01"))
    cluster = "ec-3efdba7ed46ae9e4"
    assert block_key(kalshi, cluster_id=cluster) == cluster
    assert block_key(manifold, cluster_id=cluster) == cluster
    assert block_key(kalshi, cluster_id=None) != block_key(manifold, cluster_id=None)


def test_block_key_of_a_continuous_cell_is_the_cells_own_week() -> None:
    """Ruling R186: an instrument does not resolve, so a row's block is the week of its
    ``(instrument, week)`` cell, which the caller builds with the one spelling this module exports."""
    instrument = _meta("binance-btcusdt-perp", resolved_at_ms=ms_from_iso_date("2026-12-31"))
    first_cell = iso_week_key(ms_from_iso_date("2026-06-15"))
    second_cell = iso_week_key(ms_from_iso_date("2026-06-22"))
    assert first_cell != second_cell
    assert block_key(instrument) == "w2026-53"
    assert (first_cell, second_cell) == ("w2026-25", "w2026-26")


# --------------------------------------------------------------------------------------------------
# The block bootstrap
# --------------------------------------------------------------------------------------------------
def _synthetic_agent(
    *,
    n_markets: int = 200,
    n_blocks: int = 20,
    agent_ppm: int = 700_000,
    yes_rate: float = 0.7,
) -> tuple[list[int], list[int], list[int], list[str]]:
    """A stated-probability agent against a market stuck at ``500_000``, outcomes drawn from the tree.

    Returns the per-market skill, the market's Brier, the agent's Brier and the block keys. With
    ``agent_ppm = 700_000`` and a seven-in-ten YES rate the **population** per-market skill is
    ``250_000 - (0.7 * 90_000 + 0.3 * 490_000) = 40_000`` micro-units, which is the number the interval
    has to contain.
    """
    draw = RngTree(SEED).substream("test.scratch")
    skills: list[int] = []
    market_briers: list[int] = []
    agent_briers: list[int] = []
    blocks: list[str] = []
    for index in range(n_markets):
        outcome = 1 if bernoulli(draw, yes_rate) else 0
        agent = brier_micro(agent_ppm, outcome)
        market = brier_micro(FIFTY_FIFTY_PPM, outcome)
        skills.append(market - agent)
        market_briers.append(market)
        agent_briers.append(agent)
        blocks.append(f"w2026-{index % n_blocks + 1:02d}")
    return skills, market_briers, agent_briers, blocks


def test_bootstrap_interval_contains_the_known_skill() -> None:
    """The done-when: the interval of a synthetic agent covers the skill of the process that made it."""
    population_skill = RANDOM_WALK_BRIER_MICRO - round_half_up(7 * 90_000 + 3 * 490_000, 10)
    assert population_skill == 40_000
    skills, _market, _agent, blocks = _synthetic_agent()
    interval = bootstrap_lower_bound(skills, blocks, rng=_tree())
    assert interval.lower <= population_skill <= interval.upper
    assert interval.lower < interval.point < interval.upper
    assert interval.point == round_half_up(sum(skills), len(skills))
    assert (interval.n, interval.n_blocks, interval.resamples) == (200, 20, BOOTSTRAP_RESAMPLES)
    assert interval.sd > 0


def test_bootstrap_lower_bound_is_a_lower_bound_not_a_mean() -> None:
    """A one-sided 95 percent bound sits strictly below the point estimate on a noisy sample, which is
    the whole reason a claim quotes it instead of the mean."""
    skills, _market, _agent, blocks = _synthetic_agent()
    interval = bootstrap_lower_bound(skills, blocks, rng=_tree())
    assert interval.lower < interval.point
    assert interval.upper > interval.point


def test_bootstrap_is_symmetric_under_negation() -> None:
    """A vector of losses reports the mirror of the same vector of gains: no ``//`` on a signed ratio,
    and the half-away-from-zero rounding of section 1.2 rather than banker's rounding."""
    skills, _market, _agent, blocks = _synthetic_agent()
    gains = bootstrap_lower_bound(skills, blocks, rng=_tree())
    losses = bootstrap_lower_bound([-value for value in skills], blocks, rng=_tree())
    assert losses.point == -gains.point
    assert losses.lower == -gains.upper
    assert losses.upper == -gains.lower
    assert losses.sd == gains.sd


def _correlated_values() -> tuple[list[int], list[str], list[str]]:
    """160 markets in 20 weeks whose weekly means differ and whose markets inside a week move together:
    the shape of a real politics tape, where a week is closer to one observation than to eight."""
    levels = [(week * 41 % 17) * 10_000 - 80_000 for week in range(20)]
    values = [levels[index // 8] + (index % 8) * 250 for index in range(160)]
    weeks = [f"w2026-{index // 8 + 1:02d}" for index in range(160)]
    per_market = [f"m{index:03d}" for index in range(160)]
    return values, weeks, per_market


def test_bootstrap_blocks_are_the_resample_unit() -> None:
    """The same values, resampled by week and resampled market by market. Correlated markets inside one
    block carry less information than independent ones, so the block interval must be the wider of the
    two: an interval that ignores the correlation is the one that overstates the evidence."""
    values, weeks, per_market = _correlated_values()
    by_week = bootstrap_lower_bound(values, weeks, rng=_tree())
    by_market = bootstrap_lower_bound(values, per_market, rng=_tree())
    assert by_week.point == by_market.point
    assert by_week.n_blocks == 20
    assert by_market.n_blocks == 160
    assert by_week.upper - by_week.lower > by_market.upper - by_market.lower
    assert by_week.sd > by_market.sd


def test_bootstrap_of_one_block_is_the_degenerate_interval() -> None:
    """Ruling R68: one block resampled with replacement is that block every time, so the quantiles would
    be the point pretending to be an interval. The function reports the degenerate interval instead of
    raising, because a one-block slice is a legal slice of a leaderboard."""
    values = [10, 20, 30, 41]
    interval = bootstrap_lower_bound(values, ["w2026-25"] * 4, rng=_tree())
    assert interval == Interval(
        point=25, lower=25, upper=25, sd=0, n=4, n_blocks=1, resamples=BOOTSTRAP_RESAMPLES
    )


def test_bootstrap_of_no_values_is_zero_and_not_an_error() -> None:
    """Section 12's zero-denominator rule: an agent that saw no market gets a row of zeros, not a
    ``ZeroDivisionError``."""
    interval = bootstrap_lower_bound([], [], rng=_tree())
    assert interval == Interval(point=0, lower=0, upper=0, sd=0, n=0, n_blocks=0, resamples=BOOTSTRAP_RESAMPLES)


def test_bootstrap_is_reproducible_and_seed_dependent() -> None:
    """Section 6.4's statistics row, in both directions.

    The same ``(values, seed)`` gives identical integers, field for field. Another seed draws another
    resample distribution, which a short bootstrap shows in the quantiles themselves and the declared
    10 000 draws show in the spread while the two quantiles have converged onto the same support point:
    that convergence is why 10 000 is the contract's number, and the ``sd`` inequality is the proof that
    the seed reached numpy at all rather than a global default.
    """
    values, weeks, _per_market = _correlated_values()
    other_tree = RngTree(SEED + 1).child("stats")
    first = bootstrap_lower_bound(values, weeks, rng=_tree())
    second = bootstrap_lower_bound(values, weeks, rng=_tree())
    other = bootstrap_lower_bound(values, weeks, rng=other_tree)
    assert first == second
    assert other.point == first.point
    assert other.sd != first.sd
    short = bootstrap_lower_bound(values, weeks, rng=_tree(), resamples=200)
    short_other = bootstrap_lower_bound(values, weeks, rng=other_tree, resamples=200)
    assert (short.lower, short.upper) != (short_other.lower, short_other.upper)


def test_bootstrap_alpha_moves_the_bound_the_right_way() -> None:
    """A stricter tail is a lower bound, never a higher one."""
    skills, _market, _agent, blocks = _synthetic_agent()
    ninety_five = bootstrap_lower_bound(skills, blocks, rng=_tree(), alpha_ppm=ALPHA_PPM)
    ninety_nine = bootstrap_lower_bound(skills, blocks, rng=_tree(), alpha_ppm=10_000)
    assert ninety_nine.lower < ninety_five.lower
    assert ninety_nine.upper > ninety_five.upper


@pytest.mark.parametrize(
    ("values", "blocks", "alpha_ppm", "resamples"),
    [
        ([1, 2], ["a"], ALPHA_PPM, 100),
        ([1, 2], ["a", "b"], 0, 100),
        ([1, 2], ["a", "b"], PPM_ONE, 100),
        ([1, 2], ["a", "b"], ALPHA_PPM, 0),
    ],
)
def test_bootstrap_refuses_impossible_arguments(
    values: list[int], blocks: list[str], alpha_ppm: int, resamples: int
) -> None:
    """A length mismatch, an empty tail, a whole tail and a zero draw count are caller bugs, refused at
    the call rather than answered with a number nobody can read."""
    with pytest.raises(ValueError):
        bootstrap_lower_bound(values, blocks, rng=_tree(), alpha_ppm=alpha_ppm, resamples=resamples)


# --------------------------------------------------------------------------------------------------
# The paired bound
# --------------------------------------------------------------------------------------------------
def test_paired_lower_bound_is_the_bootstrap_of_the_differences() -> None:
    """Section 12.4: the paired bound is the block bootstrap of ``agent - baseline``, and a skill is the
    market's Brier minus the agent's, so the two spellings must agree to the unit."""
    skills, market_briers, agent_briers, blocks = _synthetic_agent()
    paired = paired_lower_bound(market_briers, agent_briers, blocks, rng=_tree())
    direct = bootstrap_lower_bound(skills, blocks, rng=_tree())
    assert paired == direct


def test_pairing_removes_the_variance_the_two_series_share() -> None:
    """Why part 1 of the bar is stated against the market and not against zero: an easy market is easy
    for both, and the market-by-market difference drops that shared variance. Here the agent beats the
    market by exactly 12 000 micro on every market while both series swing wildly, so the paired
    interval is tight and the unpaired bootstrap of the agent's own Brier is not."""
    market_briers = [(index * 7_919) % 400_000 for index in range(120)]
    agent_briers = [value - 12_000 for value in market_briers]
    blocks = [f"w2026-{index % 12 + 1:02d}" for index in range(120)]
    paired = paired_lower_bound(market_briers, agent_briers, blocks, rng=_tree())
    unpaired = bootstrap_lower_bound(agent_briers, blocks, rng=_tree())
    assert paired == Interval(
        point=12_000, lower=12_000, upper=12_000, sd=0, n=120, n_blocks=12, resamples=BOOTSTRAP_RESAMPLES
    )
    assert unpaired.upper - unpaired.lower > 10_000


def test_paired_lower_bound_refuses_series_of_different_lengths() -> None:
    """Pairing means market by market: two series of different lengths are not paired."""
    with pytest.raises(ValueError):
        paired_lower_bound([1, 2, 3], [1, 2], ["a", "b", "c"], rng=_tree())


# --------------------------------------------------------------------------------------------------
# The deflation for the candidate count
# --------------------------------------------------------------------------------------------------
def _noisy_interval() -> Interval:
    """An interval with a real ``sd``: deflation is a statement about the spread of the resample."""
    skills, _market, _agent, blocks = _synthetic_agent()
    return bootstrap_lower_bound(skills, blocks, rng=_tree())


def test_deflation_is_strictly_decreasing_in_the_candidate_count() -> None:
    """The done-when: deflation widens with ``K`` over five decades, because the best of ten thousand
    genomes needs a higher bar than the best of one."""
    interval = _noisy_interval()
    bounds = [deflated_lower_bound(interval, candidates=k) for k in (1, 10, 100, 1_000, 10_000)]
    assert bounds == sorted(bounds, reverse=True)
    assert all(later < earlier for earlier, later in zip(bounds, bounds[1:], strict=False))
    assert bounds[0] < interval.point


def test_deflation_at_one_candidate_is_the_one_sided_normal_bound() -> None:
    """Section 12.4 names ``statistics.NormalDist().inv_cdf``, so the widening at ``K = 1`` is
    ``z(0.95) * sd`` rounded half away from zero and nothing else."""
    interval = _noisy_interval()
    z = NormalDist().inv_cdf(1.0 - ALPHA_PPM / PPM_ONE)
    expected = interval.point - int(z * interval.sd + 0.5)
    assert deflated_lower_bound(interval, candidates=1) == expected


def test_deflation_treats_a_missing_candidate_count_as_one() -> None:
    """``K = max(1, candidates)``: a run that counted no candidate still pays for one look."""
    interval = _noisy_interval()
    at_one = deflated_lower_bound(interval, candidates=1)
    assert deflated_lower_bound(interval, candidates=0) == at_one
    assert deflated_lower_bound(interval, candidates=-5) == at_one


def test_deflation_of_a_degenerate_interval_is_its_point() -> None:
    """No spread, nothing to charge: an interval with ``sd == 0`` deflates to itself, which is what keeps
    the market follower's exact zero from becoming a negative bound (ruling R68 feeds part 3)."""
    degenerate = Interval(point=0, lower=0, upper=0, sd=0, n=60, n_blocks=1, resamples=BOOTSTRAP_RESAMPLES)
    assert deflated_lower_bound(degenerate, candidates=10_000) == 0


def test_deflation_can_turn_a_positive_bound_negative() -> None:
    """The point of part 3 of the bar (section 12.6): a bound that clears alone does not clear once the
    family it was selected from is charged for."""
    interval = _noisy_interval()
    assert interval.lower > 0
    assert deflated_lower_bound(interval, candidates=1) > 0
    assert deflated_lower_bound(interval, candidates=20_000) < 0


# --------------------------------------------------------------------------------------------------
# The permutation null on binary outcomes
# --------------------------------------------------------------------------------------------------
def _binary_case(
    kind: str,
    *,
    n_markets: int = 120,
    n_blocks: int = 12,
    bars: int = 3,
    seed: int = SEED,
) -> tuple[
    dict[str, tuple[tuple[int, int], ...]],
    dict[str, tuple[int, ...]],
    tuple[int, ...],
    dict[str, tuple[int, ...]],
    tuple[str, ...],
]:
    """A run's worth of forecasts against a market stuck at ``500_000``.

    ``follower`` states the market's own price, so its skill is exactly zero; ``skilled`` states
    ``850_000`` on the markets that resolve YES and ``150_000`` on the others, so its skill comes from
    the association a shuffle destroys; ``coin`` states ``600_000`` or ``400_000`` by a coin flip that
    the outcome knows nothing about.
    """
    draw = RngTree(seed).substream("test.scratch")
    forecasts: dict[str, tuple[tuple[int, int], ...]] = {}
    prices: dict[str, tuple[int, ...]] = {}
    weights: dict[str, tuple[int, ...]] = {}
    outcomes: list[int] = []
    blocks: list[str] = []
    for index in range(n_markets):
        market_id = f"kalshi-M{index:03d}"
        outcome = 1 if bernoulli(draw, 0.5) else 0
        if kind == "skilled":
            prob = 850_000 if outcome == 1 else 150_000
        elif kind == "coin":
            prob = 600_000 if bernoulli(draw, 0.5) else 400_000
        else:
            prob = FIFTY_FIFTY_PPM
        forecasts[market_id] = tuple((bar * MS_PER_DAY, prob) for bar in range(bars))
        prices[market_id] = tuple(FIFTY_FIFTY_PPM for _ in range(bars))
        weights[market_id] = tuple(MS_PER_DAY for _ in range(bars))
        outcomes.append(outcome)
        blocks.append(f"w2026-{index % n_blocks + 1:02d}")
    return forecasts, prices, tuple(outcomes), weights, tuple(blocks)


def _observed_binary_interval(
    forecasts: dict[str, tuple[tuple[int, int], ...]],
    prices: dict[str, tuple[int, ...]],
    outcomes: tuple[int, ...],
    weights: dict[str, tuple[int, ...]],
    blocks: tuple[str, ...],
    *,
    resamples: int,
) -> Interval:
    """Section 12.1's per-market skill, scored by this test rather than by the module under test."""
    skills: list[int] = []
    for market_id, outcome in zip(sorted(forecasts), outcomes, strict=True):
        bar_weights = weights[market_id]
        total = sum(bar_weights)
        agent = sum(
            brier_micro(prob, outcome) * weight
            for (_bar_ms, prob), weight in zip(forecasts[market_id], bar_weights, strict=True)
        )
        market = sum(
            brier_micro(price, outcome) * weight
            for price, weight in zip(prices[market_id], bar_weights, strict=True)
        )
        skills.append(round_half_up(market, total) - round_half_up(agent, total))
    return bootstrap_lower_bound(skills, blocks, rng=_tree(), resamples=resamples)


def test_permutation_null_of_the_market_follower_is_exactly_zero() -> None:
    """The sharpest form of "the shuffled null centres on zero": an agent that states the market's own
    price has a skill of exactly ``0`` on every market and under every shuffle, so the null distribution
    is the single value zero and every permutation ties the observed mean."""
    forecasts, prices, outcomes, weights, blocks = _binary_case("follower")
    result = permutation_null(
        forecasts, prices, outcomes, weights, blocks, rng=_tree(), permutations=200, inner=200
    )
    assert result == NullResult(null_lb_micro=0, p_value_ppm=PPM_ONE, permutations=200)


def test_permutation_null_of_a_coin_flip_agent_centres_on_zero() -> None:
    """An agent whose forecasts the outcome knows nothing about: its observed mean sits inside its own
    null (a p-value neither ``0`` nor one) and the height luck reaches is a hair under zero, never the
    positive bound that would let noise clear part 4 of the bar."""
    forecasts, prices, outcomes, weights, blocks = _binary_case("coin")
    result = permutation_null(
        forecasts, prices, outcomes, weights, blocks, rng=_tree(), permutations=400, inner=200
    )
    assert result.null_lb_micro <= 0
    assert abs(result.null_lb_micro) < 50_000
    assert 100_000 < result.p_value_ppm < 900_000


def test_permutation_null_of_a_skilled_agent_is_unmatched_and_negative() -> None:
    """Part 4 of the bar (section 12.6): the agent whose skill comes from the forecast-outcome
    association is reached by no shuffle, and the bound luck alone clears is below zero."""
    forecasts, prices, outcomes, weights, blocks = _binary_case("skilled")
    observed = _observed_binary_interval(forecasts, prices, outcomes, weights, blocks, resamples=200)
    result = permutation_null(
        forecasts, prices, outcomes, weights, blocks, rng=_tree(), permutations=200, inner=200
    )
    assert observed.point > 200_000
    assert result.p_value_ppm == 0
    assert result.null_lb_micro <= 0
    assert result.null_lb_micro < observed.lower


def test_permutation_null_is_reproducible_at_the_contract_defaults() -> None:
    """The declared 1 000 shuffles and 200 inner resamples, twice, from two trees on one seed."""
    forecasts, prices, outcomes, weights, blocks = _binary_case("coin", n_markets=60, n_blocks=6)
    first = permutation_null(forecasts, prices, outcomes, weights, blocks, rng=_tree())
    second = permutation_null(forecasts, prices, outcomes, weights, blocks, rng=_tree())
    assert first == second
    assert first.permutations == PERMUTATIONS


def test_permutation_null_of_no_market_is_zero() -> None:
    """The zero-denominator rule again: no market is no evidence either way."""
    assert permutation_null({}, {}, (), {}, (), rng=_tree(), permutations=10, inner=10) == NullResult(
        null_lb_micro=0, p_value_ppm=0, permutations=10
    )


def test_permutation_null_refuses_series_that_disagree() -> None:
    """One outcome per market, one block per market, one price and one weight per forecast bar."""
    forecasts, prices, outcomes, weights, blocks = _binary_case("coin", n_markets=8, n_blocks=2)
    with pytest.raises(ValueError):
        permutation_null(forecasts, prices, outcomes[:-1], weights, blocks, rng=_tree(), permutations=4, inner=4)
    with pytest.raises(ValueError):
        permutation_null(forecasts, prices, outcomes, weights, blocks[:-1], rng=_tree(), permutations=4, inner=4)
    short_prices = dict(prices)
    short_prices[sorted(forecasts)[0]] = (FIFTY_FIFTY_PPM,)
    with pytest.raises(ValueError):
        permutation_null(forecasts, short_prices, outcomes, weights, blocks, rng=_tree(), permutations=4, inner=4)


@pytest.mark.parametrize("draw_count", [0, -1])
def test_permutation_null_refuses_a_zero_draw_count(draw_count: int) -> None:
    """Zero shuffles is an empty distribution, not a wide one."""
    forecasts, prices, outcomes, weights, blocks = _binary_case("coin", n_markets=8, n_blocks=2)
    with pytest.raises(ValueError):
        permutation_null(
            forecasts, prices, outcomes, weights, blocks, rng=_tree(), permutations=draw_count, inner=10
        )
    with pytest.raises(ValueError):
        permutation_null(
            forecasts, prices, outcomes, weights, blocks, rng=_tree(), permutations=10, inner=draw_count
        )


# --------------------------------------------------------------------------------------------------
# The permutation null on the continuous units of section 17.6
# --------------------------------------------------------------------------------------------------
def _continuous_case(
    kind: str,
    *,
    n_instruments: int = 8,
    n_weeks: int = 10,
    bars: int = 6,
    horizon_bars: int = 24,
    shared_bar_keys: bool = True,
    seed: int = SEED,
) -> tuple[
    dict[str, tuple[tuple[int, int], ...]],
    dict[str, tuple[int, ...]],
    dict[str, tuple[str, ...]],
    tuple[str, ...],
]:
    """``(instrument, ISO week)`` cells with one forecast per bar at one horizon (section 17.6).

    ``walk`` states ``500_000`` (the random walk of ruling R158), ``skilled`` states ``800_000`` when the
    realisation went up and ``200_000`` when it went down, ``coin`` states a direction the tape knows
    nothing about. With ``shared_bar_keys`` every instrument carries the same ``f"{t}/{h}"`` keys inside a
    week, which is what makes its forecasts exchangeable; without it each instrument gets its own bar
    times and no forecast has a partner.
    """
    draw = RngTree(seed).substream("test.scratch")
    forecasts: dict[str, tuple[tuple[int, int], ...]] = {}
    signs: dict[str, tuple[int, ...]] = {}
    bar_keys: dict[str, tuple[str, ...]] = {}
    week_of: dict[str, str] = {}
    for week in range(n_weeks):
        for instrument in range(n_instruments):
            unit = f"binance-i{instrument}/w2026-{week + 1:02d}"
            offset = 0 if shared_bar_keys else instrument * 1_000
            bars_seen: list[tuple[int, int]] = []
            unit_signs: list[int] = []
            unit_keys: list[str] = []
            for bar in range(bars):
                t_ms = (week * 168 + bar + offset) * MS_PER_HOUR
                sign = 1 if bernoulli(draw, 0.5) else -1
                if kind == "skilled":
                    up_ppm = 800_000 if sign > 0 else 200_000
                elif kind == "coin":
                    up_ppm = 600_000 if bernoulli(draw, 0.5) else 400_000
                else:
                    up_ppm = FIFTY_FIFTY_PPM
                bars_seen.append((t_ms, up_ppm))
                unit_signs.append(sign)
                unit_keys.append(f"{t_ms}/{horizon_bars}")
            forecasts[unit] = tuple(bars_seen)
            signs[unit] = tuple(unit_signs)
            bar_keys[unit] = tuple(unit_keys)
            week_of[unit] = f"w2026-{week + 1:02d}"
    blocks = tuple(week_of[unit] for unit in sorted(forecasts))
    return forecasts, signs, bar_keys, blocks


def _observed_continuous_interval(
    forecasts: dict[str, tuple[tuple[int, int], ...]],
    signs: dict[str, tuple[int, ...]],
    blocks: tuple[str, ...],
    *,
    resamples: int,
) -> Interval:
    """The per-cell directional skill of sections 17.5 and 17.6, scored by this test: the random walk's
    Brier minus the plain mean of the cell's directional Briers (ruling R191)."""
    skills: list[int] = []
    for unit in sorted(forecasts):
        losses: list[int] = []
        for (_bar_ms, up_ppm), sign in zip(forecasts[unit], signs[unit], strict=True):
            if sign > 0:
                losses.append(brier_micro(up_ppm, 1))
            elif sign < 0:
                losses.append(brier_micro(up_ppm, 0))
            else:
                losses.append((brier_micro(up_ppm, 1) + brier_micro(up_ppm, 0)) // 2)
        skills.append(RANDOM_WALK_BRIER_MICRO - round_half_up(sum(losses), len(losses)))
    return bootstrap_lower_bound(skills, blocks, rng=_tree(), resamples=resamples)


def test_continuous_null_of_the_random_walk_is_exactly_zero() -> None:
    """Ruling R158's identity, seen through the null: the baseline's per-cell directional skill is ``0``
    on an up, a down and a flat realisation alike, so no shuffle can move it."""
    forecasts, signs, bar_keys, blocks = _continuous_case("walk")
    flat_signs = {unit: tuple(0 for _ in values) for unit, values in signs.items()}
    for realisations in (signs, flat_signs):
        result = permutation_null(
            forecasts,
            {},
            (),
            {},
            blocks,
            rng=_tree(),
            permutations=200,
            inner=200,
            realised_signs=realisations,
            bar_keys=bar_keys,
        )
        assert result == NullResult(null_lb_micro=0, p_value_ppm=PPM_ONE, permutations=200)


def test_continuous_null_scores_a_flat_realisation_as_half_each_way() -> None:
    """Section 17.5's tie rule and the pinned worked values: a ``700_000`` up-probability scores
    ``90_000`` on an up move, ``490_000`` on a down move and ``290_000`` on a flat one, so a single-cell
    null (one block, hence the degenerate inner bound of ruling R68) reports the skill itself."""
    forecasts = {"binance-i0/w2026-25": ((0, 700_000),)}
    bar_keys = {"binance-i0/w2026-25": ("0/24",)}
    for sign, expected in ((1, 160_000), (-1, -240_000), (0, -40_000)):
        result = permutation_null(
            forecasts,
            {},
            (),
            {},
            ("w2026-25",),
            rng=_tree(),
            permutations=8,
            inner=8,
            realised_signs={"binance-i0/w2026-25": (sign,)},
            bar_keys=bar_keys,
        )
        assert result.null_lb_micro == expected
        assert expected == RANDOM_WALK_BRIER_MICRO - (
            {1: 90_000, -1: 490_000, 0: 290_000}[sign]
        )


def test_continuous_null_of_a_directional_agent_is_unmatched_and_negative() -> None:
    """The continuous half of part 4 (ruling R190): the realisations are shuffled inside the week, the
    forecasts stay put, and an agent whose direction is right is reached by no shuffle."""
    forecasts, signs, bar_keys, blocks = _continuous_case("skilled")
    observed = _observed_continuous_interval(forecasts, signs, blocks, resamples=200)
    result = permutation_null(
        forecasts,
        {},
        (),
        {},
        blocks,
        rng=_tree(),
        permutations=200,
        inner=200,
        realised_signs=signs,
        bar_keys=bar_keys,
    )
    assert observed.point == 210_000
    assert result.p_value_ppm == 0
    assert result.null_lb_micro <= 0


def test_continuous_null_of_a_coin_flip_agent_centres_on_zero() -> None:
    """The continuous form of "the shuffled null centres on zero"."""
    forecasts, signs, bar_keys, blocks = _continuous_case("coin")
    result = permutation_null(
        forecasts,
        {},
        (),
        {},
        blocks,
        rng=_tree(),
        permutations=400,
        inner=200,
        realised_signs=signs,
        bar_keys=bar_keys,
    )
    assert result.null_lb_micro <= 0
    assert abs(result.null_lb_micro) < 50_000
    assert 100_000 < result.p_value_ppm < PPM_ONE


def test_continuous_null_leaves_an_unmatched_forecast_in_place() -> None:
    """Ruling R190: a forecast whose ``(week, bar, horizon)`` no other instrument shares has no partner
    to swap with, so every permutation reproduces the observed vector and the null is the observed bound.
    This is the case where the answer is honestly "this data cannot refute anything"."""
    forecasts, signs, bar_keys, blocks = _continuous_case("skilled", shared_bar_keys=False)
    observed = _observed_continuous_interval(forecasts, signs, blocks, resamples=200)
    result = permutation_null(
        forecasts,
        {},
        (),
        {},
        blocks,
        rng=_tree(),
        permutations=50,
        inner=200,
        realised_signs=signs,
        bar_keys=bar_keys,
    )
    assert result.null_lb_micro == observed.lower
    assert result.p_value_ppm == PPM_ONE


def test_continuous_null_never_permutes_across_blocks() -> None:
    """Two clusters share every bar key, and the realisations inside each are constant and opposite. A
    permutation that respected the bar key but not the block would mix them and destroy the agent's
    skill; permuting inside ``(block, bar key)`` cannot, so the observed skill survives every shuffle."""
    bars = tuple(bar * MS_PER_HOUR for bar in range(6))
    forecasts: dict[str, tuple[tuple[int, int], ...]] = {}
    signs: dict[str, tuple[int, ...]] = {}
    bar_keys: dict[str, tuple[str, ...]] = {}
    block_of: dict[str, str] = {}
    for cluster, (sign, up_ppm) in (("ec-aaaaaaaaaaaaaaaa", (1, 800_000)), ("ec-bbbbbbbbbbbbbbbb", (-1, 200_000))):
        for instrument in range(6):
            unit = f"binance-{cluster[3:6]}{instrument}/w2026-25"
            forecasts[unit] = tuple((t_ms, up_ppm) for t_ms in bars)
            signs[unit] = tuple(sign for _ in bars)
            bar_keys[unit] = tuple(f"{t_ms}/24" for t_ms in bars)
            block_of[unit] = cluster
    blocks = tuple(block_of[unit] for unit in sorted(forecasts))
    observed = _observed_continuous_interval(forecasts, signs, blocks, resamples=200)
    result = permutation_null(
        forecasts,
        {},
        (),
        {},
        blocks,
        rng=_tree(),
        permutations=50,
        inner=200,
        realised_signs=signs,
        bar_keys=bar_keys,
    )
    assert observed.point == 210_000
    assert result.null_lb_micro == observed.lower
    assert result.p_value_ppm == PPM_ONE


def test_continuous_null_reads_no_price_and_no_weight() -> None:
    """Ruling R190's second half: ``price_realised_ticks`` is never shuffled and the pinball loss carries
    no permutation part, so a continuous answer cannot depend on a price or a time weight. Handing the
    call a full binary set of prices and weights changes nothing."""
    forecasts, signs, bar_keys, blocks = _continuous_case("coin", n_instruments=4, n_weeks=4)
    prices = {unit: tuple(FIFTY_FIFTY_PPM for _ in values) for unit, values in forecasts.items()}
    weights = {unit: tuple(MS_PER_HOUR for _ in values) for unit, values in forecasts.items()}
    bare = permutation_null(
        forecasts, {}, (), {}, blocks, rng=_tree(), permutations=50, inner=50,
        realised_signs=signs, bar_keys=bar_keys,
    )
    dressed = permutation_null(
        forecasts, prices, (), weights, blocks, rng=_tree(), permutations=50, inner=50,
        realised_signs=signs, bar_keys=bar_keys,
    )
    assert bare == dressed


def test_continuous_null_refuses_a_binary_shaped_call() -> None:
    """The two keyword-only arguments travel together, a continuous null takes no outcome, and a sign is
    a direction: three caller bugs the module refuses rather than scoring something else."""
    forecasts, signs, bar_keys, blocks = _continuous_case("coin", n_instruments=2, n_weeks=2)
    with pytest.raises(ValueError):
        permutation_null(
            forecasts, {}, (), {}, blocks, rng=_tree(), permutations=4, inner=4, realised_signs=signs
        )
    with pytest.raises(ValueError):
        permutation_null(
            forecasts, {}, (1,), {}, blocks, rng=_tree(), permutations=4, inner=4,
            realised_signs=signs, bar_keys=bar_keys,
        )
    bad_signs = dict(signs)
    first = sorted(forecasts)[0]
    bad_signs[first] = tuple(2 for _ in signs[first])
    with pytest.raises(ValueError):
        permutation_null(
            forecasts, {}, (), {}, blocks, rng=_tree(), permutations=4, inner=4,
            realised_signs=bad_signs, bar_keys=bar_keys,
        )
    short_keys = dict(bar_keys)
    short_keys[first] = bar_keys[first][:-1]
    with pytest.raises(ValueError):
        permutation_null(
            forecasts, {}, (), {}, blocks, rng=_tree(), permutations=4, inner=4,
            realised_signs=signs, bar_keys=short_keys,
        )


# --------------------------------------------------------------------------------------------------
# The null measures the statistic the leaderboard reports (sections 12.1 and 12.6)
#
# ``permutation_null`` recomputes each market's skill from the ``weights`` its caller hands over, while
# the projection's observed skill is ``pmx.scoring.skill_micro``, whose time weights are derived inside
# from ``bar_weights_ms``. If the two disagree, ``null_lb_micro`` is compared against a number the
# leaderboard never reports and part 4 of the bar of 12.6 is measured against the wrong thing. So the
# identity is pinned here, on an IRREGULAR bar grid where a constant weighting gives a different answer:
# ``WeightSeries`` is ``bar_weights_ms`` of the same bars and nothing else, and wave 4's caller (O4's
# ``claims.py``) has no second weighting to invent.
# --------------------------------------------------------------------------------------------------
#: Three forecast bars with a two-day hole in the middle, so ``w = (1d, 2d, 1d)`` and not ``(1d, 1d, 1d)``.
SKILL_BARS = (
    ForecastBar(t_ms=0, prob_ppm=700_000, market_price_bp=4_000),
    ForecastBar(t_ms=MS_PER_DAY, prob_ppm=800_000, market_price_bp=5_500),
    ForecastBar(t_ms=3 * MS_PER_DAY, prob_ppm=900_000, market_price_bp=6_000),
)


def test_the_nulls_observed_skill_is_e3s_skill_over_the_same_bar_weights() -> None:
    """``stats._binary_skill_micro`` over ``bar_weights_ms`` is exactly ``pmx.scoring.skill_micro``.

    Both outcomes are checked, because a binary null scores each market under both and selects (the
    ``skill_yes`` and ``skill_no`` lists of ``_binary_null``), and both rounding sides therefore have to
    agree, not just the YES one.
    """
    weights = bar_weights_ms(SKILL_BARS, interval_ms=MS_PER_DAY)
    assert weights == (MS_PER_DAY, 2 * MS_PER_DAY, MS_PER_DAY), "the grid is irregular on purpose"
    # ``PriceSeries`` is the market's probability in ppm and ``ForecastBar.market_price_bp`` is the same
    # price in basis points, which is the one conversion between E3's record and E4's series.
    probs = tuple((bar.t_ms, bar.prob_ppm) for bar in SKILL_BARS)
    prices = tuple(ppm_from_bp(bar.market_price_bp) for bar in SKILL_BARS)
    for outcome in (1, 0):
        assert _binary_skill_micro(probs, prices, weights, outcome=outcome) == skill_micro(
            SKILL_BARS, outcome=outcome, interval_ms=MS_PER_DAY
        ), outcome


def test_a_weighting_that_is_not_bar_weights_ms_measures_a_different_statistic() -> None:
    """Why the row above is an invariant and not a coincidence: the weights are load bearing.

    A caller that hands ``permutation_null`` one weight per bar instead of ``t_{i+1} - t_i`` gets a
    number that is not the leaderboard's skill for the same market, so the null would be compared
    against a statistic nobody reports. The zero-denominator rule of section 12 is pinned beside it: a
    market whose weights sum to zero scores ``0`` and is not silently skipped.
    """
    probs = tuple((bar.t_ms, bar.prob_ppm) for bar in SKILL_BARS)
    prices = tuple(ppm_from_bp(bar.market_price_bp) for bar in SKILL_BARS)
    flat = (MS_PER_DAY,) * len(SKILL_BARS)
    assert _binary_skill_micro(probs, prices, flat, outcome=1) != skill_micro(
        SKILL_BARS, outcome=1, interval_ms=MS_PER_DAY
    )
    assert _binary_skill_micro(probs, prices, (0, 0, 0), outcome=1) == 0
