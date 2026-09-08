"""Trading metrics, as integer functions of integer inputs (CONTRACTS_V2 section 12.3).

Why this module holds functions rather than a journal walk: the projection (``pmx.metrics.projection``)
is the one module that reads the journal, so every number here is a pure function of the vectors that
walk produced. That keeps the definitions testable one by one, keeps the walk in one place, and makes it
impossible for two callers to disagree about what ``fill_ratio_ppm`` means.

Every ratio is ``0`` when its denominator is ``0`` (section 12's preamble): nine of ten reliability bins
are empty for ``market_follower``, ``sum(requested_size)`` is ``0`` for every agent that never orders,
and ``round_half_up`` is only defined for a positive denominator. A number that would divide by zero is
returned as ``0`` before the division, never guarded after it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isqrt

from pmx.types import PPM_ONE, bp_ratio, milli_ratio, round_half_up

__all__ = (
    "Performance",
    "abstention_ppm",
    "drawdown_series_min_bp",
    "equity_change_bp",
    "fill_ratio_ppm",
    "performance",
    "return_bp",
    "sd_bp",
    "sharpe_milli",
    "turnover_cents",
)


def return_bp(*, pnl_cents: int, bankroll_cents: int) -> int:
    """The run's return in basis points of the bankroll, signed, half away from zero."""
    if bankroll_cents <= 0:
        return 0
    return bp_ratio(pnl_cents, bankroll_cents)


def drawdown_series_min_bp(drawdowns_bp: Sequence[int]) -> int:
    """``max_drawdown_bp`` is the minimum of the per-bar ``equity_marked.drawdown_bp``, ``0`` when empty.

    The series is already signed and non-positive on a binary run; since ruling R180 it may go below
    ``-10_000`` when equity is negative, so no floor is applied here either.
    """
    if not drawdowns_bp:
        return 0
    return min(drawdowns_bp)


def equity_change_bp(equities_cents: Sequence[int], *, bankroll_cents: int) -> tuple[int, ...]:
    """Successive equity changes, each in basis points of the bankroll (the Sharpe input of 12.3)."""
    if bankroll_cents <= 0 or len(equities_cents) < 2:
        return ()
    return tuple(
        bp_ratio(equities_cents[i] - equities_cents[i - 1], bankroll_cents)
        for i in range(1, len(equities_cents))
    )


def sd_bp(values_bp: Sequence[int]) -> int:
    """The integer sample standard deviation of 12.3: ``isqrt(sum((x - mean)^2) // (n - 1))``.

    ``0`` for fewer than two values. The mean is the truncated integer mean, which is what makes the
    result a function of the integers alone: a float mean would put a platform's rounding inside a
    reported number.
    """
    n = len(values_bp)
    if n < 2:
        return 0
    mean = sum(values_bp) // n
    return isqrt(sum((value - mean) ** 2 for value in values_bp) // (n - 1))


def sharpe_milli(values_bp: Sequence[int]) -> int:
    """``milli_ratio(mean_bp, sd_bp)`` over the equity changes, ``0`` when the deviation is ``0``."""
    n = len(values_bp)
    if n < 2:
        return 0
    deviation = sd_bp(values_bp)
    if deviation == 0:
        return 0
    return milli_ratio(sum(values_bp) // n, deviation)


def turnover_cents(cash_deltas_cents: Sequence[int]) -> int:
    """The gross cash a book moved: the sum of absolute fill cash deltas, event fills included."""
    return sum(abs(delta) for delta in cash_deltas_cents)


def fill_ratio_ppm(*, filled_size: int, requested_size: int) -> int:
    """What share of what the agent asked for actually filled, in parts per million."""
    if requested_size <= 0:
        return 0
    return round_half_up(PPM_ONE * filled_size, requested_size)


def abstention_ppm(*, abstained_bars: int, decision_bars: int) -> int:
    """The share of ``(agent, market, bar)`` decisions that ended flat with no order placed.

    The keyword form is deliberate: the numerator counts *bars*, not markets, and an earlier draft that
    counted the ``abstain`` keyword read ``0`` for the most silent agent in the run (section 12.3).
    """
    if decision_bars <= 0:
        return 0
    return round_half_up(PPM_ONE * abstained_bars, decision_bars)


@dataclass(frozen=True, slots=True)
class Performance:
    """One agent's trading metrics for one run (section 12.3), every field an integer or a bool."""

    agent_id: str
    pnl_cents: int
    return_bp: int
    max_drawdown_bp: int
    sharpe_milli: int
    turnover_cents: int
    fill_ratio_ppm: int
    fees_paid_cents: int
    ruined: bool
    n_markets_traded: int
    n_markets_open: int
    abstention_ppm: int
    explicit_abstain_ppm: int
    n_cash_events: int = 0
    exposure_by_kind: tuple[tuple[str, int], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "pnl_cents": self.pnl_cents,
            "return_bp": self.return_bp,
            "max_drawdown_bp": self.max_drawdown_bp,
            "sharpe_milli": self.sharpe_milli,
            "turnover_cents": self.turnover_cents,
            "fill_ratio_ppm": self.fill_ratio_ppm,
            "fees_paid_cents": self.fees_paid_cents,
            "ruined": self.ruined,
            "n_markets_traded": self.n_markets_traded,
            "n_markets_open": self.n_markets_open,
            "abstention_ppm": self.abstention_ppm,
            "explicit_abstain_ppm": self.explicit_abstain_ppm,
            "n_cash_events": self.n_cash_events,
            "exposure_by_kind": [[kind, cents] for kind, cents in self.exposure_by_kind],
        }


def performance(
    *,
    agent_id: str,
    bankroll_cents: int,
    final_cash_cents: int,
    equities_cents: Sequence[int],
    drawdowns_bp: Sequence[int],
    cash_deltas_cents: Sequence[int],
    filled_size: int,
    requested_size: int,
    fees_paid_cents: int,
    ruined: bool,
    n_markets_traded: int,
    n_markets_open: int,
    abstained_bars: int,
    explicit_abstain_bars: int,
    decision_bars: int,
    n_cash_events: int = 0,
    exposure_by_kind: Sequence[tuple[str, int]] = (),
) -> Performance:
    """Assemble one agent's :class:`Performance` from the vectors the journal walk produced.

    ``pnl_cents`` is ``final_cash - bankroll`` (section 12.3), which equals the sum of
    ``realised_pnl_cents`` at run end because every market of a run has settled or been closed and
    every cent moved through exactly one journaled event (sections 8.9 and 9.3). Amendment C1b's cash
    events are inside ``final_cash`` for the same reason (ruling R163), so nothing is added twice.
    """
    pnl = final_cash_cents - bankroll_cents
    return Performance(
        agent_id=agent_id,
        pnl_cents=pnl,
        return_bp=return_bp(pnl_cents=pnl, bankroll_cents=bankroll_cents),
        max_drawdown_bp=drawdown_series_min_bp(drawdowns_bp),
        sharpe_milli=sharpe_milli(equity_change_bp(equities_cents, bankroll_cents=bankroll_cents)),
        turnover_cents=turnover_cents(cash_deltas_cents),
        fill_ratio_ppm=fill_ratio_ppm(filled_size=filled_size, requested_size=requested_size),
        fees_paid_cents=fees_paid_cents,
        ruined=ruined,
        n_markets_traded=n_markets_traded,
        n_markets_open=n_markets_open,
        abstention_ppm=abstention_ppm(abstained_bars=abstained_bars, decision_bars=decision_bars),
        explicit_abstain_ppm=abstention_ppm(
            abstained_bars=explicit_abstain_bars, decision_bars=decision_bars
        ),
        n_cash_events=n_cash_events,
        exposure_by_kind=tuple(sorted(exposure_by_kind)),
    )
