"""The FastAPI application factory (W12/W13, CONTRACTS section 14).

``create_app`` binds the routers to a runs directory and returns a plain ``FastAPI`` instance. The REST
and WebSocket routers of :mod:`ala.api.routes` and :mod:`ala.api.ws` are strictly read-only. The single
mutating verb lives in :mod:`ala.api.control`: ``POST /runs`` launches a fresh scripted match (free,
deterministic, no LLM) so the web UI can start a run from scratch. Set ``allow_launch=False`` to bind
the read-only surface alone.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from ala.api.control import build_control_router
from ala.api.routes import build_router
from ala.api.ws import build_ws_router


def create_app(runs_dir: str | Path, *, allow_launch: bool = True) -> FastAPI:
    """Build the API over a directory of match runs (``<runs_dir>/<match_id>/journal.jsonl``).

    ``allow_launch`` (default true) mounts ``POST /runs``; set it false for a purely read-only server.
    """
    base = Path(runs_dir)
    app = FastAPI(title="AllAllowed", version="1", description="Match replay, metrics, and run launch API.")
    app.include_router(build_router(base))
    app.include_router(build_ws_router(base))
    if allow_launch:
        app.include_router(build_control_router(base))
    return app
