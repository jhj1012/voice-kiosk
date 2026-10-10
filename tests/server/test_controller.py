"""The controller with a fake Live connection and a hub (no network, no browser)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from kiosk.assistant.instructions import GREETING_CUE
from kiosk.assistant.live import (
    AudioOut,
    InputText,
    Interrupted,
    KeyRejected,
    OutputText,
    TurnComplete,
)
from kiosk.config import FlowConfig
from kiosk.domain.flow import Kiosk, Phase
from kiosk.server.controller import ApiKeys, KioskController, MissingKeyConnector
from kiosk.server.hub import Hub
from kiosk.server.settings import DisplaySettings
from kiosk.voice.hook import SimulatedHook
from kiosk.voice.pcm import level
from tests.fakes import FakeConnector

FAST = FlowConfig(insert_card_s=0, processing_s=0, done_return_s=0)


class Setup:
    def __init__(self, kiosk: Kiosk, connector: Any, tmp_path, keys: ApiKeys | None = None):
        self.hub = Hub()
        self.events = self.hub.connect()
        self.hook = SimulatedHook()
        self.connector = connector
        self.controller = KioskController(
            kiosk, connector, FAST, self.hub, self.hook, tmp_path, keys=keys
        )

    def drain(self) -> list[dict[str, Any]]:
        events = []
        while not self.events.empty():
            events.append(self.events.get_nowait())
        return events

    async def settle(self) -> None:
        for _ in range(40):
            await asyncio.sleep(0)
        await asyncio.sleep(0.01)


def run(
    menu, cafe, tmp_path, test: Callable[[Setup], Awaitable[None]], connector=None, keys=None
) -> None:
    async def main() -> None:
        setup = Setup(Kiosk(menu, cafe), connector or FakeConnector(), tmp_path, keys)
        try:
            await test(setup)
        finally:
            await setup.controller.close()

    asyncio.run(main())


def test_init_events_carry_the_menu_and_the_state(menu, cafe, tmp_path):
    async def test(s: Setup) -> None:
        init, settings, setup, state = s.controller.init_events()
        assert settings == {"type": "settings", "values": {}}
        assert init["type"] == "init" and init["menu"]["items"]
        assert setup == {"type": "setup", "api_key": "ok"}
        assert state["type"] == "state" and state["phase"] == "idle"
        assert s.controller.state()["seq"] > state["seq"]

    run(menu, cafe, tmp_path, test)


def test_init_events_pick_up_new_images(menu, cafe, tmp_path):
    async def test(s: Setup) -> None:
        (tmp_path / "americano.png").write_bytes(b"x")
        init, _, _, _ = s.controller.init_events()
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


KEY = "AIza" + "x" * 35
NEW_KEY = "AQ." + "x" * 50  # newer keys look different


class Keys:
    """Fake key handling: Google's answer is `answer`; saved keys are remembered."""

    def __init__(self, answer: str = "ok") -> None:
        self.answer = answer
        self.checked: list[str] = []
        self.saved: list[str] = []
        self.connector = FakeConnector()

    async def check(self, key: str) -> str:
        self.checked.append(key)
        return self.answer

    def api_keys(self) -> ApiKeys:
        return ApiKeys(check=self.check, save=self.saved.append, connector=lambda k: self.connector)


def test_missing_api_key_asks_for_one(menu, cafe, tmp_path):
    async def test(s: Setup) -> None:
        assert s.controller.init_events()[2] == {"type": "setup", "api_key": "missing"}
        await s.controller.handset(True)
        assert s.controller.session is None
        assert s.drain()[-1]["phase"] == "idle"

    run(menu, cafe, tmp_path, test, connector=MissingKeyConnector("GEMINI_API_KEY"))


def test_a_key_entered_on_the_display_is_checked_saved_and_used(menu, cafe, tmp_path):
    keys = Keys()

    async def test(s: Setup) -> None:
        assert await s.controller.set_api_key(f"  {KEY}\n") == "ok"
        assert keys.checked == [KEY] and keys.saved == [KEY]
        assert {"type": "setup", "api_key": "ok"} in s.drain()
        await s.controller.handset(True)  # the next customer talks with the new key
        assert s.controller.session is not None and keys.connector.connections

    run(menu, cafe, tmp_path, test, MissingKeyConnector("GEMINI_API_KEY"), keys.api_keys())


def test_newer_keys_are_accepted_too(menu, cafe, tmp_path):
    keys = Keys()

    async def test(s: Setup) -> None:
        assert await s.controller.set_api_key(NEW_KEY) == "ok"

    run(menu, cafe, tmp_path, test, keys=keys.api_keys())


@pytest.mark.parametrize("typed", ["", "short", "AIza with spaces in the middle of it", "키" * 30])
def test_text_that_is_not_a_key_is_not_sent_to_google(menu, cafe, tmp_path, typed):
    keys = Keys()

    async def test(s: Setup) -> None:
        assert await s.controller.set_api_key(typed) == "invalid"
        assert keys.checked == [] and keys.saved == []

    run(menu, cafe, tmp_path, test, keys=keys.api_keys())


@pytest.mark.parametrize("answer", ["rejected", "offline"])
def test_a_key_google_refuses_is_not_saved(menu, cafe, tmp_path, answer):
    keys = Keys(answer)

    async def test(s: Setup) -> None:
        assert await s.controller.set_api_key(KEY) == answer
        assert keys.saved == [] and s.controller.key_status == "missing"

    run(menu, cafe, tmp_path, test, MissingKeyConnector("GEMINI_API_KEY"), keys.api_keys())


def test_a_saved_key_google_refuses_asks_for_a_new_one(menu, cafe, tmp_path):
    class Refusing:
        async def connect(self, setup):
            raise KeyRejected("API key not valid")

    async def test(s: Setup) -> None:
        await s.controller.handset(True)
        assert s.controller.session is None
        assert {"type": "setup", "api_key": "rejected"} in s.drain()

    run(menu, cafe, tmp_path, test, connector=Refusing())


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


def test_display_settings_are_saved_and_sent_to_every_display(menu, cafe, tmp_path):
    async def test(s: Setup) -> None:
        s.controller.settings = DisplaySettings(tmp_path / "display.local.json")
        await s.controller.handle_client(
            {"type": "settings", "values": {"subtitles": True, "colors": {"text": "#111111"}}}
        )
        values = {"subtitles": True, "colors": {"text": "#111111"}}
        assert s.drain() == [{"type": "settings", "values": values}]
        assert DisplaySettings(tmp_path / "display.local.json").values == values
        assert s.controller.init_events()[1]["values"] == values

        await s.controller.handle_client({"type": "settings", "values": "nonsense"})
        assert s.drain() == []
        await s.controller.handle_client({"type": "settings", "reset": True})
        assert s.drain() == [{"type": "settings", "values": {}}]
        assert not (tmp_path / "display.local.json").exists()

    run(menu, cafe, tmp_path, test)
