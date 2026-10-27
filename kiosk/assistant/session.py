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
    guessed_groups,
    is_no,
    is_yes,
    meant_for_all,
    mostly_foreign,
    only_some,
    said_amount,
    thinking_aloud,
    wants_nothing_more,
    wants_to_stop,
)
from kiosk.assistant.tools import (
    STAY_QUIET,
    function_declarations,
    selection_from_args,
)
from kiosk.config import FlowConfig
from kiosk.domain.flow import Ask, Draft, Kiosk, Phase
from kiosk.domain.menu import Chosen, KioskError

log = logging.getLogger(__name__)

OUT_RATE = 24000
RECONNECT_DELAYS_S = (0.0, 1.0, 3.0)
PAYMENT_DONE_CUE = (
    "[결제 완료: 주문 번호 {number}번. 카드는 끝났으니 번호와 받는 곳만 알려 주세요.]"
)
CARD_CUE = "[카드 단말기가 화면에 나왔어요. 카드를 단말기에 꽂아 달라고 짧게 말해 주세요.]"
READ_BACK_CUE = "[결제 전에 주문 내역을 그대로 읽어 주세요: {read_back}]"
PAYMENT_STOPPED_CUE = (
    "[결제를 시작하지 않았어요. 손님이 원하면 다시 결제를 요청할 때 pay를 호출하세요.]"
)
ORDER_CHANGED_NOTE = (
    "The payment did not start because the order changed. Ask whether they want anything else "
    "or would like to pay; call pay again when they ask to pay."
)
RECONNECTED_CUE = (
    "[대화가 잠시 끊겼다가 이어졌어요. 연결 이야기는 하지 말고, 마지막 대화에 이어서 짧게 "
    "다시 물어봐 주세요.]"
)
# The model said its own thoughts out loud (in English): it was cut off; it says it again.
THOUGHT_CUE = (
    "[방금 대답에 손님에게 하지 않을 말(속생각, 영어)이 섞여서 끊겼어요. 손님에게 할 말만 한국어로 "
    "짧게 다시 말해 주세요.]"
)
MAX_THOUGHT_RETRIES = 2  # in a row, until the customer speaks again
RECENT_FOR_RECONNECT = 8  # last transcript entries a fresh session gets
MAX_READ_BACK_REMINDERS = 2
CANNOT_CONNECT = "지금은 연결할 수 없어요. 잠시 후 다시 시도해 주세요."
RECONNECTING = "연결을 다시 시도하고 있어요"
CONNECTION_LOST = "연결이 끊어졌어요. 수화기를 내려놓았다가 다시 들어 주세요."

NOT_ASKED_TO_PAY = (
    "BLOCKED: the customer has not asked to pay (or changed the order since). Do not start the "
    "payment. Ask whether they want anything else or would like to pay."
)
EXTRAS_NOT_ANSWERED = (
    "Not done: the customer has not answered '추가하실 거 있으세요?' yet. Wait for their answer; "
    "call no_more_extras only after they say they want nothing (more)."
)
NOT_SAID = (
    "The customer did not mention {groups}, so it was not set: never fill in an option. Ask the "
    "result's question."
)
CANCEL_NOT_CONFIRMED = (
    "BLOCKED: cancel the whole order only right after the customer said yes to your question "
    '"주문을 모두 취소할까요?". Ask it first.'
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
    """pay returned the read-back; the terminal starts once the assistant said the total."""

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
        ignore_unrelated: bool = False,
    ) -> None:
        self.kiosk = kiosk
        # Hesitation ("음…") always gets no answer, and with this switch (developer panel) also
        # speech not meant for the kiosk: the model calls stay_quiet, and whatever it says in
        # that turn is muted.
        self.ignore_unrelated = ignore_unrelated
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
        # Where the transcript was when the kiosk's question last changed: only customer words
        # after it answer that question (not an answer the model made up right after asking).
        self._question_mark = 0
        # Required options set since the customer last spoke: (draft, item, group, choices).
        self._answers: list[tuple[int, str, str, tuple[str, ...]]] = []
        self._answers_mark = -1
        # The kiosk asked "따뜻한 아메리카노도 레귤러로 해 드릴까요?": (draft, group, choices).
        self._confirming: tuple[int, str, tuple[str, ...]] | None = None
        self._read_back: _ReadBack | None = None
        self._terminal_id = 0
        self._quiet_turn = False  # stay_quiet was called: this turn is not heard
        self._thought_turn = False  # the model started saying its thoughts: the rest is cut
        self._thought_retries = 0
        # The greeting and the here-or-to-go question are not interrupted: while such a turn is
        # said, the handset's audio goes to the model as silence, until it has been played
        # (`_held_until`, set when the turn completes; None while it is still being said).
        self._holding = False
        self._held_until: float | None = None

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
        self._hold()  # the greeting, from before its first word
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
            if self._is_held():
                pcm = bytes(len(pcm))  # the model's turn detection hears nobody
            with contextlib.suppress(Exception):  # dropped while reconnecting
                await self._conn.send_audio(pcm)

    def _hold(self) -> None:
        if not self._holding:
            log.info("this turn is not interrupted (the greeting, here or to go)")
        self._holding = True
        self._held_until = None

    def _is_held(self) -> bool:
        if self._holding and self._held_until is not None and self._clock() >= self._held_until:
            self._holding = False  # said and played
        return self._holding

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
                self._quiet_turn = False  # the customer talks again
                self._thought_retries = 0
                utterance = self.transcript.add("customer", text)
                self.listener.on_subtitle("customer", utterance.text, False)
                if self.state is not AssistantState.SPEAKING:
                    self._set_state(AssistantState.THINKING)
            case OutputText(text) if mostly_foreign(text):
                log.debug("dropped foreign transcription: %r", text[:80])
            case OutputText(text) if self._quiet_turn:
                log.info("muted (stay_quiet): %r", text[:80])
            case OutputText(text) if self._thought_turn:
                log.info("cut (thinking aloud): %r", text[:80])
            case OutputText(text):
                self._close_utterance("customer")
                utterance = self.transcript.add("assistant", text)
                if (start := thinking_aloud(utterance.text)) is not None:
                    self._cut_thought(utterance.text[start:])
                    utterance.text = utterance.text[:start].rstrip()
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

    def _cut_thought(self, thought: str) -> None:
        """The model started saying its own thoughts: stop the sound, drop the rest of the turn
        (the transcript keeps only what came before), and have it say again, in Korean only."""
        log.warning("thinking aloud, cut: %r", thought[:120])
        self._thought_turn = True
        self.listener.on_interrupted()  # what is still buffered is not played
        self._play_end = self._clock()

    def _on_audio(self, data: bytes) -> None:
        if self._quiet_turn or self._thought_turn:
            return  # muted: the words were not for the kiosk, or the model's thoughts
        self._close_utterance("customer")
        if not self._turn_audio:
            self._turn_audio_at = self._clock()
            if self.kiosk.question.kind is Ask.DINING:
                self._hold()  # asking here or to go (again)
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
        if self._holding and self._held_until is None:
            self._held_until = self._play_end  # the customer is heard once it has been played
        if self._turn_audio:
            self._spoken_turn_at = self._turn_audio_at
        elif not self._turn_calls:
            self._set_state(AssistantState.LISTENING)  # nothing to say
        thought, self._thought_turn = self._thought_turn, False
        self._turn_audio = self._turn_calls = self._quiet_turn = False
        if thought and self._thought_retries < MAX_THOUGHT_RETRIES and self._conn is not None:
            self._thought_retries += 1
            self._spawn(self._conn.send_text(THOUGHT_CUE))
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
        quiet = {c.id for c in calls if c.name == STAY_QUIET}
        if quiet and len(quiet) == len(calls):
            await self._stay_quiet(calls)
            return
        self._turn_calls = True
        self._set_state(AssistantState.THINKING)
        results = [(call, {"ok": True} if call.id in quiet else self._run(call)) for call in calls]
        if self._conn is not None:
            await self._conn.send_results(results, silent=quiet)
        self.listener.on_state()

    async def _stay_quiet(self, calls: tuple[FunctionCall, ...]) -> None:
        """Hesitation, or words not meant for the kiosk: nothing is said, and they count for
        nothing (e.g. a friend's "내가 결제할게" is not the customer asking to pay)."""
        self._quiet_turn = True
        latest = self.transcript.last_customer()
        if latest is not None:
            latest.ignored = True
            log.info("not for the kiosk, ignored: %s", latest.text.strip())
        if self._conn is not None:
            await self._conn.send_results(
                [(c, {"ok": True}) for c in calls], silent={c.id for c in calls}
            )
        self._set_state(AssistantState.LISTENING)

    def _run(self, call: FunctionCall) -> Result:
        """Check one call against the safety rules, run it, and note what changed."""
        before = self.kiosk.order.lines_signature
        question = self.kiosk.question
        args = dict(call.args)
        if call.name == "pay":
            result = self._pay()
        elif (
            call.name == "cancel_order"
            and self.kiosk.phase is Phase.ORDERING
            and not confirmed_cancel(self.transcript)
        ):
            result = {"blocked": CANCEL_NOT_CONFIRMED}
        elif call.name == "set_options":
            result = self._answer_for_one_drink(args)
        elif call.name == "order":
            result = self._without_guesses(call.name, args)
        elif call.name == "change" and (held := self._held_for_line(args)) is not None:
            result = held
        elif call.name == "no_more_extras" and not self._extras_answered():
            log.info("no_more_extras before the customer answered: not done")
            result = {"not_done": EXTRAS_NOT_ANSWERED}
        else:
            result = self.actions.call(call.name, args)
        if self.kiosk.question != question:
            self._question_mark = len(self.transcript.entries)
        if self.kiosk.order.lines_signature != before:
            self._lines_mark = self.transcript.mark
            if self._read_back is not None:
                log.info("order changed: the payment does not start")
                self._read_back = None
                result = {**result, "payment": ORDER_CHANGED_NOTE}
        log.info("call %s(%s) -> %s", call.name, args, result)
        return result

    def _answer_for_one_drink(self, args: dict[str, Any]) -> Result:
        """set_options, with an answer that may be for several drinks ("레귤러요" while an iced and
        a hot americano both need a size, "샷 추가해 줘" while both are at the extras): it goes to
        one drink, and the kiosk asks whether the other one gets it too, unless the customer said
        it was for all ("둘 다 레귤러요")."""
        menu = self.kiosk.menu
        try:
            draft_arg = args.get("draft")
            draft = self.kiosk.find_draft(
                args.get("item_id") or None,
                selection_from_args(menu, args),
                int(float(draft_arg)) if draft_arg else None,
            )
            chosen = menu.resolve(draft.item, selection_from_args(menu, args))
        except (KioskError, TypeError, ValueError):
            return self._without_guesses("set_options", args)
        quantity = args.get("quantity")
        if chosen and quantity and int(float(quantity)) < draft.quantity:
            # "하나만 라지로": the customer said which cups (split off), nothing to check
            return self._split_rest(draft, chosen, self._without_guesses("set_options", args))
        if self._answers_mark != self.transcript.mark:  # the customer spoke: a new answer
            self._answers, self._answers_mark = [], self.transcript.mark
        latest = self.transcript.last_customer()
        for_all = meant_for_all(latest.text if latest else "")
        answer = {  # required options, and extras actually wanted (not "기본" / "없음")
            g: tuple(c.id for c in cs)
            for g, cs in chosen.items()
            if (group := draft.item.group(g)) is not None
            and (group.required or any(not c.is_none for c in cs))
        }
        # The same answer already went to another drink of this item in this turn: hold it.
        held = [
            g
            for g, ids in answer.items()
            if not for_all
            and any(
                d != draft.id and (i, gr, c) == (draft.item.id, g, ids)
                for d, i, gr, c in self._answers
            )
        ]
        for g in held:
            args.pop(g, None)
            del answer[g]
        held_group = draft.item.group(held[0]) if held else None
        if held_group is not None:
            log.info("held: the same %s for another %s", held_group.id, draft.item.id)
            confirm = self.actions.confirm_same(draft, held_group, chosen[held_group.id])
            self._confirming = (draft.id, held_group.id, tuple(c.id for c in chosen[held_group.id]))
            if not set(args) - {"item_id", "draft"}:  # nothing else to set
                return {"not_set": self.actions.held(draft), **confirm}
        if latest is not None and self._confirmed(draft, answer, latest.text):
            # "네" to the kiosk's own question (or "아니" with only one other choice).
            self._confirming = None
            result = self.actions.call("set_options", args)
        else:
            result = self._without_guesses("set_options", args)
        if "error" in result:
            return result
        if held_group is not None:
            return {**result, "not_set": self.actions.held(draft), **confirm}
        # Only what was really set (a guessed option was left out) counts as answered.
        answer = {
            g: ids
            for g, ids in answer.items()
            if tuple(c.id for c in draft.chosen.get(g, ())) == ids
        }
        self._answers += [(draft.id, draft.item.id, g, ids) for g, ids in answer.items()]
        if for_all:
            return result
        answered = {(d, g) for d, _, g, _ in self._answers}
        for g in answer:
            group = draft.item.group(g)
            others = [
                d
                for d in self.kiosk.drafts
                if d.id != draft.id
                and d.item.id == draft.item.id
                and (d.id, g) not in answered
                and (
                    any(m.id == g for m in d.missing)
                    if group is not None and group.required
                    # an extra: the other cups the extras question is about, without it yet
                    else d.ask_extras and tuple(c.id for c in d.chosen.get(g, ())) != answer[g]
                )
            ]
            if group is not None and others:
                then = str(result.get("ask", ""))
                result.update(self.actions.confirm_same(others[0], group, chosen[g], then))
                self._confirming = (others[0].id, g, answer[g])
                break
            # An extra: the same item already in the order may want it too.
            lines = [
                n
                for n, line in enumerate(self.kiosk.order.lines, start=1)
                if group is not None
                and not group.required
                and line.item.id == draft.item.id
                and tuple(c.id for c in line.chosen().get(g, ())) != answer[g]
            ]
            if group is not None and lines:
                then = str(result.get("ask", ""))
                result.update(self.actions.confirm_line(lines[-1], group, chosen[g], then))
                break
        return result

    def _split_rest(self, rest: Draft, chosen: Chosen, result: Result) -> Result:
        """After "두 잔만 아이스로" split some cups off: the rest get the other choice of a
        two-choice option (temperature, size), as "only two iced" means the others are not."""
        latest = self.transcript.last_customer()
        if "error" in result or rest not in self.kiosk.drafts or latest is None:
            return result
        if not only_some(latest.text):
            return result  # "두 잔은 아이스로": they may go on with "나머지는…"
        others: dict[str, str] = {}
        for g, choices in chosen.items():
            group = rest.item.group(g)
            if group is None or not group.required or rest.chosen.get(g):
                continue
            left = [c for c in group.choices if c not in choices]
            if len(left) == 1:
                others[g] = left[0].id
        if not others:
            return result
        log.info("the rest of %s: %s", rest.item.id, others)
        return self.actions.call("set_options", {"draft": rest.id, **others})

    def _extras_answered(self) -> bool:
        """The customer answered the extras question: they spoke after it was asked, or said
        before that they want nothing added ("레귤러로, 추가는 없어요")."""
        if self.kiosk.question.kind is not Ask.EXTRAS:
            return True  # the domain explains any mistake
        if self.transcript.customer_since(self._question_mark):
            return True
        latest = self.transcript.last_customer()
        return latest is not None and wants_nothing_more(latest.text)

    def _held_for_line(self, args: dict[str, Any]) -> Result | None:
        """change on an order line with the answer just given for a drink being chosen, which the
        customer did not say was for both: not done; the kiosk asks first."""
        if self._answers_mark != self.transcript.mark or not self._answers:
            return None
        try:
            number = int(float(args.get("line", 0)))
            line = self.kiosk.order.line(number)
            chosen = self.kiosk.menu.resolve(line.item, selection_from_args(self.kiosk.menu, args))
        except (KioskError, TypeError, ValueError):
            return None
        latest = self.transcript.last_customer()
        if meant_for_all(latest.text if latest else ""):
            return None
        for g, choices in chosen.items():
            ids = tuple(c.id for c in choices)
            group = line.item.group(g)
            same = any((i, gr, c) == (line.item.id, g, ids) for _, i, gr, c in self._answers)
            if group is not None and not group.required and same:
                log.info("held: the same %s for line %d", g, number)
                return {
                    "not_set": self.actions.held_line(number),
                    **self.actions.confirm_line(number, group, choices),
                }
        return None

    def _confirmed(self, draft: Draft, answer: dict[str, tuple[str, ...]], words: str) -> bool:
        """The answer is what the customer agreed to when the kiosk asked "따뜻한 아메리카노도
        레귤러로 해 드릴까요?": "네" and that choice, or "아니" and the only other choice."""
        if self._confirming is None or self._confirming[0] != draft.id:
            return False
        _, group_id, asked = self._confirming
        ids = answer.get(group_id)
        group = draft.item.group(group_id)
        if ids is None or group is None:
            return False
        if is_yes(words):
            return ids == asked
        others = [c.id for c in group.choices if c.id not in asked]
        return group.required and is_no(words) and len(others) == 1 and ids == tuple(others)

    def _without_guesses(self, name: str, args: dict[str, Any]) -> Result:
        """Run order / set_options without required options the customer never mentioned
        (unless the screen asks for that option and the customer spoke since: then any answer
        is taken)."""
        try:
            if name == "order":
                item = self.kiosk.menu.item(str(args.get("item_id", "")))
            else:
                draft = args.get("draft")
                item = self.kiosk.find_draft(
                    args.get("item_id") or None,
                    selection_from_args(self.kiosk.menu, args),
                    int(float(draft)) if draft else None,
                ).item
        except (KioskError, TypeError, ValueError):
            return self.actions.call(name, args)  # the domain explains the mistake
        question = self.kiosk.question
        answered = bool(self.transcript.customer_since(self._question_mark))
        asked = question.group if question.item_id == item.id and answered else ""
        latest = self.transcript.last_customer()
        selection = selection_from_args(self.kiosk.menu, args)
        guessed = guessed_groups(item, selection, latest.text if latest else "", asked)
        for group in guessed:
            args.pop(group.id, None)
        result = self.actions.call(name, args)
        if guessed and "error" not in result:
            names = ", ".join(g.name for g in guessed)
            log.info("guessed %s left out for %s", names, item.id)
            result["not_said"] = NOT_SAID.format(groups=names)
        return result

    # --- payment -----------------------------------------------------------------------------

    def _pay(self) -> Result:
        if self.kiosk.phase is Phase.ORDERING and not customer_asked_to_pay(
            self.transcript, self._lines_mark
        ):
            return {"blocked": NOT_ASKED_TO_PAY}
        result = self.actions.call("pay", {})
        if "read_back" in result:
            self._read_back = _ReadBack(
                read_back=result["read_back"],
                total=self.kiosk.order.total,
                index=len(self.transcript.entries),
            )
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
            instructions=instructions(
                self.kiosk.menu, self.kiosk.cafe, ignore_unrelated=self.ignore_unrelated
            )
            if resuming
            else instructions(
                self.kiosk.menu,
                self.kiosk.cafe,
                self.kiosk.order,
                self.kiosk.drafts,
                [
                    (u.speaker, u.text.strip())
                    for u in self.transcript.entries
                    if u.text.strip() and not u.ignored
                ][-RECENT_FOR_RECONNECT:],
                ignore_unrelated=self.ignore_unrelated,
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
