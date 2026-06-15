"""Tests of the SSE transport (replaces the WebSocket): the EventBus sequence/
ring-buffer/replay logic and the `/api/stream` endpoint's reconnection replay."""

import asyncio
import json

from starlette.requests import Request

from autospec.api import server
from autospec.orchestrator.events import EventBus, bus


def _event(line: str) -> dict:
    return {"type": "log", "project_id": "p", "source": "s", "line": line}


def _make_request(last_event_id: int | None = None) -> Request:
    """A minimal GET Request whose client never disconnects (receive blocks)."""
    headers = []
    if last_event_id is not None:
        headers.append((b"last-event-id", str(last_event_id).encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/stream",
        "headers": headers,
        "query_string": b"",
    }

    async def receive():
        await asyncio.sleep(3600)
        return {"type": "http.disconnect"}

    return Request(scope, receive)


async def _collect_data(body_iterator, n: int, timeout: float = 5.0) -> list[dict]:
    """Pull SSE frames from the response body until ``n`` `data:` events seen."""
    got: list[dict] = []

    async def pump():
        async for chunk in body_iterator:
            text = chunk if isinstance(chunk, str) else bytes(chunk).decode()
            for line in text.splitlines():
                if line.startswith("data:"):
                    got.append(json.loads(line[len("data:"):].strip()))
                    if len(got) >= n:
                        return

    await asyncio.wait_for(pump(), timeout)
    return got


def test_bus_assigns_monotonic_seq_and_replays():
    eb = EventBus()
    assert eb.latest_seq == 0
    s1 = eb.publish(_event("one"))
    s2 = eb.publish(_event("two"))
    s3 = eb.publish(_event("three"))
    assert (s1, s2, s3) == (1, 2, 3)
    assert eb.latest_seq == 3
    # Replay only what's newer than the client's last-seen id.
    missed = eb.replay_since(1)
    assert [e["line"] for _seq, e in missed] == ["two", "three"]
    assert eb.replay_since(3) == []


def test_bus_ring_buffer_is_bounded():
    eb = EventBus()
    from autospec.orchestrator.events import _RING_SIZE

    for i in range(_RING_SIZE + 50):
        eb.publish(_event(str(i)))
    # Oldest events are evicted; seq keeps climbing.
    assert eb.latest_seq == _RING_SIZE + 50
    replayed = eb.replay_since(0)
    assert len(replayed) == _RING_SIZE
    # The first kept event is the 51st published (seq 51).
    assert replayed[0][0] == 51


async def test_stream_is_event_stream_and_replays_from_last_event_id():
    # Baseline at the current live seq so other tests' events aren't replayed.
    start = bus.latest_seq
    bus.publish(_event("one"))
    bus.publish(_event("two"))

    resp = await server.astream(_make_request(last_event_id=start))
    assert resp.media_type == "text/event-stream"
    try:
        got = await _collect_data(resp.body_iterator, 2)
    finally:
        await resp.body_iterator.aclose()  # triggers unsubscribe
    assert [e["line"] for e in got] == ["one", "two"]


async def test_stream_delivers_live_events():
    # No Last-Event-ID -> starts at head; only events published after connect.
    resp = await server.astream(_make_request())
    body = resp.body_iterator
    got: list[dict] = []

    async def pump():
        async for chunk in body:
            text = chunk if isinstance(chunk, str) else bytes(chunk).decode()
            for line in text.splitlines():
                if line.startswith("data:"):
                    got.append(json.loads(line[len("data:"):].strip()))
                    return

    reader = asyncio.create_task(pump())
    # Let the generator subscribe (first chunk = `retry:`) before publishing.
    await asyncio.sleep(0.1)
    bus.publish(_event("live"))
    try:
        await asyncio.wait_for(reader, timeout=5)
    finally:
        await body.aclose()
    assert got and got[0]["line"] == "live"
