"""In-process event bus fanning out pipeline events to SSE subscribers.

Each published event is assigned a monotonic ``seq`` id and kept in a bounded
ring buffer, so a reconnecting client (EventSource ``Last-Event-ID``) can be
replayed exactly the events it missed. This is the key resilience win over the
old WebSocket transport, which lost every event emitted while disconnected and
relied on a full state resync on each reconnect.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

# How many recent events to keep for reconnection replay. Sized so a brief
# disconnect (proxy hiccup, backend reload) never loses events; a longer outage
# falls back to the frontend's full resync.
_RING_SIZE = 1000

Event = dict[str, Any]
SeqEvent = tuple[int, Event]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[SeqEvent]] = set()
        self._seq = 0
        self._ring: deque[SeqEvent] = deque(maxlen=_RING_SIZE)

    def subscribe(self) -> asyncio.Queue[SeqEvent]:
        queue: asyncio.Queue[SeqEvent] = asyncio.Queue(maxsize=500)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[SeqEvent]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: Event) -> int:
        """Assign a seq, buffer it for replay, and fan it out. Returns the seq."""
        self._seq += 1
        item: SeqEvent = (self._seq, event)
        self._ring.append(item)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                # Slow consumer: drop it rather than blocking the pipeline. The
                # client reconnects and replays from the ring buffer.
                self._subscribers.discard(queue)
        return self._seq

    def publish_ephemeral(self, event: Event) -> None:
        """Fan out an event to live subscribers WITHOUT buffering it for
        Last-Event-ID replay (B5: the heartbeat ``tick`` is a live-only signal —
        a stale heartbeat replayed on reconnect would lie about freshness).

        It still consumes a ``seq`` so live frames stay monotonic, but the event
        is never added to the replay ring.
        """
        self._seq += 1
        item: SeqEvent = (self._seq, event)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                self._subscribers.discard(queue)

    def replay_since(self, last_id: int) -> list[SeqEvent]:
        """Buffered events newer than ``last_id`` (for reconnection replay)."""
        return [item for item in self._ring if item[0] > last_id]

    @property
    def latest_seq(self) -> int:
        """The seq of the most recent event (0 if none published yet)."""
        return self._seq


bus = EventBus()
