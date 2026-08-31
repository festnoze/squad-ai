"""Core types for the prediction-market backtest arena (pmx).

The whole arena is deterministic and judged by reality: a historical market carries a resolved outcome,
and agents are scored against it by Brier (their stated probability) and by PnL (their trades at the
historical price). No metric depends on an LLM judge; the world is the referee.

Money and prices are integers. A YES contract is priced in whole cents in ``[1, 99]`` (equivalently the
implied probability in percent), and settles at 100 cents on YES or 0 on NO. A stated probability is an
integer in parts-per-million, ``[0, 1_000_000]``. No float ever touches a score or a cash balance.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PPM_ONE = 1_000_000
SETTLE_YES = 100  # cents a YES contract pays if the event happened
SETTLE_NO = 0
PRICE_MIN = 1
PRICE_MAX = 99


@dataclass(frozen=True, slots=True)
class PricePoint:
    """One snapshot of the market's YES price. ``t`` is an ISO date or datetime label, kept as text so
    the journal has no clock; ``price`` is whole cents in ``[1, 99]``."""

    t: str
    price: int


@dataclass(frozen=True, slots=True)
class Market:
    """A single resolved historical market: its question, its price evolution, and the truth.

    ``source`` is ``"imported"`` for genuine data pulled from a provider, or ``"reconstructed"`` for a
    plausible path built for the bundled demo over a real event with a real outcome. The UI shows the
    difference so a reconstructed path is never mistaken for a real tape.
    """

    id: str
    question: str
    category: str
    source: str
    resolution: int  # 1 = YES happened, 0 = NO
    resolved_date: str
    prices: tuple[PricePoint, ...]
    notes: str = ""

    def price_at(self, tick: int) -> int:
        return self.prices[tick].price

    @property
    def n_ticks(self) -> int:
        return len(self.prices)


@dataclass(frozen=True, slots=True)
class Observation:
    """What an agent sees on one tick. It never contains the resolution: the agent must judge the
    evolving price, not read the answer."""

    market_id: str
    question: str
    category: str
    tick: int
    n_ticks: int
    price: int  # current YES price in cents
    history: tuple[int, ...]  # prices up to and including this tick
    ticks_remaining: int


@dataclass(frozen=True, slots=True)
class Action:
    """An agent's move for the tick: a stated probability (scored by Brier) and a desired net YES
    position in contracts (the engine trades toward it, scored by PnL)."""

    prob_ppm: int
    target_position: int


@dataclass(slots=True)
class AgentBook:
    """The running trading book for one agent in one market. Starts flat; PnL is the closed equity."""

    cash: int = 0  # cents, may go negative (paper account, position-limited instead of cash-limited)
    position: int = 0  # net YES contracts, bounded by the engine
    last_prob_ppm: int = PPM_ONE // 2
    briers_micro: list[int] = field(default_factory=list)  # per-tick Brier in micro-units


@dataclass(frozen=True, slots=True)
class AgentResult:
    """One agent's outcome on one market, everything a metric needs, all integers."""

    agent_id: str
    market_id: str
    resolution: int
    final_prob_ppm: int
    final_brier_micro: int  # Brier of the last stated probability, in micro-units (0..1_000_000)
    mean_brier_micro: int  # mean Brier across ticks
    pnl_cents: int  # closed equity after settlement, net of costs
    trades: int  # number of contracts traded (turnover), a cost proxy
    market_brier_micro: int  # the market's own final Brier, the baseline to beat
