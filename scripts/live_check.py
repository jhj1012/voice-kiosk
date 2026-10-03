"""Milestone 3: check the Gemini Live API before building on it.

Talks to the real API (needs GEMINI_API_KEY in .env). Function calls run on the kiosk directly,
without the session's safety checks (milestone 4), to see what the model does by itself. Each
mode prints a report; details go to logs/live_check/ and the assistant's audio to
recordings/live_check/ (both git-ignored).

    uv run python scripts/live_check.py text      # typed scenarios: function calls + latency
    uv run python scripts/live_check.py audio     # synthesized Korean speech: recognition + latency
    uv run python scripts/live_check.py bargein   # interrupt a long answer
    uv run python scripts/live_check.py limits    # concurrent sessions, session resumption
    uv run python scripts/live_check.py voices    # the same sentence in several voices (listen)
    uv run python scripts/live_check.py mic       # talk yourself: mic in, speaker out

Speech for `audio` and `bargein` is synthesized with the Windows Korean voice (Heami), so those
modes run without a person; `mic` is for judging real recognition, voice and barge-in by ear.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import difflib
import json
import os
import queue
import random
import re
import subprocess
import sys
import time
import wave
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from kiosk.assistant.actions import Actions
from kiosk.assistant.instructions import GREETING_CUE, instructions
from kiosk.assistant.safety import said_amount
from kiosk.assistant.tools import function_declarations
from kiosk.config import REPO_ROOT, load_config, load_env_file
from kiosk.domain.flow import Kiosk, Phase
from kiosk.domain.loader import load_cafe, load_menu

IN_RATE = 16000
OUT_RATE = 24000
CHUNK_MS = 20
LOG_DIR = REPO_ROOT / "logs" / "live_check"
AUDIO_DIR = REPO_ROOT / "recordings" / "live_check"
TTS_DIR = REPO_ROOT / "recordings" / "tts"
QUIET_AFTER_S = 1.2  # a turn is over when the model completed and nothing came for this long
REPLY_AFTER_CALL_S = 6.0  # ...or this long if a function call has had no spoken reply yet


# --- setup -------------------------------------------------------------------------------------


@dataclass
class Setup:
    client: genai.Client
    model: str
    voice: str
    language: str
    text_via: str  # "realtime" or "client"
    vad: dict[str, Any] = field(default_factory=dict)  # automatic_activity_detection settings
    hints: bool = True  # transcription: Korean + menu vocabulary
    thinking: str = ""  # thinking level for models that need one (extended thinking)


def make_kiosk() -> Kiosk:
    data = load_config().data_dir
    kiosk = Kiosk(load_menu(data / "menu.yaml"), load_cafe(data / "cafe.yaml"))
    kiosk.start_session()
    return kiosk


def live_config(
    kiosk: Kiosk, setup: Setup, *, system: str | None = None, tools: bool = True, **extra: Any
) -> types.LiveConnectConfig:
    speech: dict[str, Any] = {}
    if setup.voice:
        speech["voice_config"] = {"prebuilt_voice_config": {"voice_name": setup.voice}}
    if setup.language:
        speech["language_code"] = setup.language
    config: dict[str, Any] = {
        "response_modalities": ["AUDIO"],
        "system_instruction": system or instructions(kiosk.menu, kiosk.cafe),
        "input_audio_transcription": transcription_config(kiosk) if setup.hints else {},
        "output_audio_transcription": {},
        **extra,
    }
    if speech:
        config["speech_config"] = speech
    if setup.thinking:
        config["thinking_config"] = {"thinking_level": setup.thinking.upper()}
    if setup.vad:
        config["realtime_input_config"] = {"automatic_activity_detection": setup.vad}
    if tools:
        config["tools"] = [{"function_declarations": function_declarations(kiosk.menu, kiosk.cafe)}]
    return types.LiveConnectConfig.model_validate(config)


def transcription_config(kiosk: Kiosk) -> dict[str, Any]:
    """Korean, biased towards the names on the menu (they are unusual words)."""
    menu = kiosk.menu
    words = [i.name for i in menu.items] + [c.name for c in menu.categories]
    words += [c.spoken for g in menu.option_groups for c in g.choices if not c.is_none]
    return {"language_codes": ["ko-KR"], "custom_vocabulary": sorted(set(words))}


# --- one session -------------------------------------------------------------------------------


@dataclass
class Turn:
    label: str
    started: float  # input began (text sent, or first speech chunk)
    input_end: float  # end of the customer's input (text sent, or last speech chunk)
    first_audio: float | None = None
    first_tool: float | None = None
    complete: float | None = None
    interrupted: float | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    heard: str = ""  # input transcription
    said: str = ""  # output transcription
    audio_s: float = 0.0
    events: list[str] = field(default_factory=list)  # order of transcripts and tool calls

    def ms(self, t: float | None) -> int | None:
        return None if t is None else round((t - self.input_end) * 1000)


class Probe:
    """Receives everything from a session, runs function calls on the kiosk, times turns."""

    def __init__(self, session: Any, kiosk: Kiosk, audio_name: str = "") -> None:
        self.session = session
        self.kiosk = kiosk
        self.actions = Actions(kiosk)
        self.turns: list[Turn] = []
        self.audio = bytearray()
        self.audio_name = audio_name
        self.last_event = time.monotonic()
        self.play_end = 0.0  # when the audio received so far would finish playing in real time
        self.resumption_handle: str | None = None
        self.go_away: str | None = None
        self.tokens = 0
        self.on_audio: Callable[[bytes], None] | None = None
        self.on_interrupted: Callable[[], None] | None = None
        # mic mode: turns start by themselves; latency is measured from `last_speech()`
        self.auto_turns = False
        self.last_speech: Callable[[], float] | None = None
        self.on_turn_complete: Callable[[Turn], None] | None = None
        self._task: asyncio.Task[None] | None = None
        self.error: BaseException | None = None

    @property
    def turn(self) -> Turn | None:
        return self.turns[-1] if self.turns else None

    def start(self) -> None:
        self._task = asyncio.create_task(self._receive())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        if self.audio and self.audio_name:
            save_wav(AUDIO_DIR / f"{self.audio_name}.wav", bytes(self.audio), OUT_RATE)

    def begin(self, label: str, started: float | None = None) -> Turn:
        now = time.monotonic()
        turn = Turn(label=label, started=started or now, input_end=now)
        self.turns.append(turn)
        return turn

    async def send_text(self, text: str, via: str) -> Turn:
        turn = self.begin(text)
        if via == "client":
            await self.session.send_client_content(
                turns={"role": "user", "parts": [{"text": text}]}, turn_complete=True
            )
        else:
            await self.session.send_realtime_input(text=text)
        turn.input_end = time.monotonic()
        return turn

    async def wait_idle(self, timeout_s: float = 30.0) -> None:
        """Until the current turn completed and nothing else arrived for a moment."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            await asyncio.sleep(0.1)
            if self.error is not None:
                raise RuntimeError(f"session ended: {self.error}")
            turn = self.turn
            now = time.monotonic()
            done = turn is None or turn.complete is not None
            # A customer answers after HEARING the reply: wait for the simulated playback too.
            # After a function call the spoken reply can come seconds later, as its own turn.
            quiet_s = QUIET_AFTER_S
            if turn is not None and _call_without_reply(turn):
                quiet_s = REPLY_AFTER_CALL_S
            if done and now - self.last_event > quiet_s and now > self.play_end + 0.3:
                return
        if self.turn is not None:
            self.turn.events.append("TIMEOUT")

    async def _receive(self) -> None:
        try:
            while True:
                async for message in self.session.receive():
                    await self._handle(message)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # connection closed, quota, ...
            self.error = e

    async def _handle(self, message: types.LiveServerMessage) -> None:
        now = time.monotonic()
        self.last_event = now
        turn = self.turn
        if message.usage_metadata is not None:
            self.tokens = message.usage_metadata.total_token_count or self.tokens
        if message.session_resumption_update is not None:
            update = message.session_resumption_update
            if update.resumable and update.new_handle:
                self.resumption_handle = update.new_handle
        if message.go_away is not None:
            self.go_away = str(message.go_away.time_left)
        content = message.server_content
        new_turn = turn is None or turn.complete is not None
        if self.auto_turns and new_turn and (message.tool_call or content is not None):
            turn = self.begin("(speech)")
        if message.tool_call is not None:
            await self._tool_call(message.tool_call, turn, now)
        if content is None or turn is None:
            return
        if content.input_transcription is not None and content.input_transcription.text:
            turn.heard += content.input_transcription.text
            turn.events.append("heard")
        if content.output_transcription is not None and content.output_transcription.text:
            turn.said += content.output_transcription.text
        if content.model_turn is not None:
            for part in content.model_turn.parts or []:
                if part.inline_data is not None and part.inline_data.data:
                    data = part.inline_data.data
                    if turn.first_audio is None:
                        turn.first_audio = now
                        turn.events.append("audio")
                        if self.last_speech is not None and self.last_speech() > turn.started - 30:
                            turn.input_end = self.last_speech()  # the customer's last loud frame
                    turn.audio_s += len(data) / 2 / OUT_RATE
                    self.play_end = max(self.play_end, now) + len(data) / 2 / OUT_RATE
                    self.audio.extend(data)
                    if self.on_audio is not None:
                        self.on_audio(data)
        if content.interrupted:
            turn.interrupted = turn.interrupted or now
            self.play_end = now  # the client stops playback
            turn.events.append("interrupted")
            if self.on_interrupted is not None:
                self.on_interrupted()
        if content.turn_complete:
            turn.complete = now
            turn.events.append("complete")
            if self.on_turn_complete is not None:
                self.on_turn_complete(turn)

    async def _tool_call(self, tool_call: types.LiveServerToolCall, turn: Turn | None, now: float):
        responses = []
        for call in tool_call.function_calls or []:
            args = dict(call.args or {})
            result = self.actions.call(call.name or "", args)
            if turn is not None:
                turn.first_tool = turn.first_tool or now
                turn.calls.append({"name": call.name, "args": args, "result": result})
                turn.events.append(f"call:{call.name}")
            responses.append(types.FunctionResponse(id=call.id, name=call.name, response=result))
        await self.session.send_tool_response(function_responses=responses)


def _call_without_reply(turn: Turn) -> bool:
    calls = [i for i, e in enumerate(turn.events) if e.startswith("call:")]
    return bool(calls) and "audio" not in turn.events[calls[-1] :]


@contextlib.asynccontextmanager
async def open_probe(setup: Setup, kiosk: Kiosk, name: str, **config: Any):
    async with setup.client.aio.live.connect(
        model=setup.model, config=live_config(kiosk, setup, **config)
    ) as session:
        probe = Probe(session, kiosk, audio_name=name)
        probe.start()
        try:
            yield probe
        finally:
            await probe.stop()


# --- audio helpers -----------------------------------------------------------------------------


def save_wav(path: Path, pcm: bytes, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def synthesize(text: str) -> bytes:
    """16 kHz mono PCM of `text` spoken by the Windows Korean voice (cached)."""
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^0-9A-Za-z가-힣]+", "_", text).strip("_")[:60]
    wav_path = TTS_DIR / f"{key}.wav"
    if not wav_path.exists():
        txt_path = TTS_DIR / f"{key}.txt"
        txt_path.write_text(text, encoding="utf-8")
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$s.SelectVoice('Microsoft Heami Desktop');"
            "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,"
            " [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,"
            " [System.Speech.AudioFormat.AudioChannel]::Mono);"
            f"$s.SetOutputToWaveFile('{wav_path}', $f);"
            f"$s.Speak((Get-Content -Raw -Encoding UTF8 '{txt_path}'));"
            "$s.Dispose()"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    with wave.open(str(wav_path), "rb") as w:
        return w.readframes(w.getnframes())


def quiet_chunk() -> bytes:
    """20 ms of faint noise (a real open mic is never exactly zero)."""
    samples = [random.randint(-30, 30) for _ in range(IN_RATE * CHUNK_MS // 1000)]
    return b"".join(s.to_bytes(2, "little", signed=True) for s in samples)


class OpenMic:
    """Streams quiet audio in real time, like an open microphone; `say` injects speech."""

    def __init__(self, session: Any) -> None:
        self.session = session
        self._speech: asyncio.Queue[tuple[bytes, asyncio.Future[tuple[float, float]]]] = (
            asyncio.Queue()
        )
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def say(self, pcm: bytes) -> tuple[float, float]:
        """Speak `pcm`; returns (start, end) times of the speech."""
        done: asyncio.Future[tuple[float, float]] = asyncio.get_running_loop().create_future()
        await self._speech.put((pcm, done))
        return await done

    async def _run(self) -> None:
        chunk_bytes = IN_RATE * CHUNK_MS // 1000 * 2
        next_at = time.monotonic()
        quiet = quiet_chunk()
        pending: list[bytes] = []
        done: asyncio.Future[tuple[float, float]] | None = None
        started = 0.0
        while True:
            if not pending and done is None and not self._speech.empty():
                pcm, done = self._speech.get_nowait()
                pending = [pcm[i : i + chunk_bytes] for i in range(0, len(pcm), chunk_bytes)]
                started = time.monotonic()
            chunk = pending.pop(0) if pending else quiet
            await self.session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={IN_RATE}")
            )
            if done is not None and not pending:
                done.set_result((started, time.monotonic()))
                done = None
            next_at += CHUNK_MS / 1000
            await asyncio.sleep(max(0.0, next_at - time.monotonic()))


# --- reporting ---------------------------------------------------------------------------------


@dataclass
class Check:
    turn: str
    expectation: str
    ok: bool


def calls_named(turn: Turn, name: str) -> list[dict[str, Any]]:
    return [c for c in turn.calls if c["name"] == name]


def has_call(turn: Turn, name: str, **args: Any) -> bool:
    return any(all(c["args"].get(k) == v for k, v in args.items()) for c in calls_named(turn, name))


def print_turns(title: str, turns: list[Turn]) -> None:
    print(f"\n=== {title}")
    for t in turns:
        calls = ", ".join(f"{c['name']}({_short(c['args'])})" for c in t.calls) or "-"
        print(
            f"- {t.label}\n    heard: {t.heard.strip() or '-'}\n"
            f"    said:  {t.said.strip() or '-'}\n"
            f"    calls: {calls}\n    first audio {t.ms(t.first_audio)} ms, first call "
            f"{t.ms(t.first_tool)} ms, audio {t.audio_s:.1f} s, events {' '.join(t.events)}"
        )


def _short(args: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in args.items())


def write_log(name: str, data: Any) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path


def median(values: list[float]) -> float | None:
    values = sorted(values)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


# --- mode: text --------------------------------------------------------------------------------

Expect = Callable[[Turn, Kiosk], bool]


def paid(turn: Turn) -> bool:
    """request_payment ran and returned the read-back (the session would start the terminal)."""
    return any("read_back" in c["result"] for c in calls_named(turn, "request_payment"))


def no_calls(*names: str) -> Expect:
    return lambda t, k: not any(calls_named(t, n) for n in names)


SCENARIOS: dict[str, list[tuple[str, dict[str, Expect]]]] = {
    "order_and_pay": [
        (GREETING_CUE, {"greets without acting": lambda t, k: not t.calls and bool(t.said)}),
        (
            "아이스 아메리카노 라지로 두 잔 주세요",
            {
                "choose_item americano x2 ice large": lambda t, k: has_call(
                    t,
                    "choose_item",
                    item_id="americano",
                    quantity=2,
                    temperature="ice",
                    size="large",
                ),
                "order has 2 americanos": lambda t, k: (
                    k.order.lines[0].quantity == 2 if k.order.lines else False
                ),
            },
        ),
        (
            "초코 쿠키도 하나 주세요",
            {
                "choose_item cookie": lambda t, k: has_call(
                    t, "choose_item", item_id="chocolate_cookie"
                )
            },
        ),
        (
            "이제 결제할게요",
            {
                "asks dine-in/take-out first (no payment yet)": lambda t, k: (
                    k.phase is Phase.ORDERING and not paid(t)
                )
            },
        ),
        (
            "포장이요",
            {
                "set_dining to_go": lambda t, k: has_call(t, "set_dining", dining="to_go"),
                "request_payment": lambda t, k: paid(t),
                "says the read-back total": lambda t, k: said_amount(t.said, k.order.total),
            },
        ),
    ],
    "required_options": [
        (
            "카페라떼 하나 주세요",
            {
                "choose_item latte without guessing": lambda t, k: (
                    has_call(t, "choose_item", item_id="cafe_latte")
                    and not any("temperature" in c["args"] or "size" in c["args"] for c in t.calls)
                ),
                "nothing added yet": lambda t, k: k.order.is_empty,
            },
        ),
        (
            "따뜻한 걸로요",
            {"set_options hot": lambda t, k: has_call(t, "set_options", temperature="hot")},
        ),
        (
            "레귤러요",
            {
                "set_options regular": lambda t, k: has_call(t, "set_options", size="regular"),
                "latte added": lambda t, k: len(k.order.lines) == 1,
            },
        ),
    ],
    "questions": [
        (
            "메뉴 뭐 있어요?",
            {
                "show_menu": lambda t, k: bool(calls_named(t, "show_menu")),
                "nothing ordered": no_calls("choose_item"),
            },
        ),
        (
            "우유 알레르기가 있는데 마실 만한 거 있어요?",
            {
                "show_menu excluding milk": lambda t, k: any(
                    "milk" in (c["args"].get("exclude_allergens") or [])
                    or (
                        c["args"].get("item_ids")
                        and not {"cafe_latte", "cafe_mocha", "flat_white"}
                        & set(c["args"]["item_ids"])
                    )
                    for c in calls_named(t, "show_menu")
                ),
            },
        ),
        (
            "아메리카노 디카페인 돼요?",
            {
                "answers yes (decaf option)": lambda t, k: "돼" in t.said or "가능" in t.said,
                "nothing ordered": no_calls("choose_item", "set_options"),
            },
        ),
        (
            "화장실 어디예요?",
            {"show_info restroom": lambda t, k: has_call(t, "show_info", topic="restroom")},
        ),
        (
            "카페라떼 칼로리는 얼마나 돼요?",
            {
                "does not invent a number": lambda t, k: (
                    not re.search(r"\d+\s*(kcal|칼로리|킬로)", t.said)
                ),
            },
        ),
    ],
    "change_and_cancel": [
        (
            "따뜻한 아메리카노 레귤러 하나랑 청포도 에이드 라지 하나 주세요",
            {"two lines": lambda t, k: len(k.order.lines) == 2},
        ),
        ("아메리카노에 샷 추가해 주세요", {"shot added": lambda t, k: has_call(t, "change_line")}),
        (
            "아메리카노는 빼 주세요",
            {
                "americano removed": lambda t, k: (
                    [line.item.id for line in k.order.lines] == ["green_grape_ade"]
                )
            },
        ),
        (
            "그냥 다 취소해 주세요",
            {"asks to confirm, does not cancel": lambda t, k: not k.order.is_empty},
        ),
        ("네", {"cancelled after yes": lambda t, k: k.order.is_empty}),
    ],
}


async def mode_text(setup: Setup, runs: int) -> dict[str, Any]:
    checks: list[Check] = []
    all_turns: list[Turn] = []
    for run in range(runs):
        for name, steps in SCENARIOS.items():
            kiosk = make_kiosk()
            async with open_probe(setup, kiosk, f"text-{name}-{run}") as probe:
                for text, expectations in steps:
                    turn = await probe.send_text(text, setup.text_via)
                    await probe.wait_idle()
                    for label, expect in expectations.items():
                        try:
                            ok = bool(expect(turn, kiosk))
                        except Exception:
                            ok = False
                        checks.append(Check(f"{name}: {text}", label, ok))
                print_turns(f"{name} (run {run + 1})", probe.turns)
                all_turns += probe.turns
    passed = sum(c.ok for c in checks)
    print(f"\n=== text: {passed}/{len(checks)} expectations met")
    for c in checks:
        if not c.ok:
            print(f"  FAILED  {c.turn}  ->  {c.expectation}")
    report = {
        "passed": passed,
        "total": len(checks),
        "failed": [asdict(c) for c in checks if not c.ok],
        "median_first_audio_ms": median([t.ms(t.first_audio) for t in all_turns if t.first_audio]),
        "median_first_call_ms": median([t.ms(t.first_tool) for t in all_turns if t.first_tool]),
        "turns": [asdict(t) for t in all_turns],
    }
    print(
        f"median send -> first audio {report['median_first_audio_ms']} ms, "
        f"-> first function call {report['median_first_call_ms']} ms"
    )
    return report


# --- mode: audio -------------------------------------------------------------------------------

PHRASES = [
    "아이스 아메리카노 라지로 두 잔 주세요",
    "카페라떼 따뜻한 걸로 하나 주세요",
    "레귤러요",
    "할메가커피도 하나 주세요",
    "청포도 에이드는 많이 달아요?",
    "우유 알레르기가 있어요",
    "화장실 어디예요?",
    "포장이요",
    "결제할게요",
]


def similarity(a: str, b: str) -> float:
    def norm(s: str) -> str:
        return re.sub(r"[^0-9A-Za-z가-힣]", "", s)

    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


async def mode_audio(setup: Setup) -> dict[str, Any]:
    kiosk = make_kiosk()
    rows = []
    async with open_probe(setup, kiosk, "audio") as probe:
        mic = OpenMic(probe.session)
        mic.start()
        try:
            for phrase in PHRASES:
                pcm = synthesize(phrase)
                turn = probe.begin(phrase)
                start, end = await mic.say(pcm)
                turn.started, turn.input_end = start, end
                await probe.wait_idle()
                rows.append(
                    {
                        "phrase": phrase,
                        "heard": turn.heard.strip(),
                        "similarity": round(similarity(phrase, turn.heard), 2),
                        "end_of_speech_to_audio_ms": turn.ms(turn.first_audio),
                        "end_of_speech_to_call_ms": turn.ms(turn.first_tool),
                        "heard_before_call": _heard_before_call(turn),
                        "calls": [f"{c['name']}({_short(c['args'])})" for c in turn.calls],
                    }
                )
        finally:
            await mic.stop()
        print_turns("audio (synthesized speech)", probe.turns)
    print("\n=== audio: recognition and latency")
    for r in rows:
        print(
            f"  {r['similarity']:.2f}  {r['end_of_speech_to_audio_ms']} ms  "
            f"heard-before-call={r['heard_before_call']}  {r['phrase']} -> {r['heard']}"
        )
    latencies = [r["end_of_speech_to_audio_ms"] for r in rows if r["end_of_speech_to_audio_ms"]]
    print(f"median end of speech -> first audio: {median(latencies)} ms")
    return {
        "rows": rows,
        "median_latency_ms": median(latencies),
        "turns": [asdict(t) for t in probe.turns],
    }


def _heard_before_call(turn: Turn) -> bool | None:
    """Did the transcription of the customer's words arrive before the first function call?"""
    calls = [i for i, e in enumerate(turn.events) if e.startswith("call:")]
    if not calls:
        return None
    return "heard" in turn.events[: calls[0]]


# --- mode: bargein -----------------------------------------------------------------------------


async def mode_bargein(setup: Setup, runs: int, after_s: float) -> dict[str, Any]:
    rows = []
    interrupt = synthesize("잠깐만요, 아이스 아메리카노 한 잔 주세요")
    all_turns: list[Turn] = []
    for run in range(runs):
        kiosk = make_kiosk()
        async with open_probe(setup, kiosk, f"bargein-{run}") as probe:
            mic = OpenMic(probe.session)
            mic.start()
            try:
                long_turn = await probe.send_text(
                    "메뉴에 있는 음료를 하나씩 전부 자세히 설명해 주세요", setup.text_via
                )
                while long_turn.first_audio is None and time.monotonic() - long_turn.input_end < 20:
                    await asyncio.sleep(0.05)
                # The customer has heard `after_s` of the answer when they start talking.
                await asyncio.sleep(after_s)
                received_s = long_turn.audio_s
                generation_done = long_turn.complete is not None
                overlap = probe.begin("customer talks over the answer")
                start, end = await mic.say(interrupt)
                follow = probe.begin("reply to the interruption", started=start)
                follow.input_end = end
                await probe.wait_idle()
                interrupted = long_turn.interrupted or overlap.interrupted or follow.interrupted
                rows.append(
                    {
                        "audio_received_when_speaking_s": round(received_s, 1),
                        "audio_played_s": after_s,
                        "generation_done_before_speaking": generation_done,
                        "interrupted_ms_after_speech_start": None
                        if interrupted is None
                        else round((interrupted - start) * 1000),
                        "heard": (overlap.heard + follow.heard).strip(),
                        "reply_first_audio_ms": follow.ms(follow.first_audio),
                        "calls": [f"{c['name']}({_short(c['args'])})" for c in follow.calls],
                        "said": follow.said.strip(),
                    }
                )
            finally:
                await mic.stop()
            print_turns(f"bargein (run {run + 1})", probe.turns)
            all_turns += probe.turns
    print("\n=== barge-in")
    for r in rows:
        print(f"  {r}")
    return {"rows": rows, "turns": [asdict(t) for t in all_turns]}


# --- mode: limits ------------------------------------------------------------------------------


async def mode_limits(setup: Setup, max_sessions: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    # Concurrent sessions: open them one by one and keep them open.
    async with contextlib.AsyncExitStack() as stack:
        opened = 0
        error = None
        for _ in range(max_sessions):
            try:
                await stack.enter_async_context(
                    setup.client.aio.live.connect(
                        model=setup.model, config=live_config(make_kiosk(), setup)
                    )
                )
                opened += 1
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                break
        result["concurrent_sessions_opened"] = opened
        result["concurrent_error"] = error
    print(f"concurrent sessions opened: {opened} of {max_sessions} ({error or 'no error'})")

    # Session resumption + context window compression.
    kiosk = make_kiosk()
    extra = {
        "session_resumption": {},
        "context_window_compression": {"sliding_window": {}},
    }
    async with open_probe(setup, kiosk, "resume-1", **extra) as probe:
        await probe.send_text("아이스 아메리카노 레귤러 한 잔 주세요", setup.text_via)
        await probe.wait_idle()
        handle = probe.resumption_handle
        result["tokens_after_one_order"] = probe.tokens
    result["resumption_handle_received"] = bool(handle)
    if handle:
        extra["session_resumption"] = {"handle": handle}
        async with open_probe(setup, kiosk, "resume-2", **extra) as probe:
            turn = await probe.send_text("제가 방금 뭐 주문했었죠?", setup.text_via)
            await probe.wait_idle()
            result["resumed_remembers_order"] = "아메리카노" in turn.said
            result["resumed_said"] = turn.said
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return result


# --- mode: voices ------------------------------------------------------------------------------

VOICE_SAMPLE = (
    "안녕하세요, 대홍단감자 카페입니다. 아이스 아메리카노 라지 두 잔, 초코 쿠키 한 개, "
    "포장으로 총 만 이천칠백 원입니다. 카드를 단말기에 꽂아 주세요."
)


async def mode_voices(setup: Setup, voices: list[str]) -> dict[str, Any]:
    rows = []
    for voice in voices:
        voice_setup = Setup(
            setup.client,
            setup.model,
            voice,
            setup.language,
            setup.text_via,
            setup.vad,
            setup.hints,
            setup.thinking,
        )
        kiosk = make_kiosk()
        system = "Read the user's Korean text aloud exactly as written, warmly and naturally."
        async with open_probe(
            voice_setup, kiosk, f"voice-{voice}", system=system, tools=False
        ) as p:
            turn = await p.send_text(VOICE_SAMPLE, setup.text_via)
            await p.wait_idle()
            rows.append(
                {"voice": voice, "first_audio_ms": turn.ms(turn.first_audio), "said": turn.said}
            )
        print(f"  {voice}: {AUDIO_DIR / f'voice-{voice}.wav'}  ({turn.said.strip()[:40]}...)")
    return {"rows": rows}


# --- mode: mic ---------------------------------------------------------------------------------


async def mode_mic(setup: Setup, input_device: Any, output_device: Any) -> dict[str, Any]:
    import numpy as np
    import sounddevice as sd

    kiosk = make_kiosk()
    playback: queue.Queue[bytes] = queue.Queue()
    leftover = bytearray()
    last_loud = [0.0]

    def play(out: Any, frames: int, _time: Any, _status: Any) -> None:
        need = frames * 2
        while len(leftover) < need:
            try:
                leftover.extend(playback.get_nowait())
            except queue.Empty:
                break
        chunk = bytes(leftover[:need]).ljust(need, b"\0")
        del leftover[:need]
        out[:] = chunk

    def interrupted() -> None:
        while not playback.empty():
            with contextlib.suppress(queue.Empty):
                playback.get_nowait()
        leftover.clear()
        print("  [interrupted: playback stopped]")

    loop = asyncio.get_running_loop()
    frames: asyncio.Queue[bytes] = asyncio.Queue()

    def record(data: Any, _frames: int, _time: Any, _status: Any) -> None:
        pcm = bytes(data)
        if np.abs(np.frombuffer(pcm, dtype=np.int16)).mean() > 500:
            last_loud[0] = time.monotonic()
        loop.call_soon_threadsafe(frames.put_nowait, pcm)

    async with open_probe(setup, kiosk, "mic") as probe:
        probe.on_audio = playback.put
        probe.on_interrupted = interrupted
        probe.auto_turns = True
        probe.last_speech = lambda: last_loud[0]
        probe.on_turn_complete = lambda turn: print_turns("turn", [turn])
        print("Talk into the microphone (Ctrl+C to stop).")
        await probe.send_text(GREETING_CUE, setup.text_via)
        with (
            sd.RawInputStream(
                samplerate=IN_RATE,
                channels=1,
                dtype="int16",
                blocksize=IN_RATE * CHUNK_MS // 1000,
                device=input_device,
                callback=record,
            ),
            sd.RawOutputStream(
                samplerate=OUT_RATE, channels=1, dtype="int16", device=output_device, callback=play
            ),
            contextlib.suppress(KeyboardInterrupt, asyncio.CancelledError),
        ):
            while probe.error is None:
                pcm = await frames.get()
                await probe.session.send_realtime_input(
                    audio=types.Blob(data=pcm, mime_type=f"audio/pcm;rate={IN_RATE}")
                )
    return {"turns": [asdict(t) for t in probe.turns]}


# --- main --------------------------------------------------------------------------------------


def vad_settings(args: argparse.Namespace) -> dict[str, Any]:
    vad: dict[str, Any] = {}
    if args.start_sensitivity:
        vad["start_of_speech_sensitivity"] = f"START_SENSITIVITY_{args.start_sensitivity.upper()}"
    if args.end_sensitivity:
        vad["end_of_speech_sensitivity"] = f"END_SENSITIVITY_{args.end_sensitivity.upper()}"
    if args.prefix_ms is not None:
        vad["prefix_padding_ms"] = args.prefix_ms
    if args.silence_ms is not None:
        vad["silence_duration_ms"] = args.silence_ms
    return vad


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("mode", choices=["text", "audio", "bargein", "limits", "voices", "mic"])
    parser.add_argument("--model", help="Live model (default: configs/settings.yaml)")
    parser.add_argument("--voice", help="prebuilt voice (default: settings or the model's)")
    parser.add_argument("--language", default="ko-KR", help="speech language code ('' = none)")
    parser.add_argument("--text-via", choices=["realtime", "client"], default="realtime")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--after", type=float, default=2.5, help="bargein: seconds heard first")
    parser.add_argument("--max-sessions", type=int, default=4)
    parser.add_argument(
        "--voices", default="Kore,Aoede,Leda,Zephyr,Puck,Charon", help="voices mode: names"
    )
    parser.add_argument("--start-sensitivity", choices=["high", "low"], help="server VAD")
    parser.add_argument("--end-sensitivity", choices=["high", "low"], help="server VAD")
    parser.add_argument("--prefix-ms", type=int, help="server VAD: audio kept before speech")
    parser.add_argument("--silence-ms", type=int, help="server VAD: silence that ends speech")
    parser.add_argument("--thinking", choices=["low", "medium", "high"], help="thinking level")
    parser.add_argument(
        "--no-hints", action="store_true", help="transcription without Korean/menu hints"
    )
    parser.add_argument("--input-device", help="mic mode: device index or name part")
    parser.add_argument("--output-device", help="mic mode: device index or name part")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_env_file()
    config = load_config()
    key = os.environ.get(config.live.api_key_env, "").strip()
    if not key:
        print(f"Set {config.live.api_key_env} in .env first (see docs/setup.md).")
        return 1
    setup = Setup(
        client=genai.Client(api_key=key),
        model=args.model or config.live.model,
        voice=args.voice if args.voice is not None else config.live.voice,
        language=args.language,
        text_via=args.text_via,
        vad=vad_settings(args),
        hints=not args.no_hints,
        thinking=args.thinking or "",
    )
    print(
        f"model {setup.model}, voice {setup.voice or '(default)'}, language {setup.language}, "
        f"text via {setup.text_via}, vad {setup.vad or '(default)'}, hints {setup.hints}"
    )

    def device(value: str | None, configured: Any) -> Any:
        if value is None:
            return configured
        return int(value) if value.isdigit() else value

    runners: dict[str, Callable[[], Any]] = {
        "text": lambda: mode_text(setup, args.runs),
        "audio": lambda: mode_audio(setup),
        "bargein": lambda: mode_bargein(setup, args.runs, args.after),
        "limits": lambda: mode_limits(setup, args.max_sessions),
        "voices": lambda: mode_voices(setup, [v for v in args.voices.split(",") if v]),
        "mic": lambda: mode_mic(
            setup,
            device(args.input_device, config.audio.input_device),
            device(args.output_device, config.audio.output_device),
        ),
    }
    started = time.monotonic()
    try:
        report = asyncio.run(runners[args.mode]())
    except KeyboardInterrupt:
        return 130
    report = {
        "mode": args.mode,
        "model": setup.model,
        "voice": setup.voice,
        "language": setup.language,
        "text_via": setup.text_via,
        "vad": setup.vad,
        "hints": setup.hints,
        "thinking": setup.thinking,
        "seconds": round(time.monotonic() - started),
        **report,
    }
    print(f"\nlog: {write_log(args.mode, report)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
