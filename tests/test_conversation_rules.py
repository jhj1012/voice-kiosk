"""The team test cases from docs/conversation-rules.md, against a fake Live connection.

Each test plays what the model did (function calls) and what the customer said, and checks
what the code made of it.
"""

from __future__ import annotations

import pytest

from kiosk.domain.flow import EXTRAS, Kiosk, Phase, Screen
from tests.assistant.test_session import Harness, run


@pytest.fixture
def new_kiosk(menu, cafe):
    return lambda: Kiosk(menu, cafe)


async def lifted(h: Harness) -> None:
    await h.reply("안녕하세요, 매장에서 드시고 가세요, 포장하세요?")
    await h.say("포장이요")
    await h.call("set_dining", dining="to_go")
    await h.reply("메뉴판에서 메뉴를 고르신 뒤 말씀해 주세요.")


def view(h: Harness) -> tuple[str, str]:
    return h.kiosk.view.item_id, h.kiosk.view.group


# --- 4. adding items ------------------------------------------------------------------------


def test_split_cups_become_separate_lines(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("아메리카노 세 잔, 하나는 차갑게 두 잔은 따뜻하게요")
        await h.call("order", item_id="americano", quantity=1, temperature="ice")
        await h.call("order", item_id="americano", quantity=2, temperature="hot")
        await h.reply("사이즈는 어떤 걸로 해 드릴까요?")
        await h.say("둘 다 레귤러요")
        await h.call("set_options", item_id="americano", size="regular")
        await h.call("set_options", item_id="americano", size="regular")
        for _ in range(2):
            await h.call("no_more_extras", item_id="americano")
        lines = sorted((ln.quantity, ln.option_text) for ln in h.kiosk.order.lines)
        assert lines == [(1, "ICE, Regular"), (2, "HOT, Regular")]

    run(scenario, new_kiosk)


def test_a_misheard_size_is_still_taken(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("차가운 아메리카노 주세요")
        await h.call("order", item_id="americano", temperature="ice")
        await h.reply("사이즈는 어떤 걸로 해 드릴까요?")
        await h.say("라디오")  # "라지요" as the transcription wrote it
        result = await h.call("set_options", size="large")
        assert "not_heard" not in result and "blocked" not in result

    run(scenario, new_kiosk)


def test_an_option_said_turns_earlier_is_taken(new_kiosk):
    # The 18:05 log: the model forgot to record "따듯한걸로" and sent it two answers later; the
    # text check had lost it by then and the temperature was asked again.
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("아이스 아메리카노는 포장, 라떼는 매장에서 먹고갈게요")
        await h.call("note_for_staff", text="아메리카노는 포장, 라떼는 매장")
        await h.call("order", item_id="americano", temperature="ice")
        await h.call("order", item_id="cafe_latte")
        await h.say("라지요")
        await h.call("set_options", item_id="americano", size="large")
        await h.say("아니요")
        await h.call("no_more_extras", item_id="americano")
        await h.say("따듯한걸로")  # no call: the model only spoke
        await h.reply("따뜻한 카페라떼 사이즈는 어떤 걸로 해 드릴까요?")
        await h.say("레귤러요")
        result = await h.call(
            "set_options", item_id="cafe_latte", size="regular", temperature="hot"
        )
        assert "not_heard" not in result
        assert "따뜻하게" not in result["ask"]  # not the temperature again
        assert result["added"] == "따뜻한 카페라떼 레귤러 1잔"

    run(scenario, new_kiosk)


def test_no_required_option_is_refused_by_a_text_check(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("카페라떼 하나요")
        result = await h.call("order", item_id="cafe_latte", temperature="hot", size="large")
        # The model is trusted; the screen and the read-back let the customer correct it.
        assert "not_heard" not in result
        assert h.kiosk.pending is not None and len(h.kiosk.pending.chosen) == 2

    run(scenario, new_kiosk)


def test_extras_are_asked_only_for_the_first_item(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("따뜻한 아메리카노 레귤러 하나요")
        result = await h.call("order", item_id="americano", temperature="hot", size="regular")
        assert "추가하실 거 있으세요?" in result["ask"]  # the first item
        await h.say("없어요")
        await h.call("no_more_extras")
        await h.say("따뜻한 카페라떼 레귤러도 하나요")
        result = await h.call("order", item_id="cafe_latte", temperature="hot", size="regular")
        assert "added" in result  # the second: added at once

    run(scenario, new_kiosk)


def test_no_to_the_extras_question_does_not_start_paying(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("따뜻한 아메리카노 레귤러 하나요")
        await h.call("order", item_id="americano", temperature="hot", size="regular")
        await h.reply("추가하실 거 있으세요?")
        await h.say("없어요")
        await h.call("no_more_extras")
        assert "blocked" in await h.call("pay")

    run(scenario, new_kiosk)


def test_no_to_more_items_goes_on_to_paying(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("따뜻한 아메리카노 레귤러 하나요")
        await h.call("order", item_id="americano", temperature="hot", size="regular")
        await h.say("없어요")
        await h.call("no_more_extras")
        await h.reply("더 추가하실 메뉴가 있으신가요, 아니면 결제를 진행할까요?")
        await h.say("없어")
        assert "blocked" not in await h.call("pay")

    run(scenario, new_kiosk, staff_question=True)


def test_the_screen_shows_the_question_the_result_asks(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("카페라떼 하나요")
        result = await h.call("order", item_id="cafe_latte")
        assert result["ask"] == "카페라떼는 따뜻하게 드릴까요, 차갑게 드릴까요?"
        assert view(h) == ("cafe_latte", "temperature")
        await h.say("차갑게요")
        result = await h.call("set_options", temperature="ice")
        assert result["ask"] == "카페라떼 사이즈는 어떤 걸로 해 드릴까요?"
        assert view(h) == ("cafe_latte", "size")
        await h.say("라지요")
        result = await h.call("set_options", size="large")
        assert "추가하실 거 있으세요?" in result["ask"] and view(h) == ("cafe_latte", EXTRAS)

    run(scenario, new_kiosk)


# --- 6. going back --------------------------------------------------------------------------


def test_back_from_the_size_question_shows_the_temperature_again(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("카페라떼 하나요")
        await h.call("order", item_id="cafe_latte")
        await h.say("차갑게요")
        await h.call("set_options", temperature="ice")
        await h.say("뒤로요")
        await h.call("go_back")
        assert view(h) == ("cafe_latte", "temperature")
        assert h.kiosk.pending is not None and "temperature" in h.kiosk.pending.chosen  # kept

    run(scenario, new_kiosk)


def test_back_to_an_added_item_shows_its_options_to_change(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.call("show", what="menu", category="latte")
        await h.say("따뜻한 카페라떼 레귤러 하나요")
        await h.call("order", item_id="cafe_latte", temperature="hot", size="regular")
        await h.say("없어요")
        await h.call("no_more_extras")
        await h.say("아까 라떼 화면 보여 주세요")
        await h.call("go_back")
        assert h.kiosk.view.item_id == "cafe_latte" and h.kiosk.view.line == 1
        await h.say("라지로 바꿔 주세요")
        await h.call("change", line=1, size="large")
        assert h.kiosk.order.line(1).option_text.endswith("Large")

    run(scenario, new_kiosk)


def test_going_back_changes_nothing_in_the_order(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.call("show", what="categories")
        await h.say("쿠키 하나요")
        await h.call("order", item_id="chocolate_cookie")
        before = h.kiosk.order.lines_signature
        await h.call("go_back")
        assert h.kiosk.order.lines_signature == before

    run(scenario, new_kiosk)


# --- 7. / 8. payment and cancelling ---------------------------------------------------------


def test_the_staff_question_comes_before_the_read_back(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("쿠키 하나요. 결제할게요")
        await h.call("order", item_id="chocolate_cookie")
        result = await h.call("pay")
        assert "ask_first" in result and h.kiosk.view.screen is Screen.REVIEW
        await h.say("없어요")
        assert "read_back" in await h.call("pay")

    run(scenario, new_kiosk, staff_question=True)


def test_cancelling_everything_needs_a_yes(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("쿠키 하나요")
        await h.call("order", item_id="chocolate_cookie")
        await h.say("전부 취소해 주세요")
        assert "blocked" in await h.call("cancel_order")
        await h.reply("주문을 모두 취소할까요?")
        await h.say("네")
        await h.call("cancel_order")
        assert h.kiosk.order.is_empty and h.kiosk.phase is Phase.ORDERING

    run(scenario, new_kiosk)


# --- 9. staff requests ----------------------------------------------------------------------


def test_mixed_dining_becomes_a_staff_note(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("아메리카노는 포장, 라떼는 매장에서 먹고 갈게요")
        result = await h.call("note_for_staff", text="아메리카노는 포장, 라떼는 매장")
        assert result["say"].startswith("네, 알겠습니다.")
        assert h.kiosk.order.notes == ["아메리카노는 포장, 라떼는 매장"]

    run(scenario, new_kiosk)


# --- 12. listening --------------------------------------------------------------------------


def test_hesitation_gets_no_answer_without_the_switch(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        names = {t["name"] for t in h.connector.setups[0].tools}
        assert "stay_quiet" in names  # always offered: "음…", "어…" get no answer

    run(scenario, new_kiosk)
