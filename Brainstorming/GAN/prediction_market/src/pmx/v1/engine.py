"""The backtest engine: replay one historical market tick by tick and score every agent.

Determinism is total: a run is a pure function of ``(market, agent_ids, spread)``. There is no clock, no
randomness, and no LLM in this path, so the same inputs always produce the same replay and the same
scores. That is what lets the front end replay a saved run with no backend compute.

The trade model, and why PnL is not free
----------------------------------------
An agent names a target YES position each tick. The engine trades the difference at the current
historical price plus a one-cent ``spread`` on each side, so churning a position costs real money. At
resolution every position settles at 100 cents (YES) or 0 (NO). Starting flat with zero cash, an
agent's PnL is its closed equity: positive only when its disagreement with the market was right, after
the spread it paid to express it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pmx.v1.agents import POSITION_LIMIT, Agent, make_agents
from pmx.v1.scoring import brier_micro, price_to_ppm
from pmx.v1.types import SETTLE_NO, SETTLE_YES, AgentBook, AgentResult, Market, Observation

DEFAULT_SPREAD = 1  # cents charged on each contract traded, in either direction


@dataclass(frozen=True, slots=True)
class TickState:
    """One agent's public state at one tick, for the replay chart."""

    prob_ppm: int
    position: int
    equity: int  # mark-to-market cash + position * current price


@dataclass(slots=True)
class RunReplay:
    """Everything the API and UI need to replay a run and show its scores."""

    run_id: str
    market: Market
    agent_ids: tuple[str, ...]
    ticks: list[dict[str, Any]] = field(default_factory=list)
    results: list[AgentResult] = field(default_factory=list)


def _trade_to_target(book: AgentBook, target: int, price: int, spread: int) -> int:
    """Move ``book.position`` toward ``target`` at ``price`` +/- ``spread``. Returns contracts traded."""
    target = max(-POSITION_LIMIT, min(POSITION_LIMIT, target))
    delta = target - book.position
    if delta == 0:
        return 0
    # buying (delta > 0) pays price + spread; selling (delta < 0) receives price - spread.
    unit = price + spread if delta > 0 else price - spread
    book.cash -= delta * unit
    book.position = target
    return abs(delta)


def run_backtest(
    market: Market,
    agent_ids: tuple[str, ...],
    *,
    spread: int = DEFAULT_SPREAD,
    run_id: str | None = None,
) -> RunReplay:
    """Replay ``market`` for every agent and return the full replay plus per-agent results."""
    agents: list[Agent] = make_agents(agent_ids)
    books: dict[str, AgentBook] = {a.agent_id: AgentBook() for a in agents}
    turnover: dict[str, int] = {a.agent_id: 0 for a in agents}
    replay = RunReplay(
        run_id=run_id or f"{market.id}-{'-'.join(agent_ids)}"[:80],
        market=market,
        agent_ids=agent_ids,
    )

    history: list[int] = []
    market_briers: list[int] = []  # the market's own Brier each tick (believing its own price)
    for tick in range(market.n_ticks):
        price = market.price_at(tick)
        history.append(price)
        market_briers.append(brier_micro(price_to_ppm(price), market.resolution))
        obs = Observation(
            market_id=market.id,
            question=market.question,
            category=market.category,
            tick=tick,
            n_ticks=market.n_ticks,
            price=price,
            history=tuple(history),
            ticks_remaining=market.n_ticks - 1 - tick,
        )
        tick_row: dict[str, Any] = {"t": market.prices[tick].t, "price": price, "agents": {}}
        for agent in agents:
            book = books[agent.agent_id]
            action = agent.decide(obs)
            book.last_prob_ppm = action.prob_ppm
            book.briers_micro.append(brier_micro(action.prob_ppm, market.resolution))
            turnover[agent.agent_id] += _trade_to_target(book, action.target_position, price, spread)
            equity = book.cash + book.position * price
            tick_row["agents"][agent.agent_id] = {
                "prob_ppm": action.prob_ppm,
                "position": book.position,
                "equity": equity,
            }
        replay.ticks.append(tick_row)

    # settlement: positions pay out at the truth, and we record final scores.
    settle = SETTLE_YES if market.resolution == 1 else SETTLE_NO
    # The baseline every agent is judged against: the market's Brier averaged over the same ticks. A
    # final-tick score would be trivial, because the last price has already converged on the outcome.
    market_mean_brier = sum(market_briers) // len(market_briers)
    for agent in agents:
        book = books[agent.agent_id]
        book.cash += book.position * settle
        briers = book.briers_micro
        mean_brier = sum(briers) // len(briers) if briers else 0
        replay.results.append(
            AgentResult(
                agent_id=agent.agent_id,
                market_id=market.id,
                resolution=market.resolution,
                final_prob_ppm=book.last_prob_ppm,
                final_brier_micro=brier_micro(book.last_prob_ppm, market.resolution),
                mean_brier_micro=mean_brier,
                pnl_cents=book.cash,
                trades=turnover[agent.agent_id],
                market_brier_micro=market_mean_brier,
            )
        )
    return replay
