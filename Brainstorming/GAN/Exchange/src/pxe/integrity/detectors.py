"""The offline integrity detectors (PRD section 7.5, CONTRACTS section 7.18, A18).

Five detectors read a finished match and describe what looks wrong with it:

* :class:`CollusionDetector` (``collusion``), the net flow correlation between
  agent pairs weighted by how concentrated each side's volume is on the other;
* :class:`OffMarketTransferDetector` (``off_market_transfer``), wealth moved
  through executions far from the reference price, beyond ``k`` standard
  deviations of the match's own execution dispersion;
* :class:`WashTradingDetector` (``wash_trading``), economic round trips between
  accomplices, that is volume without exposure;
* :class:`SpoofingDetector` (``spoofing``), an abnormal cancel to execution
  ratio;
* :class:`PredictionMismatchDetector` (``prediction_position_mismatch``),
  declaring one probability and trading against it.

Four rules shape this module, and each of them is a contract clause rather than
a preference.

**A detector is a projection.** It consumes a
:class:`~pxe.metrics.projection.MatchProjection` and nothing else: no engine
state, no world, no latent process, no agent object (CONTRACTS section 7.17). A
detector that needed engine state would be a contract issue, not a licence to
import the engine.

**A detector never influences a score.** Incidents are not journalled
(CONTRACTS section 4.5) and no metric, ranking or rating reads them, so bumping
a detector cannot move a journal hash and cannot penalise an agent. This is PRD
section 7.2's anti-hacking principle: prediction and position incoherence is a
*descriptor*, never a penalty.

**Every alert is timestamped.** ``Incident.tick`` is the last tick of the window
the alert is about, so an incident always points at a place in the replay
(PRD section 7.5: "chaque alerte cree un incident horodate").

**Integer arithmetic only.** Money is cents, every score is parts per million,
and the one square root this module needs (the norm inside a cosine) goes
through :func:`math.isqrt`, never through ``math.sqrt`` or a float division.
Floats would be *allowed* here, since nothing in this package reaches a journal
(CONTRACTS section 2.1), but a detector that is bit identical on Windows and on
Linux is a detector whose bench numbers can be quoted, so nothing is left to the
platform libm.

What ``min_trades`` is for
--------------------------
Every score below is a ratio, and a ratio over two executions is a coincidence
rather than a pattern: an agent whose whole match is one trade with one
counterparty scores a perfect 1 000 000 on concentration. ``min_trades`` is the
evidence floor that keeps those out, and it is why the honest false positive rate
of AC-P6 is reachable at all.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, ClassVar, Protocol

from pxe.events import JOURNAL_ENCODING, JOURNAL_NEWLINE, canonical_json
from pxe.metrics.projection import MatchProjection, TradeRecord
from pxe.types import (
    BPS_ONE,
    MILLI_ONE,
    PAYOUT_YES_CENTS,
    PPM_ONE,
    CancelReason,
    Incident,
    IncidentKind,
    incident_detail_to_dict,
    make_incident_id,
)

__all__ = [
    "DETECTOR_VERSION",
    "DetectorConfig",
    "Detector",
    "CollusionDetector",
    "OffMarketTransferDetector",
    "WashTradingDetector",
    "SpoofingDetector",
    "PredictionMismatchDetector",
    "DETECTORS",
    "run_detectors",
    "collusion_index",
    "write_incidents",
]

#: Version of every detector in this module. It is stamped on
#: ``Incident.detector_version`` together with the detector name, so an incident
#: read back from ``incidents.jsonl`` says which code produced it. Bump it when a
#: scoring rule changes: incidents are outside the journal, so this is the only
#: version marker that can tell two generations of alerts apart.
DETECTOR_VERSION = "1.0.0"

#: Probability, in ppm, of one cent of price. A price of ``p`` cents is the
#: market implied probability ``p / 100``, so one cent is 10 000 ppm.
_PPM_PER_CENT: int = PPM_ONE // PAYOUT_YES_CENTS

#: Parts per million per thousandth, for the ``off_market_sigma_milli`` to ppm
#: conversion of :class:`OffMarketTransferDetector`.
_PPM_PER_MILLI: int = PPM_ONE // MILLI_ONE

#: Smallest execution dispersion the off market detector will divide by, in
#: thousandths of a cent. A match whose every print landed exactly on the
#: reference price has a dispersion of zero, and without a floor a single one
#: cent print would then be infinitely many standard deviations away. One cent is
#: the price tick, so this reads as "no market is tighter than its own tick".
_MIN_DISPERSION_MILLI: int = MILLI_ONE

#: Consistency factor between a median absolute deviation and a standard
#: deviation for normally distributed data, in ten-thousandths (1.4826). It is
#: what keeps "beyond k standard deviations" meaning what it says while the scale
#: itself is estimated robustly (see :func:`_dispersion_milli`).
_MAD_TO_SIGMA_BPS: int = 14_826

#: A score at or above this many ppm is reported as ``"high"`` whatever the
#: threshold was: for a bounded score it means the evidence is nearly total.
_HIGH_SEVERITY_PPM: int = 900_000

#: A score at or above ``threshold * _MEDIUM_NUM / _MEDIUM_DEN`` is ``"medium"``.
_MEDIUM_NUM: int = 6
_MEDIUM_DEN: int = 5


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class DetectorConfig:
    """The five calibrated knobs of the detector suite (CONTRACTS section 7.18).

    The defaults are the ones the T5.5 bench calibrates and
    ``tests/test_integrity.py`` measures AC-P6 against, on a calibration set of
    seeds held out from the evaluation set.

    Attributes:
        collusion_threshold_ppm: Lowest :func:`collusion_index` value that raises
            a ``collusion`` incident. It also gates ``wash_trading``, which is
            the same pair level evidence read for balance instead of for
            direction: CONTRACTS section 7.18 deliberately carries no wash
            specific knob.
        off_market_sigma_milli: ``k`` in "beyond ``k`` standard deviations", in
            thousandths, so ``3_000`` is three sigma.
        spoofing_cancel_ratio_ppm: Lowest share of an agent's own quoted
            quantity that left the book unfilled, on the agent's own request,
            that raises a ``spoofing`` incident.
        mismatch_threshold_ppm: Lowest volume weighted contradiction between a
            declared probability and the price the agent traded at, in ppm of
            probability, that raises a ``prediction_position_mismatch``
            incident. ``300_000`` is thirty points of probability.
        min_trades: Evidence floor. An agent or a pair with fewer executions
            than this is never judged, whatever its ratios look like.
    """

    collusion_threshold_ppm: int = 700_000
    off_market_sigma_milli: int = 3_000
    spoofing_cancel_ratio_ppm: int = 900_000
    mismatch_threshold_ppm: int = 300_000
    min_trades: int = 5


class Detector(Protocol):
    """One offline detector (CONTRACTS section 7.18).

    Attributes:
        name: Detector name, a class level constant so a caller can list the
            suite without instantiating anything.
        version: Version of the scoring rule.
    """

    name: ClassVar[str]
    version: ClassVar[str]

    def run(self, projection: MatchProjection, config: DetectorConfig) -> tuple[Incident, ...]:
        """Score one finished match.

        Args:
            projection: The folded journal of the match.
            config: The calibrated thresholds.

        Returns:
            The incidents, in this detector's own canonical order. Incident ids
            are positional and :func:`run_detectors` renumbers them across the
            whole suite.
        """
        ...


# --------------------------------------------------------------------------
# Shared integer helpers. Private.
# --------------------------------------------------------------------------
def _ratio_ppm(numerator: int, denominator: int) -> int:
    """Return ``numerator / denominator`` in ppm, rounded half up.

    Args:
        numerator: Non negative numerator.
        denominator: Denominator. A non positive one means "no evidence".

    Returns:
        The ratio in parts per million, ``0`` when ``denominator`` is not
        positive.
    """
    if denominator <= 0:
        return 0
    return (numerator * 2 * PPM_ONE + denominator) // (2 * denominator)


def _product_ppm(left_ppm: int, right_ppm: int) -> int:
    """Multiply two ppm values, rounding half up.

    Args:
        left_ppm: First factor in ppm.
        right_ppm: Second factor in ppm.

    Returns:
        Their product in ppm.
    """
    return (left_ppm * right_ppm * 2 + PPM_ONE) // (2 * PPM_ONE)


def _weighted_mean(total: int, weight: int) -> int:
    """Return ``total / weight``, rounded half up.

    The sibling of :func:`_ratio_ppm` for a value that is **already** in ppm and
    only needs its weight divided out. Going through ``_ratio_ppm`` would scale
    by 1 000 000 a second time.

    Args:
        total: Sum of ``value_ppm * weight`` terms.
        weight: Sum of the weights.

    Returns:
        The weighted mean, ``0`` when there is no weight.
    """
    if weight <= 0:
        return 0
    return (total * 2 + weight) // (2 * weight)


def _cosine_ppm(left: Sequence[int], right: Sequence[int]) -> int:
    """Return the magnitude of the uncentered correlation of two series, in ppm.

    This is ``|<a, b>| / (||a|| * ||b||)``, that is the cosine of the angle
    between the two per tick net flow series, and **not** Pearson's centered
    correlation. The difference is load bearing. Two accomplices that transfer
    the same quantity on the same ticks produce two *constant* flow series over
    the ticks they act on, and a constant series has zero variance: Pearson is
    undefined exactly on the cleanest collusion pattern there is, while the
    cosine reads it as 1 000 000. Centering also subtracts a match long mean
    from a sparse series, which mixes "did not trade" with "traded against the
    average".

    The whole computation is integral, through :func:`math.isqrt`, so the value
    is bit identical on every platform.

    Args:
        left: Per tick net signed quantities of the first agent.
        right: Per tick net signed quantities of the second agent, same length.

    Returns:
        A value in ``0..1_000_000``. Zero when either series is all zeros.
    """
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = sum(a * a for a in left)
    norm_right = sum(b * b for b in right)
    if norm_left == 0 or norm_right == 0:
        return 0
    scaled = (dot * dot * PPM_ONE * PPM_ONE) // (norm_left * norm_right)
    return min(PPM_ONE, math.isqrt(scaled))


def _dispersion_milli(distances: Sequence[int]) -> int:
    """Return the robust scale of a set of distances, in thousandths of a cent.

    This is ``1.4826 * median(|price - ref_price|)``, that is a median absolute
    deviation about the null (the reference price, FR-5.4.6) rescaled to read as
    a standard deviation. **Not** the root mean square, and the difference is the
    whole detector.

    A wealth transfer is a handful of prints tens of cents away from the
    reference price. Those prints are part of the sample, and a squared estimator
    lets them inflate the very scale they are measured against: a colluding pair
    that transfers twenty-four times at forty-five cents out pushes the root mean
    square past twenty cents, so three sigma becomes sixty and the transfer
    grades as normal. The bigger the cheat, the better it hides. A median moves
    by at most one order of the sample when a minority of prints goes to an
    extreme, so the scale stays the scale of the honest flow, which is what "k
    standard deviations from the reference price" is supposed to compare against.

    Args:
        distances: One non negative distance per execution, in cents.

    Returns:
        The scale in thousandths of a cent, never below
        :data:`_MIN_DISPERSION_MILLI`.
    """
    ordered = sorted(distances)
    count = len(ordered)
    if count == 0:  # pragma: no cover - callers guard on min_trades first
        return _MIN_DISPERSION_MILLI
    if count % 2 == 1:
        median_milli = ordered[count // 2] * MILLI_ONE
    else:
        median_milli = (ordered[count // 2 - 1] + ordered[count // 2]) * MILLI_ONE // 2
    return max(_MIN_DISPERSION_MILLI, median_milli * _MAD_TO_SIGMA_BPS // BPS_ONE)


def _severity_of(score_ppm: int, threshold_ppm: int) -> str:
    """Grade one alert from how far past its threshold it landed.

    One rule for the five detectors, because a severity that means a different
    thing per family cannot be sorted in a report.

    Args:
        score_ppm: The detector score.
        threshold_ppm: The threshold it passed.

    Returns:
        ``"high"``, ``"medium"`` or ``"low"``.
    """
    if score_ppm >= 2 * threshold_ppm or score_ppm >= _HIGH_SEVERITY_PPM:
        return "high"
    if score_ppm * _MEDIUM_DEN >= threshold_ppm * _MEDIUM_NUM:
        return "medium"
    return "low"


def _signed_qty(trade: TradeRecord, agent_id: str) -> int:
    """Return the signed quantity one account took out of a trade.

    Args:
        trade: One execution row.
        agent_id: The account to look at.

    Returns:
        ``+qty`` when the account bought, ``-qty`` when it sold, ``0`` when it is
        not a party to the trade.
    """
    if trade.maker_agent_id == agent_id and trade.taker_agent_id != agent_id:
        return trade.qty if trade.maker_side == "buy" else -trade.qty
    if trade.taker_agent_id == agent_id and trade.maker_agent_id != agent_id:
        return trade.qty if trade.taker_side == "buy" else -trade.qty
    return 0


def _pair_key(first: str, second: str) -> tuple[str, str]:
    """Return one unordered pair of seats as an ordered key.

    Args:
        first: One seat id.
        second: The other seat id.

    Returns:
        The two ids, smaller first. The result is only a dictionary key here;
        every pair that reaches an output is re-ordered through the projection's
        own ``agent_ids`` order, which is the canonical seat order of CONTRACTS
        section 2.3, by :meth:`_TradeView.pairs`.
    """
    return (first, second) if first <= second else (second, first)


# --------------------------------------------------------------------------
# One pass over the trade rows, shared by four of the five detectors
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class _PairStats:
    """What two seats did to each other over one match, or over one market.

    Attributes:
        qty: Total quantity they traded with each other.
        trades: Number of such executions.
        last_tick: Tick of the last of them.
        first_bought_qty: Quantity the first seat of the key bought from the
            second one.
        first_sold_qty: Quantity the first seat sold to the second one.
    """

    qty: int
    trades: int
    last_tick: int
    first_bought_qty: int
    first_sold_qty: int


@dataclass(frozen=True)
class _TradeView:
    """The trade rows of one match, indexed the four ways the detectors read them.

    Attributes:
        agent_ids: The ranked seats, ascending, straight from the projection.
        flows: Per seat, the per tick net signed quantity, length
            ``ticks_total``.
        volume_qty: Per seat, total quantity traded against anybody, the market
            maker included.
        trade_count: Per seat, number of executions it was a party to.
        pair_stats: Per unordered seat pair, aggregated over every market.
        pair_market_stats: Per ``(seat, seat, market_id)``.
    """

    agent_ids: tuple[str, ...]
    flows: Mapping[str, tuple[int, ...]]
    volume_qty: Mapping[str, int]
    trade_count: Mapping[str, int]
    pair_stats: Mapping[tuple[str, str], _PairStats]
    pair_market_stats: Mapping[tuple[str, str, str], _PairStats]

    def pairs(self) -> tuple[tuple[str, str], ...]:
        """Return every seat pair that traded with the other, ascending.

        Returns:
            The pairs, ordered by ``(first, second)`` in the canonical seat order
            the projection publishes.
        """
        rank = {agent_id: index for index, agent_id in enumerate(self.agent_ids)}
        keys = [key for key in self.pair_stats if key[0] in rank and key[1] in rank]
        keys.sort(key=lambda key: (rank[key[0]], rank[key[1]]))
        return tuple(keys)

    def markets_of(self, pair: tuple[str, str], market_ids: Sequence[str]) -> tuple[str, ...]:
        """Return the markets one pair traded on, in the projection's order.

        Args:
            pair: The pair key.
            market_ids: ``MatchProjection.market_ids``, already ascending.

        Returns:
            The subset they met on, in that same order.
        """
        return tuple(m for m in market_ids if (pair[0], pair[1], m) in self.pair_market_stats)

    def share_ppm(self, agent_id: str, pair_qty: int) -> int:
        """Return how much of one seat's volume went to one counterparty.

        Args:
            agent_id: The seat.
            pair_qty: Quantity it traded with that counterparty.

        Returns:
            The share in ppm, ``0`` when the seat never traded.
        """
        return _ratio_ppm(pair_qty, self.volume_qty.get(agent_id, 0))


def _accumulate(
    stats: _PairStats | None,
    *,
    qty: int,
    tick: int,
    bought_by_first: int,
    sold_by_first: int,
) -> _PairStats:
    """Fold one execution into a pair accumulator.

    Args:
        stats: The accumulator so far, or ``None`` for the first execution.
        qty: Quantity of the execution.
        tick: Tick of the execution.
        bought_by_first: ``qty`` when the first seat of the key was the buyer.
        sold_by_first: ``qty`` when the first seat was the seller.

    Returns:
        The updated accumulator.
    """
    if stats is None:
        return _PairStats(
            qty=qty,
            trades=1,
            last_tick=tick,
            first_bought_qty=bought_by_first,
            first_sold_qty=sold_by_first,
        )
    return _PairStats(
        qty=stats.qty + qty,
        trades=stats.trades + 1,
        last_tick=max(stats.last_tick, tick),
        first_bought_qty=stats.first_bought_qty + bought_by_first,
        first_sold_qty=stats.first_sold_qty + sold_by_first,
    )


def _build_trade_view(projection: MatchProjection) -> _TradeView:
    """Index the trade rows of one match once, for every detector that needs them.

    Args:
        projection: The folded journal.

    Returns:
        The :class:`_TradeView` of that match.
    """
    seats = frozenset(projection.agent_ids)
    flows: dict[str, list[int]] = {agent_id: [0] * projection.ticks_total for agent_id in projection.agent_ids}
    volume: dict[str, int] = dict.fromkeys(projection.agent_ids, 0)
    counts: dict[str, int] = dict.fromkeys(projection.agent_ids, 0)
    pair_stats: dict[tuple[str, str], _PairStats] = {}
    pair_market: dict[tuple[str, str, str], _PairStats] = {}
    for trade in projection.trades:
        index = trade.tick - 1
        for agent_id in (trade.maker_agent_id, trade.taker_agent_id):
            if agent_id not in seats:
                continue
            volume[agent_id] += trade.qty
            counts[agent_id] += 1
            if 0 <= index < projection.ticks_total:
                flows[agent_id][index] += _signed_qty(trade, agent_id)
        if trade.maker_agent_id not in seats or trade.taker_agent_id not in seats:
            continue
        key = _pair_key(trade.maker_agent_id, trade.taker_agent_id)
        bought = trade.qty if _signed_qty(trade, key[0]) > 0 else 0
        pair_stats[key] = _accumulate(
            pair_stats.get(key),
            qty=trade.qty,
            tick=trade.tick,
            bought_by_first=bought,
            sold_by_first=trade.qty - bought,
        )
        market_key = (key[0], key[1], trade.market_id)
        pair_market[market_key] = _accumulate(
            pair_market.get(market_key),
            qty=trade.qty,
            tick=trade.tick,
            bought_by_first=bought,
            sold_by_first=trade.qty - bought,
        )
    return _TradeView(
        agent_ids=projection.agent_ids,
        flows={agent_id: tuple(series) for agent_id, series in flows.items()},
        volume_qty=volume,
        trade_count=counts,
        pair_stats=pair_stats,
        pair_market_stats=pair_market,
    )


def _incident(
    *,
    index: int,
    kind: IncidentKind,
    detector: str,
    tick: int,
    agent_ids: Sequence[str],
    market_ids: Sequence[str],
    score_ppm: int,
    threshold_ppm: int,
    detail: Sequence[tuple[str, Any]],
) -> Incident:
    """Build one incident with a positional id and the graded severity.

    Args:
        index: 1 based position inside this detector's own output.
        kind: Alert family.
        detector: Detector name, stamped into ``detector_version``.
        tick: Last tick of the window the alert is about.
        agent_ids: Implicated seats, already in canonical order.
        market_ids: Implicated markets, already in canonical order.
        score_ppm: The detector score.
        threshold_ppm: The threshold it passed, for the severity grading.
        detail: Ordered evidence pairs. Values are JSON scalars, never floats.

    Returns:
        The incident. Its ``incident_id`` is renumbered by
        :func:`run_detectors` across the whole suite.
    """
    return Incident(
        incident_id=make_incident_id(index),
        kind=kind,
        severity=_severity_of(score_ppm, threshold_ppm),
        tick=tick,
        agent_ids=tuple(agent_ids),
        market_ids=tuple(market_ids),
        score_ppm=score_ppm,
        detail=tuple(detail),
        detector_version=f"{detector}@{DETECTOR_VERSION}",
    )


# --------------------------------------------------------------------------
# The collusion index (CONTRACTS section 7.18)
# --------------------------------------------------------------------------
def _pair_scores(view: _TradeView, pair: tuple[str, str]) -> tuple[int, int, int]:
    """Return ``(correlation_ppm, concentration_ppm, index_ppm)`` of one pair.

    Args:
        view: The indexed trade rows.
        pair: The pair key.

    Returns:
        The two factors of the collusion index and their product.
    """
    stats = view.pair_stats[pair]
    correlation_ppm = _cosine_ppm(view.flows[pair[0]], view.flows[pair[1]])
    concentration_ppm = min(view.share_ppm(pair[0], stats.qty), view.share_ppm(pair[1], stats.qty))
    return correlation_ppm, concentration_ppm, _product_ppm(concentration_ppm, correlation_ppm)


def collusion_index(projection: MatchProjection) -> tuple[tuple[str, str, int], ...]:
    """Return ``(agent_a, agent_b, index_ppm)`` per pair, sorted by pair, ``a < b``.

    PRD section 7.5 asks for "la correlation nette des flux entre paires
    d'agents". Correlation alone cannot name a pair: two agents that both take
    the market maker's offer on the same news tick are perfectly correlated
    without ever meeting. The index is therefore the product of two ppm factors:

    * **the flow correlation**, ``|cos|`` between the two per tick net signed
      quantity series (see :func:`_cosine_ppm` for why it is uncentered);
    * **the pair concentration**, the *smaller* of the two shares
      ``quantity traded with the other / own total volume``. The minimum, not the
      mean: both sides must be concentrated on each other, so a seat that was
      merely swept once by a whale cannot be dragged into a pair by the whale's
      own concentration.

    Both factors are in ``0..1_000_000`` and so is the product, which makes
    ``DetectorConfig.collusion_threshold_ppm`` readable as "how much of this
    pair's behaviour is the other one".

    Only pairs that actually traded with each other appear. A row per unordered
    pair of seats would be mostly zeros, since in an honest match most pairs
    never meet, and a consumer looking for evidence would have to filter them out
    again.

    Args:
        projection: The folded journal, from ``project(events)``.

    Returns:
        One row per pair that traded, ascending by ``(agent_a, agent_b)`` in the
        canonical seat order.
    """
    view = _build_trade_view(projection)
    return tuple((pair[0], pair[1], _pair_scores(view, pair)[2]) for pair in view.pairs())


# --------------------------------------------------------------------------
# The five detectors
# --------------------------------------------------------------------------
class CollusionDetector:
    """Raises one ``collusion`` incident per pair whose index passes the threshold.

    The score is :func:`collusion_index`. Two evidence floors apply, and they are
    what makes AC-P6's "under 5 % false positives on an honest population"
    reachable: the pair must have met at least ``min_trades`` times, and each
    side must have traded at least ``min_trades`` times in the match, so a seat
    with three executions in total cannot score a perfect concentration.
    """

    name: ClassVar[str] = "collusion"
    version: ClassVar[str] = DETECTOR_VERSION

    def run(self, projection: MatchProjection, config: DetectorConfig) -> tuple[Incident, ...]:
        """Score every pair of seats.

        Args:
            projection: The folded journal.
            config: The calibrated thresholds.

        Returns:
            The incidents, ascending by pair.
        """
        view = _build_trade_view(projection)
        found: list[Incident] = []
        for pair in view.pairs():
            stats = view.pair_stats[pair]
            if stats.trades < config.min_trades:
                continue
            if min(view.trade_count[pair[0]], view.trade_count[pair[1]]) < config.min_trades:
                continue
            correlation_ppm, concentration_ppm, score_ppm = _pair_scores(view, pair)
            if score_ppm < config.collusion_threshold_ppm:
                continue
            found.append(
                _incident(
                    index=len(found) + 1,
                    kind=IncidentKind.COLLUSION,
                    detector=self.name,
                    tick=stats.last_tick,
                    agent_ids=pair,
                    market_ids=view.markets_of(pair, projection.market_ids),
                    score_ppm=score_ppm,
                    threshold_ppm=config.collusion_threshold_ppm,
                    detail=(
                        ("flow_correlation_ppm", correlation_ppm),
                        ("pair_concentration_ppm", concentration_ppm),
                        ("mutual_qty", stats.qty),
                        ("mutual_trades", stats.trades),
                        ("threshold_ppm", config.collusion_threshold_ppm),
                    ),
                )
            )
        return tuple(found)


class OffMarketTransferDetector:
    """Raises one ``off_market_transfer`` incident per pair and market traded far from reference.

    PRD section 7.5 asks for "detection de transferts de richesse par trades
    eloignes du prix de reference (> k ecarts-types)". The dispersion is the
    match's own: a robust scale of the distance between an execution price and the
    reference price of that market at that tick, over **every** execution
    including the market maker's, because the market maker's prints are what
    normal looks like. It is a rescaled median absolute deviation and not a root
    mean square, so the transfer cannot inflate the scale it is measured against
    (:func:`_dispersion_milli` says why that matters), and it is measured about
    zero and not about the sample mean, because the null hypothesis is not
    "trades happen at the average deviation", it is "trades happen at the
    reference price" (FR-5.4.6).

    Only executions where **both** sides are ranked seats are reported: a leg
    against the market maker moves cash between an agent and the liquidity
    provider, which is the cost of liquidity (FR-5.8.5) published as
    ``mm_pnl_cents``, and not a transfer between accomplices.

    ``score_ppm`` is the distance in standard deviations scaled to ppm, so it is
    directly comparable to ``off_market_sigma_milli * 1000`` and may exceed
    1 000 000: a print ten sigma out scores 10 000 000.

    ``min_trades`` applies to the **number of off market executions** the pair
    printed on that market, and it is what separates a transfer from an accident.
    One aggressive order that walks a thin book prints one execution far from the
    reference price, and the honest bench produces exactly that once or twice per
    match; a wealth transfer is a repeated arrangement. The cost of that floor is
    stated rather than hidden: a single very large one-shot transfer is not
    reported by this detector, and the pair still shows up in
    :func:`collusion_index` if the two sides concentrate on each other.
    """

    name: ClassVar[str] = "off_market_transfer"
    version: ClassVar[str] = DETECTOR_VERSION

    def run(self, projection: MatchProjection, config: DetectorConfig) -> tuple[Incident, ...]:
        """Score every execution against the match's own price dispersion.

        Args:
            projection: The folded journal.
            config: The calibrated thresholds.

        Returns:
            The incidents, ascending by ``(pair, market_id)``.
        """
        if len(projection.trades) < config.min_trades:
            return ()
        seats = frozenset(projection.agent_ids)
        references = dict(projection.ref_price)
        deviations: list[tuple[TradeRecord, int]] = []
        for trade in projection.trades:
            series = references.get(trade.market_id, ())
            index = trade.tick - 1
            if not 0 <= index < len(series):  # pragma: no cover - P4 marks every open market
                continue
            deviations.append((trade, trade.price - series[index]))
        if not deviations:  # pragma: no cover - guarded by min_trades above
            return ()
        dispersion_milli = _dispersion_milli([abs(deviation) for _, deviation in deviations])
        threshold_ppm = config.off_market_sigma_milli * _PPM_PER_MILLI
        grouped: dict[tuple[str, str, str], list[tuple[TradeRecord, int, int]]] = {}
        for trade, deviation in deviations:
            if trade.maker_agent_id not in seats or trade.taker_agent_id not in seats:
                continue
            score_ppm = _ratio_ppm(abs(deviation) * MILLI_ONE, dispersion_milli)
            if score_ppm < threshold_ppm:
                continue
            key = (*_pair_key(trade.maker_agent_id, trade.taker_agent_id), trade.market_id)
            grouped.setdefault(key, []).append((trade, deviation, score_ppm))
        material = {key: rows for key, rows in grouped.items() if len(rows) >= config.min_trades}
        return self._incidents_of(projection, material, dispersion_milli, threshold_ppm)

    def _incidents_of(
        self,
        projection: MatchProjection,
        grouped: Mapping[tuple[str, str, str], Sequence[tuple[TradeRecord, int, int]]],
        dispersion_milli: int,
        threshold_ppm: int,
    ) -> tuple[Incident, ...]:
        """Fold the off market executions of one pair and market into one incident.

        Args:
            projection: The folded journal, for the canonical id orders.
            grouped: Off market executions per ``(seat, seat, market)``.
            dispersion_milli: The match dispersion, for the evidence detail.
            threshold_ppm: The threshold, for the severity grading.

        Returns:
            The incidents, ascending by ``(pair, market_id)``.
        """
        rank = {agent_id: index for index, agent_id in enumerate(projection.agent_ids)}
        market_rank = {market_id: index for index, market_id in enumerate(projection.market_ids)}
        keys = sorted(grouped, key=lambda key: (rank[key[0]], rank[key[1]], market_rank.get(key[2], 0)))
        found: list[Incident] = []
        for key in keys:
            rows = grouped[key]
            found.append(
                _incident(
                    index=len(found) + 1,
                    kind=IncidentKind.OFF_MARKET_TRANSFER,
                    detector=self.name,
                    tick=max(trade.tick for trade, _, _ in rows),
                    agent_ids=(key[0], key[1]),
                    market_ids=(key[2],),
                    score_ppm=max(score for _, _, score in rows),
                    threshold_ppm=threshold_ppm,
                    detail=(
                        ("off_market_trades", len(rows)),
                        ("transferred_cents", sum(abs(deviation) * trade.qty for trade, deviation, _ in rows)),
                        ("max_deviation_cents", max(abs(deviation) for _, deviation, _ in rows)),
                        ("dispersion_milli", dispersion_milli),
                        ("threshold_ppm", threshold_ppm),
                    ),
                )
            )
        return tuple(found)


class WashTradingDetector:
    """Raises one ``wash_trading`` incident per pair and market that round trips.

    Economic wash trading (FR-5.4.4's own note, PRD section 7.5) is volume
    without exposure: two accomplices pass the same contracts back and forth, so
    the printed volume grows while neither position moves. Naive self execution
    is already impossible at engine level (self trade prevention, FR-5.4.4),
    which is exactly why this detector looks at *pairs*.

    The score multiplies two ppm factors:

    * **the round trip balance**, ``2 * min(bought, sold) / (bought + sold)`` per
      market, which is 1 000 000 when every contract bought from the accomplice
      came back to it and 0 when the flow is one directional;
    * **the pair concentration** of :func:`collusion_index`, so an isolated
      buy-then-sell between two seats whose real counterparty is the market maker
      cannot raise an alert.

    A one directional wealth transfer therefore scores near zero here and is
    reported by :class:`OffMarketTransferDetector` instead. The two families
    describe two different cheats and are deliberately not merged.
    """

    name: ClassVar[str] = "wash_trading"
    version: ClassVar[str] = DETECTOR_VERSION

    def run(self, projection: MatchProjection, config: DetectorConfig) -> tuple[Incident, ...]:
        """Score every pair and market for offsetting mutual flow.

        Args:
            projection: The folded journal.
            config: The calibrated thresholds.

        Returns:
            The incidents, ascending by ``(pair, market_id)``.
        """
        view = _build_trade_view(projection)
        found: list[Incident] = []
        for pair in view.pairs():
            whole = view.pair_stats[pair]
            concentration_ppm = min(view.share_ppm(pair[0], whole.qty), view.share_ppm(pair[1], whole.qty))
            for market_id in view.markets_of(pair, projection.market_ids):
                stats = view.pair_market_stats[(pair[0], pair[1], market_id)]
                if stats.trades < config.min_trades:
                    continue
                round_trip = min(stats.first_bought_qty, stats.first_sold_qty)
                balance_ppm = _ratio_ppm(2 * round_trip, stats.first_bought_qty + stats.first_sold_qty)
                score_ppm = _product_ppm(concentration_ppm, balance_ppm)
                if score_ppm < config.collusion_threshold_ppm:
                    continue
                found.append(
                    _incident(
                        index=len(found) + 1,
                        kind=IncidentKind.WASH_TRADING,
                        detector=self.name,
                        tick=stats.last_tick,
                        agent_ids=pair,
                        market_ids=(market_id,),
                        score_ppm=score_ppm,
                        threshold_ppm=config.collusion_threshold_ppm,
                        detail=(
                            ("round_trip_qty", round_trip),
                            ("balance_ppm", balance_ppm),
                            ("pair_concentration_ppm", concentration_ppm),
                            ("mutual_trades", stats.trades),
                            ("threshold_ppm", config.collusion_threshold_ppm),
                        ),
                    )
                )
        return tuple(found)


@dataclass
class _OrderFlow:
    """One seat's own order flow, folded from the order rows.

    Attributes:
        orders: Number of orders the seat placed.
        pulled_qty: Quantity that left the book unfilled on the seat's own
            request.
        filled_qty: Quantity its orders executed.
        cancelled_orders: Number of orders it pulled unfilled.
        last_tick: Tick of the last such cancellation.
        market_ids: Markets those cancellations were on.
    """

    orders: int = 0
    pulled_qty: int = 0
    filled_qty: int = 0
    cancelled_orders: int = 0
    last_tick: int = 0
    market_ids: frozenset[str] = frozenset()


class SpoofingDetector:
    """Raises one ``spoofing`` incident per seat with an abnormal cancel to execution ratio.

    Spoofing is quoting size that is not meant to trade, so the ratio is over
    **quantity** and not over order count: pulling one order of five hundred
    contracts is the cheat, pulling five orders of one is housekeeping. The
    numerator is the quantity that left the book unfilled on the agent's own
    request (``CancelReason.AGENT_REQUEST``); every other cancel reason is the
    engine's decision and not the agent's (a requote, an IOC residual, a
    resolution, a freeze, a self trade prevention), and counting those would flag
    the market maker's own behaviour and every bankrupt seat.

    The denominator is that quantity plus everything the seat's own orders
    executed, so the score reads as "share of my own quoted size I never intended
    to trade".
    """

    name: ClassVar[str] = "spoofing"
    version: ClassVar[str] = DETECTOR_VERSION

    def run(self, projection: MatchProjection, config: DetectorConfig) -> tuple[Incident, ...]:
        """Score every seat's own order flow.

        Args:
            projection: The folded journal.
            config: The calibrated thresholds.

        Returns:
            The incidents, ascending by seat.
        """
        flow = {agent_id: _OrderFlow() for agent_id in projection.agent_ids}
        for order in projection.orders:
            own = flow.get(order.agent_id)
            if own is None:
                continue
            own.orders += 1
            own.filled_qty += order.filled_qty
            unfilled = order.qty - order.filled_qty
            if order.cancel_reason != CancelReason.AGENT_REQUEST.value or unfilled <= 0:
                continue
            own.pulled_qty += unfilled
            own.cancelled_orders += 1
            own.last_tick = max(own.last_tick, order.cancelled_tick or order.placed_tick)
            own.market_ids = own.market_ids | {order.market_id}
        found: list[Incident] = []
        for agent_id in projection.agent_ids:
            own = flow[agent_id]
            if own.orders < config.min_trades or own.pulled_qty <= 0:
                continue
            score_ppm = _ratio_ppm(own.pulled_qty, own.pulled_qty + own.filled_qty)
            if score_ppm < config.spoofing_cancel_ratio_ppm:
                continue
            found.append(
                _incident(
                    index=len(found) + 1,
                    kind=IncidentKind.SPOOFING,
                    detector=self.name,
                    tick=own.last_tick,
                    agent_ids=(agent_id,),
                    market_ids=tuple(m for m in projection.market_ids if m in own.market_ids),
                    score_ppm=score_ppm,
                    threshold_ppm=config.spoofing_cancel_ratio_ppm,
                    detail=(
                        ("cancelled_unfilled_qty", own.pulled_qty),
                        ("executed_qty", own.filled_qty),
                        ("cancelled_orders", own.cancelled_orders),
                        ("orders_placed", own.orders),
                        ("threshold_ppm", config.spoofing_cancel_ratio_ppm),
                    ),
                )
            )
        return tuple(found)


@dataclass
class _Contradiction:
    """One seat's declared belief against its own executions on one market.

    Attributes:
        weighted_gap: Sum over executions of ``max(0, contradiction) * qty``, in
            ppm times contracts.
        qty: Quantity those executions moved.
        trades: Number of them.
        last_tick: Tick of the last of them.
    """

    weighted_gap: int = 0
    qty: int = 0
    trades: int = 0
    last_tick: int = 0


class PredictionMismatchDetector:
    """Raises one ``prediction_position_mismatch`` incident per seat and market.

    PRD section 7.2's example is literal: "declarer 0,80 et vendre massivement".
    The contradiction of one execution is how far the traded price sits on the
    wrong side of the declared probability, in ppm:

    * selling at 40 cents while declaring 800 000 ppm contradicts by 400 000,
      because the seat sold for less than it says the contract is worth;
    * buying at 40 cents while declaring 800 000 ppm contradicts by nothing: a
      cheap buy agrees with a high belief.

    The score is the **quantity weighted mean** contradiction over every
    execution of that seat on that market for which a probability was on record
    at that tick (declared or carried, FR-6.2.4: both count, exactly as section 9
    counts them for the Brier score). Weighting by quantity is what puts
    "massivement" into the measurement, and averaging over *all* executions and
    not only the contradictory ones is what stops one exotic fill from naming a
    seat that otherwise trades its book.

    This is a descriptor and never a penalty (PRD section 7.2): no score in this
    repository reads it.
    """

    name: ClassVar[str] = "prediction_position_mismatch"
    version: ClassVar[str] = DETECTOR_VERSION

    def run(self, projection: MatchProjection, config: DetectorConfig) -> tuple[Incident, ...]:
        """Score every seat against its own declared probabilities.

        Args:
            projection: The folded journal.
            config: The calibrated thresholds.

        Returns:
            The incidents, ascending by ``(agent_id, market_id)``.
        """
        declared = {(row.agent_id, row.market_id, row.tick): row.p_yes_ppm for row in projection.predictions}
        seats = frozenset(projection.agent_ids)
        folded: dict[tuple[str, str], _Contradiction] = {}
        for trade in projection.trades:
            for agent_id in (trade.maker_agent_id, trade.taker_agent_id):
                if agent_id not in seats:
                    continue
                belief_ppm = declared.get((agent_id, trade.market_id, trade.tick))
                signed = _signed_qty(trade, agent_id)
                if belief_ppm is None or signed == 0:
                    continue
                price_ppm = trade.price * _PPM_PER_CENT
                gap = price_ppm - belief_ppm if signed > 0 else belief_ppm - price_ppm
                folded_row = folded.setdefault((agent_id, trade.market_id), _Contradiction())
                folded_row.weighted_gap += max(0, gap) * trade.qty
                folded_row.qty += trade.qty
                folded_row.trades += 1
                folded_row.last_tick = max(folded_row.last_tick, trade.tick)
        found: list[Incident] = []
        for agent_id in projection.agent_ids:
            for market_id in projection.market_ids:
                row = folded.get((agent_id, market_id))
                if row is None or row.trades < config.min_trades:
                    continue
                score_ppm = _weighted_mean(row.weighted_gap, row.qty)
                if score_ppm < config.mismatch_threshold_ppm:
                    continue
                found.append(
                    _incident(
                        index=len(found) + 1,
                        kind=IncidentKind.PREDICTION_POSITION_MISMATCH,
                        detector=self.name,
                        tick=row.last_tick,
                        agent_ids=(agent_id,),
                        market_ids=(market_id,),
                        score_ppm=score_ppm,
                        threshold_ppm=config.mismatch_threshold_ppm,
                        detail=(
                            ("contradiction_ppm", score_ppm),
                            ("weighted_qty", row.qty),
                            ("trades", row.trades),
                            ("threshold_ppm", config.mismatch_threshold_ppm),
                        ),
                    )
                )
        return tuple(found)


#: The suite, in the order :func:`run_detectors` runs it and therefore in the
#: order incident ids are assigned. Collusion first because it is the AC-P6
#: headline, then the two pair level families it does not cover, then the two
#: single seat ones.
DETECTORS: tuple[Detector, ...] = (
    CollusionDetector(),
    OffMarketTransferDetector(),
    WashTradingDetector(),
    SpoofingDetector(),
    PredictionMismatchDetector(),
)


def run_detectors(
    projection: MatchProjection,
    *,
    config: DetectorConfig | None = None,
    detectors: Sequence[Detector] | None = None,
) -> tuple[Incident, ...]:
    """Run the detector suite over one finished match.

    Incident ids are **positional and restart at** ``i-0001`` **on every run**,
    which is what makes a rerun idempotent: ``Store.save_incidents`` replaces the
    previous generation instead of accumulating two sets of alerts under
    different ids, and :func:`write_incidents` rewrites the file. The order is
    the order of ``detectors``, and inside one detector its own canonical order,
    so the same journal always produces the same ids.

    Args:
        projection: The folded journal, from ``project(events)``.
        config: The calibrated thresholds. ``None`` means :class:`DetectorConfig`
            defaults.
        detectors: The suite to run. ``None`` means :data:`DETECTORS`.

    Returns:
        Every incident, renumbered across the whole suite.
    """
    resolved_config = config if config is not None else DetectorConfig()
    resolved_detectors = tuple(detectors) if detectors is not None else DETECTORS
    found: list[Incident] = []
    for detector in resolved_detectors:
        for incident in detector.run(projection, resolved_config):
            found.append(replace(incident, incident_id=make_incident_id(len(found) + 1)))
    return tuple(found)


def write_incidents(path: Path, incidents: Sequence[Incident]) -> None:
    r"""Write ``runs/<match_id>/incidents.jsonl``, one JSON object per line.

    ``detail`` is encoded with :func:`pxe.types.incident_detail_to_dict`, the one
    crossing between the ordered pairs a detector builds and a mapping (CONTRACTS
    section 7.18): A18 writes no conversion of its own. The line itself goes
    through :func:`~pxe.events.canonical_json` with the usual ``open()``
    arguments, ``encoding="utf-8", newline="\n"``, so the bytes are identical on
    Windows and on Linux (section 4.2) and a float in a detector detail is
    refused rather than written.

    The file is **replaced**, not appended to. Incident ids restart at ``i-0001``
    on every :func:`run_detectors` call, so appending would leave two generations
    of alerts sharing one id space, which is the one thing a reader of this file
    cannot recover from.

    Args:
        path: Destination file. Parent directories are created.
        incidents: What :func:`run_detectors` produced.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        for item in incidents:
            handle.write(
                canonical_json(
                    {
                        "incident_id": item.incident_id,
                        "kind": str(item.kind),
                        "severity": item.severity,
                        "tick": int(item.tick),
                        "agent_ids": list(item.agent_ids),
                        "market_ids": list(item.market_ids),
                        "score_ppm": int(item.score_ppm),
                        "detail": incident_detail_to_dict(item.detail),
                        "detector_version": item.detector_version,
                    }
                )
                + JOURNAL_NEWLINE
            )
