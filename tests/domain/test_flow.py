import random

import pytest

from kiosk.domain.flow import (
    EXTRAS,
    MAX_SHOWN,
    Ask,
    Kiosk,
    PaymentStep,
    Phase,
    Question,
    Screen,
)
from kiosk.domain.menu import KioskError
from kiosk.domain.order import CartLine, Dining


def add(kiosk: Kiosk, item_id: str, quantity: int = 1, **selection: str) -> CartLine:
    """Order a drink with its options (and no extras, if they are asked)."""
    result = kiosk.order_item(item_id, quantity, selection)
    if result.line is None:
        result = kiosk.no_more_extras(item_id)
    assert result.line is not None
    return result.line


def order_ready(kiosk: Kiosk) -> None:
    kiosk.set_dining(Dining.TO_GO)
    add(kiosk, "americano", temperature="ice", size="regular")


def question(kiosk: Kiosk) -> tuple[Ask, str, str]:
    q = kiosk.question
    return q.kind, q.item_id, q.group


# --- session -----------------------------------------------------------------------------------


def test_idle_kiosk_refuses_orders(menu, cafe):
    kiosk = Kiosk(menu, cafe)
    assert kiosk.phase is Phase.IDLE and kiosk.view.screen is Screen.ATTRACT
    assert kiosk.question.kind is Ask.NONE
    with pytest.raises(KioskError, match="idle"):
        kiosk.order_item("americano")


def test_the_first_question_is_here_or_to_go(kiosk: Kiosk):
    assert kiosk.question == Question(Ask.DINING)
    assert kiosk.view.screen is Screen.DINING
    kiosk.set_dining(Dining.HERE)
    assert kiosk.question.kind is Ask.MENU  # "메뉴판에서 메뉴를 고르신 뒤 말씀해 주세요"
    assert kiosk.view.screen is Screen.WELCOME


def test_ordering_first_is_fine_dining_comes_later(kiosk: Kiosk):
    add(kiosk, "chocolate_cookie")
    assert kiosk.question.kind is Ask.MENU
    with pytest.raises(KioskError, match="eats here or takes out"):
        kiosk.request_payment()
    assert kiosk.question.kind is Ask.DINING and kiosk.view.screen is Screen.DINING


def test_hanging_up_clears_everything(kiosk: Kiosk):
    order_ready(kiosk)
    kiosk.add_note("케이크는 포장해 주세요")
    kiosk.order_item("cafe_latte")
    kiosk.end_session()
    assert kiosk.phase is Phase.IDLE
    assert kiosk.order.is_empty and kiosk.order.dining is None and kiosk.order.notes == []
    assert kiosk.drafts == [] and kiosk.view.screen is Screen.ATTRACT


def test_second_start_is_refused(kiosk: Kiosk):
    with pytest.raises(KioskError, match="already"):
        kiosk.start_session()


# --- display -----------------------------------------------------------------------------------


def test_the_whole_menu_shows_its_categories(kiosk: Kiosk):
    shown = kiosk.show_menu()
    assert shown.categories and shown.item_ids == ()
    assert kiosk.view.screen is Screen.CATEGORIES


def test_show_category(kiosk: Kiosk):
    kiosk.show_menu(category="tea_ade")
    assert kiosk.view.title == "티·에이드"
    assert kiosk.view.item_ids == ("green_grape_ade", "chamomile_tea")


def test_assistant_chooses_items_title_and_highlights(kiosk: Kiosk):
    kiosk.show_menu(
        title="오늘의 추천",
        item_ids=["einspanner", "americano", "americano"],
        highlight_ids=["einspanner", "cafe_latte"],
    )
    assert kiosk.view.item_ids == ("einspanner", "americano")
    assert kiosk.view.highlight == ("einspanner",)


def test_at_most_five_items_highlighted_first_then_at_random(menu, cafe):
    kiosk = Kiosk(menu, cafe, rng=random.Random(1))
    kiosk.start_session()
    every = [i.id for i in menu.items]
    shown = kiosk.show_menu(item_ids=every, highlight_ids=["chocolate_cookie", "espresso"])
    assert len(shown.item_ids) == MAX_SHOWN and shown.not_shown == len(every) - MAX_SHOWN
    assert {"chocolate_cookie", "espresso"} <= set(shown.item_ids)
    assert list(shown.item_ids) == [i for i in every if i in shown.item_ids]  # menu order
    picks = {kiosk.show_menu(item_ids=every).item_ids for _ in range(10)}
    assert len(picks) > 1


def test_allergen_filter_is_done_by_code(kiosk: Kiosk):
    shown = kiosk.show_menu(title="우유가 들어가지 않은 메뉴", exclude_allergens=["milk"])
    assert "cafe_latte" not in shown.item_ids and "chocolate_cookie" in shown.removed


def test_show_rejects_unknown_ids(kiosk: Kiosk):
    for kwargs in ({"item_ids": ["pizza"]}, {"category": "food"}, {"exclude_allergens": ["x"]}):
        with pytest.raises(KioskError):
            kiosk.show_menu(**kwargs)
    with pytest.raises(KioskError, match="valid:"):
        kiosk.show_info("sauna")


def test_show_categories_item_info_order(kiosk: Kiosk):
    kiosk.show_categories()
    assert kiosk.view.screen is Screen.CATEGORIES
    kiosk.show_item("cafe_mocha")
    assert (kiosk.view.screen, kiosk.view.item_id, kiosk.view.draft) == (
        Screen.ITEM,
        "cafe_mocha",
        0,
    )
    kiosk.show_info("wifi")
    assert (kiosk.view.screen, kiosk.view.topic) == (Screen.INFO, "wifi")
    kiosk.show_order()
    assert kiosk.view.screen is Screen.REVIEW and not kiosk.review_is_current


# --- choosing drinks: one question at a time ---------------------------------------------------


def test_required_options_one_at_a_time_then_the_first_drinks_extras(kiosk: Kiosk):
    kiosk.set_dining(Dining.TO_GO)
    kiosk.show_menu(category="coffee")
    result = kiosk.order_item("americano", 2)
    assert result.line is None and question(kiosk) == (Ask.OPTION, "americano", "temperature")
    assert (kiosk.view.item_id, kiosk.view.group) == ("americano", "temperature")  # = question
    kiosk.set_options({"temperature": "ice"})
    assert question(kiosk) == (Ask.OPTION, "americano", "size")
    kiosk.set_options({"size": "large"})
    assert question(kiosk) == (Ask.EXTRAS, "americano", "") and kiosk.view.group == EXTRAS
    kiosk.set_options({"shot": "extra_shot"})
    assert kiosk.question.kind is Ask.EXTRAS  # "더 추가하실 거 있으세요?"
    result = kiosk.no_more_extras()
    assert result.line is not None and result.line.option_text == "ICE, Large, 샷 추가"
    assert result.line.quantity == 2
    assert kiosk.question.kind is Ask.MENU and kiosk.view.screen is Screen.MENU  # back


def test_extras_are_asked_once_per_item(kiosk: Kiosk):
    add(kiosk, "americano", temperature="hot", size="regular")
    result = kiosk.order_item("americano", 1, {"temperature": "ice", "size": "regular"})
    assert result.line is not None  # a second americano: added at once
    result = kiosk.order_item("cafe_latte", 1, {"temperature": "hot", "size": "regular"})
    assert result.draft is not None  # another item: its extras are asked
    assert question(kiosk) == (Ask.EXTRAS, "cafe_latte", "")


def test_extras_can_still_be_said_for_later_drinks(kiosk: Kiosk):
    add(kiosk, "americano", temperature="hot", size="regular")  # americano's extras were asked
    line = kiosk.order_item(
        "americano", 1, {"temperature": "ice", "size": "large", "shot": "decaf"}
    )
    assert line.line is not None and line.line.option_text == "ICE, Large, 디카페인"


def test_options_said_together_skip_their_questions(kiosk: Kiosk):
    kiosk.order_item("americano", 1, {"temperature": "hot", "size": "large"})
    assert kiosk.question.kind is Ask.EXTRAS


def test_items_without_options_go_in_at_once(kiosk: Kiosk):
    assert kiosk.order_item("chocolate_cookie").line is not None


def test_no_more_extras_needs_the_required_options(kiosk: Kiosk):
    kiosk.order_item("cafe_latte", 1, {"temperature": "hot"})
    with pytest.raises(KioskError, match="size not chosen yet"):
        kiosk.no_more_extras("cafe_latte")


def test_several_drinks_at_once_each_get_their_answer(kiosk: Kiosk):
    # "아메리카노 아이스로, 그리고 카페라떼는 따뜻한 걸로 주세요"
    kiosk.set_dining(Dining.TO_GO)
    kiosk.order_item("americano", 1, {"temperature": "ice"})
    kiosk.order_item("cafe_latte", 1, {"temperature": "hot"})
    assert question(kiosk) == (Ask.OPTION, "americano", "size")  # in the order they were said
    # "라떼는 레귤러요" while the americano's size is asked: goes to the latte, and the question
    # stays with the americano.
    kiosk.set_options({"size": "regular"}, item_id="cafe_latte")
    assert question(kiosk) == (Ask.OPTION, "americano", "size")
    kiosk.set_options({"size": "large"}, item_id="americano")
    assert question(kiosk) == (Ask.EXTRAS, "americano", "")  # each item's extras, once
    kiosk.no_more_extras("americano")
    assert question(kiosk) == (Ask.EXTRAS, "cafe_latte", "")
    kiosk.no_more_extras("cafe_latte")
    assert kiosk.question.kind is Ask.MENU
    assert sorted(ln.option_text for ln in kiosk.order.lines) == ["HOT, Regular", "ICE, Large"]


def test_one_item_split_into_parts_with_different_options(kiosk: Kiosk):
    # "아메리카노 세 잔이요" - "하나는 차갑게, 두 잔은 따뜻하게"
    add(kiosk, "americano", temperature="hot", size="regular")  # so no extras are asked
    kiosk.order_item("americano", 3)
    kiosk.order_item("americano", 1, {"temperature": "ice"})
    kiosk.order_item("americano", 2, {"temperature": "hot"})
    assert sorted((d.quantity, d.chosen["temperature"][0].id) for d in kiosk.drafts) == [
        (1, "ice"),
        (2, "hot"),
    ]
    # "둘 다 라지요": one answer per part, each goes to a part still missing it.
    kiosk.set_options({"size": "large"}, item_id="americano")
    kiosk.set_options({"size": "large"}, item_id="americano")
    lines = sorted((ln.quantity, ln.option_text) for ln in kiosk.order.lines[1:])
    assert lines == [(1, "ICE, Large"), (2, "HOT, Large")]


def test_another_cup_with_other_options_is_its_own_drink(kiosk: Kiosk):
    kiosk.order_item("americano", 1, {"temperature": "hot"})
    kiosk.order_item("americano", 1, {"temperature": "ice"})  # "차가운 아메리카노도 하나"
    assert len(kiosk.drafts) == 2


def test_ordering_a_drink_being_chosen_again_updates_it(kiosk: Kiosk):
    kiosk.order_item("cafe_latte", None, {"temperature": "hot"})
    kiosk.order_item("cafe_latte", 2, {"size": "large"})
    assert len(kiosk.drafts) == 1
    assert kiosk.drafts[0].quantity == 2 and set(kiosk.drafts[0].chosen) == {"temperature", "size"}


def test_a_late_answer_is_taken(kiosk: Kiosk):
    # The 18:05 log: the temperature was said, recorded only two answers later.
    kiosk.order_item("cafe_latte")
    kiosk.set_options({"size": "regular"})
    assert question(kiosk) == (Ask.OPTION, "cafe_latte", "temperature")
    kiosk.set_options({"size": "regular", "temperature": "hot"})
    assert kiosk.question.kind is Ask.EXTRAS  # not the temperature again


def test_quantity_zero_cancels_a_drink_being_chosen(kiosk: Kiosk):
    kiosk.order_item("cafe_latte")
    kiosk.order_item("americano")
    kiosk.set_options(quantity=0, item_id="cafe_latte")
    assert [d.item.id for d in kiosk.drafts] == ["americano"]
    with pytest.raises(KioskError, match="not being chosen"):
        kiosk.set_options({"size": "large"}, item_id="cafe_latte")


def test_set_options_without_a_drink(kiosk: Kiosk):
    with pytest.raises(KioskError, match="use order"):
        kiosk.set_options({"temperature": "ice"})


def test_an_invalid_choice_changes_nothing(kiosk: Kiosk):
    kiosk.order_item("americano")
    with pytest.raises(KioskError):
        kiosk.order_item("cold_brew", 1, {"temperature": "hot"})
    assert [d.item.id for d in kiosk.drafts] == ["americano"]


# --- changing the order ------------------------------------------------------------------------


def test_changing_a_line_shows_the_changed_option(kiosk: Kiosk):
    kiosk.show_menu(category="coffee")
    add(kiosk, "americano", temperature="ice", size="large")
    kiosk.change_line(1, selection={"size": "regular"})
    view = kiosk.view
    assert (view.item_id, view.line, view.group) == ("americano", 1, "size")
    kiosk.change_line(1, selection={"temperature": "ice", "size": "large"})  # ice: as it was
    assert kiosk.view.group == "size"
    kiosk.change_line(1, selection={"temperature": "hot", "shot": "extra_shot"})
    assert kiosk.view.group == ""  # several: all options at a glance
    assert kiosk.order.line(1).option_text == "HOT, Large, 샷 추가"


def test_change_line_quantity_and_remove(kiosk: Kiosk):
    add(kiosk, "chocolate_cookie")
    kiosk.change_line(1, quantity=4)
    assert kiosk.order.line(1).quantity == 4
    assert kiosk.change_line(1, quantity=0) is None and kiosk.order.is_empty


def test_cancel_order(kiosk: Kiosk):
    order_ready(kiosk)
    kiosk.cancel_order()
    assert kiosk.order.is_empty and kiosk.phase is Phase.ORDERING
    assert kiosk.question.kind is Ask.DINING


# --- going back --------------------------------------------------------------------------------


def test_back_from_the_size_question_shows_the_temperature_again(kiosk: Kiosk):
    kiosk.set_dining(Dining.HERE)
    kiosk.order_item("cafe_latte")
    kiosk.set_options({"temperature": "ice"})
    assert kiosk.view.group == "size"
    kiosk.go_back()
    assert question(kiosk) == (Ask.OPTION, "cafe_latte", "temperature")
    assert kiosk.view.group == "temperature"
    assert "temperature" in kiosk.drafts[0].chosen  # kept: going back changes nothing
    kiosk.set_options({"temperature": "hot"})  # changed there
    assert question(kiosk) == (Ask.OPTION, "cafe_latte", "size")


def test_back_to_an_added_drink_shows_its_line(kiosk: Kiosk):
    kiosk.set_dining(Dining.HERE)
    kiosk.show_categories()
    kiosk.show_menu(category="latte")
    add(kiosk, "cafe_latte", temperature="hot", size="regular")
    assert kiosk.view.screen is Screen.MENU
    view = kiosk.go_back()
    assert (view.item_id, view.line, view.draft) == ("cafe_latte", 1, 0)
    assert kiosk.question.kind is Ask.LINE
    kiosk.change_line(1, selection={"size": "large"})
    assert kiosk.order.line(1).option_text == "HOT, Large"


def test_back_to_a_named_screen(kiosk: Kiosk):
    kiosk.set_dining(Dining.HERE)
    add(kiosk, "cafe_latte", temperature="hot", size="regular")
    kiosk.show_categories()
    kiosk.show_info("wifi")
    view = kiosk.go_back("cafe_latte")  # "아까 라떼 화면 보여 주세요"
    assert view.item_id == "cafe_latte" and view.line == 1
    with pytest.raises(KioskError, match="was not shown"):
        kiosk.go_back("einspanner")


def test_going_back_changes_nothing_in_the_order(kiosk: Kiosk):
    kiosk.show_categories()
    kiosk.show_menu(category="dessert")
    add(kiosk, "chocolate_cookie")
    before = kiosk.order.lines_signature
    assert kiosk.go_back().screen is Screen.CATEGORIES
    assert kiosk.order.lines_signature == before
    with pytest.raises(KioskError, match="no previous screen"):
        kiosk.go_back()


# --- notes, review and payment -----------------------------------------------------------------


def test_notes_for_the_staff(kiosk: Kiosk):
    kiosk.add_note("  아메리카노는 포장, 카페모카는 매장에서  ")
    kiosk.add_note("아메리카노는 포장, 카페모카는 매장에서")
    assert kiosk.order.notes == ["아메리카노는 포장, 카페모카는 매장에서"]
    with pytest.raises(KioskError, match="empty"):
        kiosk.add_note("   ")


def test_paying_asks_the_staff_question_then_reads_back(kiosk: Kiosk):
    order_ready(kiosk)
    assert kiosk.request_payment() is Ask.STAFF
    assert kiosk.question.kind is Ask.STAFF and kiosk.view.screen is Screen.REVIEW
    assert kiosk.request_payment() is Ask.REVIEW
    assert kiosk.read_back == (
        "주문 확인해 드릴게요. 차가운 아메리카노 레귤러 1잔, 포장으로 총 사천 원입니다."
    )
    assert kiosk.review_is_current


def test_paying_needs_the_drinks_finished(kiosk: Kiosk):
    with pytest.raises(KioskError, match="empty"):
        kiosk.request_payment()
    order_ready(kiosk)
    kiosk.order_item("cafe_latte")
    with pytest.raises(KioskError, match="still being chosen"):
        kiosk.request_payment()
    assert question(kiosk) == (Ask.OPTION, "cafe_latte", "temperature")


def test_a_change_after_the_read_back_needs_a_new_one(kiosk: Kiosk):
    order_ready(kiosk)
    kiosk.request_payment()
    kiosk.request_payment()
    add(kiosk, "chocolate_cookie")
    assert not kiosk.review_is_current and kiosk.question.kind is Ask.MENU
    with pytest.raises(KioskError, match="read the order back"):
        kiosk.start_payment()
    assert kiosk.request_payment() is Ask.REVIEW  # the staff question was asked already


def test_payment_steps_to_done_with_an_order_number(menu, cafe):
    kiosk = Kiosk(menu, cafe, first_order_number=101)
    kiosk.start_session()
    order_ready(kiosk)
    kiosk.request_payment()
    kiosk.request_payment()
    kiosk.start_payment()
    assert (kiosk.phase, kiosk.payment_step) == (Phase.PAYING, PaymentStep.INSERT_CARD)
    assert kiosk.view.screen is Screen.PAYMENT and kiosk.question.kind is Ask.NONE
    kiosk.advance_payment()
    assert kiosk.payment_step is PaymentStep.PROCESSING
    kiosk.advance_payment()
    assert (kiosk.phase, kiosk.order_number) == (Phase.DONE, 101)
    assert kiosk.view.screen is Screen.DONE
    kiosk.show_info("pickup")  # "어디서 받아요?"
    with pytest.raises(KioskError, match="done"):
        kiosk.order_item("chocolate_cookie")


def test_order_is_locked_while_paying(kiosk: Kiosk):
    order_ready(kiosk)
    kiosk.request_payment()
    kiosk.request_payment()
    kiosk.start_payment()
    for change in (
        lambda: kiosk.order_item("chocolate_cookie"),
        lambda: kiosk.change_line(1, quantity=2),
        lambda: kiosk.cancel_order(),
        lambda: kiosk.show_menu(),
        lambda: kiosk.go_back(),
    ):
        with pytest.raises(KioskError, match="paying"):
            change()


def test_cancel_payment_only_before_processing(kiosk: Kiosk):
    order_ready(kiosk)
    kiosk.request_payment()
    kiosk.request_payment()
    kiosk.start_payment()
    kiosk.cancel_payment()
    assert kiosk.phase is Phase.ORDERING and kiosk.view.screen is Screen.REVIEW
    kiosk.start_payment()  # the read-back is still current
    kiosk.advance_payment()
    with pytest.raises(KioskError, match="already"):
        kiosk.cancel_payment()
