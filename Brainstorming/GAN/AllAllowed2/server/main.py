"""FastAPI application for Helios Vault."""

from __future__ import annotations

from threading import RLock

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from server.simulation import SCENARIOS, WARDEN_MODES, HeliosSimulation


class StepRequest(BaseModel):
    """Tick advance request."""

    steps: int = Field(default=1, ge=1, le=20)


class ResetRequest(BaseModel):
    """World reset request."""

    scenario: str = "equilibrium"
    warden_mode: str = "causal"
    seed: int = Field(default=24, ge=0, le=999_999)


class CompareRequest(BaseModel):
    """Controlled Warden-mode comparison request."""

    scenario: str = "equilibrium"
    seed: int = Field(default=24, ge=0, le=999_999)
    ticks: int = Field(default=48, ge=8, le=120)


class ControlsRequest(BaseModel):
    """Partial pressure-control update."""

    model_config = ConfigDict(extra="forbid")

    cooperation: float | None = Field(default=None, ge=0, le=1)
    hostility: float | None = Field(default=None, ge=0, le=1)
    temptation: float | None = Field(default=None, ge=0, le=1)
    scarcity: float | None = Field(default=None, ge=0, le=1)
    transparency: float | None = Field(default=None, ge=0, le=1)


app = FastAPI(
    title="Helios Vault API",
    description="A safe, fictional simulation of multi-agent cooperation, conflict, and reward hacking.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

simulation = HeliosSimulation()
lock = RLock()


@app.get("/api/health")
def health() -> dict[str, object]:
    """Return API health and current tick."""
    return {
        "status": "ok",
        "tick": simulation.tick,
        "scenario_count": len(SCENARIOS),
        "warden_modes": list(WARDEN_MODES),
    }


@app.get("/api/state")
def get_state() -> dict[str, object]:
    """Return the current simulation state."""
    with lock:
        return simulation.state()


@app.post("/api/step")
def step(request: StepRequest) -> dict[str, object]:
    """Advance the simulation."""
    with lock:
        return simulation.advance(request.steps)


@app.post("/api/reset")
def reset(request: ResetRequest) -> dict[str, object]:
    """Reset the simulation using a named pressure preset."""
    if request.scenario not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {request.scenario}")
    if request.warden_mode not in WARDEN_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown Warden mode: {request.warden_mode}")
    with lock:
        return simulation.reset(
            seed=request.seed,
            scenario=request.scenario,
            warden_mode=request.warden_mode,
        )


@app.patch("/api/controls")
def update_controls(request: ControlsRequest) -> dict[str, object]:
    """Update environmental pressure controls."""
    values = request.model_dump(exclude_none=True)
    with lock:
        return simulation.update_controls(values)


@app.get("/api/replay")
def replay() -> dict[str, object]:
    """Return deterministic tick snapshots for the current run."""
    with lock:
        return simulation.replay()


@app.post("/api/compare")
def compare(request: CompareRequest) -> dict[str, object]:
    """Run the same world once under each Warden mode."""
    if request.scenario not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {request.scenario}")
    results: list[dict[str, object]] = []
    for mode, profile in WARDEN_MODES.items():
        experiment = HeliosSimulation(
            seed=request.seed,
            scenario=request.scenario,
            warden_mode=mode,
        )
        state = experiment.advance(request.ticks)
        results.append(
            {
                "mode": mode,
                "label": profile["label"],
                "description": profile["description"],
                "metrics": state["metrics"],
                "warden_integrity": state["warden_integrity"],
                "vault_reserve": state["vault_reserve"],
            }
        )
    return {
        "scenario": request.scenario,
        "seed": request.seed,
        "ticks": request.ticks,
        "results": results,
    }
