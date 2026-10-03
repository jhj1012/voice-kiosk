"""One customer's conversation, from lifting the handset to hanging up.

The session owns the Live connection. It records the transcript (for subtitles and the safety
checks), runs every function call through the safety rules and then on the kiosk, tracks what
the assistant is doing (listening, thinking, speaking), starts the simulated card terminal once
the read-back was said, and reconnects (resuming the conversation) if the connection ends early.

Everything the outside needs to know goes through a `SessionListener`: the server turns it into
display events and audio playback (milestones 6 and 7); `kiosk.assistant.chat` prints it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from kiosk.assistant.actions import Actions, Result
from kiosk.assistant.instructions import GREETING_CUE, instructions, transcription_vocabulary
from kiosk.assistant.live import (
    AudioOut,
    FunctionCall,
    GoAway,
    InputText,
    Interrupted,
    KeyRejected,
    LiveConnection,
    LiveConnector,
    OutputText,
    Resumable,
    ServerEvent,
    SessionSetup,
    ToolCall,
    TurnComplete,
)
from kiosk.assistant.safety import (
    Speaker,
    Transcript,
    asks_to_pay,
    confirmed_cancel,
    customer_asked_to_pay,
    is_yes,
    mention_start,
    mostly_foreign,
    said_amount,
    unheard_required,
    wants_to_stop,
)
from kiosk.assistant.tools import function_declarations, option_params, selection_from_args
from kiosk.config import FlowConfig
from kiosk.domain.flow import Kiosk, Phase
from kiosk.domain.menu import KioskError, MenuItem

log = logging.getLogger(__name__)

OUT_RATE = 24000
RECONNECT_DELAYS_S = (0.0, 1.0, 3.0)
PAYMENT_DONE_CUE = (
    "[결제 완료: 주문 번호 {number}번. 카드는 끝났으니 번호와 받는 곳만 알려 주세요.]"
)
CARD_CUE = "[카드 단말기가 화면에 나왔어요. 카드를 단말기에 꽂아 달라고 짧게 말해 주세요.]"
READ_BACK_CUE = "[결제 전에 주문 내역을 그대로 읽어 주세요: {read_back}]"
PAYMENT_STOPPED_CUE = (
    "[결제를 시작하지 않았어요. 손님이 원하면 다시 결제를 요청할 때 request_payment를 호출하세요.]"
)
ORDER_CHANGED_NOTE = (
    "The payment did not start because the order changed. Ask whether they want anything else "
    "or would like to pay; call request_payment again when they ask to pay."
)
RECONNECTED_CUE = (
    "[대화가 잠시 끊겼다가 이어졌어요. 연결 이야기는 하지 말고, 마지막 대화에 이어서 짧게 "
    "다시 물어봐 주세요.]"
)
RECENT_FOR_RECONNECT = 8  # last transcript entries a fresh session gets
MAX_READ_BACK_REMINDERS = 2
CANNOT_CONNECT = "지금은 연결할 수 없어요. 잠시 후 다시 시도해 주세요."
RECONNECTING = "연결을 다시 시도하고 있어요"
CONNECTION_LOST = "연결이 끊어졌어요. 수화기를 내려놓았다가 다시 들어 주세요."

NOT_ASKED_TO_PAY = (
    "BLOCKED: the customer has not asked to pay (or changed the order since). Do not start the "
    "payment. Ask whether they want anything else or would like to pay."
)
CANCEL_NOT_CONFIRMED = (
    "BLOCKED: cancel the whole order only right after the customer said yes to your question "
    '"주문을 모두 취소할까요?". Ask it first.'
)
NOT_HEARD = (
    "The customer did not say these required options, so they were not set: {groups}. Ask the "
    "customer; never choose a required option for them."
)


class AssistantState(StrEnum):
    IDLE = "idle"  # no session (handset on hook)
    CONNECTING = "connecting"
    LISTENING = "listening"
    THINKING = "thinking"  # the customer spoke or a function ran; the reply is coming
    SPEAKING = "speaking"


class SessionListener:
    """What the session tells the rest of the kiosk. Every method does nothing by default."""

    def on_state(self) -> None:
        """The kiosk's state or the assistant's state changed."""

    def on_subtitle(self, speaker: Speaker, text: str, final: bool) -> None:
        """What the customer said or the assistant says (so far, until `final`)."""

    def on_audio(self, pcm: bytes) -> None:
        """24 kHz 16-bit mono speech to play in the earpiece."""

    def on_interrupted(self) -> None:
        """The customer started talking: stop playing at once."""

    def on_notice(self, level: str, text: str) -> None:
        """A message for the screen (level: info, warn, error; empty text clears it)."""

    def on_finished(self) -> None:
        """The done screen has been shown long enough: end the session."""

    def on_key_rejected(self) -> None:
        """There is no API key or Google refused it: someone has to enter a valid one."""


@dataclass
class _ReadBack:
    """request_payment succeeded; the terminal starts once the assistant said the total."""

    read_back: str
    total: int
    index: int  # assistant words from this transcript entry on count
    spoke: bool = False  # audio arrived since
    reminders: int = 0
    interrupted: bool = False  # the customer talked over the read-back: their words decide


class AssistantSession:
    def __init__(
        self,
        kiosk: Kiosk,
        connector: LiveConnector,
        flow: FlowConfig,
        listener: SessionListener | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        read_back_grace_s: float = 0.5,
    ) -> None:
        self.kiosk = kiosk
        self.connector = connector
        self.flow = flow
        self.listener = listener or SessionListener()
        self.actions = Actions(kiosk)
        self.transcript = Transcript()
        self.state = AssistantState.IDLE
        self._clock = clock
        self._read_back_grace_s = read_back_grace_s
        self._conn: LiveConnection | None = None
        self._receiver: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._speaking_watch: asyncio.Task[None] | None = None
        self._resume_handle: str | None = None
        self._closing = False
        self._reconnect_after_turn = False
        self._play_end = 0.0
        self._turn_audio = False
        self._turn_calls = False
        self._turn_audio_at = 0.0  # when the current turn's audio began
        self._spoken_turn_at = 0.0  # when the last completed turn with audio began
        self._lines_mark = 0  # transcript mark when the items last changed (payment intent)
        self._read_back: _ReadBack | None = None
        self._terminal_id = 0

    # --- lifecycle ---------------------------------------------------------------------------

    async def start(self) -> bool:
        """The handset was lifted: connect and let the assistant greet. False if offline."""
        self.kiosk.start_session()
        self._set_state(AssistantState.CONNECTING)
        try:
            self._conn = await self._connect()
        except KeyRejected as e:
            log.error("the API key was refused: %s", e)
            self.listener.on_key_rejected()
            self.kiosk.end_session()
            self._set_state(AssistantState.IDLE)
            return False
        except Exception as e:
            log.error("could not connect to the Live API: %s", e)
            self.listener.on_notice("error", CANNOT_CONNECT)
            self.kiosk.end_session()
            self._set_state(AssistantState.IDLE)
            return False
        self._receiver = asyncio.create_task(self._receive_loop())
        await self._conn.send_text(GREETING_CUE)
        self._set_state(AssistantState.THINKING)
        return True

    async def stop(self) -> None:
        """The handset was put down (or the done screen timed out): forget everything."""
        self._closing = True
        tasks = [t for t in (self._receiver, self._speaking_watch, *self._tasks) if t is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
        self.kiosk.end_session()
        self._set_state(AssistantState.IDLE)
        self.listener.on_state()
        log.info("session ended")

    # --- input -------------------------------------------------------------------------------

    async def send_audio(self, pcm: bytes) -> None:
        """16 kHz 16-bit mono audio from the handset's microphone."""
        if self._conn is not None and not self._closing:
            with contextlib.suppress(Exception):  # dropped while reconnecting
                await self._conn.send_audio(pcm)

    async def send_text(self, text: str) -> None:
        """Typed customer words (developer mode): handled exactly like speech."""
        text = text.strip()
        if not text or self._conn is None or self._closing:
            return
        self._close_utterance("customer")
        self.transcript.add("customer", text, typed=True)
        self.listener.on_subtitle("customer", text, True)
        log.info("customer (typed): %s", text)
        await self._conn.send_text(text)
        self._decide_read_back()
        self._set_state(AssistantState.THINKING)

    # --- receiving ---------------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        while not self._closing:
            conn = self._conn
            if conn is None:
                return
            try:
                async for event in conn.events():
                    await self._handle(event)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("Live API dropped the connection (%s); reconnecting", e)
            if self._closing:
                return
            if conn is self._conn:  # ended by itself, not replaced by a planned reconnect
                await self._reconnect()

    async def _handle(self, event: ServerEvent) -> None:
        match event:
            case Resumable(handle):
                self._resume_handle = handle
            case InputText(text) if not mostly_foreign(text):
                utterance = self.transcript.add("customer", text)
                self.listener.on_subtitle("customer", utterance.text, False)
                if self.state is not AssistantState.SPEAKING:
                    self._set_state(AssistantState.THINKING)
            case OutputText(text) if mostly_foreign(text):
                log.debug("dropped foreign transcription: %r", text[:80])
            case OutputText(text):
                self._close_utterance("customer")
                utterance = self.transcript.add("assistant", text)
                self.listener.on_subtitle("assistant", utterance.text, False)
            case AudioOut(data):
                self._on_audio(data)
            case ToolCall(calls):
                await self._on_tool_call(calls)
            case Interrupted():
                self._on_interrupted()
            case TurnComplete():
                await self._on_turn_complete()
            case GoAway():
                self._reconnect_after_turn = True
                if self.state in (AssistantState.LISTENING, AssistantState.IDLE):
                    await self._planned_reconnect()

    def _on_audio(self, data: bytes) -> None:
        self._close_utterance("customer")
        if not self._turn_audio:
            self._turn_audio_at = self._clock()
        self._turn_audio = True
        if self._read_back is not None:
            self._read_back.spoke = True
        now = self._clock()
        self._play_end = max(self._play_end, now) + len(data) / 2 / OUT_RATE
        self._set_state(AssistantState.SPEAKING)
        self.listener.on_audio(data)
        if self._speaking_watch is None or self._speaking_watch.done():
            self._speaking_watch = asyncio.create_task(self._watch_speaking())

    async def _watch_speaking(self) -> None:
        """Back to listening when the audio received so far has been played."""
        while (left := self._play_end - self._clock()) > 0:
            await asyncio.sleep(min(left, 0.2))
        if self.state is AssistantState.SPEAKING:
            self._set_state(AssistantState.LISTENING)

    def _on_interrupted(self) -> None:
        self.listener.on_interrupted()
        self._play_end = self._clock()
        self._close_utterance("assistant")
        if self._read_back is not None:
            # "네" over the read-back agrees; "잠깐만요" stops. Their words decide (typed words are
            # already here; spoken ones arrive with the transcription).
            log.info("read-back interrupted: the customer's words decide")
            self._read_back.interrupted = True
            self._decide_read_back()
        self._set_state(AssistantState.LISTENING)

    async def _on_turn_complete(self) -> None:
        self._close_utterance("customer")
        self._close_utterance("assistant")
        if self._turn_audio:
            self._spoken_turn_at = self._turn_audio_at
        elif not self._turn_calls:
            self._set_state(AssistantState.LISTENING)  # nothing to say
        self._turn_audio = self._turn_calls = False
        read_back = self._read_back
        if read_back is not None and read_back.spoke and not read_back.interrupted:
            self._spawn(self._check_read_back())
        if self._reconnect_after_turn:
            await self._planned_reconnect()

    def _close_utterance(self, speaker: Speaker) -> None:
        utterance = self.transcript.close(speaker)
        if utterance is not None and utterance.text.strip():
            self.listener.on_subtitle(speaker, utterance.text, True)
            log.info("%s: %s", speaker, utterance.text.strip())
            if speaker == "customer":
                self._decide_read_back()

    # --- function calls ----------------------------------------------------------------------

    async def _on_tool_call(self, calls: tuple[FunctionCall, ...]) -> None:
        self._close_utterance("customer")
        self._turn_calls = True
        self._set_state(AssistantState.THINKING)
        results = [(call, self._run(call)) for call in calls]
        if self._conn is not None:
            await self._conn.send_results(results)
        self.listener.on_state()

    def _run(self, call: FunctionCall) -> Result:
        """Check one call against the safety rules, run it, and note what changed."""
        before = self.kiosk.order.lines_signature
        args = dict(call.args)
        if call.name == "request_payment":
            result = self._request_payment()
        elif call.name == "cancel_order" and not confirmed_cancel(self.transcript):
            result = {"blocked": CANCEL_NOT_CONFIRMED}
        elif call.name in ("choose_item", "set_options", "change_line"):
            result = self._order_call(call.name, args)
        else:
            result = self.actions.call(call.name, args)
        if self.kiosk.order.lines_signature != before:
            self._lines_mark = self.transcript.mark
            if self._read_back is not None:
                log.info("order changed: the payment does not start")
                self._read_back = None
                result = {**result, "payment": ORDER_CHANGED_NOTE}
        log.info("call %s(%s) -> %s", call.name, args, result)
        return result

    def _order_call(self, name: str, args: dict[str, Any]) -> Result:
        """Run choose_item / set_options / change_line without required options nobody said."""
        target = self._order_target(name, args)
        if target is None:  # unknown item or line, no pending item: let the domain explain
            return self.actions.call(name, args)
        item, already, since = target
        menu = self.kiosk.menu
        texts = [u.text for u in self.transcript.customer_since(since)]
        unheard = unheard_required(item, selection_from_args(menu, args), texts, already)
        for group in unheard:
            args.pop(group.id, None)
        names = ", ".join(g.name for g in unheard)
        if unheard and name != "choose_item":
            settable = set(option_params(menu)) | {"quantity"}
            if not any(key in settable for key in args):
                return {"blocked": NOT_HEARD.format(groups=names)}
        result = self.actions.call(name, args)
        if unheard and "error" not in result:
            result["not_heard"] = NOT_HEARD.format(groups=names)
        return result

    def _order_target(
        self, name: str, args: dict[str, Any]
    ) -> tuple[MenuItem, dict[str, tuple[str, ...]], int] | None:
        """(item, choices it already has, where the customer's words about it start)."""
        try:
            if name == "choose_item":
                item = self.kiosk.menu.item(str(args.get("item_id", "")))
                return item, {}, mention_start(self.transcript, item)
            if name == "set_options":
                pending = self.kiosk.pending_item(args.get("item_id") or None)
                chosen = {g: tuple(c.id for c in cs) for g, cs in pending.chosen.items()}
                return pending.item, chosen, mention_start(self.transcript, pending.item)
            line = self.kiosk.order.line(int(float(args.get("line", 0))))
        except (KioskError, TypeError, ValueError):
            return None
        chosen = {g: tuple(c.id for c in cs) for g, cs in line.chosen().items()}
        return line.item, chosen, mention_start(self.transcript, line.item)

    # --- payment -----------------------------------------------------------------------------

    def _request_payment(self) -> Result:
        if self.kiosk.phase is Phase.ORDERING and not customer_asked_to_pay(
            self.transcript, self._lines_mark
        ):
            return {"blocked": NOT_ASKED_TO_PAY}
        result = self.actions.call("request_payment", {})
        if "read_back" in result:
            self._read_back = _ReadBack(
                read_back=result["read_back"],
                total=self.kiosk.order.total,
                index=len(self.transcript.entries),
            )
            result["next"] = "Say the read_back now, word for word; nothing about the card yet."
        return result

    def _decide_read_back(self) -> None:
        """The customer talked over the read-back: a yes starts the terminal, a stop cancels
        the payment, anything else waits for the assistant's next answer."""
        read_back = self._read_back
        if read_back is None or not read_back.interrupted:
            return
        words = [
            u
            for u in self.transcript.entries[read_back.index :]
            if u.speaker == "customer" and not u.open and u.text.strip()
        ]
        if not words:
            return  # still listening to them
        text = words[-1].text
        if wants_to_stop(text):
            log.info("customer stopped the payment: %s", text)
            self._read_back = None
            if self._conn is not None:
                self._spawn(self._conn.send_text(PAYMENT_STOPPED_CUE))
        elif is_yes(text) or asks_to_pay(text):
            log.info("customer agreed over the read-back: %s", text)
            self._spawn(self._start_terminal())
        else:
            read_back.interrupted = False  # the next spoken answer decides (`_check_read_back`)
            read_back.spoke = False

    async def _check_read_back(self) -> None:
        """After the assistant's turn: start the terminal if the total was said, else remind."""
        await asyncio.sleep(self._read_back_grace_s)  # the transcription may trail the audio
        read_back = self._read_back
        if read_back is None or not read_back.spoke:
            return
        said = self.transcript.assistant_since(read_back.index)
        if said_amount(said, read_back.total):
            await self._start_terminal()
            return
        read_back.reminders += 1
        read_back.spoke = False
        if read_back.reminders > MAX_READ_BACK_REMINDERS:
            log.warning("total not heard in the read-back; starting anyway (it is on screen)")
            await self._start_terminal()
            return
        if self._conn is not None:
            await self._conn.send_text(READ_BACK_CUE.format(read_back=read_back.read_back))

    async def _start_terminal(self) -> None:
        self._read_back = None
        try:
            self.kiosk.start_payment()
        except KioskError as e:
            log.info("payment not started: %s", e)
            return
        self.listener.on_state()
        self._terminal_id += 1
        self._spawn(self._run_terminal(self._terminal_id))

    async def _run_terminal(self, terminal_id: int) -> None:
        """The simulated card terminal: insert card -> processing -> approved."""

        def still_mine() -> bool:
            return terminal_id == self._terminal_id and self.kiosk.phase is Phase.PAYING

        # The card screen is up: now the assistant asks for the card, then the customer
        # "inserts" it (simulated).
        cue_at = self._clock()
        if self._conn is not None:
            await self._conn.send_text(CARD_CUE)
        await self._wait_for_reply(since=cue_at, timeout_s=10.0)
        await asyncio.sleep(self.flow.insert_card_s)
        if not still_mine():
            return
        self.kiosk.advance_payment()  # card inserted: processing
        self.listener.on_state()
        await asyncio.sleep(self.flow.processing_s)
        if not still_mine():
            return
        self.kiosk.advance_payment()  # approved: done
        self.listener.on_state()
        cue_at = self._clock()
        if self._conn is not None:
            await self._conn.send_text(PAYMENT_DONE_CUE.format(number=self.kiosk.order_number))
        await self._wait_for_reply(since=cue_at, timeout_s=20.0)
        await asyncio.sleep(self.flow.done_return_s)
        self.listener.on_finished()

    async def _wait_for_reply(self, since: float, timeout_s: float) -> None:
        """Until a spoken turn that began after `since` was said and played (or `timeout_s`).
        A turn still running when the cue was sent (e.g. the rest of the read-back) does not
        count."""
        deadline = self._clock() + timeout_s
        while self._clock() < deadline:
            replied = self._spoken_turn_at > since
            if replied and self.state is AssistantState.LISTENING:
                return
            await asyncio.sleep(0.1)

    # --- connection --------------------------------------------------------------------------

    async def _connect(self) -> LiveConnection:
        resuming = self._resume_handle is not None
        setup = SessionSetup(
            instructions=instructions(self.kiosk.menu, self.kiosk.cafe)
            if resuming
            else instructions(
                self.kiosk.menu,
                self.kiosk.cafe,
                self.kiosk.order,
                self.kiosk.pending_items,
                [(u.speaker, u.text.strip()) for u in self.transcript.entries if u.text.strip()][
                    -RECENT_FOR_RECONNECT:
                ],
            ),
            tools=function_declarations(self.kiosk.menu, self.kiosk.cafe),
            vocabulary=transcription_vocabulary(self.kiosk.menu),
            resume_handle=self._resume_handle,
        )
        return await self.connector.connect(setup)

    async def _planned_reconnect(self) -> None:
        """The server announced the end of this connection: move to a new one now."""
        self._reconnect_after_turn = False
        await self._reconnect(planned=True)

    async def _reconnect(self, planned: bool = False) -> None:
        if not planned:
            self.listener.on_notice("warn", RECONNECTING)
        for delay in RECONNECT_DELAYS_S:
            await asyncio.sleep(delay)
            if self._closing:
                return
            resuming = self._resume_handle is not None
            try:
                new = await self._connect()
            except Exception as e:
                log.warning(
                    "could not %s the conversation (%s); %s",
                    "resume" if resuming else "reconnect",
                    e,
                    "starting a fresh one with the order" if resuming else "trying again",
                )
                self._resume_handle = None  # the next try starts fresh, with the order
                continue
            old, self._conn = self._conn, new
            if old is not None:
                await old.close()
            if not resuming:
                await new.send_text(RECONNECTED_CUE)
            log.info("reconnected (resumed=%s, planned=%s)", resuming, planned)
            if not planned:
                self.listener.on_notice("info", "")
            return
        self.listener.on_notice("error", CONNECTION_LOST)

    # --- helpers -----------------------------------------------------------------------------

    def _set_state(self, state: AssistantState) -> None:
        if state is not self.state:
            self.state = state
            self.listener.on_state()

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
