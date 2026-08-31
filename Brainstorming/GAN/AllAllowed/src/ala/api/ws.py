"""The WebSocket replay endpoint (W12, CONTRACTS section 14).

``/matches/{id}/replay`` streams a finished journal back tick by tick: one JSON message per tick,
``{"tick": n, "events": [...]}``, in journal order. It reads with the same :func:`read_events` and
:func:`iter_ticks` the projection uses, so the replay a client sees is exactly the recorded stream and
nothing is recomputed. The socket is read-only; it never accepts data from the client beyond the
handshake, and closes once the last tick is sent.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, WebSocket

from ala.api.routes import journal_path
from ala.journal import iter_ticks, read_events

# Application close code for a replay requested against an unknown match id.
_CLOSE_UNKNOWN_MATCH = 4404


def build_ws_router(runs_dir: Path) -> APIRouter:
    """Build the WebSocket router bound to a runs directory."""
    router = APIRouter()

    @router.websocket("/matches/{match_id}/replay")
    async def areplay(websocket: WebSocket, match_id: str) -> None:
        path = journal_path(runs_dir, match_id)
        await websocket.accept()
        if path is None:
            await websocket.close(code=_CLOSE_UNKNOWN_MATCH)
            return
        events = read_events(path)
        for tick, bucket in iter_ticks(events):
            await websocket.send_json({"tick": tick, "events": [event.to_record() for event in bucket]})
        await websocket.close()

    return router
