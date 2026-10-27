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


def test_an_option_nobody_mentioned_is_left_out_and_asked(new_kiosk):
    # Team scenario run: "아메리카노 세 잔이요, 하나는 차갑게…" came with size=regular, a guess.
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("카페라떼 하나요")
        result = await h.call("order", item_id="cafe_latte", temperature="hot", size="large")
        assert "not_said" in result and h.kiosk.pending.chosen == {}
        assert result["ask"] == "카페라떼는 따뜻하게 드릴까요, 차갑게 드릴까요?"

    run(scenario, new_kiosk)


def test_answers_to_the_question_asked_are_always_taken(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("카페라떼 하나요")
        await h.call("order", item_id="cafe_latte")
        await h.say("음 그걸로요")  # unclear, but an answer to the temperature question
        result = await h.call("set_options", temperature="hot")
        assert "not_said" not in result and "temperature" in h.kiosk.pending.chosen

    run(scenario, new_kiosk)


def test_an_answer_the_customer_did_not_give_is_not_taken(new_kiosk):
    # Team log 04:01: the model asked the size, then made up the customer's answer ("The
    # customer said ...레귤러요") and set it, before the customer said anything.
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("아이스아메리카노")
        await h.call("order", item_id="americano", temperature="ice")
        assert view(h) == ("americano", "size")
        await h.reply("아메리카노 사이즈는 어떤 걸로 해 드릴까요?")
        result = await h.call("set_options", item_id="americano", size="regular")
        assert "not_said" in result and "size" not in h.kiosk.pending.chosen
        await h.say("레귤러요")  # the real answer is taken
        result = await h.call("set_options", item_id="americano", size="regular")
        assert "not_said" not in result
        assert [c.id for c in h.kiosk.pending.chosen["size"]] == ["regular"]

    run(scenario, new_kiosk)


async def iced_and_hot(h: Harness) -> None:
    await lifted(h)
    await h.say("아이스 아메리카노 하나랑 핫 아메리카노 하나 주세요")
    await h.call("order", item_id="americano", temperature="ice")
    await h.call("order", item_id="americano", temperature="hot")
    assert view(h) == ("americano", "size")
    await h.reply("차가운 아메리카노 사이즈는 어떤 걸로 해 드릴까요?")


def sizes(h: Harness) -> dict[str, list[str]]:
    """Each americano's temperature and size, being chosen or in the order."""
    drinks = [d.chosen for d in h.kiosk.drafts] + [line.chosen() for line in h.kiosk.order.lines]
    return {
        c["temperature"][0].id: [x.id for x in c.get("size", ())]
        for c in drinks
        if "temperature" in c
    }


def test_an_answer_that_may_be_for_two_drinks_is_checked(new_kiosk):
    # Team test: "아이스/핫 아메리카노" at once; "레귤러요" went to both, or only one was asked.
    async def scenario(h: Harness):
        await iced_and_hot(h)
        await h.say("레귤러요")
        result = await h.call("set_options", draft=1, size="regular")
        assert sizes(h) == {"ice": ["regular"], "hot": []}
        assert result["ask"] == "따뜻한 아메리카노도 레귤러로 해 드릴까요?"
        assert "size large" in result["confirm_note"]  # "아니요": the other size, not asked again
        await h.say("네")
        result = await h.call("set_options", draft=2, size="regular")
        assert sizes(h) == {"ice": ["regular"], "hot": ["regular"]}
        assert "confirm_note" not in result

    run(scenario, new_kiosk)


def test_no_to_the_check_means_the_other_of_two_choices(new_kiosk):
    # Team log 13:26: "차가운 아메리카노도 라지로 해 드릴까요?" - "아니" was asked again; with two
    # sizes it means regular.
    async def scenario(h: Harness):
        await iced_and_hot(h)
        await h.say("라지요")
        await h.call("set_options", draft=1, size="large")
        await h.reply("따뜻한 아메리카노도 라지로 해 드릴까요?")
        await h.say("아니")
        result = await h.call("set_options", draft=2, size="regular")
        assert sizes(h) == {"ice": ["large"], "hot": ["regular"]}
        assert "not_said" not in result

    run(scenario, new_kiosk)


def test_options_for_only_some_cups_split_them_off(new_kiosk):
    # Team log 13:26: two hot americanos, "하나만 라지로 해줘" made both large.
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("따뜻한 아메리카노 두 잔이요")
        await h.call("order", item_id="americano", quantity=2, temperature="hot")
        await h.reply("아메리카노 사이즈는 어떤 걸로 해 드릴까요?")
        await h.say("하나만 라지로 해줘")
        result = await h.call("set_options", item_id="americano", quantity=1, size="large")
        cups = sorted(
            (d.quantity, [c.id for c in d.chosen.get("size", ())]) for d in h.kiosk.drafts
        )
        assert cups == [(1, ["large"]), (1, ["regular"])]  # "하나만": the other one is regular
        assert "confirm_note" not in result

    run(scenario, new_kiosk)


def test_the_rest_goes_to_the_cups_still_open(new_kiosk):
    # Real run of the 13:26 log: "2개는 따듯하게, 나머지는 차갑게" with three americanos; the model
    # split off two hot ones, then sent "the rest" to the number of the hot drink.
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("아메리카노 3개")
        await h.call("order", item_id="americano", quantity=3)
        await h.reply("아메리카노는 따뜻하게 드릴까요, 차갑게 드릴까요?")
        await h.say("2개는 따듯하게, 나머지는 차갑게")
        await h.call("set_options", item_id="americano", draft=1, quantity=2, temperature="hot")
        hot = next(d.id for d in h.kiosk.drafts if d.chosen.get("temperature"))
        await h.call("set_options", item_id="americano", draft=hot, quantity=1, temperature="ice")
        cups = sorted((d.chosen["temperature"][0].id, d.quantity) for d in h.kiosk.drafts)
        assert cups == [("hot", 2), ("ice", 1)]

    run(scenario, new_kiosk)


def test_split_cups_are_asked_about_extras_once(new_kiosk):
    # Real run: after "하나만 라지로" every split-off cup asked "추가하실 거 있으세요?" again.
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("따뜻한 아메리카노 세 잔이요")
        await h.call("order", item_id="americano", quantity=3, temperature="hot")
        await h.reply("아메리카노 사이즈는 어떤 걸로 해 드릴까요?")
        await h.say("하나만 라지로 해줘")
        await h.call("set_options", item_id="americano", quantity=1, size="large")
        await h.reply("아메리카노 사이즈는 어떤 걸로 해 드릴까요?")
        await h.say("나머지는 레귤러요")
        await h.call("set_options", item_id="americano", size="regular")
        await h.reply("아메리카노에 추가하실 거 있으세요?")
        await h.say("없어요")
        await h.call("no_more_extras", item_id="americano")
        assert not h.kiosk.drafts
        cups = sorted((line.chosen()["size"][0].id, line.quantity) for line in h.kiosk.order.lines)
        assert cups == [("large", 1), ("regular", 2)]

    run(scenario, new_kiosk)


def test_an_extra_that_may_be_for_two_drinks_is_checked(new_kiosk):
    # Team test: three americanos split into one iced and two hot; at the extras question
    # "샷추가 해줘" went to all of them without asking.
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("아메리카노 3개")
        await h.call("order", item_id="americano", quantity=3)
        await h.say("1개는 차갑게, 나머지는 따뜻하게")
        await h.call("set_options", item_id="americano", quantity=1, temperature="ice")
        hot = next(d.id for d in h.kiosk.drafts if not d.chosen.get("temperature"))
        await h.call("set_options", draft=hot, temperature="hot")
        iced = next(d.id for d in h.kiosk.drafts if d.id != hot)
        await h.say("셋 다 레귤러로")
        await h.call("set_options", draft=iced, size="regular")
        result = await h.call("set_options", draft=hot, size="regular")
        assert "confirm_note" not in result and "not_set" not in result  # "셋 다"
        await h.reply("아메리카노에 추가하실 거 있으세요?")
        await h.say("샷추가 해줘")
        asked = h.kiosk.question.draft
        other = hot if asked == iced else iced
        result = await h.call("set_options", draft=asked, shot="extra_shot")
        assert result["ask"].endswith("에도 샷 추가 해 드릴까요?")
        held = await h.call("set_options", draft=other, shot="extra_shot")  # the model's guess

        def shots():
            return {d.id: [c.id for c in d.chosen.get("shot", ())] for d in h.kiosk.drafts}

        assert "not_set" in held and shots()[other] != ["extra_shot"]
        await h.say("응")
        await h.call("set_options", draft=other, shot="extra_shot")
        assert shots() == {asked: ["extra_shot"], other: ["extra_shot"]}

    run(scenario, new_kiosk)


def test_an_extra_may_be_for_a_drink_already_in_the_order(new_kiosk):
    # An iced and a hot americano ordered separately: the hot one went into the order as soon as
    # its size was set, so "샷추가 해줘" for the iced one never asked about it.
    async def scenario(h: Harness):
        await iced_and_hot(h)
        await h.say("둘 다 레귤러요")
        await h.call("set_options", draft=1, size="regular")
        await h.call("set_options", draft=2, size="regular")
        assert len(h.kiosk.order.lines) == 1  # the hot one, in the order
        await h.reply("아메리카노에 추가하실 거 있으세요?")
        await h.say("샷추가 해줘")
        result = await h.call("set_options", draft=1, shot="extra_shot")
        assert result["ask"] == "따뜻한 레귤러 아메리카노에도 샷 추가 해 드릴까요?"
        held = await h.call("change", line=1, shot="extra_shot")  # the model's guess
        assert "not_set" in held
        assert [c.id for c in h.kiosk.order.lines[0].chosen()["shot"]] == ["none"]
        await h.say("응")
        await h.call("change", line=1, shot="extra_shot")
        assert [c.id for c in h.kiosk.order.lines[0].chosen()["shot"]] == ["extra_shot"]

    run(scenario, new_kiosk)


def test_only_some_in_other_words():
    from kiosk.assistant.safety import only_some

    for words in ["2개만 아이스로", "두 잔만 아이스로", "하나만 라지로 해줘", "한 잔만 차갑게"]:
        assert only_some(words), words
    for words in ["두 잔은 아이스로", "레귤러만 돼요?", "아메리카노 두 잔이요"]:
        assert not only_some(words), words


def test_all_of_them_in_other_words():
    from kiosk.assistant.safety import meant_for_all

    for words in [
        "둘 다 레귤러요",
        "셋 다 레귤러로",
        "세 잔 다요",
        "3잔 다 라지",
        "전부 샷 추가",
        "똑같이요",
        "다 레귤러로",
    ]:
        assert meant_for_all(words), words
    for words in ["레귤러요", "하나만 라지로", "다음에요", "다 됐어요"]:
        assert not meant_for_all(words), words


def test_only_some_cups_means_the_rest_get_the_other_choice(new_kiosk):
    # Team test: "아메리카노 6잔" → "2개만 아이스로" asked the other four's temperature (twice).
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("아메리카노 6잔")
        await h.call("order", item_id="americano", quantity=6)
        await h.reply("아메리카노는 따뜻하게 드릴까요, 차갑게 드릴까요?")
        await h.say("2개만 아이스로")
        result = await h.call("set_options", item_id="americano", quantity=2, temperature="ice")
        cups = sorted((d.chosen["temperature"][0].id, d.quantity) for d in h.kiosk.drafts)
        assert cups == [("hot", 4), ("ice", 2)]
        assert "사이즈" in result["ask"]  # on to the next question

    run(scenario, new_kiosk)


def test_some_cups_without_only_leaves_the_rest_to_ask(new_kiosk):
    async def scenario(h: Harness):
        await lifted(h)
        await h.say("아메리카노 3잔")
        await h.call("order", item_id="americano", quantity=3)
        await h.say("두 잔은 아이스로 하고")  # "나머지는…" may follow
        await h.call("set_options", item_id="americano", quantity=2, temperature="ice")
        rest = [d for d in h.kiosk.drafts if not d.chosen.get("temperature")]
        assert [d.quantity for d in rest] == [1]

    run(scenario, new_kiosk)


def test_the_same_answer_is_not_put_on_both_drinks_unasked(new_kiosk):
    async def scenario(h: Harness):
        await iced_and_hot(h)
        await h.say("레귤러요")
        await h.call("set_options", draft=1, size="regular")
        result = await h.call("set_options", draft=2, size="regular")  # the model's guess
        assert sizes(h) == {"ice": ["regular"], "hot": []}
        assert "not_set" in result
        assert result["ask"] == "따뜻한 아메리카노도 레귤러로 해 드릴까요?"

    run(scenario, new_kiosk)


def test_an_answer_for_both_drinks_goes_to_both(new_kiosk):
    async def scenario(h: Harness):
        await iced_and_hot(h)
        await h.say("둘 다 레귤러요")
        await h.call("set_options", draft=1, size="regular")
        result = await h.call("set_options", draft=2, size="regular")
        assert sizes(h) == {"ice": ["regular"], "hot": ["regular"]}
        assert "confirm_note" not in result and "not_set" not in result

    run(scenario, new_kiosk)


def test_different_answers_for_each_drink_are_taken(new_kiosk):
    async def scenario(h: Harness):
        await iced_and_hot(h)
        await h.say("아이스는 레귤러, 핫은 라지로 주세요")
        await h.call("set_options", draft=1, size="regular")
        result = await h.call("set_options", draft=2, size="large")
        assert sizes(h) == {"ice": ["regular"], "hot": ["large"]}
        assert "confirm_note" not in result and "not_set" not in result

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
