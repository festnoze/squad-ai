"""The six MAP-Elites behavioral descriptors (PRD section 7.4, CONTRACTS 7.17, A17).

A descriptor answers "what does this harness *play like*", not "how well did it
do". Section 9 fixes the six of them, and PRD section 7.4 fixes the one rule
that makes them usable as MAP-Elites axes: they are computed **exclusively from
the journal**, through a :class:`~pxe.metrics.projection.MatchProjection` and
never from engine state, so an archive built today can be rebuilt from a stored
journal a year later and land in the same cell.

Every value is an exact integer, in parts per million for a ratio and in
thousandths of a tick for a duration (section 2.1). Nothing here rounds with the
builtin ``round``, nothing here divides a signed numerator with ``//``, and the
only division that is not integral happens inside :class:`fractions.Fraction`,
which is exact and never lets a float reach an output field.

What has to be reconstructed, and why that is not a licence to read events
--------------------------------------------------------------------------
Two of the six descriptors are about state the projection does not carry as a
per tick series: ``leverage_ppm`` needs ``reserved_cents`` at the close of every
tick and ``holding_horizon_milli`` needs the per market position. Both are
rebuilt here from the rows the projection does carry, using the section 6.1
formulas:

* a position is the running sum of the executions on that market, flattened at
  the tick the market settles (P1 of ``resolution_tick + 1``, section 5.0) or is
  unwound (FR-5.4.5);
* ``reserved_cents`` is ``sum over resting orders of order_collateral_cents(...)
  + sum over markets of position_collateral_cents(...)``, which is **the same
  expression invariant I3 checks against the ledger on every tick**, so the
  reconstruction equals the journalled ``PositionSnapshot.reserved_cents`` by
  construction rather than by luck.

Reading the events directly would be shorter and is forbidden: a metric consumes
a projection (section 7.17). The alternative, adding two per tick series to
``MatchProjection``, is an A15 contract change and is reported as such.

Ticks played, not ticks scheduled
---------------------------------
A frozen agent stops acting at its freeze tick (FR-5.5.5), and section 9 already
settles the principle for calibration: "its Brier is the mean over the ticks it
actually played". The same normalisation is applied here to ``leverage_ppm``,
``message_intensity_ppm``, the spell window of ``holding_horizon_milli`` and the
signal window of ``reaction_latency_milli``. Without it a bankruptcy at tick 3
of 48 would report a near zero leverage for an agent whose whole behaviour was
to over-lever, which inverts the axis.
"""

from __future__ import annotations

import bisect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from pxe.metrics.projection import MatchProjection
from pxe.types import (
    MILLI_ONE,
    PPM_ONE,
    CancelReason,
    Side,
    order_collateral_cents,
    position_collateral_cents,
)

__all__ = ["DESCRIPTOR_NAMES", "BehavioralDescriptors", "compute_descriptors"]

#: The six axes, in the order :meth:`BehavioralDescriptors.as_tuple` returns
#: them. ``EliteArchive(axes=...)`` (A20) names its grid dimensions with these
#: exact strings, so the order and the spelling are both part of the contract.
DESCRIPTOR_NAMES: tuple[str, ...] = (
    "maker_ratio_ppm",
    "reaction_latency_milli",
    "holding_horizon_milli",
    "herfindahl_ppm",
    "leverage_ppm",
    "message_intensity_ppm",
)

#: ``maker_ratio_ppm`` of a seat that never traded (section 9). Neutral rather
#: than 0 or 1 000 000: an agent with no execution is neither passive nor
#: aggressive, and parking it at an extreme would populate one corner cell of
#: the MAP-Elites grid with every mute harness.
_NEUTRAL_MAKER_RATIO_PPM: int = PPM_ONE // 2

#: ``Highlight.kind`` of an ``AgentFrozen``. The projection publishes the string
#: and not a constant, so it is mirrored here (section 7.17).
_KIND_BANKRUPTCY = "bankruptcy"


@dataclass(frozen=True)
class BehavioralDescriptors:
    """The PRD section 7.4 style vector of one ranked seat.

    Attributes:
        agent_id: The ranked seat.
        maker_ratio_ppm: Share of the seat's executions where it was the
            **maker**, that is the passive side already resting on the book.
            Neutral (``500_000``) when it never traded.
        reaction_latency_milli: Mean number of ticks between a
            ``SignalDelivered`` about a market and the seat's next execution on
            that market, in thousandths of a tick, capped at the horizon. A
            signal the seat never acted on contributes the cap, which is what
            makes "ignores its information" a reachable end of the axis.
        holding_horizon_milli: Mean length, in thousandths of a tick, of a spell
            during which the seat held a non zero position on one market. ``0``
            when it never held one.
        herfindahl_ppm: ``sum over markets of (abs(notional_m) / total)^2`` at
            the median tick of the match, notional being
            ``abs(position_qty) * ref_price``. ``1_000_000`` for a seat holding
            one market only, ``0`` for a seat holding nothing at that tick.
        leverage_ppm: Mean over the ticks played of
            ``reserved_cents / cash_cents``. Bounded by ``1_000_000`` because
            invariant I4 keeps ``reserved <= cash``.
        message_intensity_ppm: Share of the ticks played on which the seat
            posted a public message (FR-5.6.1). Always ``0`` when talking mode
            is off, which is the default.
    """

    agent_id: str
    maker_ratio_ppm: int
    reaction_latency_milli: int
    holding_horizon_milli: int
    herfindahl_ppm: int
    leverage_ppm: int
    message_intensity_ppm: int

    def as_tuple(self) -> tuple[int, ...]:
        """Return the six descriptors in :data:`DESCRIPTOR_NAMES` order.

        This is the vector ``EliteArchive.coords_for`` bins, so the order is not
        a convenience: a permutation here silently relabels every MAP-Elites
        axis.

        Returns:
            The six values, ``agent_id`` excluded.
        """
        return (
            self.maker_ratio_ppm,
            self.reaction_latency_milli,
            self.holding_horizon_milli,
            self.herfindahl_ppm,
            self.leverage_ppm,
            self.message_intensity_ppm,
        )


def compute_descriptors(projection: MatchProjection) -> tuple[BehavioralDescriptors, ...]:
    """Compute the six MAP-Elites descriptors of every ranked seat.

    Args:
        projection: The folded journal. ``MM`` and ``FEES`` are not ranked seats
            and get no descriptor: the market maker is a fixture of the
            environment, not a competitor (FR-5.8.5).

    Returns:
        One vector per ranked seat, in canonical agent order (section 2.3),
        which is already the order of ``projection.agent_ids``.
    """
    timeline = _build_timeline(projection)
    return tuple(_descriptors_for(projection, timeline, agent_id) for agent_id in projection.agent_ids)


# --------------------------------------------------------------------------
# The reconstructed per tick state. Private.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class _Timeline:
    """Per tick state of one match, rebuilt from the projection rows.

    Attributes:
        ticks_total: Horizon of the match. Every series below has that length.
        played: Per ranked seat, the number of ticks it actually acted on, that
            is ``ticks_total`` or its freeze tick.
        positions: Per ``(agent_id, market_id)`` that ever traded, the signed net
            position at the close of each tick.
        reserved: Per ranked seat, ``reserved_cents`` at the close of each tick,
            recomputed with the section 6.1 formulas.
        trade_ticks: Per ``(agent_id, market_id)``, the ascending ticks on which
            the seat executed there. Kept sorted for the latency search.
        message_ticks: Per ranked seat, the ticks it posted a message on.
    """

    ticks_total: int
    played: Mapping[str, int]
    positions: Mapping[tuple[str, str], tuple[int, ...]]
    reserved: Mapping[str, tuple[int, ...]]
    trade_ticks: Mapping[tuple[str, str], tuple[int, ...]]
    message_ticks: Mapping[str, frozenset[int]]


def _build_timeline(projection: MatchProjection) -> _Timeline:
    """Rebuild everything the six descriptors need that is not already a row.

    Args:
        projection: The folded journal.

    Returns:
        The reconstructed :class:`_Timeline`.
    """
    seats = frozenset(projection.agent_ids)
    positions, trade_ticks = _positions(projection, seats=seats, flat_from=_flat_from(projection))
    return _Timeline(
        ticks_total=projection.ticks_total,
        played=_ticks_played(projection),
        positions=positions,
        reserved=_reserved(projection, seats=seats, positions=positions),
        trade_ticks=trade_ticks,
        message_ticks={
            agent_id: frozenset(row.tick for row in projection.messages if row.agent_id == agent_id)
            for agent_id in projection.agent_ids
        },
    )


def _flat_from(projection: MatchProjection) -> Mapping[str, int]:
    """Return, per market, the first tick at which every position on it is flat.

    A market whose scheduled ``resolution_tick`` is ``r`` settles in P1 of tick
    ``r + 1`` (section 5.0), so the P4 snapshot of tick ``r + 1`` is the first
    one showing a flat book. A market cancelled at tick ``c`` is unwound in P1 of
    tick ``c`` (P1 step 5), so ``c`` itself is already flat. A market that
    neither resolved nor was cancelled inside this journal never flattens, which
    is the truncated replay case.

    Args:
        projection: The folded journal.

    Returns:
        Market id to the first flat tick, possibly ``ticks_total + 1``.
    """
    resolved = frozenset(market_id for market_id, _outcome in projection.outcomes)
    scheduled = dict(projection.resolution_ticks)
    cancelled_at: dict[str, int] = {}
    for row in projection.orders:
        if row.cancel_reason != CancelReason.MARKET_CANCELLED or row.cancelled_tick is None:
            continue
        held = cancelled_at.get(row.market_id)
        cancelled_at[row.market_id] = row.cancelled_tick if held is None else min(held, row.cancelled_tick)
    out: dict[str, int] = {}
    for market_id in projection.market_ids:
        if market_id in resolved:
            out[market_id] = scheduled[market_id] + 1
        elif market_id in cancelled_at:
            out[market_id] = cancelled_at[market_id]
        else:
            out[market_id] = projection.ticks_total + 1
    return out


def _positions(
    projection: MatchProjection,
    *,
    seats: frozenset[str],
    flat_from: Mapping[str, int],
) -> tuple[Mapping[tuple[str, str], tuple[int, ...]], Mapping[tuple[str, str], tuple[int, ...]]]:
    """Rebuild the per tick position of every seat on every market it traded.

    The sign convention is the one :func:`pxe.metrics.performance.pnl_of` uses:
    the maker's position moves with ``Side(maker_side).sign`` and the taker's
    against it, because the two legs of one execution are opposite by definition.

    Args:
        projection: The folded journal.
        seats: The ranked seats. ``MM`` legs are ignored here.
        flat_from: Output of :func:`_flat_from`.

    Returns:
        A pair ``(positions, trade_ticks)``, both keyed by
        ``(agent_id, market_id)`` and both built in sorted key order.
    """
    deltas: dict[tuple[str, str], dict[int, int]] = {}
    ticks: dict[tuple[str, str], list[int]] = {}
    for row in projection.trades:
        sign = Side(row.maker_side).sign
        legs = ((row.maker_agent_id, sign * row.qty), (row.taker_agent_id, -sign * row.qty))
        for agent_id, signed_qty in legs:
            if agent_id not in seats:
                continue
            key = (agent_id, row.market_id)
            per_tick = deltas.setdefault(key, {})
            per_tick[row.tick] = per_tick.get(row.tick, 0) + signed_qty
            held = ticks.setdefault(key, [])
            if not held or held[-1] != row.tick:
                held.append(row.tick)

    positions: dict[tuple[str, str], tuple[int, ...]] = {}
    for key in sorted(deltas):
        per_tick = deltas[key]
        flat = flat_from[key[1]]
        series: list[int] = []
        running = 0
        for tick in range(1, projection.ticks_total + 1):
            running += per_tick.get(tick, 0)
            series.append(0 if tick >= flat else running)
        positions[key] = tuple(series)
    return positions, {key: tuple(ticks[key]) for key in sorted(ticks)}


def _reserved(
    projection: MatchProjection,
    *,
    seats: frozenset[str],
    positions: Mapping[tuple[str, str], tuple[int, ...]],
) -> Mapping[str, tuple[int, ...]]:
    """Recompute ``reserved_cents`` at the close of every tick, per ranked seat.

    This is the section 6.1 formula, that is the very expression invariant I3
    checks the ledger against, so the result equals the journalled
    ``PositionSnapshot.reserved_cents`` rather than approximating it. A fill at
    tick ``t`` happens in P3 and the snapshot is taken in P4, so the tick's own
    fills are subtracted before the tick's collateral is measured.

    Args:
        projection: The folded journal.
        seats: The ranked seats.
        positions: Output of :func:`_positions`.

    Returns:
        Agent id to a series of length ``ticks_total``.
    """
    ticks_total = projection.ticks_total
    reserved: dict[str, list[int]] = {agent_id: [0] * ticks_total for agent_id in projection.agent_ids}
    for (agent_id, _market_id), series in positions.items():
        row = reserved[agent_id]
        for index, qty in enumerate(series):
            if qty < 0:
                row[index] += position_collateral_cents(qty)

    fills = _fills_by_order(projection)
    for order in projection.orders:
        if order.agent_id not in seats:
            continue
        row = reserved[order.agent_id]
        last_tick = ticks_total if order.cancelled_tick is None else min(order.cancelled_tick - 1, ticks_total)
        remaining = order.qty
        per_tick = fills.get(order.order_id, {})
        for tick in range(order.placed_tick, last_tick + 1):
            remaining -= per_tick.get(tick, 0)
            if remaining <= 0:
                break
            row[tick - 1] += order_collateral_cents(Side(order.side), order.price, remaining)
    return {agent_id: tuple(series) for agent_id, series in reserved.items()}


def _fills_by_order(projection: MatchProjection) -> Mapping[str, Mapping[int, int]]:
    """Return, per order id, the quantity it filled on each tick.

    Args:
        projection: The folded journal.

    Returns:
        Order id to a tick keyed mapping of filled quantity.
    """
    out: dict[str, dict[int, int]] = {}
    for row in projection.trades:
        for order_id in (row.maker_order_id, row.taker_order_id):
            per_tick = out.setdefault(order_id, {})
            per_tick[row.tick] = per_tick.get(row.tick, 0) + row.qty
    return out


def _ticks_played(projection: MatchProjection) -> Mapping[str, int]:
    """Return the number of ticks each ranked seat actually acted on.

    A freeze at tick ``t`` takes effect from tick ``t + 1`` (P4 step 14), so a
    frozen seat played ticks ``1..t``. The freeze tick comes from the
    projection's ``bankruptcy`` highlights, which are folded from
    ``AgentFrozen``.

    Args:
        projection: The folded journal.

    Returns:
        Agent id to a count in ``1..ticks_total``.
    """
    played = dict.fromkeys(projection.agent_ids, projection.ticks_total)
    for highlight in projection.highlights:
        if highlight.kind != _KIND_BANKRUPTCY:
            continue
        for agent_id in highlight.agent_ids:
            if agent_id in played:
                played[agent_id] = max(1, min(played[agent_id], highlight.tick))
    return played


# --------------------------------------------------------------------------
# The six descriptors. Private.
# --------------------------------------------------------------------------
def _descriptors_for(projection: MatchProjection, timeline: _Timeline, agent_id: str) -> BehavioralDescriptors:
    """Build the style vector of one ranked seat.

    Args:
        projection: The folded journal.
        timeline: The reconstructed per tick state.
        agent_id: The ranked seat.

    Returns:
        Its :class:`BehavioralDescriptors`.
    """
    return BehavioralDescriptors(
        agent_id=agent_id,
        maker_ratio_ppm=_maker_ratio_ppm(projection, agent_id),
        reaction_latency_milli=_reaction_latency_milli(projection, timeline, agent_id),
        holding_horizon_milli=_holding_horizon_milli(timeline, agent_id),
        herfindahl_ppm=_herfindahl_ppm(projection, timeline, agent_id),
        leverage_ppm=_leverage_ppm(projection, timeline, agent_id),
        message_intensity_ppm=_message_intensity_ppm(timeline, agent_id),
    )


def _maker_ratio_ppm(projection: MatchProjection, agent_id: str) -> int:
    """Return the share of the seat's executions where it was the maker, in ppm.

    Args:
        projection: The folded journal.
        agent_id: The ranked seat.

    Returns:
        A ratio in ``0..1_000_000``, neutral when the seat never traded.
    """
    maker = 0
    total = 0
    for row in projection.trades:
        is_maker = row.maker_agent_id == agent_id
        if not is_maker and row.taker_agent_id != agent_id:
            continue
        total += 1
        maker += 1 if is_maker else 0
    if total == 0:
        return _NEUTRAL_MAKER_RATIO_PPM
    return _ratio_ppm(maker, total)


def _reaction_latency_milli(projection: MatchProjection, timeline: _Timeline, agent_id: str) -> int:
    """Return the mean signal to trade delay of one seat, in thousandths of a tick.

    A signal delivered in P1 of tick ``s`` can be acted on in P3 of that same
    tick, so a trade at tick ``s`` is a latency of zero. A signal the seat never
    answered contributes the horizon, which is the cap section 9 asks for: an
    agent that ignores its private information sits at the far end of the axis
    instead of dropping out of the average and looking fast.

    Args:
        projection: The folded journal.
        timeline: The reconstructed per tick state.
        agent_id: The ranked seat.

    Returns:
        The scaled mean, ``0..ticks_total * 1000``.
    """
    horizon = timeline.ticks_total
    played = timeline.played[agent_id]
    total = 0
    count = 0
    for signal in projection.signals:
        if signal.agent_id != agent_id or signal.tick > played:
            continue
        answered = _first_at_or_after(timeline.trade_ticks.get((agent_id, signal.market_id), ()), signal.tick)
        total += horizon if answered is None else min(answered - signal.tick, horizon)
        count += 1
    if count == 0:
        return horizon * MILLI_ONE
    return _scaled_mean(total, count, MILLI_ONE)


def _holding_horizon_milli(timeline: _Timeline, agent_id: str) -> int:
    """Return the mean length of a non zero position spell, in thousandths of a tick.

    A spell is a maximal run of consecutive played ticks on which the seat held a
    non zero position on one market. A spell still open when the seat stops
    playing counts with its truncated length: it happened, and dropping it would
    reward a bankruptcy with a shorter apparent horizon.

    Args:
        timeline: The reconstructed per tick state.
        agent_id: The ranked seat.

    Returns:
        The scaled mean, ``0`` when the seat never held a position.
    """
    played = timeline.played[agent_id]
    spells: list[int] = []
    for (holder, _market_id), series in timeline.positions.items():
        if holder != agent_id:
            continue
        run = 0
        for qty in series[:played]:
            if qty != 0:
                run += 1
                continue
            if run > 0:
                spells.append(run)
            run = 0
        if run > 0:
            spells.append(run)
    if not spells:
        return 0
    return _scaled_mean(sum(spells), len(spells), MILLI_ONE)


def _herfindahl_ppm(projection: MatchProjection, timeline: _Timeline, agent_id: str) -> int:
    """Return the concentration of the seat's book at the median tick, in ppm.

    The median tick of a match of ``T`` ticks is ``(T + 1) // 2``, that is the
    lower median of ``1..T``: an exact integer, which is what keeps the
    descriptor reproducible. Exposure is measured as
    ``abs(position_qty) * ref_price`` so that a large position on a one cent
    market does not read as concentration.

    Args:
        projection: The folded journal.
        timeline: The reconstructed per tick state.
        agent_id: The ranked seat.

    Returns:
        ``0`` when the seat is flat everywhere at that tick, ``1_000_000`` when
        its whole exposure sits on one market.
    """
    index = (timeline.ticks_total + 1) // 2 - 1
    ref_of = dict(projection.ref_price)
    notionals: list[int] = []
    for (holder, market_id), series in timeline.positions.items():
        if holder != agent_id:
            continue
        notional = abs(series[index]) * ref_of[market_id][index]
        if notional > 0:
            notionals.append(notional)
    total = sum(notionals)
    if total == 0:
        return 0
    return _ratio_ppm(sum(value * value for value in notionals), total * total)


def _leverage_ppm(projection: MatchProjection, timeline: _Timeline, agent_id: str) -> int:
    """Return the mean collateral utilisation of one seat over the ticks it played.

    The mean is taken over the exact per tick fractions and rounded once, with
    :class:`fractions.Fraction`, so no intermediate rounding accumulates. A tick
    with zero cash contributes zero: invariant I4 keeps ``reserved <= cash``, so
    zero cash means zero reserved and the ratio is genuinely nothing rather than
    undefined.

    Args:
        projection: The folded journal.
        timeline: The reconstructed per tick state.
        agent_id: The ranked seat.

    Returns:
        A ratio in ``0..1_000_000``.
    """
    played = timeline.played[agent_id]
    cash = projection.cash_series(agent_id)
    reserved = timeline.reserved[agent_id]
    acc = Fraction(0)
    for index in range(played):
        if cash[index] > 0:
            acc += Fraction(reserved[index], cash[index])
    return _round_fraction(acc * PPM_ONE / played)


def _message_intensity_ppm(timeline: _Timeline, agent_id: str) -> int:
    """Return the share of played ticks on which the seat posted a message, in ppm.

    Args:
        timeline: The reconstructed per tick state.
        agent_id: The ranked seat.

    Returns:
        A ratio in ``0..1_000_000``, ``0`` whenever talking mode is off.
    """
    played = timeline.played[agent_id]
    spoken = sum(1 for tick in timeline.message_ticks[agent_id] if tick <= played)
    return _ratio_ppm(spoken, played)


# --------------------------------------------------------------------------
# Exact integer helpers. Private.
# --------------------------------------------------------------------------
def _ratio_ppm(numerator: int, denominator: int) -> int:
    """Return ``numerator / denominator`` in ppm, rounded half up.

    Both arguments are counts or squared notionals and are therefore never
    negative, which is why this helper is not :func:`pxe.types.bps_ratio`: that
    one exists for signed ratios and reports basis points.

    Args:
        numerator: Non negative numerator.
        denominator: Strictly positive denominator.

    Returns:
        The ratio in parts per million.
    """
    return (numerator * 2 * PPM_ONE + denominator) // (2 * denominator)


def _scaled_mean(total: int, count: int, scale: int) -> int:
    """Return ``scale * total / count``, rounded half up.

    Args:
        total: Non negative sum of the terms.
        count: Strictly positive number of terms.
        scale: The unit multiplier, :data:`pxe.types.MILLI_ONE` here.

    Returns:
        The scaled mean.
    """
    return (total * scale * 2 + count) // (2 * count)


def _round_fraction(value: Fraction) -> int:
    """Round a non negative exact fraction to the nearest integer, halves up.

    :func:`pxe.types.round_half_up` takes a float, and going through one would
    reintroduce the representation error this module avoids by using
    :class:`~fractions.Fraction` at all.

    Args:
        value: A non negative exact fraction.

    Returns:
        The rounded integer.
    """
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def _first_at_or_after(ticks: Sequence[int], tick: int) -> int | None:
    """Return the first entry of an ascending tick list that is ``>= tick``.

    Args:
        ticks: Ascending, duplicate free ticks.
        tick: The tick to search from, inclusive.

    Returns:
        The matching tick, or ``None`` when the list ends before it.
    """
    index = bisect.bisect_left(ticks, tick)
    return ticks[index] if index < len(ticks) else None
