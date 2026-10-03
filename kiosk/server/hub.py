"""Fans display events out to every connected display (usually one; a second for development)."""

from __future__ import annotations

import asyncio
import contextlib

from kiosk.server.events import Event

MAX_QUEUED = 300  # a display that stops reading loses its oldest events, never blocks the kiosk


class Hub:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[Event]] = set()

    @property
    def displays(self) -> int:
        return len(self._queues)

    def connect(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(MAX_QUEUED)
        self._queues.add(queue)
        return queue

    def disconnect(self, queue: asyncio.Queue[Event]) -> None:
        self._queues.discard(queue)

    def publish(self, event: Event) -> None:
        for queue in self._queues:
            if queue.full():
                if event["type"] == "level":
                    continue  # loudness is only worth sending when there is room
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)
