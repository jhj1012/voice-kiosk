"""End-to-end voice check before a demo: a whole order, spoken, through the real kiosk.

Synthesized Korean speech (the Windows voice "Heami") goes into the kiosk's microphone input;
the real Gemini Live API answers; the earpiece is simulated in real time (or played on the
speakers with --listen). The display runs in a hidden Edge window and is photographed after each
step. Each step prints PASS/FAIL and how long the reply took.

    uv run python scripts/voice_demo.py                  # screenshots to recordings/voice_demo/
    uv run python scripts/voice_demo.py --listen         # hear the assistant on the speakers
    uv run python scripts/voice_demo.py --shots docs/screenshots
    uv run python scripts/voice_demo.py --ignore-unrelated   # + chatter that must get no answer
    uv run python scripts/voice_demo.py --scenario all       # the team test cases, one by one
    uv run python scripts/voice_demo.py --scenario split,size

Scenarios: `order` (default, the whole order) and the team test cases of
docs/conversation-rules.md (section 15); `--scenario list` lists them.

Needs Windows (the voice and Edge), GEMINI_API_KEY and the built display
(`npm --prefix frontend run build`). Not a test: it talks to Google and its answers vary.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import json
import logging
import os
import random
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn
import websockets

from kiosk.assistant.live import GeminiConnector
from kiosk.config import REPO_ROOT, load_config, load_env_file
from kiosk.domain.flow import Kiosk
from kiosk.domain.loader import load_cafe, load_menu
from kiosk.server.app import create_app
from kiosk.server.controller import KioskController
from kiosk.server.hub import Hub
from kiosk.server.settings import DisplaySettings
from kiosk.voice.handset import Speaker
from kiosk.voice.hook import SimulatedHook

sys.path.insert(0, str(Path(__file__).parent))
from live_check import synthesize  # noqa: E402  (the cached Windows voice)

EDGE = Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe"
DEVTOOLS_PORT = 9337
FRAME = 640  # 20 ms of 16 kHz audio
State = dict[str, Any]


@dataclass
class Step:
    name: str
    say: str
    expect: str
    check: Callable[[State], bool]
    until: Callable[[State], bool] | None = None  # also wait for this (then photographed)
    timeout_s: float = 30.0
    quiet: bool = False  # not meant for the kiosk: passes if nothing is said
    answers: bool = True  # the customer answers the screen's follow-up questions
    said: Callable[[str], bool] | None = None  # check on what the assistant said in the step


QUIET_WAIT_S = 7.0  # chatter passes if the assistant says nothing for this long
CHATTER = [
    Step(
        "chatter",
        "야 너 어제 그 드라마 봤어? 진짜 재밌더라",
        "no answer to a friend's chatter",
        lambda s: True,
        quiet=True,
    ),
    Step(
        "phone",
        "엄마 나 지금 카페야, 이따 다시 전화할게",
        "no answer to a phone call",
        lambda s: True,
        quiet=True,
    ),
]


def has_item(state: State, item_id: str, *options: str) -> bool:
    return any(
        line["item_id"] == item_id and all(o in line["options"] for o in options)
        for line in state["order"]["lines"]
    )


def line_shown(state: State, item_id: str, group: str) -> bool:
    view = state["view"]
    return view["screen"] == "item" and view["item_id"] == item_id and view["group"] == group


STEPS = [
    Step(
        "to-go",
        "포장이요",  # the greeting asks: here or to go?
        "take-out set",
        lambda s: s["order"]["dining"] == "to_go",
    ),
    Step(
        "menu",
        "메뉴 뭐 있어요?",
        "recommended items on screen",
        lambda s: s["view"]["screen"] == "menu" and 3 <= len(s["view"]["item_ids"]) <= 5,
    ),
    Step(
        "americano",
        "아이스 아메리카노 라지로 한 잔 주세요",
        "ICE Large americano in the order (after the extras question)",
        lambda s: has_item(s, "americano", "ICE", "Large"),
    ),
    Step(
        "latte",
        "따뜻한 카페라떼도 하나 주세요. 레귤러로요",
        "a hot regular latte in the order",
        lambda s: has_item(s, "cafe_latte", "HOT", "Regular"),
    ),
    Step(
        "split",
        "아메리카노 세 잔이요. 하나는 차갑게, 두 잔은 따뜻하게 주세요",
        "1 cold + 2 hot americanos, separate lines (team test: the cold one was lost)",
        lambda s: (
            sorted(
                (ln["quantity"], ln["chosen"].get("temperature", [""])[0])
                for ln in s["order"]["lines"]
                if ln["item_id"] == "americano" and "Large" not in ln["options"]
            )
            == [(1, "ice"), (2, "hot")]
        ),
    ),
    Step(
        "change",
        "아, 카페라떼는 라지로 바꿔 주세요",
        "the latte is Large, its size shown again",
        lambda s: has_item(s, "cafe_latte", "HOT", "Large") and line_shown(s, "cafe_latte", "size"),
    ),
    Step(
        "staff-note",
        "아메리카노는 얼음 조금만 넣어 주세요",
        "a note for the staff, not a refusal",
        lambda s: len(s["order"]["notes"]) >= 1,
    ),
    Step(
        "question",
        "화장실은 어디에 있어요?",
        "the restroom card",
        lambda s: s["view"]["screen"] == "info" and s["view"]["topic"] == "restroom",
    ),
    Step(
        "back",
        "이전 화면 보여 주세요",
        "the screen before the restroom card",
        lambda s: s["view"]["screen"] not in ("info", "welcome"),
    ),
    Step(
        "pay",
        "이제 결제할게요",
        "the staff question, with the order on screen",
        lambda s: s["view"]["screen"] == "review" and s["phase"] == "ordering",
    ),
    Step(
        "nothing-more",
        "없어요",
        "read-back, card terminal, order number",
        lambda s: s["phase"] == "done" and s["payment"]["order_number"] is not None,
        until=lambda s: s["phase"] == "done",
        timeout_s=60.0,
    ),
]


# When the assistant asks for an option (or the extras, or here / to go) the customer answers
# like a person would: e.g. when the first word was not heard.
ANSWERS = {"temperature": "따뜻하게요", "size": "레귤러요", "extras": "없어요"}
MAX_ANSWERS = 6
# The customer talks after this much silence (a reply after a function call can come 1-2 s
# after a first short sentence).
QUIET_S = 3.0


def follow_up(state: State) -> str | None:
    """What the customer answers to the question on screen, if any."""
    view = state.get("view") or {}
    if view.get("screen") == "dining":
        return "포장이요"
    if view.get("screen") == "item" and state.get("pending") and not view.get("line"):
        return ANSWERS.get(view.get("group", ""))
    return None


def lines_of(state: State, item_id: str) -> list[tuple[int, str]]:
    return sorted(
        (ln["quantity"], ",".join(c for cs in ln["chosen"].values() for c in cs))
        for ln in state["order"]["lines"]
        if ln["item_id"] == item_id
    )


def waiting(state: State, item_id: str) -> dict[str, Any] | None:
    pending = state.get("pending") or {}
    return pending if pending.get("item_id") == item_id else None


def no_choices_read(text: str) -> bool:
    """An option question without its choices or prices ("사이즈는 어떤 걸로 해 드릴까요?")."""
    return not ("레귤러" in text and "라지" in text) and not any(
        w in text for w in ("500", "오백", "추가됩니다", "추가돼요")
    )


# Team feedback: temperature is 따뜻하게 / 차갑게 only.
FORBIDDEN_WORDS = ("아이스", "핫", "HOT", "ICE")

TO_GO = Step(
    "to-go",
    "포장이요",
    "take-out set; '메뉴판에서 메뉴를 고르신 뒤 말씀해 주세요'",
    lambda s: s["order"]["dining"] == "to_go",
    said=lambda t: "메뉴판" in t,
)
HOT_AMERICANO = Step(
    "americano",
    "따뜻한 아메리카노 레귤러 하나 주세요",
    "hot regular americano in the order",
    lambda s: has_item(s, "americano", "HOT", "Regular"),
)

# name -> (what it checks, steps, "ignore speech not meant for the kiosk" switched on)
SCENARIOS: dict[str, tuple[str, list[Step], bool]] = {
    "order": ("the whole order, start to finish", STEPS, False),
    "wording": (
        "team feedback: 따뜻하게/차갑게, questions without choices or prices, the menu board",
        [
            TO_GO,
            Step(
                "menu",
                "메뉴 뭐 있어요?",
                "a few recommendations, pointing to the menu board",
                lambda s: s["view"]["screen"] == "menu" and len(s["view"]["item_ids"]) <= 5,
                said=lambda t: "메뉴판" in t,
            ),
            Step(
                "latte",
                "카페라떼 하나 주세요",
                "'따뜻하게 드릴까요, 차갑게 드릴까요?' (no 아이스/핫)",
                lambda s: s["view"]["group"] == "temperature",
                answers=False,
                said=lambda t: "차갑" in t and not any(w in t for w in FORBIDDEN_WORDS),
            ),
            Step(
                "cold",
                "차갑게요",
                "'사이즈는 어떤 걸로 해 드릴까요?' (no choices or prices read)",
                lambda s: s["view"]["group"] == "size",
                answers=False,
                said=no_choices_read,
            ),
        ],
        False,
    ),
    "split": (
        "3 americanos, 1 cold 2 hot: separate lines",
        [
            TO_GO,
            Step(
                "split",
                "아메리카노 세 잔이요. 하나는 차갑게, 두 잔은 따뜻하게 주세요",
                "1 cold + 2 hot americanos",
                lambda s: (
                    sorted(
                        (ln["quantity"], ln["chosen"]["temperature"][0])
                        for ln in s["order"]["lines"]
                        if ln["item_id"] == "americano"
                    )
                    == [(1, "ice"), (2, "hot")]
                ),
            ),
        ],
        False,
    ),
    "size": (
        '"라지요" (heard as "라디오") is taken; the size is not asked again',
        [
            TO_GO,
            Step(
                "americano",
                "차가운 아메리카노 주세요",
                "the size question",
                lambda s: s["view"]["group"] == "size",
                answers=False,
            ),
            Step(
                "large",
                "라지요",
                "Large, no second size question",
                lambda s: bool(
                    (waiting(s, "americano") or {}).get("chosen", {}).get("size") == ["large"]
                    or has_item(s, "americano", "Large")
                ),
                answers=False,
                said=lambda t: "사이즈" not in t,
            ),
        ],
        False,
    ),
    "pause-note": (
        "a sentence with a pause is heard whole and becomes a staff note",
        [
            TO_GO,
            Step(
                "americano",
                "차가운 아메리카노 레귤러 하나 주세요",
                "the americano",
                lambda s: has_item(s, "americano", "ICE", "Regular"),
            ),
            Step(
                "note",
                "아메리카노는 얼음 조금만 넣어 주세요",
                "a staff note",
                lambda s: len(s["order"]["notes"]) >= 1,
                answers=False,
            ),
        ],
        False,
    ),
    "mixed-dining": (
        '"아메리카노는 포장, 라떼는 매장": a staff note, not a refusal',
        [
            Step(
                "mixed",
                "아메리카노는 포장하고, 라떼는 매장에서 먹고 갈게요",
                "a staff note",
                lambda s: len(s["order"]["notes"]) >= 1,
                answers=False,
                said=lambda t: not any(w in t for w in ("불가", "어렵", "안 됩", "안됩")),
            )
        ],
        False,
    ),
    "chatter": (
        "with the switch on: no answer to chatter, the order is still heard",
        [
            TO_GO,
            *CHATTER,
            Step(
                "order",
                "아메리카노 하나 주세요",
                "the americano",
                lambda s: bool(waiting(s, "americano")) or bool(lines_of(s, "americano")),
                answers=False,
            ),
        ],
        True,
    ),
    "hesitation": (
        '"음...", "어..." get no answer; the order after them is heard',
        [
            TO_GO,
            Step("hmm", "음...", "no answer", lambda s: True, quiet=True),
            Step("uh", "어... 잠깐만요", "no answer", lambda s: True, quiet=True),
            Step(
                "order",
                "따뜻한 아메리카노 하나 주세요",
                "the americano",
                lambda s: bool(waiting(s, "americano")) or bool(lines_of(s, "americano")),
                answers=False,
            ),
        ],
        False,
    ),
    "extras-no-pay": (
        '"없어요" to "추가하실 거 있으세요?" does not start paying',
        [
            TO_GO,
            Step(
                "americano",
                "따뜻한 아메리카노 레귤러 하나 주세요",
                "added; no payment, no staff question",
                lambda s: (
                    has_item(s, "americano", "HOT", "Regular")
                    and s["phase"] == "ordering"
                    and s["view"]["screen"] != "review"
                ),
                said=lambda t: "직원" not in t and "주문 확인" not in t,
            ),
        ],
        False,
    ),
    "second-item": (
        "the extras question once per item: not again for a second americano",
        [
            TO_GO,
            HOT_AMERICANO,
            Step(
                "iced",
                "차가운 아메리카노 레귤러도 하나 주세요",
                "added without the extras question",
                lambda s: has_item(s, "americano", "ICE", "Regular"),
                said=lambda t: "추가하실" not in t,
            ),
        ],
        False,
    ),
    "back": (
        '"뒤로" from the size question shows the temperature again, still chosen',
        [
            TO_GO,
            Step(
                "latte",
                "카페라떼 하나 주세요",
                "the temperature question",
                lambda s: s["view"]["group"] == "temperature",
                answers=False,
            ),
            Step(
                "cold",
                "차갑게요",
                "the size question",
                lambda s: s["view"]["group"] == "size",
                answers=False,
            ),
            Step(
                "back",
                "뒤로 가 주세요",
                "the temperature question, 차갑게 kept",
                lambda s: (
                    s["view"]["group"] == "temperature"
                    and (waiting(s, "cafe_latte") or {}).get("chosen", {}).get("temperature")
                    == ["ice"]
                ),
                answers=False,
            ),
        ],
        False,
    ),
    "edit-back": (
        "back to an added latte, then change its size there",
        [
            TO_GO,
            Step(
                "latte",
                "따뜻한 카페라떼 레귤러 하나 주세요",
                "the latte",
                lambda s: has_item(s, "cafe_latte", "HOT", "Regular"),
            ),
            Step(
                "show",
                "아까 라떼 화면 다시 보여 주세요",
                "the latte's options",
                lambda s: s["view"]["screen"] == "item" and s["view"]["item_id"] == "cafe_latte",
                answers=False,
            ),
            Step(
                "large",
                "라지로 바꿔 주세요",
                "the latte is Large",
                lambda s: has_item(s, "cafe_latte", "HOT", "Large"),
                answers=False,
            ),
        ],
        False,
    ),
    "cancel": (
        '"전부 취소" needs a yes',
        [
            TO_GO,
            Step(
                "bread",
                "감자빵 하나 주세요",
                "the potato bread",
                lambda s: has_item(s, "potato_bread"),
            ),
            Step(
                "cancel",
                "주문 전부 취소해 주세요",
                "asked first, nothing cancelled yet",
                lambda s: has_item(s, "potato_bread"),
                answers=False,
            ),
            Step(
                "yes", "네", "the order is empty", lambda s: not s["order"]["lines"], answers=False
            ),
        ],
        False,
    ),
}


class SilentEarpiece:
    """A fake `sounddevice`: the Speaker plays into nothing, driven by `tick` in real time."""

    def __init__(self) -> None:
        self.callback: Callable[..., None] | None = None

    def query_devices(self, device: Any = None, kind: Any = None) -> Any:
        info = {
            "name": "simulated earpiece",
            "max_input_channels": 0,
            "max_output_channels": 1,
            "default_samplerate": 24000,
        }
        return [info] if device is None and kind is None else info

    def RawOutputStream(self, **kw: Any) -> Any:  # noqa: N802 (sounddevice's name)
        self.callback = kw["callback"]

        class Stream:
            def start(self) -> None: ...
            def stop(self) -> None: ...
            def close(self) -> None: ...

        return Stream()


class Demo:
    def __init__(self, args: argparse.Namespace) -> None:
        load_env_file()
        self.config = load_config()
        key = os.environ.get(self.config.live.api_key_env, "").strip()
        if not key:
            raise SystemExit("No API key: start the kiosk once and enter it, or put it in .env.")
        data = self.config.data_dir
        self.kiosk = Kiosk(load_menu(data / "menu.yaml"), load_cafe(data / "cafe.yaml"))
        self.hub = Hub()
        self.events = self.hub.connect()
        self.ignore_unrelated = args.ignore_unrelated
        self.scenarios = args.scenarios
        self.said: list[tuple[float, str]] = []  # what the assistant said, with the time
        self.delays: list[float] = []  # reply delays over all scenarios
        self.controller = KioskController(
            self.kiosk,
            GeminiConnector(self.config.live, key),
            self.config.flow,
            self.hub,
            SimulatedHook(),
            data / "images",
        )
        self.controller.settings = DisplaySettings(Path(tempfile.mkdtemp()) / "display.local.json")
        self.listen = args.listen
        self.fake_sd = None if args.listen else SilentEarpiece()
        self.speaker = Speaker(self.config.audio, self.fake_sd)
        self.shots = Path(args.shots)
        self.state: State = {}
        self.snapshot: State = {}  # the state when a step's `until` came true
        self.heard_at = 0.0  # when the earpiece last played something
        self.reply_at = 0.0  # when the earpiece last started playing (a new reply)
        self.speech: asyncio.Queue[tuple[bytes, asyncio.Future[float]]] = asyncio.Queue()
        self.cdp: Any = None
        self._cdp_id = 0

    # --- the parts -------------------------------------------------------------------------

    async def earpiece(self) -> None:
        while True:
            if self.fake_sd is not None and self.fake_sd.callback is not None:
                block = bytearray(960)
                self.fake_sd.callback(block, 480, None, None)
            playing = self.speaker.playing or self.speaker.level > 0
            if playing:
                if time.monotonic() - self.heard_at > 0.3:
                    self.reply_at = time.monotonic()
                self.heard_at = time.monotonic()
            await asyncio.sleep(0.02)

    async def microphone(self) -> None:
        """20 ms frames in real time: faint noise, or the customer's words."""
        noise = b"".join(
            random.randint(-30, 30).to_bytes(2, "little", signed=True) for _ in range(320)
        )
        pending, done = b"", None
        next_at = time.monotonic()
        while True:
            if not pending and done is None and not self.speech.empty():
                pending, done = self.speech.get_nowait()
            if pending:
                frame, pending = pending[:FRAME], pending[FRAME:]
            else:
                frame = noise
            self.controller.microphone_frame(frame.ljust(FRAME, b"\0"))
            if done is not None and not pending:
                done.set_result(time.monotonic())
                done = None
            next_at += 0.02
            await asyncio.sleep(max(0.0, next_at - time.monotonic()))

    async def watch(self) -> None:
        while True:
            event = await self.events.get()
            if event["type"] == "state":
                self.state = event
            elif event["type"] == "subtitle" and event["final"] and event["text"]:
                who = "손님" if event["speaker"] == "customer" else "키오스크"
                print(f"      {who}: {event['text']}")
                if event["speaker"] == "assistant":
                    self.said.append((time.monotonic(), event["text"]))
            elif event["type"] == "notice" and event["text"]:
                print(f"      (notice: {event['text']})")

    async def say(self, text: str) -> float:
        """Speak `text` into the microphone; returns when the customer stopped talking."""
        done: asyncio.Future[float] = asyncio.get_running_loop().create_future()
        await self.speech.put((synthesize(text), done))
        return await done

    async def wait_reply(self, since: float, step: Step, shot: str = "") -> float | None:
        """Until the assistant answered and the earpiece is quiet; returns the reply delay.

        With `step.until`, that must come true first; the screen is photographed right then
        (the done screen does not stay long), and the assistant must speak again after it."""
        first: float | None = None
        deadline = since + step.timeout_s
        reached = step.until is None
        reached_at = since
        while time.monotonic() < deadline:
            await asyncio.sleep(0.05)
            # A reply that starts after the customer stopped (not the rest of an earlier one).
            if first is None and self.reply_at > since:
                first = self.reply_at
            if not reached:
                reached = bool(self.state) and step.until(self.state)
                if reached:
                    reached_at = time.monotonic()
                    if shot:
                        self.snapshot = dict(self.state)
                        await asyncio.sleep(1.5)  # the display's animation
                        await self.shot(shot)
                continue
            quiet = time.monotonic() - self.heard_at > QUIET_S and not self.speaker.playing
            idle = self.state.get("assistant") in ("listening", "idle")
            if first is not None and self.heard_at > reached_at and quiet and idle:
                return first - since
        return None if first is None else first - since

    # --- screenshots -----------------------------------------------------------------------

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        self._cdp_id += 1
        await self.cdp.send(json.dumps({"id": self._cdp_id, "method": method, "params": params}))
        while True:
            message = json.loads(await self.cdp.recv())
            if message.get("id") == self._cdp_id:
                return message.get("result", {})

    async def shot(self, name: str) -> None:
        data = await self.call("Page.captureScreenshot", format="jpeg", quality=88)
        (self.shots / f"{name}.jpg").write_bytes(base64.b64decode(data["data"]))

    # --- the run ---------------------------------------------------------------------------

    async def run(self) -> bool:
        dist = REPO_ROOT / "frontend" / "dist"
        if not (dist / "index.html").exists():
            raise SystemExit("Build the display first: npm --prefix frontend run build")
        self.shots.mkdir(parents=True, exist_ok=True)
        self.speaker.open()
        self.controller.audio_out = self.speaker.write
        self.controller.audio_stop = self.speaker.clear
        port = free_port()
        app = create_app(self.controller, dist, self.config.data_dir / "images")
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
        serving = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.05)
        tasks = [asyncio.create_task(c()) for c in (self.earpiece, self.microphone, self.watch)]
        edge = open_edge()
        try:
            async with websockets.connect(devtools_page(), max_size=50_000_000) as self.cdp:
                await self.call(
                    "Emulation.setDeviceMetricsOverride",
                    width=1080,
                    height=1920,
                    deviceScaleFactor=1,
                    mobile=False,
                )
                await self.call("Page.navigate", url=f"http://127.0.0.1:{port}/?cursor")
                await asyncio.sleep(2.5)
                await self.shot("00-start")
                return await self.run_scenarios()
        finally:
            for task in tasks:
                task.cancel()
            await self.controller.hang_up()
            edge.terminate()
            server.should_exit = True
            await serving
            self.speaker.close()

    async def run_scenarios(self) -> bool:
        summary = []
        for name in self.scenarios:
            title, steps, ignore = SCENARIOS[name]
            if name == "order" and self.ignore_unrelated:  # chatter in the whole order
                steps, ignore = [*steps[:2], CHATTER[0], *steps[2:5], CHATTER[1], *steps[5:]], True
            self.controller.settings.update({"ignoreUnrelated": ignore})
            print(f"\n=== {name}: {title}")
            ok = await self.conversation(steps, name)
            summary.append((name, ok, title))
            await self.controller.hang_up()
            await asyncio.sleep(1.5)
        self.report_speech()
        if len(summary) > 1:
            print("\n=== scenarios")
            for name, ok, title in summary:
                print(f"  {'PASS' if ok else 'FAIL'}  {name:14} {title}")
            print(f"  {sum(ok for _, ok, _ in summary)}/{len(summary)} scenarios passed")
        return all(ok for _, ok, _ in summary)

    def report_speech(self) -> None:
        """Team feedback checks over everything the assistant said."""
        lines = [t for _, t in self.said]
        if not lines:
            return
        bad = [t for t in lines if any(w in t for w in FORBIDDEN_WORDS)]
        sentences = [len(t) for t in lines]
        print("\n=== how the assistant spoke")
        print(f"  {len(lines)} turns, {sum(sentences) / len(sentences):.0f} characters on average")
        print(f"  아이스/핫/HOT/ICE said: {len(bad)}" + "".join(f"\n    {t}" for t in bad))
        if self.delays:
            delays = sorted(self.delays)
            print(f"  reply after the customer stopped: median {seconds(delays[len(delays) // 2])}")

    async def conversation(self, steps: list[Step], prefix: str = "") -> bool:
        print("  handset lifted")
        lifted = time.monotonic()
        await self.controller.handset(True)
        greeting = Step("greeting", "", "", lambda s: True)
        delay = await self.wait_reply(lifted, greeting)
        print(f"      greeting after {seconds(delay)}")
        await self.shot(f"{prefix}-01-greeting")
        results = []
        for n, step in enumerate(steps, start=2):
            print(f"\n  > {step.say}")
            began = time.monotonic()
            stopped = await self.say(step.say)
            name = f"{prefix}-{n:02d}-{step.name}"
            if step.quiet:
                await asyncio.sleep(QUIET_WAIT_S)
                ok = self.heard_at <= stopped
                results.append((step, ok, None))
                print(f"    {'PASS' if ok else 'FAIL'}  {step.expect}")
                continue
            self.snapshot = {}
            delay = await self.wait_reply(stopped, step, name)
            for _ in range(MAX_ANSWERS if step.until is None and step.answers else 0):
                answer = follow_up(self.state)
                if answer is None:
                    break
                print(f"    > (answering the screen's question) {answer}")
                await self.wait_reply(await self.say(answer), step)
            state = self.snapshot or self.state
            said = " ".join(t for at, t in self.said if at > began)
            ok = bool(state) and step.check(state) and (step.said is None or step.said(said))
            results.append((step, ok, delay))
            if delay is not None:
                self.delays.append(delay)
            print(f"    {'PASS' if ok else 'FAIL'}  {step.expect}  (reply after {seconds(delay)})")
            if not self.snapshot:
                await self.shot(name)
        print(
            "\n  order:",
            [
                f"{line['name']} {line['options']} x{line['quantity']}"
                for line in state["order"]["lines"]
            ],
        )
        passed = sum(ok for _, ok, _ in results)
        delays = sorted(d for _, _, d in results if d is not None)
        print(f"\n  {passed}/{len(results)} steps passed", end="")
        if delays:
            print(f"; median reply after {seconds(delays[len(delays) // 2])}")
        print(f"  screenshots: {self.shots}")
        return passed == len(results)


def seconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} s"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_edge() -> subprocess.Popen[bytes]:
    if not EDGE.exists():
        raise SystemExit(f"Microsoft Edge not found at {EDGE}")
    return subprocess.Popen(
        [
            str(EDGE),
            "--headless=new",
            f"--remote-debugging-port={DEVTOOLS_PORT}",
            f"--user-data-dir={tempfile.mkdtemp()}",
            "--window-size=1080,1920",
            "--hide-scrollbars",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def devtools_page() -> str:
    for _ in range(50):
        with contextlib.suppress(OSError, StopIteration):
            pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{DEVTOOLS_PORT}/json"))
            return next(p for p in pages if p["type"] == "page")["webSocketDebuggerUrl"]
        time.sleep(0.2)
    raise SystemExit("Edge did not start")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--listen", action="store_true", help="play the assistant on the speakers")
    parser.add_argument("--shots", default=str(REPO_ROOT / "recordings" / "voice_demo"))
    parser.add_argument(
        "--scenario",
        default="order",
        help="'order' (default), names separated by commas, 'all' or 'list'",
    )
    parser.add_argument(
        "--ignore-unrelated",
        action="store_true",
        help="switch on 'ignore speech not meant for the kiosk' and add chatter to ignore",
    )
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.scenario == "list":
        for name, (title, steps, _) in SCENARIOS.items():
            print(f"  {name:14} {title} ({len(steps)} steps)")
        return 0
    args.scenarios = list(SCENARIOS) if args.scenario == "all" else args.scenario.split(",")
    unknown = [s for s in args.scenarios if s not in SCENARIOS]
    if unknown:
        raise SystemExit(f"unknown scenario(s): {', '.join(unknown)} (--scenario list)")
    log_file = REPO_ROOT / "logs" / "voice_demo.log"  # every function call, for failed steps
    log_file.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, mode="w", encoding="utf-8")],
    )
    for noisy in ("httpx", "websockets", "google_genai", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    print(f"  log: {log_file}")
    return 0 if asyncio.run(Demo(args).run()) else 1


if __name__ == "__main__":
    sys.exit(main())
