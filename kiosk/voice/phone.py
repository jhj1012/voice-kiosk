"""The phone's browser as the handset (phone mode): its microphone and its speaker, over the
network.

The phone sends 20 ms frames of 16 kHz 16-bit mono PCM (the Live API's input) as binary
WebSocket messages and plays the 24 kHz PCM this sends back. "clear" (a text message) makes it
stop playing at once (barge-in, hang-up). The phone reports what it really plays
(`{"out": 0.4}`), so the assistant animation follows the speaker as with the laptop's handset.

One phone at a time: a newer connection replaces the older one. Everything here runs on the
server's event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Callable

from kiosk.config import AudioConfig
from kiosk.voice.pcm import level

log = logging.getLogger(__name__)

MAX_FRAME_BYTES = 32000  # 1 s of 16 kHz audio; a 20 ms frame is 640 bytes
MAX_QUEUED_S = 60.0  # the assistant's audio arrives faster than it plays; keep up to a minute

Message = bytes | str


class PhoneLink:
    """What the server sends to one connected phone, in order."""

    def __init__(self, max_bytes: int) -> None:
        self._messages: deque[Message] = deque()
        self._bytes = 0
        self._max_bytes = max_bytes
        self._ready = asyncio.Event()
        self.closed = False

    async def next(self) -> Message | None:
        """The next message to send; None once this phone was replaced or the server stops."""
        while not self._messages and not self.closed:
            self._ready.clear()
            await self._ready.wait()
        if self.closed:
            return None
        message = self._messages.popleft()
        if isinstance(message, bytes):
            self._bytes -= len(message)
        return message

    def put(self, message: Message) -> None:
        self._messages.append(message)
        if isinstance(message, bytes):
            self._bytes += len(message)
            while self._bytes > self._max_bytes and isinstance(self._messages[0], bytes):
                self._bytes -= len(self._messages.popleft())
        self._ready.set()

    def drop_audio(self) -> None:
        """Forget the audio not sent yet."""
        self._messages = deque(m for m in self._messages if not isinstance(m, bytes))
        self._bytes = 0

    def close(self) -> None:
        self.closed = True
        self._ready.set()


class PhoneHandset:
    def __init__(self, config: AudioConfig, on_frame: Callable[[bytes], None]) -> None:
        self.config = config
        self._on_frame = on_frame
        self._link: PhoneLink | None = None
        self._mic = 0.0
        self._out = 0.0

    @property
    def connected(self) -> bool:
        return self._link is not None

    def connect(self) -> PhoneLink:
        """A phone connected; an older one is let go."""
        if self._link is not None:
            log.info("another phone connected; the older one is let go")
            self._link.close()
        self._link = PhoneLink(int(MAX_QUEUED_S * self.config.output_rate) * 2)
        log.info("phone connected")
        return self._link

    def disconnect(self, link: PhoneLink) -> None:
        link.close()
        if link is self._link:
            self._link = None
            self._mic = self._out = 0.0
            log.info("phone disconnected")

    def receive(self, link: PhoneLink, message: Message) -> None:
        """A message from the phone: a microphone frame, or what its speaker plays."""
        if link is not self._link:
            return  # replaced by a newer phone
        if isinstance(message, bytes):
            if not message or len(message) % 2 or len(message) > MAX_FRAME_BYTES:
                return
            self._mic = level(message)
            self._on_frame(message)
            return
        try:
            out = json.loads(message).get("out")
        except (ValueError, AttributeError):
            return
        if isinstance(out, int | float) and 0 <= out <= 1:
            self._out = float(out)

    # --- the same as the laptop's Speaker / Handset, for the controller ------------------------

    def write(self, pcm: bytes) -> None:
        """Queue 24 kHz audio for the phone to play (dropped while no phone is connected)."""
        if self._link is not None and pcm:
            self._link.put(pcm)

    def clear(self) -> None:
        """Stop at once: drop the audio not sent yet, and tell the phone to drop the rest."""
        if self._link is not None:
            self._link.drop_audio()
            self._link.put("clear")
        self._out = 0.0

    def levels(self) -> tuple[float, float]:
        """(microphone, speaker) loudness, 0..1."""
        return self._mic, self._out
