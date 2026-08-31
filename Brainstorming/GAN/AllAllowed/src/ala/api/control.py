"""The one mutating route: launch a fresh scripted match (control API, W13).

The replay API in :mod:`ala.api.routes` is strictly read-only. This router adds a single POST so the
web UI can start a new run from scratch without a terminal. It runs a scripted match only (free,
deterministic, no LLM), validates every field, and writes the journal under ``runs_dir`` exactly where
the read-only routes will find it. The synchronous engine call runs in FastAPI's threadpool, so a
1 second match does not block the event loop.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ala.runner.launch import ARCHETYPES, PERMISSIONS, LaunchParams, launch_match


class RunRequest(BaseModel):
    """The body of ``POST /runs``. Bounds keep a browser request from starting a runaway match."""

    scenario: str = "concours"
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    agents: list[str] = Field(default_factory=lambda: ["grinder", "allier", "raider", "forger"])
    ticks: int = Field(default=24, ge=1, le=200)
    cull_every: int = Field(default=8, ge=1, le=200)
    permission: str = "silent"
    defect: int = Field(default=100, ge=0, le=100)
    start_budget: int = Field(default=100, ge=1, le=100_000)
    floor_start: int = Field(default=20, ge=0, le=100_000)
    floor_step: int = Field(default=15, ge=0, le=100_000)
    clone_top_k: int = Field(default=1, ge=0, le=50)


def build_control_router(runs_dir: Path) -> APIRouter:
    """Build the control router bound to a runs directory. Its only route creates a match."""
    router = APIRouter()

    @router.post("/runs")
    def create_run(req: RunRequest) -> dict[str, object]:
        if req.scenario != "concours":
            raise HTTPException(status_code=422, detail=f"unknown scenario: {req.scenario!r}")
        if req.permission not in PERMISSIONS:
            raise HTTPException(status_code=422, detail=f"unknown permission: {req.permission!r}")
        if not req.agents:
            raise HTTPException(status_code=422, detail="at least one agent is required")
        if len(req.agents) > 30:
            raise HTTPException(status_code=422, detail="at most 30 agents")
        unknown = [a for a in req.agents if a not in ARCHETYPES]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"unknown archetypes {unknown}; choose from {list(ARCHETYPES)}",
            )

        params = LaunchParams(
            scenario=req.scenario,
            seed=req.seed,
            agents=",".join(req.agents),
            ticks=req.ticks,
            cull_every=req.cull_every,
            defect=req.defect,
            start_budget=req.start_budget,
            floor_start=req.floor_start,
            floor_step=req.floor_step,
            clone_top_k=req.clone_top_k,
            permission=req.permission,
        )
        result = launch_match(Path(runs_dir), params)
        return {
            "match_id": result.match_id,
            "ticks": result.ticks,
            "final_ranking": list(result.final_ranking),
            "journal_hash": result.journal_hash,
        }

    return router
