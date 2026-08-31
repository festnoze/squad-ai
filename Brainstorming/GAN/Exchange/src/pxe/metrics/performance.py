"""Per match performance metrics (PRD section 7.1, CONTRACTS sections 7.17 and 9).

Everything here is a projection of a projection: the only input is a
:class:`~pxe.metrics.projection.MatchProjection`, and the only events it reads
through it are ``TradeExecuted``, ``PositionSnapshot``, ``SettlementApplied`` and
``MarketResolved``. **No declared prediction reaches any number in this module**,
which is one half of AC-P4 (the other half being that
:mod:`pxe.metrics.calibration` reads only ``PredictionRecorded``).

The PnL of a settled match is exactly ``final_cash_cents - initial_cash_cents``,
and it is derived here from the trades and the outcomes rather than copied from
``MatchEnded.rankings``:

* a trade moves cash by its own ``*_cash_delta_cents``, fee included for the
  taker (section 6.1);
* a resolution pays ``qty * outcome.payout_cents`` on the net position
  (``accounts.apply_settlement``);
* a **cancellation** unwinds every execution and restores the cash (FR-5.4.5),
  so a cancelled market contributes exactly zero, which is why the trades of a
  market with no outcome are skipped instead of being counted and then reversed.

That derivation is a real second opinion on the ranking the runner journalled,
and ``test_metrics_performance.py`` asserts the two agree agent by agent on all
three golden matches. Copying ``MatchEnded.rankings`` instead would make the
comparison tautological, which section 9 explicitly does not want:
``MatchRanking.pnl_pct_bps`` and ``PerformanceMetrics.pnl_bps`` are the same
number under two names and what is not optional is that they agree.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from pxe.metrics.projection import MatchProjection
from pxe.types import MatchRanking, Side, bps_ratio, round_half_up

__all__ = ["PerformanceMetrics", "compute_performance", "final_ranking"]

#: Scale of ``sharpe_milli``: the ratio is reported in thousandths (section 9).
_SHARPE_SCALE = 1000


@dataclass(frozen=True)
class PerformanceMetrics:
    """The PRD section 7.1 block for one ranked seat.

    Attributes:
        agent_id: The ranked seat.
        pnl_cents: ``final_cash_cents - initial_cash_cents``, after settlement,
            never marked (FR-5.5.4).
        pnl_bps: ``bps_ratio(pnl_cents, initial_cash_cents)``. Never
            ``pnl_cents * 10_000 // initial_cash_cents``: floor division on a
            signed numerator overstates every loss (section 2.1).
        sharpe_milli: ``round_half_up(1000 * mean(d) / stdev(d))`` over the per
            tick equity difference series ``d``, and ``0`` when ``stdev(d)`` is
            zero or ``d`` is too short to have one.
        max_drawdown_cents: ``max over t of (max over u <= t of equity_u) -
            equity_t`` on the mark to market equity trajectory, in cents. Never
            negative.
        max_drawdown_bps: ``bps_ratio(max_drawdown_cents, initial_cash_cents)``.
        volume_qty: Contracts traded, as maker or as taker.
        trade_count: Executions the seat was a party to.
        maker_trade_count: Executions where it was the maker.
        fees_paid_cents: Taker fees it paid, from ``TradeExecuted``.
    """

    agent_id: str
    pnl_cents: int
    pnl_bps: int
    sharpe_milli: int
    max_drawdown_cents: int
    max_drawdown_bps: int
    volume_qty: int
    trade_count: int
    maker_trade_count: int
    fees_paid_cents: int


def compute_performance(projection: MatchProjection) -> tuple[PerformanceMetrics, ...]:
    """Compute the PRD section 7.1 block of every ranked seat.

    Args:
        projection: The folded journal.

    Returns:
        One block per ranked seat, in canonical agent order (section 2.3), which
        is already the order of ``projection.agent_ids``.
    """
    return tuple(_metrics_for(projection, agent_id) for agent_id in projection.agent_ids)


def final_ranking(projection: MatchProjection) -> tuple[MatchRanking, ...]:
    """Rank the seats on cash after settlement, best first (FR-5.5.4).

    The ranking comes from the settlement and never from the mark to market: it
    is built from :func:`pnl_of`, which is a function of the executions and the
    realised outcomes only. Ties share the lowest rank and are broken, for
    display only, by ascending ``agent_id``.

    Args:
        projection: The folded journal.

    Returns:
        The ranking, best first, one line per ranked seat.
    """
    initial = projection.initial_cash_cents
    rows = [(agent_id, pnl_of(projection, agent_id)) for agent_id in projection.agent_ids]
    position_of = {agent_id: index for index, (agent_id, _pnl) in enumerate(rows)}
    ordered = sorted(rows, key=lambda row: (-row[1], position_of[row[0]]))
    rankings: list[MatchRanking] = []
    for place, (agent_id, pnl_cents) in enumerate(ordered, start=1):
        rank = rankings[-1].rank if rankings and pnl_cents == ordered[place - 2][1] else place
        rankings.append(
            MatchRanking(
                rank=rank,
                agent_id=agent_id,
                pnl_cents=pnl_cents,
                final_cash_cents=initial + pnl_cents,
                pnl_pct_bps=bps_ratio(pnl_cents, initial),
            )
        )
    return tuple(rankings)


def pnl_of(projection: MatchProjection, agent_id: str) -> int:
    """Return the settled PnL of one account, in cents.

    This is the one implementation of the PnL of section 9, and it works for
    ``MM`` as well as for a ranked seat, because the market maker's PnL is
    "computed like any agent PnL but excluded from ranking and ratings"
    (FR-5.8.5).

    Args:
        projection: The folded journal.
        agent_id: A ranked seat or ``MM``.

    Returns:
        ``final_cash_cents - initial_cash_cents``, derived from the executions
        and the realised outcomes.
    """
    resolved = dict(projection.outcomes)
    cash = 0
    position: dict[str, int] = {}
    for row in projection.trades:
        if row.market_id not in resolved:
            # Cancelled, or not resolved in this journal: FR-5.4.5 unwinds every
            # execution and restores the cash, so the market contributes zero.
            continue
        maker_sign = Side(row.maker_side).sign
        if row.maker_agent_id == agent_id:
            cash += row.maker_cash_delta_cents
            position[row.market_id] = position.get(row.market_id, 0) + maker_sign * row.qty
        if row.taker_agent_id == agent_id:
            cash += row.taker_cash_delta_cents
            position[row.market_id] = position.get(row.market_id, 0) - maker_sign * row.qty
    for market_id, qty in position.items():
        cash += qty * resolved[market_id].payout_cents
    return cash


def sharpe_milli_of(equity: tuple[int, ...]) -> int:
    """Return the risk adjusted return of one equity trajectory, in thousandths.

    ``round_half_up(1000 * mean(d) / stdev(d))`` where ``d`` is the per tick
    equity difference series, and ``0`` when the series cannot have a standard
    deviation or that deviation is zero (section 9).

    Args:
        equity: The per tick equity series, in cents.

    Returns:
        The scaled ratio, signed.
    """
    diffs = [equity[index + 1] - equity[index] for index in range(len(equity) - 1)]
    if len(diffs) < 2:
        return 0
    spread = statistics.stdev(diffs)
    if spread == 0.0:
        return 0
    return round_half_up(_SHARPE_SCALE * statistics.mean(diffs) / spread)


def max_drawdown_cents_of(equity: tuple[int, ...]) -> int:
    """Return the largest peak to trough fall of one equity trajectory, in cents.

    Args:
        equity: The per tick equity series, in cents.

    Returns:
        ``max over t of (max over u <= t of equity_u) - equity_t``, never
        negative and ``0`` on an empty series.
    """
    if not equity:
        return 0
    peak = equity[0]
    worst = 0
    for value in equity:
        peak = max(peak, value)
        worst = max(worst, peak - value)
    return worst


def _metrics_for(projection: MatchProjection, agent_id: str) -> PerformanceMetrics:
    """Build the performance block of one seat.

    Args:
        projection: The folded journal.
        agent_id: The ranked seat.

    Returns:
        Its :class:`PerformanceMetrics`.
    """
    volume_qty = 0
    trade_count = 0
    maker_trade_count = 0
    fees_paid_cents = 0
    for row in projection.trades:
        is_maker = row.maker_agent_id == agent_id
        is_taker = row.taker_agent_id == agent_id
        if not is_maker and not is_taker:
            continue
        volume_qty += row.qty
        trade_count += 1
        if is_maker:
            maker_trade_count += 1
        if is_taker:
            fees_paid_cents += row.taker_fee_cents

    equity = projection.equity_series(agent_id)
    pnl_cents = pnl_of(projection, agent_id)
    drawdown = max_drawdown_cents_of(equity)
    initial = projection.initial_cash_cents
    return PerformanceMetrics(
        agent_id=agent_id,
        pnl_cents=pnl_cents,
        pnl_bps=bps_ratio(pnl_cents, initial),
        sharpe_milli=sharpe_milli_of(equity),
        max_drawdown_cents=drawdown,
        max_drawdown_bps=bps_ratio(drawdown, initial),
        volume_qty=volume_qty,
        trade_count=trade_count,
        maker_trade_count=maker_trade_count,
        fees_paid_cents=fees_paid_cents,
    )
