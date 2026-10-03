"""Connects the hook switch, the assistant session and the displays.

Lifting the handset starts an `AssistantSession`; putting it down (or the done screen timing out)
stops it. Everything the session reports becomes a display event on the `Hub`. The display's
developer events (simulated hook, typed text, mute) arrive in `handle_client`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from kiosk.assistant.live import LiveConnection, LiveConnector, SessionSetup
from kiosk.assistant.safety import Speaker
from kiosk.assistant.session import AssistantSession, SessionListener
from kiosk.config import FlowConfig
from kiosk.domain.flow import Kiosk
from kiosk.server.events import (
    Event,
    Subtitles,
    image_urls,
    init_event,
    level_event,
    notice_event,
    state_event,
)
from kiosk.server.hub import Hub
from kiosk.voice.hook import SimulatedHook
from kiosk.voice.pcm import level

log = logging.getLogger(__name__)

LEVEL_EVERY_S = 0.08  # loudness events for the animation, at most ~12 per second
MIC_QUEUE = 50  # 1 s of 20 ms frames; older frames are dropped if sending falls behind


class MissingKeyConnector:
    """Used when no API key is configured: lifting the handset shows an error."""

    def __init__(self, env_name: str) -> None:
        self.env_name = env_name

    async def connect(self, setup: SessionSetup) -> LiveConnection:
        raise RuntimeError(f"{self.env_name} is not set (see docs/setup.md)")


class KioskController(SessionListener):
    def __init__(
        self,
        kiosk: Kiosk,
        connector: LiveConnector,
        flow: FlowConfig,
        hub: Hub,
        hook: SimulatedHook,
        images_dir: Path,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.kiosk = kiosk
        self.connector = connector
        self.flow = flow
        self.hub = hub
        self.hook = hook
        self.images_dir = images_dir
        self.session: AssistantSession | None = None
        self.audio_enabled = True
        # The handset (set by the server when audio devices are open):
        self.audio_out: Callable[[bytes], None] | None = None  # play in the earpiece
        self.audio_stop: Callable[[], None] | None = None  # stop playing at once
        self.levels: Callable[[], tuple[float, float]] | None = None  # (mic, earpiece) 0..1
        self._clock = clock
        self._seq = 0
        self._subtitles = Subtitles()
        self._level_at = 0.0
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._background: list[asyncio.Task[Any]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mic: asyncio.Queue[bytes] = asyncio.Queue(MIC_QUEUE)
        hook.subscribe(self._on_hook)

    # --- for the displays --------------------------------------------------------------------

    def init_events(self) -> list[Event]:
        """What a newly connected display needs: the menu (with current images) and the state."""
        menu, cafe = self.kiosk.menu, self.kiosk.cafe
        return [init_event(menu, cafe, image_urls(menu, self.images_dir)), self.state()]

    def state(self) -> Event:
        self._seq += 1
        assistant = self.session.state.value if self.session is not None else "idle"
        return state_event(self.kiosk, assistant, self._seq)

    async def handle_client(self, message: Any) -> None:
        """A developer event from a display: `hook`, `dev_text` or `dev_mute`."""
        if not isinstance(message, dict):
            return
        kind = message.get("type")
        if kind == "hook":
            await self.handset(bool(message.get("off_hook")))
        elif kind == "dev_text":
            await self.type_text(str(message.get("text", "")))
        elif kind == "dev_mute":
            self.audio_enabled = bool(message.get("audio", True))
            if not self.audio_enabled and self.audio_stop is not None:
                self.audio_stop()
            log.info("audio %s", "on" if self.audio_enabled else "muted")
        else:
            log.warning("unknown display event: %r", message)

    # --- the handset -------------------------------------------------------------------------

    async def handset(self, off_hook: bool) -> None:
        """The simulated hook. Lifting again after a finished order starts a new session."""
        if off_hook and self.hook.off_hook and self.session is None:
            await self.lift()
        else:
            self.hook.set(off_hook)
            await self._settle()

    async def lift(self) -> None:
        async with self._lock:
            if self.session is not None:
                return
            log.info("handset lifted")
            session = AssistantSession(self.kiosk, self.connector, self.flow, self)
            self.session = session
            if not await session.start():
                self.session = None
                self.hub.publish(self.state())

    async def hang_up(self) -> None:
        async with self._lock:
            session, self.session = self.session, None
            if session is None:
                return
            log.info("session ended")
            if self.audio_stop is not None:
                self.audio_stop()
            await session.stop()
            self.hub.publish(self.state())

    async def type_text(self, text: str) -> None:
        """Typed customer words (developer mode). Lifts the handset if nobody did."""
        if not text.strip():
            return
        if self.session is None:
            await self.handset(True)
        if self.session is not None:
            await self.session.send_text(text)

    async def start(self) -> None:
        """Start streaming the microphone and publishing loudness (the server's event loop)."""
        self._loop = asyncio.get_running_loop()
        self._background = [
            asyncio.create_task(self._pump_microphone()),
            asyncio.create_task(self._publish_levels()),
        ]

    async def close(self) -> None:
        await self.hang_up()
        for task in [*self._tasks, *self._background]:
            task.cancel()

    # --- the handset's audio -----------------------------------------------------------------

    def microphone_frame(self, pcm: bytes) -> None:
        """A 20 ms microphone frame, from the audio thread."""
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._queue_frame, pcm)

    def _queue_frame(self, pcm: bytes) -> None:
        if self.session is None or not self.audio_enabled:
            return  # nobody is talking to the assistant (or developer mode muted the audio)
        if self._mic.full():
            self._mic.get_nowait()
        self._mic.put_nowait(pcm)

    async def _pump_microphone(self) -> None:
        while True:
            pcm = await self._mic.get()
            session = self.session
            if session is not None:
                await session.send_audio(pcm)

    async def _publish_levels(self) -> None:
        """What the microphone hears and the earpiece plays, for the assistant animation."""
        last = (0.0, 0.0)
        while True:
            await asyncio.sleep(LEVEL_EVERY_S)
            if self.levels is None or self.session is None:
                continue
            mic, out = self.levels()
            if (mic, out) != last:
                last = (mic, out)
                self.hub.publish(level_event(mic, out))

    def _on_hook(self, off_hook: bool) -> None:
        self._spawn(self.lift() if off_hook else self.hang_up())

    async def _settle(self) -> None:
        """Let a lift or hang-up started by the hook switch finish."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.get_running_loop().create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # --- SessionListener ---------------------------------------------------------------------

    def on_state(self) -> None:
        self.hub.publish(self.state())

    def on_subtitle(self, speaker: Speaker, text: str, final: bool) -> None:
        self.hub.publish(self._subtitles.event(speaker, text, final))

    def on_audio(self, pcm: bytes) -> None:
        if self.audio_out is not None and self.audio_enabled:
            self.audio_out(pcm)
        if self.levels is not None:
            return  # the earpiece reports what it really plays (`_publish_levels`)
        now = self._clock()
        if now - self._level_at >= LEVEL_EVERY_S:
            self._level_at = now
            self.hub.publish(level_event(0.0, level(pcm)))

    def on_interrupted(self) -> None:
        if self.audio_stop is not None:
            self.audio_stop()
        self.hub.publish(level_event(0.0, 0.0))

    def on_notice(self, level: str, text: str) -> None:
        self.hub.publish(notice_event(level, text))

    def on_finished(self) -> None:
        self._spawn(self.hang_up())
