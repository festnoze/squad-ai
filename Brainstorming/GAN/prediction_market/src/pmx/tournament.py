"""Run every agent over a set of markets and rank them, with a walk-forward split to stay honest.

The plain tournament runs all agents on all markets and builds one leaderboard. The walk-forward variant
does the thing that separates a real result from a story: it picks the best agent on the earlier half of
history (train), then reports how that pick actually does on the later half (test) it never saw. An agent
that wins on train but not on test was overfit to the past, and the split is what exposes it.
"""

from __future__ import annotations

from dataclasses import dataclass

from pmx.engine import DEFAULT_SPREAD, RunReplay, run_backtest
from pmx.metrics import LeaderRow, leaderboard
from pmx.types import AgentResult, Market


@dataclass(frozen=True, slots=True)
class Tournament:
    agent_ids: tuple[str, ...]
    replays: list[RunReplay]
    results: list[AgentResult]
    board: list[LeaderRow]


def run_tournament(markets: list[Market], agent_ids: tuple[str, ...], *, spread: int = DEFAULT_SPREAD) -> Tournament:
    """Backtest every agent on every market and rank them into one leaderboard."""
    replays = [run_backtest(m, agent_ids, spread=spread) for m in markets]
    results: list[AgentResult] = [r for rep in replays for r in rep.results]
    return Tournament(agent_ids=agent_ids, replays=replays, results=results, board=leaderboard(results))


@dataclass(frozen=True, slots=True)
class WalkForward:
    train_ids: tuple[str, ...]
    test_ids: tuple[str, ...]
    train_board: list[LeaderRow]
    test_board: list[LeaderRow]
    train_winner: str
    test_winner: str
    generalised: bool  # did the train winner also lead on the held-out test half


def walk_forward(markets: list[Market], agent_ids: tuple[str, ...], *, spread: int = DEFAULT_SPREAD) -> WalkForward:
    """Split markets in time, pick the best agent on the past, and grade it on the future.

    Markets are already sorted by ``resolved_date`` by the loader, so the split is chronological. With
    an odd count the extra market goes to train.
    """
    if len(markets) < 4:
        raise ValueError("walk-forward needs at least four markets to split")
    cut = (len(markets) + 1) // 2
    train, test = markets[:cut], markets[cut:]

    train_board = run_tournament(train, agent_ids, spread=spread).board
    test_board = run_tournament(test, agent_ids, spread=spread).board
    train_winner = train_board[0].agent_id
    test_winner = test_board[0].agent_id
    return WalkForward(
        train_ids=tuple(m.id for m in train),
        test_ids=tuple(m.id for m in test),
        train_board=train_board,
        test_board=test_board,
        train_winner=train_winner,
        test_winner=test_winner,
        generalised=train_winner == test_winner,
    )
