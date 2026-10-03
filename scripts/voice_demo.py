"""End-to-end voice check before a demo: a whole order, spoken, through the real kiosk.

Synthesized Korean speech (the Windows voice "Heami") goes into the kiosk's microphone input;
the real Gemini Live API answers; the earpiece is simulated in real time (or played on the
speakers with --listen). The display runs in a hidden Edge window and is photographed after each
step. Each step prints PASS/FAIL and how long the reply took.

    uv run python scripts/voice_demo.py                  # screenshots to recordings/voice_demo/
    uv run python scripts/voice_demo.py --listen         # hear the assistant on the speakers
    uv run python scripts/voice_demo.py --shots docs/screenshots

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


def has_item(state: State, item_id: str, *options: str) -> bool:
    return any(
        line["item_id"] == item_id and all(o in line["options"] for o in options)
        for line in state["order"]["lines"]
    )


STEPS = [
    Step(
        "menu",
        "메뉴 뭐 있어요?",
        "recommended items on screen",
        lambda s: s["view"]["screen"] == "menu" and 3 <= len(s["view"]["item_ids"]) <= 5,
    ),
    Step(
        "americano",
        "아이스 아메리카노 라지로 한 잔 주세요",
        "ICE Large americano in the order",
        lambda s: has_item(s, "americano", "ICE", "Large"),
    ),
    Step(
        "latte",
        "따뜻한 카페라떼도 하나 주세요. 레귤러로요",
        "a hot regular latte in the order",
        lambda s: has_item(s, "cafe_latte", "HOT"),
    ),
    Step(
        "question",
        "화장실은 어디에 있어요?",
        "the restroom card",
        lambda s: s["view"]["screen"] == "info" and s["view"]["topic"] == "restroom",
    ),
    Step(
        "pay",
        "이제 결제할게요",
        "asks for dining (or reads back)",
        lambda s: s["order"]["count"] >= 2,
    ),
    Step(
        "to-go",
        "포장이요",
        "read-back, card terminal, order number",
        lambda s: s["phase"] == "done" and s["payment"]["order_number"] is not None,
        until=lambda s: s["phase"] == "done",
        timeout_s=60.0,
    ),
]


# When the assistant asks for a missing option (e.g. the first word was not heard), the customer
# answers like a person would.
ANSWERS = {"temperature": "따뜻한 걸로요", "size": "레귤러요"}
MAX_ANSWERS = 2
# The customer talks after this much silence (a reply after a function call can come 1-2 s
# after a first short sentence).
QUIET_S = 2.5


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
        self.controller = KioskController(
            self.kiosk,
            GeminiConnector(self.config.live, key),
            self.config.flow,
            self.hub,
            SimulatedHook(),
            data / "images",
        )
        self.listen = args.listen
        self.fake_sd = None if args.listen else SilentEarpiece()
        self.speaker = Speaker(self.config.audio, self.fake_sd)
        self.shots = Path(args.shots)
        self.state: State = {}
        self.snapshot: State = {}  # the state when a step's `until` came true
        self.heard_at = 0.0  # when the earpiece last played something
        self.speech: asyncio.Queue[tuple[bytes, asyncio.Future[float]]] = asyncio.Queue()
        self.cdp: Any = None
        self._cdp_id = 0

    # --- the parts -------------------------------------------------------------------------

    async def earpiece(self) -> None:
        while True:
            if self.fake_sd is not None and self.fake_sd.callback is not None:
                block = bytearray(960)
                self.fake_sd.callback(block, 480, None, None)
            if self.speaker.playing or self.speaker.level > 0:
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
            if first is None and self.heard_at > since:
                first = self.heard_at
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
                return await self.conversation()
        finally:
            for task in tasks:
                task.cancel()
            await self.controller.hang_up()
            edge.terminate()
            server.should_exit = True
            await serving
            self.speaker.close()

    async def conversation(self) -> bool:
        print("  handset lifted")
        lifted = time.monotonic()
        await self.controller.handset(True)
        greeting = Step("greeting", "", "", lambda s: True)
        delay = await self.wait_reply(lifted, greeting)
        print(f"      greeting after {seconds(delay)}")
        await self.shot("01-greeting")
        results = []
        for n, step in enumerate(STEPS, start=2):
            print(f"\n  > {step.say}")
            stopped = await self.say(step.say)
            name = f"{n:02d}-{step.name}"
            self.snapshot = {}
            delay = await self.wait_reply(stopped, step, name)
            for _ in range(MAX_ANSWERS if step.until is None else 0):
                missing = (self.state.get("pending") or {}).get("missing") or []
                if not missing or missing[0] not in ANSWERS:
                    break
                print(f"    > (asked for {missing[0]}) {ANSWERS[missing[0]]}")
                await self.wait_reply(await self.say(ANSWERS[missing[0]]), step)
            state = self.snapshot or self.state
            ok = bool(state) and step.check(state)
            results.append((step, ok, delay))
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
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
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
