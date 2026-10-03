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
    def __init__(self, kiosk: Kiosk, connector: FakeConnector) -> None:
        self.kiosk = kiosk
        self.connector = connector
        self.listener = RecordingListener()
        self.session = AssistantSession(kiosk, connector, FAST, self.listener, read_back_grace_s=0)

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


def run(test: Callable[[Harness], Awaitable[None]], kiosk_factory, connector=None) -> Harness:
    """Run an async scenario with a started session; the session is stopped afterwards."""

    async def main() -> Harness:
        harness = Harness(kiosk_factory(), connector or FakeConnector())
        assert await harness.session.start()
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
    await h.call("choose_item", item_id="americano", temperature="ice", size="regular")
    await h.call("set_dining", dining="to_go")
    await h.reply("담았어요. 더 필요하신 메뉴 있으신가요?")


# --- lifecycle ---------------------------------------------------------------------------------


def test_start_connects_and_greets(new_kiosk):
    async def scenario(h: Harness):
        assert h.conn.texts == [GREETING_CUE]
        assert h.kiosk.phase is Phase.ORDERING
        assert h.session.state is AssistantState.THINKING
        setup = h.connector.setups[0]
        assert "소리 카페" in setup.instructions
        assert {t["name"] for t in setup.tools} >= {"choose_item", "request_payment"}
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
            "choose_item", item_id="americano", quantity=2, temperature="ice", size="large"
        )
        assert result["added"] == "아이스 아메리카노 라지 2잔"
        assert h.kiosk.order.total == 9000
        assert h.session.state is AssistantState.THINKING
        result = await h.call("show_menu", category="dessert")
        assert h.kiosk.view.screen is Screen.MENU

    run(scenario, new_kiosk)


def test_required_options_nobody_said_are_not_set(new_kiosk):
    async def scenario(h: Harness):
        await h.say("카페라떼 하나 주세요")
        result = await h.call("choose_item", item_id="cafe_latte", temperature="ice", size="large")
        assert "온도, 사이즈" in result["not_heard"]
        assert h.kiosk.pending is not None and h.kiosk.pending.chosen == {}
        assert h.kiosk.view.screen is Screen.ITEM  # the screen shows the choices
        await h.reply("따뜻하게 드릴까요, 아이스로 드릴까요?")
        await h.say("아이스요")
        result = await h.call("set_options", temperature="ice", size="large")
        assert "사이즈" in result["not_heard"]
        assert [g.id for g in h.kiosk.pending.missing] == ["size"]
        await h.reply("사이즈는요?")
        await h.say("큰 걸로요")
        result = await h.call("set_options", size="large")
        assert result["added"] == "아이스 카페라떼 라지 1잔"

    run(scenario, new_kiosk)


def test_set_options_with_only_unheard_values_is_blocked(new_kiosk):
    async def scenario(h: Harness):
        await h.say("카페라떼 하나")
        await h.call("choose_item", item_id="cafe_latte")
        await h.reply("온도는요?")
        await h.say("가 있어")  # a half-heard sentence
        result = await h.call("set_options", size="large")
        assert result["blocked"].startswith("The customer did not say")
        assert h.kiosk.pending.chosen == {}

    run(scenario, new_kiosk)


def test_typed_words_count_as_heard(new_kiosk):
    async def scenario(h: Harness):
        await h.session.send_text("뜨아 작은 걸로 하나요")
        result = await h.call("choose_item", item_id="americano", temperature="hot", size="regular")
        assert "added" in result

    run(scenario, new_kiosk)


def test_change_line_repeating_current_options_is_fine(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("샷 추가해 주세요")
        result = await h.call(
            "change_line", line=1, temperature="ice", size="regular", shot="extra_shot"
        )
        assert result["changed"] == "아이스 아메리카노 레귤러(샷 추가) 1잔"
        result = await h.call("change_line", line=1, size="large")
        assert "blocked" in result  # nobody said 라지

    run(scenario, new_kiosk)


# --- payment -----------------------------------------------------------------------------------


def test_payment_without_a_request_is_blocked(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("포장이요")
        result = await h.call("request_payment")
        assert result["blocked"].startswith("BLOCKED: the customer has not asked to pay")
        assert not h.kiosk.review_is_current

    run(scenario, new_kiosk)


def test_full_payment_after_the_read_back(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        result = await h.call("request_payment")
        assert result["read_back"].endswith("포장으로 총 4,000원입니다.")
        assert h.kiosk.view.screen is Screen.REVIEW
        assert h.kiosk.phase is Phase.ORDERING  # not before the read-back was said
        await h.reply(result["read_back"] + " 카드를 단말기에 꽂아 주세요.")
        await h.settle()
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
        assert "read_back" in await h.call("request_payment")

    run(scenario, new_kiosk)


def test_items_changed_after_the_pay_request_need_a_new_request(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        await h.reply("네")
        await h.say("아 쿠키도 하나 주세요")
        await h.call("choose_item", item_id="chocolate_cookie")
        assert "blocked" in await h.call("request_payment")

    run(scenario, new_kiosk)


def test_read_back_interrupted_does_not_pay(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        await h.call("request_payment")
        h.conn.push(OutputText("주문 확인해"), AudioOut(b"\0" * 48), Interrupted(), TurnComplete())
        await h.settle()
        assert h.kiosk.phase is Phase.ORDERING

    run(scenario, new_kiosk)


def test_read_back_without_the_total_gets_a_reminder(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        result = await h.call("request_payment")
        await h.reply("카드를 꽂아 주세요.")
        assert h.kiosk.phase is Phase.ORDERING
        assert h.conn.texts[-1].startswith("[결제 전에 주문 내역을 그대로 읽어 주세요")
        await h.reply(result["read_back"])
        assert h.kiosk.phase is Phase.DONE

    run(scenario, new_kiosk)


def test_order_change_during_the_read_back_cancels_the_payment(new_kiosk):
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요 아 쿠키도요")
        await h.call("request_payment")
        await h.call("choose_item", item_id="chocolate_cookie")
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
        assert await h.call("cancel_order") == {"ok": True, "order": []}
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
        assert "read_back" in await h.call("request_payment")

    run(scenario, new_kiosk)


def test_failed_resume_starts_fresh_with_the_order(new_kiosk, monkeypatch):
    monkeypatch.setattr(session_module, "RECONNECT_DELAYS_S", (0.0, 0.0, 0.0))
    connector = FakeConnector()

    async def scenario(h: Harness):
        h.conn.push(Resumable("expired"))
        await order_ready(h)
        connector.failures = 1
        h.conn.drop()
        await h.settle()
        await h.settle()
        setup = connector.setups[-1]
        assert setup.resume_handle is None
        assert "1. 아이스 아메리카노 레귤러 1잔 4,000원" in setup.instructions
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
        await h.call("choose_item", item_id="green_grape_ade")
        result = await h.call("choose_item", item_id="americano")
        assert result["still_waiting_for_options"][0]["item_id"] == "green_grape_ade"
        await h.reply("사이즈는요?")
        await h.say("아메리카노는 아이스요")
        await h.call("set_options", item_id="americano", temperature="ice")
        await h.reply("사이즈는요?")
        await h.say("둘 다 라지로요")
        assert "added" in await h.call("set_options", item_id="green_grape_ade", size="large")
        assert "added" in await h.call("set_options", item_id="americano", size="large")
        assert [line.option_text for line in h.kiosk.order.lines] == ["Large", "ICE, Large"]

    run(scenario, new_kiosk)


def test_an_earlier_items_options_do_not_count_for_the_next(new_kiosk):
    async def scenario(h: Harness):
        await h.say("아이스 아메리카노 라지 주세요")
        await h.call("choose_item", item_id="americano", temperature="ice", size="large")
        await h.reply("담았어요")
        await h.say("카페라떼도 하나요")
        result = await h.call("choose_item", item_id="cafe_latte", temperature="ice", size="large")
        assert "not_heard" in result
        assert h.kiosk.pending is not None and h.kiosk.pending.chosen == {}

    run(scenario, new_kiosk)


def test_typed_yes_over_the_read_back_starts_the_payment(new_kiosk):
    # Seen in testing: the customer typed "네" while the read-back was still being "spoken".
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        result = await h.call("request_payment")
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
        result = await h.call("request_payment")
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
        result = await h.call("request_payment")
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
        await h.call("request_payment")
        result = await h.call("choose_item", item_id="chocolate_cookie")
        assert result["payment"] == ORDER_CHANGED_NOTE

    run(scenario, new_kiosk)


def test_done_waits_for_a_reply_that_starts_after_the_cue(new_kiosk):
    # Seen in testing: the end of the read-back finished after the "[결제 완료]" cue and was
    # taken for the reply, so the session ended before the order number was said.
    async def scenario(h: Harness):
        await order_ready(h)
        await h.say("결제할게요")
        result = await h.call("request_payment")
        h.conn.push(OutputText(result["read_back"]), AudioOut(b"\0" * 48))
        await h.settle()
        await h.session.send_text("네")
        h.conn.push(Interrupted())
        await h.settle()
        assert h.conn.texts[-1] == PAYMENT_DONE_CUE.format(number=1)
        h.conn.push(OutputText("카드를 꽂아 주세요"), AudioOut(b"\0" * 48), TurnComplete())
        await asyncio.sleep(0.3)
        assert not h.listener.finished  # that turn began before the cue
        await h.reply("주문 번호는 1번입니다.")
        await asyncio.sleep(0.3)
        assert h.listener.finished

    run(scenario, new_kiosk)
