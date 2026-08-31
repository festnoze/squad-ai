"""REST routes for the backtest arena.

Everything is computed on demand from the market files: a backtest is a fast, deterministic pure
function, so there is nothing to persist and no mutating verb. The server loads the market set once at
startup and serves replays, tournaments, and the walk-forward split from it.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from pmx.agents import AGENT_IDS
from pmx.data.loader import load_markets
from pmx.engine import RunReplay, run_backtest
from pmx.metrics import row_to_dict
from pmx.tournament import run_tournament, walk_forward
from pmx.types import AgentResult, Market


def _market_meta(m: Market) -> dict[str, object]:
    return {
        "id": m.id,
        "question": m.question,
        "category": m.category,
        "source": m.source,
        "resolution": m.resolution,
        "resolved_date": m.resolved_date,
        "n_ticks": m.n_ticks,
        "notes": m.notes,
    }


def _result_dict(r: AgentResult) -> dict[str, object]:
    return asdict(r)


def _replay_dict(rep: RunReplay) -> dict[str, object]:
    return {
        "run_id": rep.run_id,
        "market": {**_market_meta(rep.market), "prices": [asdict(p) for p in rep.market.prices]},
        "agent_ids": list(rep.agent_ids),
        "ticks": rep.ticks,
        "results": [_result_dict(r) for r in rep.results],
    }


def _parse_agents(agents: str | None) -> tuple[str, ...]:
    if not agents:
        return AGENT_IDS
    picked = tuple(a.strip() for a in agents.split(",") if a.strip())
    unknown = [a for a in picked if a not in AGENT_IDS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown agents {unknown}; choose from {list(AGENT_IDS)}")
    return picked or AGENT_IDS


def build_router(data_dir: Path) -> APIRouter:
    """Build the router bound to a directory of market JSON files, loaded once at startup."""
    markets = load_markets(data_dir)
    by_id = {m.id: m for m in markets}
    router = APIRouter()

    @router.get("/agents")
    def get_agents() -> dict[str, list[str]]:
        return {"agents": list(AGENT_IDS)}

    @router.get("/markets")
    def get_markets() -> list[dict[str, object]]:
        return [_market_meta(m) for m in markets]

    @router.get("/markets/{market_id}")
    def get_market(market_id: str) -> dict[str, object]:
        m = by_id.get(market_id)
        if m is None:
            raise HTTPException(status_code=404, detail=f"unknown market {market_id!r}")
        return {**_market_meta(m), "prices": [asdict(p) for p in m.prices]}

    @router.get("/markets/{market_id}/backtest")
    def get_backtest(market_id: str, agents: str | None = Query(default=None)) -> dict[str, object]:
        m = by_id.get(market_id)
        if m is None:
            raise HTTPException(status_code=404, detail=f"unknown market {market_id!r}")
        return _replay_dict(run_backtest(m, _parse_agents(agents)))

    @router.get("/tournament")
    def get_tournament(agents: str | None = Query(default=None)) -> dict[str, object]:
        if not markets:
            raise HTTPException(status_code=404, detail="no markets loaded")
        t = run_tournament(markets, _parse_agents(agents))
        return {
            "agent_ids": list(t.agent_ids),
            "board": [row_to_dict(r) for r in t.board],
            "per_market": [
                {"market": _market_meta(rep.market), "results": [_result_dict(r) for r in rep.results]}
                for rep in t.replays
            ],
        }

    @router.get("/walkforward")
    def get_walkforward(agents: str | None = Query(default=None)) -> dict[str, object]:
        if len(markets) < 4:
            raise HTTPException(status_code=422, detail="walk-forward needs at least four markets")
        wf = walk_forward(markets, _parse_agents(agents))
        return {
            "train_ids": list(wf.train_ids),
            "test_ids": list(wf.test_ids),
            "train_board": [row_to_dict(r) for r in wf.train_board],
            "test_board": [row_to_dict(r) for r in wf.test_board],
            "train_winner": wf.train_winner,
            "test_winner": wf.test_winner,
            "generalised": wf.generalised,
        }

    return router
