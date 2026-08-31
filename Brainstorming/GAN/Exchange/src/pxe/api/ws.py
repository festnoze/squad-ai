"""The replay WebSocket (CONTRACTS section 7.21, "WebSocket protocol").

One socket, one stream, and the **server is the clock**. The journal is already
complete when a socket opens, so ``speed`` only paces the frames: there is no
back pressure protocol, no partial tick and no live match. A ``tick`` frame
carries the whole :class:`~pxe.api.routes.TickState`, which is what makes
``seek`` cheap and what lets a client that missed frames resume from any tick
with no state of its own.

Frame types, server to client: ``hello``, ``snapshot``, ``tick``,
``highlight``, ``ended``, ``error``, ``pong``. Client to server: ``play``,
``pause``, ``seek``, ``speed``, ``ping``. A bad client frame produces an
``error`` frame and the socket **stays open**; only a bad ``speed`` or
``from_tick`` at connect time, or an unknown match, closes it, with the codes
section 7.21 fixes:

* ``4404`` unknown match;
* ``4400`` a bad ``speed`` or ``from_tick``;
* ``1011`` server error.

``web/src/api/socket.ts`` reconnects on ``1006`` and ``1011`` only and never on
a ``44xx``, because a client bug does not get retried.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from pxe import ENGINE_VERSION
from pxe.api.routes import API_VERSION, WS_SPEEDS, Highlight, ReplayService, _MatchView

__all__ = [
    "CLOSE_UNKNOWN_MATCH",
    "CLOSE_BAD_PARAMETER",
    "CLOSE_SERVER_ERROR",
    "build_ws_router",
]

#: Close code for an unknown match id (section 7.21).
CLOSE_UNKNOWN_MATCH: int = 4404

#: Close code for a ``speed`` outside :data:`~pxe.api.routes.WS_SPEEDS` or a
#: ``from_tick`` outside ``0..ticks_total + 1``.
CLOSE_BAD_PARAMETER: int = 4400

#: Close code for an unexpected server side failure.
CLOSE_SERVER_ERROR: int = 1011


class _Stream:
    """The mutable state of one open socket: where it is, how fast, and whether it plays."""

    def __init__(self, *, view: _MatchView, speed: int, from_tick: int) -> None:
        """Position a fresh stream.

        Args:
            view: The cached match view the frames are read from.
            speed: Ticks per second, one of :data:`~pxe.api.routes.WS_SPEEDS`.
            from_tick: Where the ``snapshot`` sits; streaming resumes after it.
        """
        self.view = view
        self.speed = speed
        self.cursor = from_tick
        self.playing = True
        self.ended_sent = False
        self._anchor = time.monotonic()
        self._emitted = 0

    @property
    def finished(self) -> bool:
        """True once the cursor has reached the finalisation tick."""
        return self.cursor >= self.view.last_tick

    def rebase(self) -> None:
        """Restart the pacing schedule from now.

        Called on ``play``, ``seek`` and ``speed``: a rate change takes effect
        on the next tick, and a seek must not inherit the backlog of the
        position it left.
        """
        self._anchor = time.monotonic()
        self._emitted = 0

    def note_emitted(self) -> None:
        """Count one emitted ``tick`` frame against the schedule."""
        self._emitted += 1

    def delay_s(self) -> float | None:
        """Seconds to wait before the next ``tick`` frame, ``None`` to wait for the client.

        The schedule is a deadline from an anchor, not a fixed sleep per frame:
        ``speed`` means ticks per second, and a per frame sleep on a platform
        whose timer granularity is coarser than ``1 / speed`` (Windows, about
        15 ms) accumulates drift and silently serves ``x64`` at half rate. A
        deadline that is already past yields ``0.0``, so the stream catches up
        instead of falling behind for good.
        """
        if not self.playing or self.finished:
            return None
        due = self._anchor + float(self._emitted + 1) / float(self.speed)
        return max(0.0, due - time.monotonic())


def build_ws_router(service: ReplayService) -> APIRouter:
    """Build the router holding ``WS /ws/matches/{match_id}``.

    Args:
        service: The data layer. The socket reads the same cached
            :class:`~pxe.api.routes.TickState` bytes the REST route serves, which
            is what makes ``test_api.py::test_ws_tick_frame_equals_rest_tick``
            true by construction rather than by review.

    Returns:
        The router, mounted at the application root.
    """
    router = APIRouter(tags=["replay"])

    @router.websocket("/ws/matches/{match_id}")
    async def areplay_socket(websocket: WebSocket, match_id: str, speed: int = 1, from_tick: int = 1) -> None:
        """Stream one recorded match, paced by the server.

        Args:
            websocket: The socket.
            match_id: The match to replay.
            speed: Ticks per second, one of the seven legal values.
            from_tick: Opening position, ``0`` and ``ticks_total + 1`` included.
        """
        await _aserve(service, websocket, match_id=match_id, speed=speed, from_tick=from_tick)

    return router


async def _aserve(service: ReplayService, websocket: WebSocket, *, match_id: str, speed: int, from_tick: int) -> None:
    """Accept, validate, then stream until the client leaves.

    Args:
        service: The data layer.
        websocket: The socket.
        match_id: The match to replay.
        speed: Requested pace in ticks per second.
        from_tick: Requested opening position.
    """
    await websocket.accept()
    try:
        view = service.view(match_id)
    except Exception:  # any lookup failure reads as "unknown match" to a client
        await _aclose(websocket, CLOSE_UNKNOWN_MATCH)
        return
    if speed not in WS_SPEEDS:
        await _asend(websocket, _bad_speed_frame())
        await _aclose(websocket, CLOSE_BAD_PARAMETER)
        return
    if not view.first_tick <= from_tick <= view.last_tick:
        await _asend(
            websocket,
            {
                "type": "error",
                "code": "INVALID_TICK",
                "message": f"from_tick must be within {view.first_tick}..{view.last_tick}",
            },
        )
        await _aclose(websocket, CLOSE_BAD_PARAMETER)
        return

    stream = _Stream(view=view, speed=speed, from_tick=from_tick)
    try:
        await _asend(
            websocket,
            {
                "type": "hello",
                "match_id": view.match_id,
                "ticks_total": view.ticks_total,
                "speed": speed,
                "from_tick": from_tick,
                "api_version": API_VERSION,
                "engine_version": ENGINE_VERSION,
            },
        )
        await _asend_state(websocket, view, stream.cursor, kind="snapshot")
        await _arun(websocket, stream)
    except WebSocketDisconnect:
        return
    except RuntimeError:
        # Starlette raises RuntimeError when the peer vanished between two
        # sends. A client that closes mid stream is normal, not an error.
        return
    except Exception:  # never leak a traceback into a socket
        await _aclose(websocket, CLOSE_SERVER_ERROR)


async def _arun(websocket: WebSocket, stream: _Stream) -> None:
    """Drive the stream: emit paced ticks, answer client frames, never close on idle.

    Args:
        websocket: The socket.
        stream: The mutable position of this socket.
    """
    receiver: asyncio.Task[str] = asyncio.create_task(websocket.receive_text())
    try:
        while True:
            delay = stream.delay_s()
            if stream.playing and stream.finished and not stream.ended_sent:
                # The cursor reached finalisation while playing. A paused or
                # seeked cursor sitting at the end announces nothing: `ended`
                # means "the stream is over", not "the cursor is at T + 1".
                await _asend_ended(websocket, stream.view)
                stream.ended_sent = True
                continue
            done, _pending = await asyncio.wait({receiver}, timeout=delay)
            if receiver in done:
                try:
                    raw = receiver.result()
                except (WebSocketDisconnect, RuntimeError):
                    return
                await _ahandle(websocket, stream, raw)
                if websocket.client_state is not WebSocketState.CONNECTED:
                    return
                receiver = asyncio.create_task(websocket.receive_text())
                continue
            if stream.playing and not stream.finished:
                cursor = stream.cursor + 1
                stream.cursor = cursor
                stream.note_emitted()
                await _asend_highlights(websocket, stream.view, cursor)
                await _asend_state(websocket, stream.view, cursor, kind="tick")
                if cursor >= stream.view.last_tick:
                    await _asend_ended(websocket, stream.view)
                    stream.ended_sent = True
    finally:
        receiver.cancel()


async def _ahandle(websocket: WebSocket, stream: _Stream, raw: str) -> None:
    """Apply one client frame.

    Args:
        websocket: The socket.
        stream: The mutable position of this socket.
        raw: The received text frame.
    """
    try:
        frame = json.loads(raw)
    except json.JSONDecodeError:
        await _asend(websocket, {"type": "error", "code": "INVALID_FRAME", "message": "frame is not JSON"})
        return
    if not isinstance(frame, dict):
        await _asend(websocket, {"type": "error", "code": "INVALID_FRAME", "message": "frame is not an object"})
        return
    kind = str(frame.get("type", ""))
    if kind == "play":
        stream.playing = True
        stream.rebase()
    elif kind == "pause":
        stream.playing = False
    elif kind == "seek":
        stream.cursor = stream.view.clamp_tick(_as_int(frame.get("tick"), stream.cursor))
        stream.rebase()
        if stream.cursor < stream.view.last_tick:
            # Seeking back into the match reopens the stream, so reaching the
            # end a second time announces itself a second time.
            stream.ended_sent = False
        await _asend_state(websocket, stream.view, stream.cursor, kind="snapshot")
    elif kind == "speed":
        requested = _as_int(frame.get("speed"), stream.speed)
        if requested not in WS_SPEEDS:
            await _asend(websocket, _bad_speed_frame())
            return
        stream.speed = requested
        stream.rebase()
    elif kind == "ping":
        await _asend(websocket, {"type": "pong", "t": _as_int(frame.get("t"), 0)})
    else:
        await _asend(websocket, {"type": "error", "code": "INVALID_FRAME", "message": f"unknown frame type {kind!r}"})


async def _asend_state(websocket: WebSocket, view: _MatchView, tick: int, *, kind: str) -> None:
    """Send a ``snapshot`` or a ``tick`` frame carrying the whole ``TickState``.

    The state body is the cached bytes of the REST route, spliced into the
    frame envelope, so the two paths cannot drift.

    Args:
        websocket: The socket.
        view: The match view.
        tick: The tick to send.
        kind: ``"snapshot"`` or ``"tick"``.
    """
    body = view.tick_bytes(tick).decode("utf-8")
    await websocket.send_text(f'{{"type":"{kind}","tick":{tick},"state":{body}}}')


async def _asend_highlights(websocket: WebSocket, view: _MatchView, tick: int) -> None:
    """Send one ``highlight`` frame per highlight of the tick, before its ``tick`` frame."""
    for row in view.highlights([]):
        if row.tick == tick:
            await _asend(websocket, {"type": "highlight", "highlight": _highlight_dict(row)})


async def _asend_ended(websocket: WebSocket, view: _MatchView) -> None:
    """Send the terminal ``ended`` frame. The socket stays open afterwards."""
    await _asend(
        websocket,
        {
            "type": "ended",
            "final_tick": view.ended.final_tick if view.ended is not None else view.ticks_total,
            "rankings": [row.model_dump() for row in view.rankings()],
            "mm_pnl_cents": view.projection.mm_pnl_cents,
            "fees_collected_cents": view.projection.fees_collected_cents,
        },
    )


async def _asend(websocket: WebSocket, frame: dict[str, Any]) -> None:
    """Send one JSON text frame, separators fixed so frames are comparable."""
    await websocket.send_text(json.dumps(frame, separators=(",", ":"), ensure_ascii=False))


async def _aclose(websocket: WebSocket, code: int) -> None:
    """Close a socket once, ignoring a peer that already vanished."""
    if websocket.client_state is WebSocketState.CONNECTED:
        try:
            await websocket.close(code=code)
        except RuntimeError:
            return


def _bad_speed_frame() -> dict[str, Any]:
    """Build the ``error`` frame refusing a speed outside the seven legal values."""
    return {
        "type": "error",
        "code": "INVALID_SPEED",
        "message": f"speed must be one of {list(WS_SPEEDS)}",
    }


def _highlight_dict(row: Highlight) -> dict[str, Any]:
    """Render one highlight for a frame payload."""
    return row.model_dump()


def _as_int(value: object, fallback: int) -> int:
    """Coerce a client supplied value to an int, falling back on anything else."""
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return fallback
    return fallback
