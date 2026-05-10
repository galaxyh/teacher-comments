"""Tiny in-process pub/sub keyed by topic (e.g., `batch:<batch_job_id>`).

Walking-skeleton scope: single-process broadcast. Subscribers attached AFTER
publish miss those messages — the design is "subscribers get future events,
caller polls get_status to see initial state." V2 horizontal-scale would
swap this for Redis pub/sub (ADR-worthy change at that point).

Event payload is a JSON-serialisable dict; the SSE handler stringifies it.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class SSEPublisher:
    def __init__(self) -> None:
        # topic → set of subscriber asyncio.Queue
        self._subscribers: dict[str, set[asyncio.Queue[dict]]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, event: dict) -> None:
        """Broadcast event to all current subscribers of `topic`. Non-blocking."""
        async with self._lock:
            queues = list(self._subscribers.get(topic, set()))
        for q in queues:
            # Non-blocking put — if a subscriber is slow / disconnected, drop the event
            # rather than stall the publisher. Walking-skeleton trade-off; production
            # should track drops and reconcile via get_status.
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("SSE queue full for topic=%s; dropping event", topic)

    async def subscribe(self, topic: str) -> AsyncIterator[dict]:
        """Async generator that yields events. Yields until consumer breaks the loop."""
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._subscribers.setdefault(topic, set()).add(q)
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            async with self._lock:
                if topic in self._subscribers:
                    self._subscribers[topic].discard(q)
                    if not self._subscribers[topic]:
                        del self._subscribers[topic]

    @staticmethod
    def format_sse(event: dict) -> bytes:
        """Encode event for `text/event-stream`. One blank line terminates the message."""
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


# Module singleton — wired through Depends like the write queue
_publisher: SSEPublisher | None = None


def get_sse_publisher() -> SSEPublisher:
    global _publisher
    if _publisher is None:
        _publisher = SSEPublisher()
    return _publisher


def reset_sse_publisher_cache() -> None:
    """Test-only — drop singleton so per-test queues bind to the right loop."""
    global _publisher
    _publisher = None
