"""FastAPI backend for Trading Agents."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import data, backtest, sweep, evolution, multi, validate, optimize

app = FastAPI(title="Trading Agents API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Dev mode — accept all origins
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data.router, prefix="/api/data", tags=["data"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(sweep.router, prefix="/api/sweep", tags=["sweep"])
app.include_router(evolution.router, prefix="/api/evolution", tags=["evolution"])
app.include_router(multi.router, prefix="/api/multi", tags=["multi-strategy"])
app.include_router(validate.router, prefix="/api/validate", tags=["validation"])
app.include_router(optimize.router, prefix="/api/optimize", tags=["optimization"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
