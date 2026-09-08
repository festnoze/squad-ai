"""The block bootstrap, the paired lower bound, the permutation null and the candidate deflation
(CONTRACTS_V2 section 12.4, with 16.3's cluster blocks and 17.6's continuous units).

Why the arena needs its own statistics module rather than a mean: a per-market mean of skill over a few
hundred markets is a number with no error bar, and the whole point of PRD 2.6 is that a claim carries one.
Two dependencies break the naive interval. First, markets are not independent draws: two venues quoting
the same event move together, and a week of correlated politics markets is closer to one observation than
to forty, so the resample unit is a **block** (an event cluster when the dataset knows one, else the
market's own event key, else the ISO week of its resolution) and never a market. Second, a champion is
selected out of thousands of candidates, so the best validation lower bound of a large family is positive
by construction; `deflated_lower_bound` charges the family-wise count `K` against the bound, which is the
one number that turns "the best of 5 000 genomes beat the market" into an honest statement.

Everything reported here is an integer in the unit of its input (micro-units for a skill, cents for a
PnL): a bound printed as a float would suggest a precision the resample does not have, and section 1
bans a float in a score anyway. The two float sites are the normal quantile of `deflated_lower_bound`
(`statistics.NormalDist().inv_cdf`, which section 12.4 names, its product rounded half away from zero
through `Decimal`) and numpy's index arithmetic, which never touches a reported value.

The scores themselves belong to E3: the binary Brier is `pmx.types.brier_micro` and the directional
Brier of a continuous forecast, tie rule included, is `pmx.scoring.directional_brier_micro` against
`pmx.scoring.RANDOM_WALK_BRIER_MICRO`. This module rescores a permutation, it does not invent a loss.

This is the one module of `pmx` that imports numpy (architecture rule 4): the resample is 10 000 draws
over every block of the dataset and a Python loop over it would dominate the run. numpy is seeded from
the run's own tree (`stats.bootstrap` and `stats.permutation`, section 6.3) and never from its global
state, so the same `(journal, seed)` gives the same integers on any machine, which is the determinism
claim of section 6.4's "Statistics" row. Every draw is an integer draw: no float random key ever decides
which block or which sign lands where.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import isqrt
from statistics import NormalDist

import numpy as np
from numpy.typing import NDArray

from pmx.rng import RngTree
from pmx.scoring import RANDOM_WALK_BRIER_MICRO, directional_brier_micro
from pmx.types import (
    PPM_ONE,
    MarketMeta,
    brier_micro,
    iso_date_from_ms,
    round_half_up,
    round_half_up_decimal,
)

__all__ = [
    "ALPHA_PPM",
    "BOOTSTRAP_RESAMPLES",
    "PERMUTATIONS",
    "PERMUTATION_INNER_RESAMPLES",
    "BarKeys",
    "ForecastSeries",
    "Interval",
    "NullResult",
    "PriceSeries",
    "RealisedSigns",
    "WeightSeries",
    "block_key",
    "bootstrap_lower_bound",
    "deflated_lower_bound",
    "iso_week_key",
    "paired_lower_bound",
    "permutation_null",
]

#: Bootstrap draws of a reported interval (section 12.4).
BOOTSTRAP_RESAMPLES = 10_000

#: Outcome (or realised-sign) shuffles of a permutation null.
PERMUTATIONS = 1_000

#: Bootstrap draws inside one permutation: the null needs the shape of the bound, not its last unit.
PERMUTATION_INNER_RESAMPLES = 200

#: One-sided 95 percent bounds, in ppm of the tail.
ALPHA_PPM = 50_000

#: One forecast series per market (or per continuous ``(instrument, week)`` cell): ``(bar_ms, prob_ppm)``
#: pairs in bar order. On a continuous cell ``prob_ppm`` is ``up_probability_ppm`` at the claim's horizon
#: and ``bar_ms`` is the forecast bar whose ``f"{t}/{h}"`` key ``BarKeys`` carries (section 17.6).
ForecastSeries = Mapping[str, Sequence[tuple[int, int]]]

#: The market's own probability on the same bars, in ppm (``ppm_from_bp(market_priced.last_close_bp)``).
PriceSeries = Mapping[str, Sequence[int]]

#: The time weight of each forecast bar in milliseconds (section 12.1's ``w_i``).
WeightSeries = Mapping[str, Sequence[int]]

#: The realised direction of each forecast of a continuous cell, in ``{-1, 0, 1}`` (section 17.5).
RealisedSigns = Mapping[str, Sequence[int]]

#: The ``f"{t}/{h}"`` key of each forecast of a continuous cell: what makes two instruments' forecasts
#: exchangeable inside one week (section 17.6, ruling R190).
BarKeys = Mapping[str, Sequence[str]]

#: Rows of the resample index drawn per numpy call: the index matrix is bounded at this many rows
#: whatever the resample count, so a 10 000-resample bootstrap over a thousand blocks costs the same
#: memory as a 200-resample one and the chunking itself is not a function of the count.
_CHUNK_ROWS = 256


@dataclass(frozen=True, slots=True)
class Interval:
    """A block-bootstrap interval, every field an integer in the unit of the values it was built from.

    ``point`` is the observed mean (never a resample statistic), ``lower`` and ``upper`` the empirical
    one-sided quantiles at ``alpha_ppm`` and its complement, ``sd`` the standard deviation of the
    resampled means (the input of ``deflated_lower_bound``), ``n`` the number of values, ``n_blocks`` the
    number of resample units and ``resamples`` the draw count that produced the quantiles.
    """

    point: int
    lower: int
    upper: int
    sd: int
    n: int
    n_blocks: int
    resamples: int

    def to_dict(self) -> dict[str, int]:
        """The payload shape of a claim, a leaderboard row and a model card (section 12.11)."""
        return {
            "point": self.point,
            "lower": self.lower,
            "upper": self.upper,
            "sd": self.sd,
            "n": self.n,
            "n_blocks": self.n_blocks,
            "resamples": self.resamples,
        }


@dataclass(frozen=True, slots=True)
class NullResult:
    """What the permutation null answers: how high a lower bound pure luck reaches, and how often luck
    matched the observed mean (part 4 of the bar, section 12.6)."""

    null_lb_micro: int
    p_value_ppm: int
    permutations: int

    def to_dict(self) -> dict[str, int]:
        """The ``null`` block of a claim file (section 12.8)."""
        return {
            "null_lb_micro": self.null_lb_micro,
            "p_value_ppm": self.p_value_ppm,
            "permutations": self.permutations,
        }


def iso_week_key(t_ms: int) -> str:
    """``f"w{iso_year}-{iso_week:02d}"`` of the UTC instant ``t_ms``: the default block of section 12.4.

    The one spelling of a week block, so that ``block_key`` and the callers that group a continuous
    instrument into ``(instrument, ISO week)`` cells (section 17.6) write the same string. The instant is
    converted through ``pmx.types.iso_date_from_ms``, which is the data layer's one epoch conversion, so
    no clock and no timezone database is involved.
    """
    iso_year, iso_week, _ = date.fromisoformat(iso_date_from_ms(t_ms)).isocalendar()
    return f"w{iso_year}-{iso_week:02d}"


def block_key(market: MarketMeta, *, cluster_id: str | None = None) -> str:
    """The resample unit of a market: its cluster, else its event, else the ISO week it resolved in.

    The keyword-only ``cluster_id`` is amendment C1's (ruling R118): two venues' markets on one event are
    one block and not two independent draws, and the value arrives from ``pmx.data.clusters`` in wave 7
    while the argument ships here in wave 2 so no signature is widened later. This is the engine's own
    use of the grouping, in the statistics, where hindsight is allowed because no agent is looking
    (section 16.3).

    On a continuous ``(instrument, week)`` row the block is the **cell's** week and not the meta's
    (ruling R186): the caller builds it with ``iso_week_key(cell_ms)``, or passes the instrument's
    ``cluster_id`` when it has one, because a `MarketMeta` alone cannot say which of an instrument's weeks
    a row belongs to.
    """
    if cluster_id is not None:
        return cluster_id
    if market.event_key is not None:
        return market.event_key
    return iso_week_key(market.resolved_at_ms)


def bootstrap_lower_bound(
    values: Sequence[int],
    blocks: Sequence[str],
    *,
    rng: RngTree,
    alpha_ppm: int = ALPHA_PPM,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> Interval:
    """Resample ``n_blocks`` blocks with replacement and report the interval of the concatenated mean.

    ``values`` are the per-market (or per-cell) integers of the projection and ``blocks`` their block
    keys, one per value, in the same order. A block is drawn whole, which is what makes the interval
    honest when markets inside a block move together.

    Fewer than two blocks (an empty ``values`` included) has no bootstrap and returns the degenerate
    interval of ruling R68 rather than raising: one block resampled with replacement is that block every
    time, so the quantiles would be the point and pretend to be an interval.

    Raises:
        ValueError: If ``values`` and ``blocks`` differ in length, or ``alpha_ppm`` or ``resamples`` is
            outside its range.
    """
    _check_alpha(alpha_ppm)
    _check_count(resamples, "resamples")
    if len(values) != len(blocks):
        raise ValueError(f"values and blocks must have the same length, got {len(values)} and {len(blocks)}")
    block_sums, block_counts = _group_blocks(values, blocks)
    total = int(block_sums.sum())
    n = len(values)
    point = _mean_half_away(total, n)
    n_blocks = int(block_sums.size)
    if n_blocks < 2:
        return Interval(point=point, lower=point, upper=point, sd=0, n=n, n_blocks=n_blocks, resamples=resamples)
    means = _resampled_means(block_sums, block_counts, _generator(rng, "stats.bootstrap"), resamples)
    return _interval_from_means(means, point=point, n=n, n_blocks=n_blocks, alpha_ppm=alpha_ppm)


def paired_lower_bound(
    agent: Sequence[int],
    baseline: Sequence[int],
    blocks: Sequence[str],
    *,
    rng: RngTree,
    alpha_ppm: int = ALPHA_PPM,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> Interval:
    """The block bootstrap of ``agent - baseline``, market by market.

    The difference is taken in the order given, and a Brier is a **loss**: a skill is the baseline's loss
    minus the agent's, so a caller measuring skill against the market passes the market's per-market Brier
    as ``agent`` and the agent's as ``baseline``, exactly as ``skill_micro`` is spelled in section 12.1.
    A caller measuring PnL passes the agent's cents first.

    Pairing is not a convenience: the market-by-market difference removes the variance the two series
    share (an easy market is easy for both), which is why part 1 of the bar is stated against the market
    rather than against zero. On a continuous kind the baseline is the random walk, whose per-unit skill
    is ``0`` by construction (section 17.5), so the paired bootstrap there is the plain one and the caller
    may pass a vector of zeros or call ``bootstrap_lower_bound`` directly.

    Raises:
        ValueError: If the three sequences do not all have the same length.
    """
    if len(agent) != len(baseline):
        raise ValueError(f"agent and baseline must have the same length, got {len(agent)} and {len(baseline)}")
    differences = [int(a) - int(b) for a, b in zip(agent, baseline, strict=True)]
    return bootstrap_lower_bound(differences, blocks, rng=rng, alpha_ppm=alpha_ppm, resamples=resamples)


def deflated_lower_bound(interval: Interval, *, candidates: int) -> int:
    """The lower bound charged for the ``candidates`` genomes the champion was selected out of.

    Bonferroni on the family-wise count: ``point - z(1 - alpha / K) * sd`` with ``K = max(1, candidates)``.
    The undeflated bound is an empirical quantile; this one is the normal approximation on purpose,
    because an empirical quantile at ``alpha / K`` needs ``B >= 20 K / alpha`` resamples, which is out of
    reach for the ``K`` in the thousands that a real evolution run reports (section 12.4).

    The quantile is ``statistics.NormalDist().inv_cdf``, which section 12.4 names: pure Python, identical
    on every platform, and its product with ``sd`` is rounded half away from zero through ``Decimal`` so
    the returned bound is an integer in the unit of the interval.
    """
    k = max(1, candidates)
    z = NormalDist().inv_cdf(1.0 - ALPHA_PPM / (PPM_ONE * k))
    widening = round_half_up_decimal(Decimal(z) * Decimal(interval.sd))
    return interval.point - widening


def permutation_null(
    forecasts: ForecastSeries,
    market_prices: PriceSeries,
    outcomes: Sequence[int],
    weights: WeightSeries,
    blocks: Sequence[str],
    *,
    rng: RngTree,
    permutations: int = PERMUTATIONS,
    inner: int = PERMUTATION_INNER_RESAMPLES,
    realised_signs: RealisedSigns | None = None,
    bar_keys: BarKeys | None = None,
) -> NullResult:
    """How high a block-bootstrap lower bound reaches when the outcomes carry no information.

    The forecasts and the prices are held fixed and only the **realisations** are shuffled, because under
    the hypothesis of no skill the exchangeable object is the realisation and not the score: permuting
    per-market skills would test a different, easier claim (ruling R190). Each permutation recomputes the
    per-market skill, takes its block-bootstrap lower bound over ``inner`` resamples, and the reported
    ``null_lb_micro`` is the 95th percentile of those bounds: the height luck alone clears. Part 4 of the
    bar (section 12.6) asks for ``null_lb_micro <= 0``.

    Keys and order. Every mapping is keyed by market id (by ``(instrument, week)`` cell key on a
    continuous kind) and ``outcomes`` and ``blocks`` are aligned with ``sorted(forecasts)``, the one
    order this module reads, so two callers that hand over the same data get the same integers.

    Binary kinds pass ``forecasts``, ``market_prices``, ``outcomes`` (one per market, ``1`` or ``0``) and
    ``weights``; the skill of a market is section 12.1's time-weighted market Brier minus the agent's.

    Continuous kinds (amendment C1b, section 17.6, ruling R190) pass an empty ``outcomes``, one
    ``realised_signs`` entry and one ``bar_keys`` entry per forecast, and may pass empty ``market_prices``
    and ``weights``: the baseline is the random walk's constant Brier and the per-cell score is the plain
    mean of ruling R191, so neither a market price nor a time weight enters it. A permutation permutes
    ``realised_sign`` among the forecasts that share a block and a ``f"{t}/{h}"`` key (the same forecast
    bar and horizon in the same week, across instruments), leaves an unmatched forecast in place, and
    recomputes the per-cell directional skill. ``price_realised_ticks`` is never shuffled, so there is no
    permutation part for the pinball loss.

    Raises:
        ValueError: If a sequence length disagrees with another, if ``outcomes`` is non-empty on a
            continuous call, or if only one of ``realised_signs`` and ``bar_keys`` is given.
    """
    _check_count(permutations, "permutations")
    _check_count(inner, "inner")
    keys = tuple(sorted(forecasts))
    if len(blocks) != len(keys):
        raise ValueError(f"blocks must carry one key per unit, got {len(blocks)} for {len(keys)}")
    if (realised_signs is None) != (bar_keys is None):
        raise ValueError("realised_signs and bar_keys travel together: a continuous null needs both")
    if realised_signs is not None and bar_keys is not None:
        if len(outcomes) != 0:
            raise ValueError(f"a continuous null takes no outcomes, got {len(outcomes)}")
        return _continuous_null(
            keys,
            forecasts,
            realised_signs,
            bar_keys,
            blocks,
            rng=rng,
            permutations=permutations,
            inner=inner,
        )
    return _binary_null(
        keys,
        forecasts,
        market_prices,
        outcomes,
        weights,
        blocks,
        rng=rng,
        permutations=permutations,
        inner=inner,
    )


# --------------------------------------------------------------------------------------------------
# The two nulls
# --------------------------------------------------------------------------------------------------
def _binary_null(
    keys: tuple[str, ...],
    forecasts: ForecastSeries,
    market_prices: PriceSeries,
    outcomes: Sequence[int],
    weights: WeightSeries,
    blocks: Sequence[str],
    *,
    rng: RngTree,
    permutations: int,
    inner: int,
) -> NullResult:
    """Shuffle the outcomes across markets. A binary outcome has two values, so each market's skill under
    either of them is computed once and a permutation is a selection rather than a rescoring."""
    if len(outcomes) != len(keys):
        raise ValueError(f"outcomes must carry one outcome per market, got {len(outcomes)} for {len(keys)}")
    skill_yes: list[int] = []
    skill_no: list[int] = []
    for key in keys:
        probs = forecasts[key]
        prices = market_prices.get(key, ())
        bar_weights = weights.get(key, ())
        if len(prices) != len(probs) or len(bar_weights) != len(probs):
            raise ValueError(f"forecasts, market_prices and weights disagree in length on {key!r}")
        skill_yes.append(_binary_skill_micro(probs, prices, bar_weights, outcome=1))
        skill_no.append(_binary_skill_micro(probs, prices, bar_weights, outcome=0))
    n = len(keys)
    if n == 0:
        return NullResult(null_lb_micro=0, p_value_ppm=0, permutations=permutations)
    yes = np.array(skill_yes, dtype=np.int64)
    no = np.array(skill_no, dtype=np.int64)
    truth = np.array([1 if int(outcome) == 1 else 0 for outcome in outcomes], dtype=np.int64)
    observed = _mean_half_away(int(np.where(truth == 1, yes, no).sum()), n)
    block_of, block_counts = _block_index(blocks)
    perm_gen = _generator(rng, "stats.permutation")
    boot_gen = _generator(rng, "stats.bootstrap")
    bounds: list[int] = []
    at_least = 0
    for _ in range(permutations):
        permuted = truth[perm_gen.permutation(n)]
        skills = np.where(permuted == 1, yes, no)
        if _mean_half_away(int(skills.sum()), n) >= observed:
            at_least += 1
        bounds.append(_inner_lower_bound(skills, block_of, block_counts, boot_gen, n=n, resamples=inner))
    return _null_from_bounds(bounds, at_least=at_least, permutations=permutations)


def _continuous_null(
    keys: tuple[str, ...],
    forecasts: ForecastSeries,
    realised_signs: RealisedSigns,
    bar_keys: BarKeys,
    blocks: Sequence[str],
    *,
    rng: RngTree,
    permutations: int,
    inner: int,
) -> NullResult:
    """Permute ``realised_sign`` inside every ``(block, bar key)`` group and rescore the cells.

    The three directional Briers a forecast can score (down, flat, up) are precomputed once, so a
    permutation is a gather and two integer reductions rather than a rescoring of every forecast.
    """
    unit_of: list[int] = []
    table: list[tuple[int, int, int]] = []
    signs: list[int] = []
    group_names: list[tuple[str, str]] = []
    for index, key in enumerate(keys):
        probs = forecasts[key]
        unit_signs = realised_signs[key]
        unit_bars = bar_keys[key]
        if len(unit_signs) != len(probs) or len(unit_bars) != len(probs):
            raise ValueError(f"forecasts, realised_signs and bar_keys disagree in length on {key!r}")
        for (_bar_ms, up_ppm), sign, bar in zip(probs, unit_signs, unit_bars, strict=True):
            unit_of.append(index)
            table.append(
                (
                    directional_brier_micro(up_ppm, -1),
                    directional_brier_micro(up_ppm, 0),
                    directional_brier_micro(up_ppm, 1),
                )
            )
            signs.append(_clamped_sign(sign))
            group_names.append((blocks[index], bar))
    n = len(keys)
    if n == 0 or not table:
        return NullResult(null_lb_micro=0, p_value_ppm=0, permutations=permutations)
    unit_index = np.array(unit_of, dtype=np.int64)
    unit_counts = np.bincount(unit_index, minlength=n).astype(np.int64)
    briers = np.array(table, dtype=np.int64)
    sign_array = np.array(signs, dtype=np.int64)
    rows = np.arange(briers.shape[0], dtype=np.int64)
    group_ids = {name: gid for gid, name in enumerate(sorted(set(group_names)))}
    group_of = np.array([group_ids[name] for name in group_names], dtype=np.int64)
    grouped = np.argsort(group_of, kind="stable")
    observed = _mean_half_away(
        int(_continuous_skills(briers[rows, sign_array + 1], unit_index, unit_counts, n).sum()), n
    )
    block_of, block_counts = _block_index(blocks)
    perm_gen = _generator(rng, "stats.permutation")
    boot_gen = _generator(rng, "stats.bootstrap")
    bounds: list[int] = []
    at_least = 0
    for _ in range(permutations):
        permuted = _permute_within_groups(sign_array, group_of, grouped, perm_gen)
        skills = _continuous_skills(briers[rows, permuted + 1], unit_index, unit_counts, n)
        if _mean_half_away(int(skills.sum()), n) >= observed:
            at_least += 1
        bounds.append(_inner_lower_bound(skills, block_of, block_counts, boot_gen, n=n, resamples=inner))
    return _null_from_bounds(bounds, at_least=at_least, permutations=permutations)


def _null_from_bounds(bounds: Sequence[int], *, at_least: int, permutations: int) -> NullResult:
    """The 95th percentile of the permutation bounds and the share of permutations that matched."""
    ordered = sorted(bounds)
    null_lb = ordered[_upper_index(ALPHA_PPM, len(ordered))] if ordered else 0
    return NullResult(
        null_lb_micro=null_lb,
        p_value_ppm=round_half_up(PPM_ONE * at_least, permutations),
        permutations=permutations,
    )


def _binary_skill_micro(
    probs: Sequence[tuple[int, int]],
    prices: Sequence[int],
    weights: Sequence[int],
    *,
    outcome: int,
) -> int:
    """Section 12.1's skill of one market under one outcome: the market's time-weighted Brier minus the
    agent's, both over the agent's own forecast bars. A market with no bar or no weight scores ``0``,
    which is section 12's zero-denominator rule and not a silent skip."""
    total_weight = sum(int(weight) for weight in weights)
    if total_weight <= 0:
        return 0
    agent = sum(
        brier_micro(prob, outcome) * int(weight) for (_bar_ms, prob), weight in zip(probs, weights, strict=True)
    )
    market = sum(
        brier_micro(int(price), outcome) * int(weight) for price, weight in zip(prices, weights, strict=True)
    )
    return round_half_up(market, total_weight) - round_half_up(agent, total_weight)


def _continuous_skills(
    chosen: NDArray[np.int64],
    unit_index: NDArray[np.int64],
    unit_counts: NDArray[np.int64],
    n_units: int,
) -> NDArray[np.int64]:
    """Per-cell directional skill: ``RANDOM_WALK_BRIER_MICRO`` minus the plain mean of the cell's
    directional Briers (sections 17.5 and 17.6, ruling R191), where the Brier of one forecast is E3's
    ``pmx.scoring.directional_brier_micro`` and its tie rule. Every Brier is non-negative, so the mean is
    ``round_half_up`` and needs no sign branch."""
    sums = np.zeros(n_units, dtype=np.int64)
    np.add.at(sums, unit_index, chosen)
    counts = np.maximum(unit_counts, 1)
    means = (2 * sums + counts) // (2 * counts)
    skills: NDArray[np.int64] = RANDOM_WALK_BRIER_MICRO - means
    return skills


def _permute_within_groups(
    signs: NDArray[np.int64],
    group_of: NDArray[np.int64],
    grouped: NDArray[np.int64],
    gen: np.random.Generator,
) -> NDArray[np.int64]:
    """A uniform permutation of ``signs`` inside every group, from one integer draw.

    ``grouped`` lists every position sorted by group (stably, so once). Sorting a random permutation by
    group with a stable sort lists the same groups in the same order but with their members in random
    order, and assigning one listing onto the other permutes inside each group and never across two. A
    group of one is its own permutation, which is exactly "an unmatched forecast stays in place".
    """
    draw = gen.permutation(signs.size)
    shuffled = draw[np.argsort(group_of[draw], kind="stable")]
    permuted = np.empty_like(signs)
    permuted[grouped] = signs[shuffled]
    return permuted


def _clamped_sign(sign: int) -> int:
    """``-1``, ``0`` or ``1``: a realised sign is a direction, and anything else is a caller's bug."""
    value = int(sign)
    if value not in (-1, 0, 1):
        raise ValueError(f"realised_sign must be -1, 0 or 1, got {value}")
    return value


# --------------------------------------------------------------------------------------------------
# The resample itself
# --------------------------------------------------------------------------------------------------
def _generator(rng: RngTree, name: str) -> np.random.Generator:
    """numpy seeded from the run's tree and never from its global state (section 6.3)."""
    return np.random.default_rng(rng.seed_for(name) % 2**64)


def _group_blocks(values: Sequence[int], blocks: Sequence[str]) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """The per-block sum and count, blocks in ascending key order so the draw is reproducible."""
    sums: dict[str, int] = {}
    counts: dict[str, int] = {}
    for value, key in zip(values, blocks, strict=True):
        sums[key] = sums.get(key, 0) + int(value)
        counts[key] = counts.get(key, 0) + 1
    keys = sorted(sums)
    return (
        np.array([sums[key] for key in keys], dtype=np.int64),
        np.array([counts[key] for key in keys], dtype=np.int64),
    )


def _block_index(blocks: Sequence[str]) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """The block id of every unit and the size of every block, in ascending key order: what a permutation
    loop needs to rebuild the block sums of a rescored vector without regrouping the keys."""
    ids = {key: index for index, key in enumerate(sorted(set(blocks)))}
    block_of = np.array([ids[key] for key in blocks], dtype=np.int64)
    counts = np.bincount(block_of, minlength=len(ids)).astype(np.int64) if len(ids) else np.zeros(0, dtype=np.int64)
    return block_of, counts


def _inner_lower_bound(
    values: NDArray[np.int64],
    block_of: NDArray[np.int64],
    block_counts: NDArray[np.int64],
    gen: np.random.Generator,
    *,
    n: int,
    resamples: int,
) -> int:
    """One permutation's block-bootstrap lower bound, computed from the block sums of ``values``."""
    n_blocks = int(block_counts.size)
    total = int(values.sum())
    if n_blocks < 2:
        return _mean_half_away(total, n)
    block_sums = np.zeros(n_blocks, dtype=np.int64)
    np.add.at(block_sums, block_of, values)
    means = _resampled_means(block_sums, block_counts, gen, resamples)
    return int(means[_lower_index(ALPHA_PPM, resamples)])


def _resampled_means(
    block_sums: NDArray[np.int64],
    block_counts: NDArray[np.int64],
    gen: np.random.Generator,
    resamples: int,
) -> NDArray[np.int64]:
    """``resamples`` means of ``n_blocks`` blocks drawn with replacement, each rounded half away from
    zero, sorted ascending. Drawn in fixed-size chunks so the draw sequence does not depend on the
    resample count and the index matrix never grows with it."""
    n_blocks = int(block_sums.size)
    means = np.empty(resamples, dtype=np.int64)
    filled = 0
    while filled < resamples:
        rows = min(_CHUNK_ROWS, resamples - filled)
        index = gen.integers(0, n_blocks, size=(rows, n_blocks), dtype=np.int64)
        sums = block_sums[index].sum(axis=1)
        counts = block_counts[index].sum(axis=1)
        means[filled : filled + rows] = _round_means(sums, counts)
        filled += rows
    means.sort()
    return means


def _round_means(sums: NDArray[np.int64], counts: NDArray[np.int64]) -> NDArray[np.int64]:
    """``sum / count`` rounded half away from zero, elementwise, without a float: a mean of losses and
    the mirror mean of gains must report the same magnitude (section 1.2's ``bp_ratio`` rule)."""
    magnitude = (2 * np.abs(sums) + counts) // (2 * counts)
    return np.where(sums >= 0, magnitude, -magnitude).astype(np.int64)


def _interval_from_means(
    means: NDArray[np.int64],
    *,
    point: int,
    n: int,
    n_blocks: int,
    alpha_ppm: int,
) -> Interval:
    """The interval read off a sorted resample distribution."""
    resamples = int(means.size)
    return Interval(
        point=point,
        lower=int(means[_lower_index(alpha_ppm, resamples)]),
        upper=int(means[_upper_index(alpha_ppm, resamples)]),
        sd=_sd_of(means),
        n=n,
        n_blocks=n_blocks,
        resamples=resamples,
    )


def _sd_of(means: NDArray[np.int64]) -> int:
    """The sample standard deviation of the resampled means, as an integer.

    Computed from exact Python integers (``B * sum(m^2) - sum(m)^2`` over ``B * (B - 1)``) and closed with
    ``math.isqrt``, so no float and no overflow enters a number that ``deflated_lower_bound`` multiplies
    by a normal quantile. ``0`` for fewer than two resamples, which is the zero-denominator rule.
    """
    resamples = int(means.size)
    if resamples < 2:
        return 0
    total = 0
    total_squares = 0
    for value in means.tolist():
        total += value
        total_squares += value * value
    numerator = resamples * total_squares - total * total
    return isqrt(round_half_up(numerator, resamples * (resamples - 1)))


def _mean_half_away(total: int, count: int) -> int:
    """The mean of ``count`` values summing to ``total``, rounded half away from zero; ``0`` for no
    value (section 12's zero-denominator rule)."""
    if count <= 0:
        return 0
    magnitude = round_half_up(abs(total), count)
    return magnitude if total >= 0 else -magnitude


def _lower_index(alpha_ppm: int, resamples: int) -> int:
    """``floor(alpha * B)``, clamped into the distribution (section 12.4)."""
    return min(max((alpha_ppm * resamples) // PPM_ONE, 0), resamples - 1)


def _upper_index(alpha_ppm: int, resamples: int) -> int:
    """``ceil((1 - alpha) * B) - 1``, clamped into the distribution (section 12.4)."""
    complement = PPM_ONE - alpha_ppm
    ceiling = -((-complement * resamples) // PPM_ONE)
    return min(max(ceiling - 1, 0), resamples - 1)


def _check_alpha(alpha_ppm: int) -> None:
    """A one-sided tail is strictly inside ``(0, PPM_ONE)``: a zero tail has no quantile and a full one
    is not an interval."""
    if alpha_ppm <= 0 or alpha_ppm >= PPM_ONE:
        raise ValueError(f"alpha_ppm must be in (0, {PPM_ONE}), got {alpha_ppm}")


def _check_count(count: int, name: str) -> None:
    """A draw count is at least one: zero draws is an empty distribution, not a wide interval."""
    if count < 1:
        raise ValueError(f"{name} must be at least 1, got {count}")
