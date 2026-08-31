"""The FastAPI application factory.

``create_app`` binds the read-only router to a directory of market JSON files. Every endpoint computes
its answer from those files on demand: a backtest is a deterministic pure function, so there is nothing
to store and no mutating verb.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from pmx.api.routes import build_router


def create_app(data_dir: str | Path) -> FastAPI:
    """Build the API over a directory of market files (``<data_dir>/<market_id>.json``)."""
    app = FastAPI(
        title="pmx",
        version="1",
        description="Deterministic backtest arena for prediction markets. Reality is the referee.",
    )
    app.include_router(build_router(Path(data_dir)))
    return app
