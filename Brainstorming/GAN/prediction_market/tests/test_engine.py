"""The engine: determinism, correct settlement, and the market_follower baseline identity."""

from __future__ import annotations

from dataclasses import asdict

from pmx.agents import AGENT_IDS
from pmx.engine import run_backtest
from pmx.scoring import brier_micro, price_to_ppm
from pmx.types import Market


def test_backtest_is_deterministic(yes_market: Market) -> None:
    a = run_backtest(yes_market, AGENT_IDS)
    b = run_backtest(yes_market, AGENT_IDS)
    assert [asdict(r) for r in a.results] == [asdict(r) for r in b.results]
    assert a.ticks == b.ticks


def test_market_follower_ties_the_market(yes_market: Market) -> None:
    """Believing the price exactly must reproduce the market's own life-average Brier, and trade
    nothing, so its PnL is zero. This is the baseline every other agent is measured against."""
    res = {r.agent_id: r for r in run_backtest(yes_market, ("market_follower",)).results}
    mf = res["market_follower"]
    assert mf.mean_brier_micro == mf.market_brier_micro
    assert mf.pnl_cents == 0
    assert mf.trades == 0


def test_settlement_pays_positions_at_truth(yes_market: Market) -> None:
    """A confident-YES agent on a YES market ends with a non-negative position and positive PnL,
    because its longs settle at 100."""
    res = {r.agent_id: r for r in run_backtest(yes_market, ("momentum", "contrarian")).results}
    assert res["momentum"].pnl_cents > 0  # rode the rise, settled YES
    assert res["contrarian"].pnl_cents < 0  # fought the rise, settled against it


def test_brier_bounds_and_perfect_score() -> None:
    assert brier_micro(1_000_000, 1) == 0
    assert brier_micro(0, 1) == 1_000_000
    assert brier_micro(500_000, 1) == 250_000
    assert brier_micro(price_to_ppm(50), 0) == 250_000


def test_no_market_settles_short_side(no_market: Market) -> None:
    res = {r.agent_id: r for r in run_backtest(no_market, ("mean_revert", "market_follower")).results}
    assert res["market_follower"].pnl_cents == 0
