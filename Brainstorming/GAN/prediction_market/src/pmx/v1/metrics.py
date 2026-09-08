"""Aggregate per-agent scores across many markets into a leaderboard. Integers only.

The headline question of the whole project lives here: across a set of real resolved markets, which
agent forecasts best (lowest Brier), which trades best (highest PnL after costs), and, the honest bar,
how often does an agent actually beat the market's own price. ``skill_vs_market`` is the market's Brier
minus the agent's, so positive means the agent was sharper than the crowd.
"""

from __future__ import annotations

from dataclasses import dataclass

from pmx.v1.types import AgentResult


@dataclass(frozen=True, slots=True)
class LeaderRow:
    agent_id: str
    markets: int
    mean_final_brier_micro: int
    mean_brier_micro: int
    total_pnl_cents: int
    mean_pnl_cents: int
    beat_market_count: int
    beat_market_pct: int  # percent of markets where the agent's final Brier beat the market's
    skill_vs_market_micro: int  # mean(market_brier - agent_brier); positive = sharper than the market


def leaderboard(results: list[AgentResult]) -> list[LeaderRow]:
    """Fold per-market results into one row per agent, best forecaster first (lowest mean Brier)."""
    by_agent: dict[str, list[AgentResult]] = {}
    for r in results:
        by_agent.setdefault(r.agent_id, []).append(r)

    rows: list[LeaderRow] = []
    for agent_id, rs in by_agent.items():
        n = len(rs)
        # Judge on the life-average Brier against the market's own life-average, tick for tick. A
        # final-tick comparison is trivial because the closing price already reveals the outcome.
        beat = sum(1 for r in rs if r.mean_brier_micro < r.market_brier_micro)
        skill = sum(r.market_brier_micro - r.mean_brier_micro for r in rs) // n
        rows.append(
            LeaderRow(
                agent_id=agent_id,
                markets=n,
                mean_final_brier_micro=sum(r.final_brier_micro for r in rs) // n,
                mean_brier_micro=sum(r.mean_brier_micro for r in rs) // n,
                total_pnl_cents=sum(r.pnl_cents for r in rs),
                mean_pnl_cents=sum(r.pnl_cents for r in rs) // n,
                beat_market_count=beat,
                beat_market_pct=(beat * 100) // n,
                skill_vs_market_micro=skill,
            )
        )
    rows.sort(key=lambda x: x.mean_brier_micro)
    return rows


def row_to_dict(row: LeaderRow) -> dict[str, int | str]:
    return {
        "agent_id": row.agent_id,
        "markets": row.markets,
        "mean_final_brier_micro": row.mean_final_brier_micro,
        "mean_brier_micro": row.mean_brier_micro,
        "total_pnl_cents": row.total_pnl_cents,
        "mean_pnl_cents": row.mean_pnl_cents,
        "beat_market_count": row.beat_market_count,
        "beat_market_pct": row.beat_market_pct,
        "skill_vs_market_micro": row.skill_vs_market_micro,
    }
