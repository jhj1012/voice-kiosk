"""The controller with a fake Live connection and a hub (no network, no browser)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from kiosk.assistant.instructions import GREETING_CUE
from kiosk.assistant.live import AudioOut, InputText, Interrupted, OutputText, TurnComplete
from kiosk.config import FlowConfig
from kiosk.domain.flow import Kiosk, Phase
from kiosk.server.controller import KioskController, MissingKeyConnector
from kiosk.server.hub import Hub
from kiosk.voice.hook import SimulatedHook
from kiosk.voice.pcm import level
from tests.fakes import FakeConnector

FAST = FlowConfig(insert_card_s=0, processing_s=0, done_return_s=0)


class Setup:
    def __init__(self, kiosk: Kiosk, connector: Any, tmp_path) -> None:
        self.hub = Hub()
        self.events = self.hub.connect()
        self.hook = SimulatedHook()
        self.connector = connector
        self.controller = KioskController(kiosk, connector, FAST, self.hub, self.hook, tmp_path)

    def drain(self) -> list[dict[str, Any]]:
        events = []
        while not self.events.empty():
            events.append(self.events.get_nowait())
        return events

    async def settle(self) -> None:
        for _ in range(40):
            await asyncio.sleep(0)
        await asyncio.sleep(0.01)


def run(menu, cafe, tmp_path, test: Callable[[Setup], Awaitable[None]], connector=None) -> None:
    async def main() -> None:
        setup = Setup(Kiosk(menu, cafe), connector or FakeConnector(), tmp_path)
        try:
            await test(setup)
        finally:
            await setup.controller.close()

    asyncio.run(main())


def test_init_events_carry_the_menu_and_the_state(menu, cafe, tmp_path):
    async def test(s: Setup) -> None:
        init, state = s.controller.init_events()
        assert init["type"] == "init" and init["menu"]["items"]
        assert state["type"] == "state" and state["phase"] == "idle"
        assert s.controller.state()["seq"] > state["seq"]

    run(menu, cafe, tmp_path, test)


def test_init_events_pick_up_new_images(menu, cafe, tmp_path):
    async def test(s: Setup) -> None:
        (tmp_path / "americano.png").write_bytes(b"x")
        init, _ = s.controller.init_events()
        urls = {i["id"]: i["image_url"] for i in init["menu"]["items"]}
        assert urls["americano"].startswith("/images/americano.png?v=")

    run(menu, cafe, tmp_path, test)


def test_lifting_and_putting_down_the_handset(menu, cafe, tmp_path):
    async def test(s: Setup) -> None:
        await s.controller.handle_client({"type": "hook", "off_hook": True})
        assert s.controller.session is not None
        assert s.connector.conn.texts == [GREETING_CUE]
        states = [e for e in s.drain() if e["type"] == "state"]
        assert states[-1]["phase"] == "ordering"
        assert states[-1]["assistant"] == "thinking"
        await s.controller.handle_client({"type": "hook", "off_hook": False})
        assert s.controller.session is None
        assert s.connector.conn.closed
        assert s.drain()[-1]["phase"] == "idle"

    run(menu, cafe, tmp_path, test)


def test_typed_text_lifts_the_handset_if_needed(menu, cafe, tmp_path):
    async def test(s: Setup) -> None:
        await s.controller.handle_client({"type": "dev_text", "text": "라떼 주세요"})
        assert s.hook.off_hook
        assert s.connector.conn.texts == [GREETING_CUE, "라떼 주세요"]
        subtitles = [e for e in s.drain() if e["type"] == "subtitle"]
        assert subtitles[-1]["speaker"] == "customer" and subtitles[-1]["final"]

    run(menu, cafe, tmp_path, test)


def test_session_events_become_display_events(menu, cafe, tmp_path):
    played: list[bytes] = []

    async def test(s: Setup) -> None:
        s.controller.audio_out = played.append
        await s.controller.handset(True)
        s.drain()
        s.connector.conn.push(
            OutputText("안녕하세요"), AudioOut(b"\x00\x40" * 480), TurnComplete(), InputText("네")
        )
        await s.settle()
        events = s.drain()
        kinds = [e["type"] for e in events]
        assert "level" in kinds
        subtitles = [
            (e["speaker"], e["text"], e["final"]) for e in events if e["type"] == "subtitle"
        ]
        assert ("assistant", "안녕하세요", True) in subtitles
        assert ("customer", "네", False) in subtitles
        assert played == [b"\x00\x40" * 480]
        await s.controller.handle_client({"type": "dev_mute", "audio": False})
        s.connector.conn.push(AudioOut(b"\x00\x00" * 10))
        await s.settle()
        assert len(played) == 1  # muted

    run(menu, cafe, tmp_path, test)


def test_finished_order_hangs_up_and_a_new_lift_starts_again(menu, cafe, tmp_path):
    async def test(s: Setup) -> None:
        await s.controller.handset(True)
        s.controller.on_finished()  # the done screen timed out
        await s.settle()
        assert s.controller.session is None
        assert s.controller.kiosk.phase is Phase.IDLE
        assert s.hook.off_hook  # the handset is still in the customer's hand
        await s.controller.handset(True)  # Space again: the next customer
        assert s.controller.session is not None
        assert len(s.connector.connections) == 2

    run(menu, cafe, tmp_path, test)


def test_missing_api_key_shows_an_error(menu, cafe, tmp_path):
    async def test(s: Setup) -> None:
        await s.controller.handset(True)
        assert s.controller.session is None
        events = s.drain()
        assert any(e["type"] == "notice" and e["level"] == "error" for e in events)
        assert events[-1]["phase"] == "idle"

    run(menu, cafe, tmp_path, test, connector=MissingKeyConnector("GEMINI_API_KEY"))


@pytest.mark.parametrize("message", [None, "x", {"type": "fly"}, {"type": "dev_text", "text": " "}])
def test_odd_display_messages_are_ignored(menu, cafe, tmp_path, message):
    async def test(s: Setup) -> None:
        await s.controller.handle_client(message)
        assert s.controller.session is None

    run(menu, cafe, tmp_path, test)


def test_level():
    assert level(b"") == 0.0
    assert level(b"\x00\x00" * 10) == 0.0
    assert level(b"\xff\x7f" * 10) == 1.0  # full scale


def test_hub_drops_levels_for_slow_displays():
    hub = Hub()
    queue = hub.connect()
    for i in range(400):
        hub.publish({"type": "state", "seq": i})
    hub.publish({"type": "level", "mic": 0, "out": 0})
    events = [queue.get_nowait() for _ in range(queue.qsize())]
    assert events[-1] == {"type": "state", "seq": 399}  # newest kept, level dropped
    hub.disconnect(queue)
    assert hub.displays == 0


def test_microphone_frames_reach_the_session_only_during_a_call(menu, cafe, tmp_path):
    async def test(s: Setup) -> None:
        await s.controller.start()
        s.controller.microphone_frame(b"before")  # on hook: dropped
        await s.settle()
        await s.controller.handset(True)
        s.controller.microphone_frame(b"\x01\x00")
        await s.settle()
        assert s.connector.conn.audio == [b"\x01\x00"]
        await s.controller.handle_client({"type": "dev_mute", "audio": False})
        s.controller.microphone_frame(b"\x02\x00")  # muted: dropped
        await s.settle()
        assert s.connector.conn.audio == [b"\x01\x00"]

    run(menu, cafe, tmp_path, test)


def test_earpiece_plays_and_stops_on_interruption(menu, cafe, tmp_path):
    played: list[bytes] = []
    stops: list[bool] = []

    async def test(s: Setup) -> None:
        s.controller.audio_out = played.append
        s.controller.audio_stop = lambda: stops.append(True)
        await s.controller.handset(True)
        s.connector.conn.push(AudioOut(b"\x00\x10" * 100), Interrupted())
        await s.settle()
        assert played == [b"\x00\x10" * 100]
        assert stops == [True]

    run(menu, cafe, tmp_path, test)


def test_levels_come_from_the_handset(menu, cafe, tmp_path):
    async def test(s: Setup) -> None:
        s.controller.levels = lambda: (0.4, 0.7)
        await s.controller.start()
        await s.controller.handset(True)
        s.drain()
        await asyncio.sleep(0.2)
        levels = [e for e in s.drain() if e["type"] == "level"]
        assert levels and levels[0] == {"type": "level", "mic": 0.4, "out": 0.7}

    run(menu, cafe, tmp_path, test)
