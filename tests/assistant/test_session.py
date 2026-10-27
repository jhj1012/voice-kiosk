"""The assistant session against a fake Live connection (no network, no audio devices).

Each test pushes server events (what the customer said, function calls, audio, ...) and checks
what the session answered, what it did to the kiosk and what it told the listener.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from kiosk.assistant import session as session_module
from kiosk.assistant.instructions import GREETING_CUE
from kiosk.assistant.live import (
    AudioOut,
    FunctionCall,
    GoAway,
    InputText,
    Interrupted,
    OutputText,
    Resumable,
    ToolCall,
    TurnComplete,
)
from kiosk.assistant.session import (
    CARD_CUE,
    ORDER_CHANGED_NOTE,
    PAYMENT_DONE_CUE,
    PAYMENT_STOPPED_CUE,
    RECONNECTED_CUE,
    AssistantSession,
    AssistantState,
    SessionListener,
)
from kiosk.config import FlowConfig
from kiosk.domain.flow import Kiosk, PaymentStep, Phase, Screen
from tests.fakes import FakeConnection, FakeConnector

FAST = FlowConfig(insert_card_s=0, processing_s=0, done_return_s=0)


class RecordingListener(SessionListener):
    def __init__(self) -> None:
        self.subtitles: list[tuple[str, str, bool]] = []
        self.interruptions = 0
        self.notices: list[tuple[str, str]] = []
        self.audio: list[bytes] = []
        self.finished = False

    def on_subtitle(self, speaker, text, final):
        self.subtitles.append((speaker, text, final))

    def on_audio(self, pcm):
        self.audio.append(pcm)

    def on_interrupted(self):
        self.interruptions += 1

    def on_notice(self, level, text):
        self.notices.append((level, text))

    def on_finished(self):
        self.finished = True


class Harness:
    def __init__(self, kiosk: Kiosk, connector: FakeConnector, **options: Any) -> None:
        self.kiosk = kiosk
        self.connector = connector
        self.listener = RecordingListener()
        self.session = AssistantSession(
            kiosk, connector, FAST, self.listener, read_back_grace_s=0, **options
        )

    @property
    def conn(self) -> FakeConnection:
        return self.connector.conn

    async def settle(self) -> None:
        for _ in range(30):
            await asyncio.sleep(0)
        await asyncio.sleep(0.01)
        for _ in range(30):
            await asyncio.sleep(0)

    async def say(self, text: str) -> None:
        """The customer speaks: the transcription arrives (before any function call)."""
        self.conn.push(InputText(text))
        await self.settle()

    async def reply(self, text: str) -> None:
        """The assistant speaks one turn (a few ms of audio)."""
        self.conn.push(OutputText(text), AudioOut(b"\0" * 48), TurnComplete())
        await self.settle()

    async def call(self, name: str, **args: Any) -> dict[str, Any]:
        self.conn.push(ToolCall((FunctionCall(f"id-{name}", name, args),)))
        await self.settle()
        return self.conn.last_result


def run(
    test: Callable[[Harness], Awaitable[None]],
    kiosk_factory,
    connector=None,
    staff_question: bool = False,
    **options: Any,
) -> Harness:
    """Run an async scenario with a started session; the session is stopped afterwards.

    The question about the staff before payment is skipped unless `staff_question`: most
    scenarios are about other things."""

    async def main() -> Harness:
        harness = Harness(kiosk_factory(), connector or FakeConnector(), **options)
        assert await harness.session.start()
        harness.kiosk.staff_asked = not staff_question
        try:
            await test(harness)
        finally:
            await harness.session.stop()
        return harness

    return asyncio.run(main())


@pytest.fixture
def new_kiosk(menu, cafe):
    return lambda: Kiosk(menu, cafe)


async def order_ready(h: Harness) -> None:
    await h.say("아이스 아메리카노 레귤러 하나 포장이요")
    await h.call("order", item_id="americano", temperature="ice", size="regular")
    await h.reply("추가하실 거 있으세요?")
    await h.say("없어요")
    await h.call("no_more_extras")
    await h.call("set_dining", dining="to_go")
    await h.reply("담았어요. 더 필요하신 메뉴 있으신가요?")


# --- lifecycle ---------------------------------------------------------------------------------


def test_start_connects_and_greets(new_kiosk):
    async def scenario(h: Harness):
        assert h.conn.texts == [GREETING_CUE]
        assert h.kiosk.phase is Phase.ORDERING
        assert h.session.state is AssistantState.THINKING
        setup = h.connector.setups[0]
        assert "대홍단감자 카페" in setup.instructions
        assert {t["name"] for t in setup.tools} >= {"order", "pay", "stay_quiet"}
        assert "아메리카노" in setup.vocabulary
        assert setup.resume_handle is None

    run(scenario, new_kiosk)


def test_stop_closes_everything(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        conn = h.conn
        await h.session.stop()
        assert conn.closed
        assert h.kiosk.phase is Phase.IDLE and h.kiosk.order.is_empty
        assert h.session.state is AssistantState.IDLE

    run(scenario, new_kiosk)


def test_start_offline(new_kiosk):
    async def main():
        h = Harness(new_kiosk(), FakeConnector(failures=1))
        assert not await h.session.start()
        assert h.kiosk.phase is Phase.IDLE
        assert h.listener.notices[-1][0] == "error"

    asyncio.run(main())


# --- conversation, subtitles and state ---------------------------------------------------------


def test_subtitles_and_assistant_state(new_kiosk):
    async def scenario(h: Harness):
        h.conn.push(OutputText("안녕하세요"), AudioOut(b"\0" * 4800))
        await h.settle()
        assert h.session.state is AssistantState.SPEAKING
        assert h.listener.audio == [b"\0" * 4800]
        h.conn.push(TurnComplete())
        await asyncio.sleep(0.2)  # the 100 ms of audio have been played
        assert h.session.state is AssistantState.LISTENING
        await h.say("아메리카노")
        assert h.session.state is AssistantState.THINKING
        assert h.listener.subtitles == [
            ("assistant", "안녕하세요", False),
            ("assistant", "안녕하세요", True),
            ("customer", "아메리카노", False),
        ]

    run(scenario, new_kiosk)


def test_typed_text_is_sent_and_shown(new_kiosk):
    async def scenario(h: Harness):
        await h.session.send_text("  초코 쿠키 하나요 ")
        assert h.conn.texts[-1] == "초코 쿠키 하나요"
        assert h.listener.subtitles[-1] == ("customer", "초코 쿠키 하나요", True)
        assert h.session.transcript.last_customer().typed

    run(scenario, new_kiosk)


def test_interruption_stops_playback(new_kiosk):
    async def scenario(h: Harness):
        h.conn.push(OutputText("메뉴를 하나씩"), AudioOut(b"\0" * 48000))
        await h.settle()
        h.conn.push(Interrupted())
        await h.settle()
        assert h.listener.interruptions == 1
        assert h.session.state is AssistantState.LISTENING
        assert ("assistant", "메뉴를 하나씩", True) in h.listener.subtitles

    run(scenario, new_kiosk)


def test_foreign_transcription_is_dropped(new_kiosk):
    async def scenario(h: Harness):
        h.conn.push(OutputText("안녕하세요."), OutputText(" क्रांतिकारी रूप से"), TurnComplete())
        await h.settle()
        assert h.session.transcript.entries[-1].text == "안녕하세요."

    run(scenario, new_kiosk)


def test_audio_from_the_handset_goes_to_the_connection(new_kiosk):
    async def scenario(h: Harness):
        await h.session.send_audio(b"\1\2")
        assert h.conn.audio == [b"\1\2"]

    run(scenario, new_kiosk)


# --- function calls and required options -------------------------------------------------------


def test_function_calls_change_the_kiosk(new_kiosk):
    async def scenario(h: Harness):
        await h.say("아이스 아메리카노 라지 두 잔 주세요")
        result = await h.call(
            "order", item_id="americano", quantity=2, temperature="ice", size="large"
        )
        assert "추가하실 거 있으세요?" in result["ask"]  # the first item's extras
        await h.say("없어요")
        result = await h.call("no_more_extras")
        assert result["added"] == "차가운 아메리카노 라지 2잔"
        assert h.kiosk.order.total == 9000
        assert h.session.state is AssistantState.THINKING
        result = await h.call("show", what="menu", category="dessert")
        assert h.kiosk.view.screen is Screen.MENU

    run(scenario, new_kiosk)


def test_options_are_taken_as_the_model_understood_them(new_kiosk):
    # No text check any more: "라디오" (as the transcription wrote "라지요") is large.
    async def scenario(h: Harness):
        await h.say("차가운 아메리카노 하나요")
        await h.call("order", item_id="americano", temperature="ice")
        await h.reply("아메리카노 사이즈는 어떤 걸로 해 드릴까요?")
        await h.say("라디오")
        result = await h.call("set_options", size="large")
        assert "추가하실 거 있으세요?" in result["ask"]
        await h.say("샷 추가해 주세요")
        await h.call("set_options", shot="extra_shot")
        result = await h.call("no_more_extras")
        assert result["added"] == "차가운 아메리카노 라지(샷 추가) 1잔"
        result = await h.call("change", line=1, temperature="ice", size="regular")
        assert result["changed"] == "차가운 아메리카노 레귤러(샷 추가) 1잔"

    run(scenario, new_kiosk)


# --- payment -----------------------------------------------------------------------------------


def test_payment_without_a_request_is_blocked(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("포장이요")
        result = await h.call("pay")
        assert result["blocked"].startswith("BLOCKED: the customer has not asked to pay")
        assert not h.kiosk.review_is_current

    run(scenario, new_kiosk)


def test_full_payment_after_the_read_back(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        result = await h.call("pay")
        assert result["read_back"].endswith("포장으로 총 사천 원입니다.")
        assert h.kiosk.view.screen is Screen.REVIEW
        assert h.kiosk.phase is Phase.ORDERING  # not before the read-back was said
        await h.reply(result["read_back"])
        await h.settle()
        # The card screen comes after the read-back; then the assistant asks for the card.
        assert h.kiosk.phase is Phase.PAYING
        assert h.kiosk.view.screen is Screen.PAYMENT
        assert h.kiosk.payment_step is PaymentStep.INSERT_CARD
        assert h.conn.texts[-1] == CARD_CUE
        await h.reply("카드를 단말기에 꽂아 주세요.")
        await asyncio.sleep(0.3)  # the terminal waits until that sentence has been played
        assert h.kiosk.phase is Phase.DONE
        assert h.kiosk.payment_step is PaymentStep.APPROVED
        assert h.conn.texts[-1] == PAYMENT_DONE_CUE.format(number=1)
        await h.reply("주문 번호는 1번입니다.")
        await asyncio.sleep(0.3)
        assert h.listener.finished

    run(scenario, new_kiosk)


def test_no_more_items_counts_as_asking_to_pay(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)  # the assistant asked "더 필요하신 메뉴 있으신가요?"
        await h.say("아니요 없어요")
        assert "read_back" in await h.call("pay")

    run(scenario, new_kiosk)


def test_items_changed_after_the_pay_request_need_a_new_request(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        await h.reply("네")
        await h.say("아 쿠키도 하나 주세요")
        await h.call("order", item_id="chocolate_cookie")
        assert "blocked" in await h.call("pay")

    run(scenario, new_kiosk)


def test_read_back_interrupted_does_not_pay(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        await h.call("pay")
        h.conn.push(OutputText("주문 확인해"), AudioOut(b"\0" * 48), Interrupted(), TurnComplete())
        await h.settle()
        assert h.kiosk.phase is Phase.ORDERING

    run(scenario, new_kiosk)


def test_read_back_without_the_total_gets_a_reminder(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        result = await h.call("pay")
        await h.reply("카드를 꽂아 주세요.")
        assert h.kiosk.phase is Phase.ORDERING
        assert h.conn.texts[-1].startswith("[결제 전에 주문 내역을 그대로 읽어 주세요")
        await h.reply(result["read_back"])
        assert h.kiosk.phase is Phase.PAYING
        assert h.conn.texts[-1] == CARD_CUE

    run(scenario, new_kiosk)


def test_order_change_during_the_read_back_cancels_the_payment(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요 아 쿠키도요")
        await h.call("pay")
        await h.call("order", item_id="chocolate_cookie")
        await h.reply("총 4,000원입니다.")
        assert h.kiosk.phase is Phase.ORDERING

    run(scenario, new_kiosk)


# --- cancelling --------------------------------------------------------------------------------


def test_cancel_order_needs_a_confirmed_yes(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("다 취소해 주세요")
        assert "blocked" in await h.call("cancel_order")
        assert not h.kiosk.order.is_empty
        await h.reply("주문을 모두 취소할까요?")
        await h.say("네")
        assert (await h.call("cancel_order"))["cancelled"] == "주문 전체"
        assert h.kiosk.order.is_empty

    run(scenario, new_kiosk)


# --- connection --------------------------------------------------------------------------------


def test_dropped_connection_resumes_with_the_handle(new_kiosk):
    async def scenario(h: Harness):
        h.conn.push(Resumable("handle-1"))
        await order_ready(h)
        first = h.conn
        first.drop()
        await h.settle()
        assert len(h.connector.connections) == 2
        assert h.connector.setups[-1].resume_handle == "handle-1"
        assert "order so far" not in h.connector.setups[-1].instructions  # resumed: it knows
        assert h.conn.texts == []
        await h.say("결제할게요")  # the new connection works
        assert "read_back" in await h.call("pay")

    run(scenario, new_kiosk)


def test_failed_resume_starts_fresh_with_the_order(new_kiosk, monkeypatch):
    monkeypatch.setattr(session_module, "RECONNECT_DELAYS_S", (0.0, 0.0, 0.0))
    connector = FakeConnector()

    async def scenario(h: Harness):
        h.conn.push(Resumable("expired"))
        await order_ready(h)
        await h.say("카페라떼도 하나요")
        await h.call("order", item_id="cafe_latte")
        await h.reply("따뜻하게 드릴까요, 아이스로 드릴까요?")
        connector.failures = 1  # Google lost the session: resuming fails too (seen as 1011)
        h.conn.drop()
        await h.settle()
        await h.settle()
        setup = connector.setups[-1]
        assert setup.resume_handle is None
        # The fresh session knows the order, what is still waiting and what was just said.
        assert "1. 차가운 아메리카노 레귤러 1잔 사천 원" in setup.instructions
        assert "cafe_latte 카페라떼 x1, missing 온도, 사이즈" in setup.instructions
        assert "- assistant: 따뜻하게 드릴까요, 아이스로 드릴까요?" in setup.instructions
        assert h.conn.texts == [RECONNECTED_CUE]
        assert ("warn", "연결을 다시 시도하고 있어요") in h.listener.notices

    run(scenario, new_kiosk, connector)


def test_go_away_moves_to_a_new_connection(new_kiosk):
    async def scenario(h: Harness):
        await h.reply("안녕하세요")
        await asyncio.sleep(0.02)
        assert h.session.state is AssistantState.LISTENING
        h.conn.push(Resumable("h2"), GoAway(5.0))
        await h.settle()
        assert h.connector.connections[0].closed
        assert len(h.connector.connections) == 2
        assert h.connector.setups[-1].resume_handle == "h2"

    run(scenario, new_kiosk)


def test_two_items_in_one_sentence_wait_side_by_side(new_kiosk):
    async def scenario(h: Harness):
        await h.say("청포도 에이드 하나랑 아메리카노 하나 주세요")
        await h.call("order", item_id="green_grape_ade")
        result = await h.call("order", item_id="americano")
        assert [d["item_id"] for d in result["being_chosen"]] == ["green_grape_ade", "americano"]
        assert result["ask"] == "청포도 에이드 사이즈는 어떤 걸로 해 드릴까요?"  # said first
        await h.reply(result["ask"])
        await h.say("아메리카노는 차갑게요")
        result = await h.call("set_options", item_id="americano", temperature="ice")
        assert result["ask"] == "청포도 에이드 사이즈는 어떤 걸로 해 드릴까요?"  # still asked
        await h.reply(result["ask"])
        await h.say("둘 다 라지로요")
        result = await h.call("set_options", item_id="green_grape_ade", size="large")
        assert "추가하실 거 있으세요?" in result["ask"]  # the first item's extras
        result = await h.call("set_options", item_id="americano", size="large")
        assert result["added"] == "차가운 아메리카노 라지 1잔"  # the second: no extras
        await h.reply("청포도 에이드에 추가하실 거 있으세요?")
        await h.say("아니요 없어요")
        assert "added" in await h.call("no_more_extras", item_id="green_grape_ade")
        assert sorted(line.option_text for line in h.kiosk.order.lines) == ["ICE, Large", "Large"]

    run(scenario, new_kiosk)


def test_typed_yes_over_the_read_back_starts_the_payment(new_kiosk):
    # Seen in testing: the customer typed "네" while the read-back was still being "spoken".
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        result = await h.call("pay")
        h.conn.push(OutputText(result["read_back"]), AudioOut(b"\0" * 48000))
        await h.settle()
        await h.session.send_text("네")
        h.conn.push(Interrupted(), TurnComplete())
        await h.settle()
        assert h.kiosk.phase in (Phase.PAYING, Phase.DONE)

    run(scenario, new_kiosk)


def test_spoken_stop_over_the_read_back_cancels_and_tells_the_model(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        result = await h.call("pay")
        h.conn.push(OutputText(result["read_back"]), AudioOut(b"\0" * 48000), Interrupted())
        await h.settle()
        h.conn.push(InputText("잠깐만요"), TurnComplete())
        await h.settle()
        assert h.kiosk.phase is Phase.ORDERING
        assert h.conn.texts[-1] == PAYMENT_STOPPED_CUE
        await h.reply("네, 말씀하세요. 총 4,000원입니다.")  # a later total does not pay
        assert h.kiosk.phase is Phase.ORDERING

    run(scenario, new_kiosk)


def test_other_words_over_the_read_back_wait_for_the_next_answer(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        result = await h.call("pay")
        h.conn.push(OutputText(result["read_back"]), AudioOut(b"\0" * 48000), Interrupted())
        await h.settle()
        h.conn.push(InputText("얼마라고요?"), TurnComplete())
        await h.settle()
        assert h.kiosk.phase is Phase.ORDERING
        await h.reply("총 4,000원입니다. 카드를 꽂아 주세요.")
        assert h.kiosk.phase in (Phase.PAYING, Phase.DONE)

    run(scenario, new_kiosk)


def test_order_change_during_the_read_back_is_reported_to_the_model(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요 아 쿠키도요")
        await h.call("pay")
        result = await h.call("order", item_id="chocolate_cookie")
        assert result["payment"] == ORDER_CHANGED_NOTE

    run(scenario, new_kiosk)


def test_done_waits_for_a_reply_that_starts_after_the_cue(new_kiosk):
    # Seen in testing: the end of the read-back finished after the "[결제 완료]" cue and was
    # taken for the reply, so the session ended before the order number was said.
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        result = await h.call("pay")
        h.conn.push(OutputText(result["read_back"]), AudioOut(b"\0" * 48))
        await h.settle()
        await h.session.send_text("네")
        h.conn.push(Interrupted())
        await h.settle()
        assert h.conn.texts[-1] == CARD_CUE
        h.conn.push(OutputText("포장으로 총 4,000원입니다."), AudioOut(b"\0" * 48), TurnComplete())
        await asyncio.sleep(0.3)
        assert h.kiosk.payment_step is PaymentStep.INSERT_CARD  # that turn began before the cue
        await h.reply("카드를 단말기에 꽂아 주세요.")
        await asyncio.sleep(0.3)  # the terminal waits until that sentence has been played
        assert h.conn.texts[-1] == PAYMENT_DONE_CUE.format(number=1)
        await asyncio.sleep(0.3)
        assert not h.listener.finished
        await h.reply("주문 번호는 1번입니다.")
        await asyncio.sleep(0.3)
        assert h.listener.finished

    run(scenario, new_kiosk)


def test_the_staff_question_comes_before_the_read_back(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        result = await h.call("pay")
        assert result["ask_first"] == "직원에게 따로 전달할 말씀 있으세요?"
        assert h.kiosk.view.screen is Screen.REVIEW
        await h.reply("직원에게 따로 전달할 말씀 있으세요?")
        await h.say("얼음은 조금만 넣어 주세요")
        assert "noted" in await h.call("note_for_staff", text="얼음 적게")
        await h.reply("네, 알겠습니다. 해당 사항은 직원에게 전달하겠습니다.")
        result = await h.call("pay")  # they asked to pay before the question
        assert result["read_back"].startswith("주문 확인해 드릴게요.")
        assert h.kiosk.order.notes == ["얼음 적게"]

    run(scenario, new_kiosk, staff_question=True)


# --- speech not meant for the kiosk (developer panel switch) -----------------------------------


def test_stay_quiet_is_always_offered_other_speech_only_with_the_switch(new_kiosk):
    async def on(h: Harness):
        assert "stay_quiet" in {t["name"] for t in h.connector.setups[0].tools}
        assert "## Speech that is not for you" in h.connector.setups[0].instructions

    run(on, new_kiosk, ignore_unrelated=True)

    async def off(h: Harness):
        assert "stay_quiet" in {t["name"] for t in h.connector.setups[0].tools}  # hesitation
        assert "## Speech that is not for you" not in h.connector.setups[0].instructions

    run(off, new_kiosk)


def test_hesitation_gets_no_answer(new_kiosk):
    async def scenario(h: Harness):
        await h.reply("메뉴판에서 메뉴를 고르신 뒤 말씀해 주세요.")
        before = len(h.listener.audio)
        await h.say("음...")
        h.conn.push(ToolCall((FunctionCall("q1", "stay_quiet", {}),)))
        await h.settle()
        await h.reply("네, 천천히 고르세요.")  # if it speaks anyway: muted
        assert len(h.listener.audio) == before and h.conn.silent == {"q1"}
        await h.say("아메리카노 하나요")
        assert "being_chosen" in await h.call("order", item_id="americano")

    run(scenario, new_kiosk)


def test_words_not_for_the_kiosk_get_no_answer_and_count_for_nothing(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("내가 결제할게, 너는 자리 좀 잡아 줘")  # to a friend
        h.conn.push(ToolCall((FunctionCall("q1", "stay_quiet", {}),)))
        await h.settle()
        assert h.conn.silent == {"q1"}  # answered without a spoken reply
        assert h.session.state is AssistantState.LISTENING
        before = len(h.listener.audio)
        await h.reply("네, 결제 도와드릴게요.")  # if it speaks anyway: muted
        assert len(h.listener.audio) == before
        assert not any(
            s == ("assistant", "네, 결제 도와드릴게요.", True) for s in h.listener.subtitles
        )
        assert h.session.transcript.entries[-1].speaker == "customer"
        # A friend's "결제할게" is not the customer asking to pay.
        assert "blocked" in await h.call("pay")
        # The customer talks to the kiosk again: heard and answered as usual.
        await h.say("결제할게요")
        assert "read_back" in await h.call("pay")
        await h.reply("주문 확인해 드릴게요.")
        assert len(h.listener.audio) > before

    run(scenario, new_kiosk, ignore_unrelated=True)


def test_no_more_extras_is_not_asking_to_pay(new_kiosk):
    async def scenario(h: Harness):
        await h.say("아이스 아메리카노 레귤러 하나요")
        await h.call("order", item_id="americano", temperature="ice", size="regular")
        await h.reply("추가하실 거 있으세요?")
        await h.say("시럽 넣어 주세요")
        await h.call("set_options", syrup="vanilla")
        await h.reply("더 추가하실 거 있으세요?")
        await h.say("없어요")
        await h.call("no_more_extras")
        await h.call("set_dining", dining="to_go")
        assert "blocked" in await h.call("pay")

    run(scenario, new_kiosk)


def test_three_cups_one_cold_two_hot(new_kiosk):
    # Team test: only the two hot ones were left.
    async def scenario(h: Harness):
        await h.say("아메리카노 세 잔이요")
        await h.call("order", item_id="americano", quantity=3)
        await h.reply("아메리카노는 따뜻하게 드릴까요, 차갑게 드릴까요?")
        await h.say("하나는 차갑게, 두 잔은 따뜻하게요")
        await h.call("order", item_id="americano", quantity=1, temperature="ice")
        result = await h.call("order", item_id="americano", quantity=2, temperature="hot")
        whats = sorted(d["what"] for d in result["being_chosen"])
        assert whats == ["따뜻한 아메리카노 2잔", "차가운 아메리카노 1잔"]
        assert sorted(d.quantity for d in h.kiosk.drafts) == [1, 2]

    run(scenario, new_kiosk)
