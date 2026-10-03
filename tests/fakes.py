"""A fake Live API connection for tests: push server events, see what the session sent."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

from kiosk.assistant.live import FunctionCall, ServerEvent, SessionSetup


class FakeConnection:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[ServerEvent | None] = asyncio.Queue()
        self.texts: list[str] = []
        self.audio: list[bytes] = []
        self.results: list[list[tuple[FunctionCall, dict[str, Any]]]] = []
        self.closed = False

    async def send_audio(self, pcm: bytes) -> None:
        self.audio.append(pcm)

    async def send_text(self, text: str) -> None:
        self.texts.append(text)

    async def send_results(self, results: Sequence[tuple[FunctionCall, dict[str, Any]]]) -> None:
        self.results.append(list(results))

    async def events(self) -> AsyncIterator[ServerEvent]:
        while (event := await self.queue.get()) is not None:
            yield event

    async def close(self) -> None:
        self.closed = True
        self.queue.put_nowait(None)

    def push(self, *events: ServerEvent) -> None:
        for event in events:
            self.queue.put_nowait(event)

    def drop(self) -> None:
        """The connection ends unexpectedly."""
        self.queue.put_nowait(None)

    @property
    def last_result(self) -> dict[str, Any]:
        return self.results[-1][-1][1]


class FakeConnector:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.connections: list[FakeConnection] = []
        self.setups: list[SessionSetup] = []

    async def connect(self, setup: SessionSetup) -> FakeConnection:
        self.setups.append(setup)
        if self.failures:
            self.failures -= 1
            raise ConnectionError("offline")
        connection = FakeConnection()
        self.connections.append(connection)
        return connection

    @property
    def conn(self) -> FakeConnection:
        return self.connections[-1]
