"""Forecast scores across the six instrument kinds, in integers only (CONTRACTS_V2 12.1 and 17.5).

This module is the arithmetic of "was the agent right", and it is deliberately separated from the
arithmetic of "did the agent make money" (``pmx.metrics.performance``, E5): a forecast score reads a
probability, a price and an outcome, never a fill, a fee or a balance. Decoupling them by module is what
makes the claim "this agent forecasts better than the market" checkable on its own, and what lets the
calibration module beside it (``pmx.metrics.calibration``) import nothing from execution.

Three rules shape every function below and none of them is a preference:

* **Integers only.** Brier and the two continuous losses are micro-units, the log score is micro-nats,
  PMV is basis points, probability is parts per million. There is no float in a score, so no platform's
  libm can move a number: the one logarithm is ``pmx.types.neg_ln_micronats``, which is ``Decimal.ln``
  at precision 40 and therefore identical everywhere (section 1.3).
* **Every ratio is zero on a zero denominator** (ruling R2). An agent that saw no bar, a horizon bucket
  no bar fell into, a PMV horizon no bar could reach: each reports ``n: 0`` and every other field ``0``
  rather than raising, because on the common path those denominators really are zero.
* **The baseline is an agent.** On a binary the market's own statement is scored on the same bars from
  ``market_priced.last_close_bp`` (the close of the last completed bar, and ``first_price_bp`` on the
  market's first bar, ruling R11), so ``skill(market_follower) == 0`` holds by construction. On a
  continuous instrument the random walk (``500_000`` ppm and the reference price as every quantile) is
  scored the same way, so ``skill(random_walk) == 0`` holds by construction too (ruling R158).

The last section of the file is not a score at all: it is the integer logit table section 10.3 puts here
(``logit_milli`` and ``unlogit_ppm``), because a log-odds update in fixed point needs the same
platform-independent logarithm a log score does, and there is no second place in ``pmx`` that owns one.

What this module does not own: the reference and realisation *lookups* of a continuous horizon, the
carried statements and the journal events are E5's (section 17.5, "who owns what"); the block bootstrap
and the permutation null are E4's; the trading metrics and the behavioural descriptors are E5's.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

from pmx.types import (
    BP_ONE,
    HORIZON_BUCKETS,
    LOG_CLAMP_HI_PPM,
    LOG_CLAMP_LO_PPM,
    MS_PER_DAY,
    PPM_ONE,
    QUANTILE_LEVELS_PPM,
    RANDOM_WALK_BRIER_MICRO,
    RANDOM_WALK_UP_PPM,
    RE_HORIZON_BUCKET,
    bp_ratio,
    brier_micro,
    neg_ln_micronats,
    ppm_from_bp,
    round_half_up,
)

#: The constant forecast the second binary skill is measured against (section 12.1): 5 000 bp.
BASELINE_5000_PPM = 500_000

#: The two PMV horizons of section 12.1, in days.
PMV_HORIZONS_DAYS = (1, 7)


# --------------------------------------------------------------------------------------------------
# Integer means. Three of them, because the contract asks for three: a weighted score (12.1), a plain
# score (17.5, ruling R191) and a signed series such as PMV, which rounds half away from zero so that a
# loss and the mirror gain report the same magnitude (section 1.2).
# --------------------------------------------------------------------------------------------------
def weighted_mean_micro(values: Sequence[int], weights: Sequence[int]) -> int:
    """``round_half_up(sum(v * w), sum(w))``, and ``0`` when the weights sum to zero (ruling R2)."""
    total_weight = sum(weights)
    if total_weight <= 0:
        return 0
    total = sum(value * weight for value, weight in zip(values, weights, strict=True))
    return round_half_up(total, total_weight)


def plain_mean_micro(values: Sequence[int]) -> int:
    """The plain mean of a non-negative integer series, rounded half up, and ``0`` over an empty one.

    This is the per-instrument aggregation of a continuous kind (17.5, ruling R191): forecast bars weigh
    equally and a session gap is the tape's, not a weight on the forecast.
    """
    if not values:
        return 0
    return round_half_up(sum(values), len(values))


def signed_mean(values: Sequence[int]) -> int:
    """The mean of a signed integer series, rounded half away from zero, and ``0`` over an empty one.

    The rounding is ``bp_ratio``'s and ``milli_ratio``'s (section 1.2) without their scale, because the
    values are already in the unit they are reported in: a mean of basis points is basis points.
    """
    n = len(values)
    if n == 0:
        return 0
    total = sum(values)
    quotient, remainder = divmod(abs(total), n)
    if 2 * remainder >= n:
        quotient += 1
    return quotient if total >= 0 else -quotient


# --------------------------------------------------------------------------------------------------
# 12.1 The binary forecast record: one bar of one (agent, market).
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ForecastBar:
    """One scored bar: what the agent said, and what the market said on the same bar.

    ``market_price_bp`` is ``market_priced.last_close_bp`` (section 9.2): the close of the last completed
    bar at ``t_ms``, and the market's ``first_price_bp`` on the market's first bar, where no bar is
    completed (ruling R11). Carrying the market's own statement in the same record as the agent's is what
    makes a mismatched bar set impossible: the two Briers of section 12.1 are always over the same bars,
    which is what the ``skill(market_follower) == 0`` identity rests on.
    """

    t_ms: int
    prob_ppm: int
    market_price_bp: int

    @property
    def market_prob_ppm(self) -> int:
        """The market's own forecast on this bar, in ppm."""
        return ppm_from_bp(self.market_price_bp)

    def to_dict(self) -> dict[str, int]:
        return {"t_ms": self.t_ms, "prob_ppm": self.prob_ppm, "market_price_bp": self.market_price_bp}


@dataclass(frozen=True, slots=True)
class HorizonBucket:
    """One horizon slice of a forecast record (section 12.11).

    On a binary the bucket is one of ``HORIZON_BUCKETS``; on a continuous kind it is ``h<n>`` for the
    declared horizon ``n`` and ``market_brier_tw_micro`` carries the random walk's constant loss
    (17.5, ruling R161). ``HORIZON_BUCKETS`` itself stays the four binary buckets, because horizons are
    per-run config and it is a module constant (ruling R188), so the string is validated by shape.
    """

    bucket: str
    n_bars: int
    brier_tw_micro: int
    market_brier_tw_micro: int
    skill_micro: int

    def __post_init__(self) -> None:
        if RE_HORIZON_BUCKET.fullmatch(self.bucket) is None:
            raise ValueError(f"bucket {self.bucket!r} does not match RE_HORIZON_BUCKET")

    def to_dict(self) -> dict[str, object]:
        return {
            "bucket": self.bucket,
            "n_bars": self.n_bars,
            "brier_tw_micro": self.brier_tw_micro,
            "market_brier_tw_micro": self.market_brier_tw_micro,
            "skill_micro": self.skill_micro,
        }


def bar_weights_ms(bars: Sequence[ForecastBar], *, interval_ms: int) -> tuple[int, ...]:
    """The time weights of 12.1: ``w_i = t_{i+1} - t_i`` for ``i < n`` and ``w_n = interval_ms``.

    The bars arrive in ascending ``t_ms`` (section 3), so every weight is positive. On a regular grid
    every weight is ``interval_ms`` and the weighted mean equals the plain mean exactly, which
    ``tests/test_scoring.py`` asserts rather than assumes.
    """
    if not bars:
        return ()
    return tuple(bars[index + 1].t_ms - bars[index].t_ms for index in range(len(bars) - 1)) + (interval_ms,)


def brier_series_micro(bars: Sequence[ForecastBar], *, outcome: int) -> tuple[int, ...]:
    """The agent's per-bar Brier, in micro-units."""
    return tuple(brier_micro(bar.prob_ppm, outcome) for bar in bars)


def market_brier_series_micro(bars: Sequence[ForecastBar], *, outcome: int) -> tuple[int, ...]:
    """The market's per-bar Brier on the same bars, from ``last_close_bp`` (section 12.1)."""
    return tuple(brier_micro(bar.market_prob_ppm, outcome) for bar in bars)


def brier_tw_micro(bars: Sequence[ForecastBar], *, outcome: int, interval_ms: int) -> int:
    """``settlement_applied.agent_brier_tw_micro`` (sections 8.7 and 12.1)."""
    return weighted_mean_micro(
        brier_series_micro(bars, outcome=outcome), bar_weights_ms(bars, interval_ms=interval_ms)
    )


def market_brier_tw_micro(bars: Sequence[ForecastBar], *, outcome: int, interval_ms: int) -> int:
    """``settled.market_brier_tw_micro`` (sections 8.7 and 12.1)."""
    return weighted_mean_micro(
        market_brier_series_micro(bars, outcome=outcome), bar_weights_ms(bars, interval_ms=interval_ms)
    )


def skill_micro(bars: Sequence[ForecastBar], *, outcome: int, interval_ms: int) -> int:
    """``market_brier_tw_micro - brier_tw_micro``: positive means sharper than the market."""
    return market_brier_tw_micro(bars, outcome=outcome, interval_ms=interval_ms) - brier_tw_micro(
        bars, outcome=outcome, interval_ms=interval_ms
    )


def skill_vs_5000_micro(bars: Sequence[ForecastBar], *, outcome: int, interval_ms: int) -> int:
    """The same skill against the constant ``500_000`` ppm forecast (section 12.1)."""
    weights = bar_weights_ms(bars, interval_ms=interval_ms)
    baseline = weighted_mean_micro([brier_micro(BASELINE_5000_PPM, outcome)] * len(bars), weights)
    return baseline - brier_tw_micro(bars, outcome=outcome, interval_ms=interval_ms)


def log_series_micronats(bars: Sequence[ForecastBar], *, outcome: int) -> tuple[int, ...]:
    """The per-bar log score in micro-nats, clamped at 1 percent and 99 percent (section 12.1).

    The clamp is what keeps the score finite: an agent that states ``0`` on a market that resolves YES
    scores ``neg_ln_micronats(LOG_CLAMP_LO_PPM) == 4_605_170`` and not an infinity no integer can hold.
    """
    scores: list[int] = []
    for bar in bars:
        stated = bar.prob_ppm if outcome == 1 else PPM_ONE - bar.prob_ppm
        scores.append(neg_ln_micronats(max(LOG_CLAMP_LO_PPM, min(LOG_CLAMP_HI_PPM, stated))))
    return tuple(scores)


def log_micronats(bars: Sequence[ForecastBar], *, outcome: int, interval_ms: int) -> int:
    """The time-weighted log score of one (agent, market) record, in micro-nats (section 12.1)."""
    return weighted_mean_micro(
        log_series_micronats(bars, outcome=outcome), bar_weights_ms(bars, interval_ms=interval_ms)
    )


def days_to_close(t_ms: int, *, close_at_ms: int) -> int:
    """``(close_at_ms - t_ms) // MS_PER_DAY``, negative on a settlement-lag bar (section 12.1)."""
    return (close_at_ms - t_ms) // MS_PER_DAY


def horizon_bucket_of(t_ms: int, *, close_at_ms: int) -> str:
    """The bucket of one bar: ``30d`` (``>= 30``), ``7d`` (``[7, 30)``), ``2d`` (``[2, 7)``), ``0d`` (``< 2``).

    The last bucket is ``< 2`` and not ``[0, 2)`` because section 5.3 keeps a market open between
    ``close_at_ms`` and ``resolved_at_ms``, where ``days_to_close`` is negative: every settlement-lag bar
    falls in ``0d`` and none is dropped (ruling R56).
    """
    days = days_to_close(t_ms, close_at_ms=close_at_ms)
    if days >= 30:
        return "30d"
    if days >= 7:
        return "7d"
    if days >= 2:
        return "2d"
    return "0d"


def horizon_buckets(
    bars: Sequence[ForecastBar], *, outcome: int, close_at_ms: int, interval_ms: int
) -> tuple[HorizonBucket, ...]:
    """The four buckets of section 12.1, always all four, in ``HORIZON_BUCKETS`` order.

    A bucket no bar fell into reports ``n_bars: 0`` with every other field ``0`` (ruling R2), so the tuple
    has a fixed length and a fixed order and no consumer has to guess which buckets exist. The weights are
    the record's own (12.1's ``w_i``), not recomputed inside the bucket: a bucket is a slice of one
    weighted series, so a bar's weight does not change because it is looked at through a bucket.
    """
    weights = bar_weights_ms(bars, interval_ms=interval_ms)
    agent = brier_series_micro(bars, outcome=outcome)
    market = market_brier_series_micro(bars, outcome=outcome)
    buckets: list[HorizonBucket] = []
    for name in HORIZON_BUCKETS:
        picked = [
            index
            for index, bar in enumerate(bars)
            if horizon_bucket_of(bar.t_ms, close_at_ms=close_at_ms) == name
        ]
        slice_weights = [weights[index] for index in picked]
        agent_tw = weighted_mean_micro([agent[index] for index in picked], slice_weights)
        market_tw = weighted_mean_micro([market[index] for index in picked], slice_weights)
        buckets.append(
            HorizonBucket(
                bucket=name,
                n_bars=len(picked),
                brier_tw_micro=agent_tw,
                market_brier_tw_micro=market_tw,
                skill_micro=market_tw - agent_tw,
            )
        )
    return tuple(buckets)


def pmv_bp(bars: Sequence[ForecastBar], *, horizon_days: int, settle_bar_ms: int) -> int:
    """Price-move value at ``horizon_days`` days, in basis points (section 12.1).

    ``pmv_bp(t_i) = sign(p_i - ppm_from_bp(price_i)) * (price_{t_i + h} - price_i)`` where ``price`` is the
    one series the agent could see (``market_priced.last_close_bp``) and ``price_{t_i + h}`` is that series
    at the first bar ``>= t_i + h`` days that is still before ``settle_bar_ms`` (``bar_of(resolved_at_ms)``).
    A bar with no such future bar is skipped, and a record whose every bar was skipped reports ``0``.

    Reading the same series on both sides is what makes the number mean "did the market move toward the
    agent": the sign is taken against the price the agent was disagreeing with, and the move is measured on
    that same price, so no part of the number compares two different series.
    """
    values: list[int] = []
    n = len(bars)
    for index, bar in enumerate(bars):
        target_ms = bar.t_ms + horizon_days * MS_PER_DAY
        future: ForecastBar | None = None
        for candidate in range(index + 1, n):
            if bars[candidate].t_ms >= target_ms:
                if bars[candidate].t_ms < settle_bar_ms:
                    future = bars[candidate]
                break
        if future is None:
            continue
        stance = bar.prob_ppm - bar.market_prob_ppm
        sign = 0 if stance == 0 else (1 if stance > 0 else -1)
        values.append(sign * (future.market_price_bp - bar.market_price_bp))
    return signed_mean(values)


@dataclass(frozen=True, slots=True)
class BinaryMarketScore:
    """Every forecast number of one ``(agent, binary market)`` row (the ``PerMarket`` fields of 12.11)."""

    n_forecast_bars: int
    agent_brier_tw_micro: int
    market_brier_tw_micro: int
    skill_micro: int
    skill_vs_5000_micro: int
    log_micronats: int
    pmv_1d_bp: int
    pmv_7d_bp: int
    horizons: tuple[HorizonBucket, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "n_forecast_bars": self.n_forecast_bars,
            "agent_brier_tw_micro": self.agent_brier_tw_micro,
            "market_brier_tw_micro": self.market_brier_tw_micro,
            "skill_micro": self.skill_micro,
            "skill_vs_5000_micro": self.skill_vs_5000_micro,
            "log_micronats": self.log_micronats,
            "pmv_1d_bp": self.pmv_1d_bp,
            "pmv_7d_bp": self.pmv_7d_bp,
            "horizons": [bucket.to_dict() for bucket in self.horizons],
        }


def score_binary_market(
    bars: Sequence[ForecastBar], *, outcome: int, close_at_ms: int, settle_bar_ms: int, interval_ms: int
) -> BinaryMarketScore:
    """Score one ``(agent, binary market)`` record: section 12.1 end to end, in one pass of arguments.

    ``settle_bar_ms`` is ``bar_of(resolved_at_ms)``, which PMV needs in order to refuse a future price
    taken from the settling bar (the election-night tape), and ``close_at_ms`` is the market's own close,
    which the horizon buckets need. Both are the runner's to supply: this module reads no dataset.
    """
    return BinaryMarketScore(
        n_forecast_bars=len(bars),
        agent_brier_tw_micro=brier_tw_micro(bars, outcome=outcome, interval_ms=interval_ms),
        market_brier_tw_micro=market_brier_tw_micro(bars, outcome=outcome, interval_ms=interval_ms),
        skill_micro=skill_micro(bars, outcome=outcome, interval_ms=interval_ms),
        skill_vs_5000_micro=skill_vs_5000_micro(bars, outcome=outcome, interval_ms=interval_ms),
        log_micronats=log_micronats(bars, outcome=outcome, interval_ms=interval_ms),
        pmv_1d_bp=pmv_bp(bars, horizon_days=PMV_HORIZONS_DAYS[0], settle_bar_ms=settle_bar_ms),
        pmv_7d_bp=pmv_bp(bars, horizon_days=PMV_HORIZONS_DAYS[1], settle_bar_ms=settle_bar_ms),
        horizons=horizon_buckets(bars, outcome=outcome, close_at_ms=close_at_ms, interval_ms=interval_ms),
    )


# --------------------------------------------------------------------------------------------------
# 17.5 The continuous forecast record: one resolved horizon of one (agent, instrument).
#
# A continuous instrument has no outcome to be right about, so the referee is the realised price path:
# the direction of the move over the horizon (scored by the directional Brier against the random walk's
# 500_000) and, when the agent stated quantiles, how wrong the five of them were (the pinball loss,
# relative to the reference price so that ES and EURUSD pool as relative errors).
# --------------------------------------------------------------------------------------------------
def realised_sign_of(price_realised_ticks: int, price_ref_ticks: int) -> int:
    """``sign(price_realised_ticks - price_ref_ticks)``, in ``{-1, 0, 1}`` (17.5)."""
    move = price_realised_ticks - price_ref_ticks
    if move > 0:
        return 1
    if move < 0:
        return -1
    return 0


def directional_brier_micro(up_ppm: int, realised_sign: int) -> int:
    """The directional Brier of one horizon forecast, in micro-units (17.5, ruling R159).

    A flat return scores half each way, which is the whole point of the tie rule: the random walk then
    scores ``RANDOM_WALK_BRIER_MICRO`` on every realisation including a tie, so its skill is ``0``
    identically and a directional forecast is not rewarded for a price that did not move.
    """
    if realised_sign > 0:
        return brier_micro(up_ppm, 1)
    if realised_sign < 0:
        return brier_micro(up_ppm, 0)
    return (brier_micro(up_ppm, 1) + brier_micro(up_ppm, 0)) // 2


def pinball_micro(quantiles_ticks: Sequence[int], realised_ticks: int, price_ref_ticks: int) -> int:
    """The pinball loss of five quantiles, in micro-units of the reference price (17.5, ruling R159).

    The five levels are ``QUANTILE_LEVELS_PPM`` and the sum is exact in ``ticks * ppm`` before the one
    division, so nothing is rounded twice. ``price_ref_ticks == 0`` reports ``0`` (ruling R2), and a tuple
    that is not five long is a caller's error (``zip(strict=True)`` says so): a non-monotone or short tuple
    is refused at the action boundary as ``action_rejected(bad_quantiles)``, which is E5's, not here.
    """
    if price_ref_ticks <= 0:
        return 0
    total = 0
    for level_ppm, quantile in zip(QUANTILE_LEVELS_PPM, quantiles_ticks, strict=True):
        total += level_ppm * max(0, realised_ticks - quantile) + (PPM_ONE - level_ppm) * max(
            0, quantile - realised_ticks
        )
    return round_half_up(total, len(QUANTILE_LEVELS_PPM) * price_ref_ticks)


def baseline_quantiles_ticks(price_ref_ticks: int) -> tuple[int, ...]:
    """The random walk's five quantiles: the reference price, five times (ruling R158)."""
    return (price_ref_ticks,) * len(QUANTILE_LEVELS_PPM)


def baseline_pinball_micro(realised_ticks: int, price_ref_ticks: int) -> int:
    """The random walk's pinball loss on the same realisation (17.5)."""
    return pinball_micro(baseline_quantiles_ticks(price_ref_ticks), realised_ticks, price_ref_ticks)


def directional_skill_micro(agent_brier_micro: int) -> int:
    """``RANDOM_WALK_BRIER_MICRO - agent_brier_micro`` (17.5)."""
    return RANDOM_WALK_BRIER_MICRO - agent_brier_micro


def pinball_skill_micro(baseline_micro: int, agent_micro: int) -> int:
    """``baseline_pinball_micro - agent_pinball_micro`` (17.5)."""
    return baseline_micro - agent_micro


@dataclass(frozen=True, slots=True)
class HorizonResolution:
    """One resolved horizon forecast: the scored core of a ``forecast_resolved`` event (9.2, R160).

    E5 owns the two lookups that fill ``price_ref_ticks`` and ``price_realised_ticks`` (the close of the
    last completed bar at the forecast bar, and the close of the ``h``-th completed bar after it) and the
    ``carried`` flag; every scored field below is this module's, so the journal and the projection cannot
    disagree about what a loss was.
    """

    forecast_bar_ms: int
    horizon_bars: int
    up_probability_ppm: int
    quantiles_ticks: tuple[int, ...] | None
    price_ref_ticks: int
    price_realised_ticks: int
    realised_sign: int
    directional_brier_micro: int
    pinball_micro: int | None
    baseline_pinball_micro: int
    carried: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "forecast_bar_ms": self.forecast_bar_ms,
            "horizon_bars": self.horizon_bars,
            "up_probability_ppm": self.up_probability_ppm,
            "quantiles_ticks": None if self.quantiles_ticks is None else list(self.quantiles_ticks),
            "price_ref_ticks": self.price_ref_ticks,
            "price_realised_ticks": self.price_realised_ticks,
            "realised_sign": self.realised_sign,
            "directional_brier_micro": self.directional_brier_micro,
            "pinball_micro": self.pinball_micro,
            "baseline_pinball_micro": self.baseline_pinball_micro,
            "carried": self.carried,
        }


def resolve_horizon(
    *,
    forecast_bar_ms: int,
    horizon_bars: int,
    up_probability_ppm: int,
    quantiles_ticks: Sequence[int] | None,
    price_ref_ticks: int,
    price_realised_ticks: int,
    carried: bool = False,
) -> HorizonResolution:
    """Score one horizon at the bar its realisation became public (17.5, ruling R160).

    ``baseline_pinball_micro`` is filled whatever the agent stated, because it depends on the realisation
    and not on the agent; ``pinball_micro`` is ``None`` when the agent stated no quantiles, which is how
    the record says "scored on direction only" instead of pretending a zero loss.
    """
    sign = realised_sign_of(price_realised_ticks, price_ref_ticks)
    quantiles = None if quantiles_ticks is None else tuple(quantiles_ticks)
    return HorizonResolution(
        forecast_bar_ms=forecast_bar_ms,
        horizon_bars=horizon_bars,
        up_probability_ppm=up_probability_ppm,
        quantiles_ticks=quantiles,
        price_ref_ticks=price_ref_ticks,
        price_realised_ticks=price_realised_ticks,
        realised_sign=sign,
        directional_brier_micro=directional_brier_micro(up_probability_ppm, sign),
        pinball_micro=None if quantiles is None else pinball_micro(quantiles, price_realised_ticks, price_ref_ticks),
        baseline_pinball_micro=baseline_pinball_micro(price_realised_ticks, price_ref_ticks),
        carried=carried,
    )


def random_walk_resolution(
    *, forecast_bar_ms: int, horizon_bars: int, price_ref_ticks: int, price_realised_ticks: int
) -> HorizonResolution:
    """The baseline's own resolution on one horizon: ``500_000`` ppm and the reference as every quantile.

    It exists here, in the module that scores, so that the identity ``skill(random_walk) == 0`` is checked
    against the same arithmetic every agent is scored with, rather than against a second implementation in
    the ``random_walk`` family (A1) or in a test.
    """
    return resolve_horizon(
        forecast_bar_ms=forecast_bar_ms,
        horizon_bars=horizon_bars,
        up_probability_ppm=RANDOM_WALK_UP_PPM,
        quantiles_ticks=baseline_quantiles_ticks(price_ref_ticks),
        price_ref_ticks=price_ref_ticks,
        price_realised_ticks=price_realised_ticks,
    )


def horizon_bucket_name(horizon_bars: int) -> str:
    """``f"h{horizon_bars}"``: the bucket string of a continuous horizon (17.5, ruling R161)."""
    return f"h{horizon_bars}"


@dataclass(frozen=True, slots=True)
class ContinuousHorizonScore:
    """One ``(agent, instrument, horizon)`` row: the continuous fields of ``PerMarket`` (12.11, R163)."""

    horizon_bars: int
    bucket: str
    n_resolved: int
    dir_brier_micro: int
    skill_micro: int
    n_quantile_forecasts: int
    pinball_micro: int
    baseline_pinball_micro: int
    pinball_skill_micro: int
    pmv_ticks: int
    pmv_bp: int

    def to_dict(self) -> dict[str, object]:
        return {
            "horizon_bars": self.horizon_bars,
            "bucket": self.bucket,
            "n_resolved": self.n_resolved,
            "dir_brier_micro": self.dir_brier_micro,
            "skill_micro": self.skill_micro,
            "n_quantile_forecasts": self.n_quantile_forecasts,
            "pinball_micro": self.pinball_micro,
            "baseline_pinball_micro": self.baseline_pinball_micro,
            "pinball_skill_micro": self.pinball_skill_micro,
            "pmv_ticks": self.pmv_ticks,
            "pmv_bp": self.pmv_bp,
        }

    def as_bucket(self) -> HorizonBucket:
        """The same row as a ``HorizonBucket``, which is what ``AgentResult.horizons`` carries (17.5)."""
        return HorizonBucket(
            bucket=self.bucket,
            n_bars=self.n_resolved,
            brier_tw_micro=self.dir_brier_micro,
            market_brier_tw_micro=RANDOM_WALK_BRIER_MICRO if self.n_resolved > 0 else 0,
            skill_micro=self.skill_micro,
        )


def score_continuous_horizon(
    resolutions: Sequence[HorizonResolution], *, horizon_bars: int
) -> ContinuousHorizonScore:
    """Aggregate one ``(agent, instrument, horizon)`` cell: the plain mean, stated as a rule (R191).

    The directional mean is over every resolved forecast; the pinball mean is over the forecasts that
    stated quantiles, and the baseline's pinball is averaged over **that same subset**, so the two sides of
    ``pinball_skill_micro`` are paired forecast by forecast and an agent cannot improve its pinball skill
    by staying silent on the bars where the baseline did badly. A cell with no resolved forecast, or one
    where nobody stated a quantile, reports zeros with its ``n`` at ``0`` (ruling R2).
    """
    picked = [item for item in resolutions if item.horizon_bars == horizon_bars]
    dir_brier = plain_mean_micro([item.directional_brier_micro for item in picked])
    quantile_rows = [item for item in picked if item.pinball_micro is not None]
    agent_pinball = plain_mean_micro([item.pinball_micro or 0 for item in quantile_rows])
    baseline_pinball = plain_mean_micro([item.baseline_pinball_micro for item in quantile_rows])
    moves_ticks: list[int] = []
    moves_bp: list[int] = []
    for item in picked:
        stance = item.up_probability_ppm - RANDOM_WALK_UP_PPM
        sign = 0 if stance == 0 else (1 if stance > 0 else -1)
        move = sign * (item.price_realised_ticks - item.price_ref_ticks)
        moves_ticks.append(move)
        moves_bp.append(bp_ratio(move, item.price_ref_ticks) if item.price_ref_ticks > 0 else 0)
    return ContinuousHorizonScore(
        horizon_bars=horizon_bars,
        bucket=horizon_bucket_name(horizon_bars),
        n_resolved=len(picked),
        dir_brier_micro=dir_brier,
        skill_micro=directional_skill_micro(dir_brier) if picked else 0,
        n_quantile_forecasts=len(quantile_rows),
        pinball_micro=agent_pinball,
        baseline_pinball_micro=baseline_pinball,
        pinball_skill_micro=pinball_skill_micro(baseline_pinball, agent_pinball),
        pmv_ticks=signed_mean(moves_ticks),
        pmv_bp=signed_mean(moves_bp),
    )


def score_continuous_market(
    resolutions: Sequence[HorizonResolution], *, horizons_bars: Sequence[int]
) -> tuple[ContinuousHorizonScore, ...]:
    """One row per declared horizon, in the ascending order ``RunConfig.horizons_bars`` declares (17.5).

    Every declared horizon gets a row even when nothing resolved at it, for the reason the four binary
    buckets are always all four: a fixed shape is what lets the projection, the leaderboard and the claim
    line up without asking which horizons happened to resolve.
    """
    return tuple(score_continuous_horizon(resolutions, horizon_bars=horizon) for horizon in horizons_bars)


# --------------------------------------------------------------------------------------------------
# 10.3 The integer logit table: the fixed-point log-odds `newsbayes` updates in, and the `logit_last_milli`
# feature of `features.v1`.
#
# `newsbayes` states `logit_milli(p) = logit_milli(prior) + sum(hits * weight_per_hit_milli)` and reads
# the probability back. Doing that with `math.log` would put a platform's libm inside a genome's output,
# so the same genome would score differently on glibc and on msvcrt and every determinism claim of
# section 6.4 would be false. The table is therefore built once, at import, from `Decimal` at the
# precision section 1.3 pins, and both directions read it: the arithmetic between them is integer
# addition, which is exact.
#
# 10 001 entries, indexed by a probability in basis points (`0..BP_ONE`), because a basis point is the
# resolution a price is quoted in (section 1.1) and `logit_last_milli` is the logit of `last_price_bp`.
# The two ends are not representable (`logit(0)` and `logit(1)` are infinite), so index `0` carries index
# `1`'s value and index `BP_ONE` carries index `BP_ONE - 1`'s: the clamp of `bp_from_ppm` (a tradable
# price is never 0 and never 1), applied to the logit rather than to the price.
# --------------------------------------------------------------------------------------------------
#: Milli-nats per nat: the unit `logit_milli` reports and `weight_per_hit_milli` is added in (section 1.1).
LOGIT_MILLI_SCALE = 1_000

#: The precision of the one `Decimal` context that builds the table (section 1.3's, for the same reason).
LOGIT_PRECISION = 40

#: The table's probability resolution: one basis point, so `BP_ONE + 1 == 10_001` entries (section 10.3).
LOGIT_TABLE_STEPS = BP_ONE
LOGIT_TABLE_SIZE = LOGIT_TABLE_STEPS + 1

#: The first and last representable indices: a logit exists strictly inside `(0, 1)`.
LOGIT_MIN_INDEX = 1
LOGIT_MAX_INDEX = LOGIT_TABLE_STEPS - 1

#: The index of even odds: `500_000` ppm, where the logit is `0` and the two halves meet.
LOGIT_EVEN_INDEX = LOGIT_TABLE_STEPS // 2

#: How many ppm one table step spans: `1_000_000 // 10_000`.
PPM_PER_LOGIT_STEP = PPM_ONE // LOGIT_TABLE_STEPS

#: The table's worst resolution loss over a full round trip, in ppm, reached at even odds where one basis
#: point of probability is four tenths of a milli-nat and a run of indices shares one milli value. It is
#: declared because it is the honest resolution of a milli-nat log-odds, not a tolerance to be widened:
#: the test pins it and asserts that it is **attained**, so a change of the table or of either direction
#: that made the loss larger fails rather than being absorbed.
LOGIT_ROUND_TRIP_PPM_MAX = 250


def _build_logit_table() -> tuple[int, ...]:
    """``ln(i / (BP_ONE - i))`` in milli-nats at every index, from ``Decimal`` at ``LOGIT_PRECISION``.

    Only the lower half is computed and the upper half is its mirror: ``logit(1 - p) == -logit(p)``, so
    mirroring makes the table **exactly** antisymmetric instead of antisymmetric up to two roundings, and
    it is what lets ``logit_milli`` be added to and subtracted from without a bias toward one side. The
    rounding is half away from zero for the reason ``bp_ratio`` rounds that way (section 1.2): a move up
    and the mirror move down must report the same magnitude.
    """
    table = [0] * LOGIT_TABLE_SIZE
    with localcontext() as ctx:
        ctx.prec = LOGIT_PRECISION
        scale = Decimal(LOGIT_MILLI_SCALE)
        for index in range(LOGIT_MIN_INDEX, LOGIT_TABLE_STEPS // 2):
            value = -(Decimal(LOGIT_TABLE_STEPS - index) / Decimal(index)).ln() * scale
            milli = int(value.to_integral_value(rounding=ROUND_HALF_UP))
            table[index] = milli
            table[LOGIT_TABLE_STEPS - index] = -milli
    table[0] = table[LOGIT_MIN_INDEX]
    table[LOGIT_TABLE_STEPS] = table[LOGIT_MAX_INDEX]
    return tuple(table)


#: The one table (section 10.3): non-decreasing, antisymmetric, ``0`` at ``500_000`` ppm.
LOGIT_TABLE: tuple[int, ...] = _build_logit_table()


def logit_index_of(prob_ppm: int) -> int:
    """The table index of a probability: ``prob_ppm`` to the nearest basis point, a tie toward even odds.

    Rounding rather than truncating is what keeps ``logit_milli`` antisymmetric on the ppm grid and not
    only on the table's own: ``// PPM_PER_LOGIT_STEP`` would send ``250_050`` ppm and its mirror
    ``749_950`` ppm to indices that do not sum to ``BP_ONE``. A tie resolves **toward** ``LOGIT_EVEN_INDEX``
    for the same reason ``bp_ratio`` rounds half away from zero (section 1.2): the two directions must be
    treated identically, and half up would round both a probability and its mirror the same way (up),
    which is the one rule that cannot be symmetric. Rounding toward even odds also never makes a
    statement more confident than it was.
    """
    if prob_ppm <= 0:
        return 0
    if prob_ppm >= PPM_ONE:
        return LOGIT_TABLE_STEPS
    index, remainder = divmod(prob_ppm, PPM_PER_LOGIT_STEP)
    twice = 2 * remainder
    if twice > PPM_PER_LOGIT_STEP or (twice == PPM_PER_LOGIT_STEP and index < LOGIT_EVEN_INDEX):
        index += 1
    return index


def logit_milli(prob_ppm: int) -> int:
    """``ln(p / (1 - p))`` in milli-nats, from the table (section 10.3).

    The argument is a probability in ppm, the one probability unit of ``pmx`` (``neg_ln_micronats`` and
    ``brier_micro`` read the same unit), so a caller holding a price in basis points writes
    ``logit_milli(ppm_from_bp(price_bp))`` and no second convention exists. ``0`` and ``PPM_ONE`` are
    clamped to the first and last representable index rather than raising, because a genome's prior can
    reach either end and a family is never allowed to crash the run.
    """
    return LOGIT_TABLE[logit_index_of(prob_ppm)]


def unlogit_ppm(logit_value_milli: int) -> int:
    """The probability in ppm whose ``logit_milli`` is nearest to ``logit_value_milli`` (section 10.3).

    The inverse is a lookup in the same table, not a second formula, so ``newsbayes`` cannot drift from
    its own prior by disagreeing with itself. Two properties hold and are tested:

    * the result is always representable, in ``[100, 999_900]`` ppm: a log-odds sum of any size returns a
      tradable probability rather than ``0``, ``PPM_ONE`` or an exception;
    * it is **idempotent** under a round trip (``unlogit_ppm(logit_milli(unlogit_ppm(x)))`` is
      ``unlogit_ppm(x)``), and antisymmetric (``unlogit_ppm(-x) == PPM_ONE - unlogit_ppm(x)``).

    It is not injective, and cannot be: near ``500_000`` ppm one basis point of probability is four tenths
    of a milli-nat, so a run of two or three indices shares one milli value. The representative of such a
    run is its member nearest ``LOGIT_EVEN_INDEX``, which is what makes both properties above hold and
    what keeps the resolution loss pointed at even odds rather than at certainty; the whole round trip is
    within ``LOGIT_ROUND_TRIP_PPM_MAX`` ppm of the probability it started from, and the value round trip
    ``logit_milli(unlogit_ppm(logit_milli(p))) == logit_milli(p)`` is exact.
    """
    if logit_value_milli <= LOGIT_TABLE[LOGIT_MIN_INDEX]:
        return LOGIT_MIN_INDEX * PPM_PER_LOGIT_STEP
    if logit_value_milli >= LOGIT_TABLE[LOGIT_MAX_INDEX]:
        return LOGIT_MAX_INDEX * PPM_PER_LOGIT_STEP
    above = bisect_left(LOGIT_TABLE, logit_value_milli, lo=LOGIT_MIN_INDEX, hi=LOGIT_MAX_INDEX)
    below = above - 1
    distance_above = LOGIT_TABLE[above] - logit_value_milli
    distance_below = logit_value_milli - LOGIT_TABLE[below]
    if distance_above == distance_below:
        nearer = above if above <= LOGIT_EVEN_INDEX else below
    else:
        nearer = above if distance_above < distance_below else below
    step = 1 if nearer < LOGIT_EVEN_INDEX else -1
    while nearer != LOGIT_EVEN_INDEX and LOGIT_TABLE[nearer + step] == LOGIT_TABLE[nearer]:
        nearer += step
    return nearer * PPM_PER_LOGIT_STEP
