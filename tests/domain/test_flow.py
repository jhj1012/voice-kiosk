import pytest

from kiosk.domain.flow import EXTRAS, Kiosk, PaymentStep, Phase, Screen
from kiosk.domain.menu import KioskError
from kiosk.domain.order import CartLine, Dining


def add(kiosk: Kiosk, item_id: str, quantity: int = 1, **selection: str) -> CartLine:
    """Choose an item with its options and say no to the extras."""
    result = kiosk.choose_item(item_id, quantity=quantity, selection=selection)
    if result.line is None:
        result = kiosk.finish_item(item_id)
    assert result.line is not None
    return result.line


def order_ready(kiosk: Kiosk) -> None:
    add(kiosk, "americano", temperature="ice", size="regular")
    kiosk.set_dining(Dining.TO_GO)


# --- session -----------------------------------------------------------------------------------


def test_idle_kiosk_refuses_orders(menu, cafe):
    kiosk = Kiosk(menu, cafe)
    assert kiosk.phase is Phase.IDLE
    assert kiosk.view.screen is Screen.ATTRACT
    with pytest.raises(KioskError, match="idle"):
        kiosk.choose_item("americano")


def test_session_starts_with_the_take_out_question_and_hanging_up_clears_everything(
    kiosk: Kiosk,
):
    assert kiosk.phase is Phase.ORDERING
    assert kiosk.view.screen is Screen.DINING  # "매장에서 드시고 가세요, 포장하세요?"
    kiosk.set_dining(Dining.HERE)
    assert kiosk.view.screen is Screen.WELCOME
    order_ready(kiosk)
    kiosk.add_note("케이크는 포장해 주세요")
    kiosk.choose_item("cafe_latte")  # pending
    kiosk.end_session()
    assert kiosk.phase is Phase.IDLE
    assert kiosk.order.is_empty and kiosk.order.dining is None and kiosk.order.notes == []
    assert kiosk.pending is None
    assert kiosk.view.screen is Screen.ATTRACT


def test_second_start_is_refused(kiosk: Kiosk):
    with pytest.raises(KioskError, match="already"):
        kiosk.start_session()


def test_every_change_increases_the_revision(kiosk: Kiosk):
    before = kiosk.revision
    kiosk.show_menu(category="coffee")
    assert kiosk.revision > before


# --- display -----------------------------------------------------------------------------------


def test_show_whole_menu_or_category(kiosk: Kiosk, menu):
    shown = kiosk.show_menu()
    assert shown.item_ids == tuple(i.id for i in menu.items)
    assert kiosk.view.title == ""  # no heading unless the assistant gives one
    kiosk.show_menu(category="tea_ade")
    assert kiosk.view.title == "티·에이드"
    assert kiosk.view.item_ids == ("green_grape_ade", "chamomile_tea")


def test_assistant_chooses_items_title_and_highlights(kiosk: Kiosk):
    kiosk.show_menu(
        title="오늘의 추천",
        item_ids=["einspanner", "americano", "americano"],
        highlight_ids=["einspanner", "cafe_latte"],
    )
    assert kiosk.view.screen is Screen.MENU
    assert kiosk.view.title == "오늘의 추천"
    assert kiosk.view.item_ids == ("einspanner", "americano")  # duplicates dropped
    assert kiosk.view.highlight == ("einspanner",)  # only highlights that are shown


def test_allergen_filter_is_done_by_code(kiosk: Kiosk):
    shown = kiosk.show_menu(title="우유가 들어가지 않은 메뉴", exclude_allergens=["milk"])
    assert "cafe_latte" not in shown.item_ids
    assert "chocolate_cookie" in shown.removed
    assert set(shown.item_ids) == {
        "espresso",
        "americano",
        "cold_brew",
        "green_grape_ade",
        "chamomile_tea",
    }


def test_show_menu_rejects_unknown_ids(kiosk: Kiosk):
    for kwargs in ({"item_ids": ["pizza"]}, {"category": "food"}, {"exclude_allergens": ["x"]}):
        with pytest.raises(KioskError):
            kiosk.show_menu(**kwargs)


def test_show_categories(kiosk: Kiosk):
    kiosk.show_categories()
    assert kiosk.view.screen is Screen.CATEGORIES


def test_show_item_and_info(kiosk: Kiosk):
    kiosk.show_item("cafe_mocha")
    assert (kiosk.view.screen, kiosk.view.item_id) == (Screen.ITEM, "cafe_mocha")
    kiosk.show_info("wifi")
    assert (kiosk.view.screen, kiosk.view.topic) == (Screen.INFO, "wifi")
    with pytest.raises(KioskError, match="valid:"):
        kiosk.show_info("sauna")


# --- choosing items ----------------------------------------------------------------------------


def test_options_are_asked_one_at_a_time_then_the_extras(kiosk: Kiosk):
    kiosk.show_menu(category="coffee")
    result = kiosk.choose_item("americano", quantity=2)
    assert result.line is None and result.pending is not None
    assert result.pending.asking == "temperature"  # one question at a time
    assert (kiosk.view.item_id, kiosk.view.group) == ("americano", "temperature")
    kiosk.set_options({"temperature": "ice"})
    assert kiosk.view.group == "size"
    result = kiosk.set_options({"size": "large"})
    assert result.line is None and kiosk.view.group == EXTRAS  # "추가하실 거 있으세요?"
    kiosk.set_options({"shot": "extra_shot"})
    assert kiosk.view.group == EXTRAS  # "더 추가하실 거 있으세요?"
    result = kiosk.finish_item()
    assert result.line is not None and result.line.quantity == 2
    assert result.line.option_text == "ICE, Large, 샷 추가"
    assert kiosk.pending is None
    assert kiosk.view.screen is Screen.MENU  # back to where the customer was


def test_options_said_at_once_skip_to_the_extras(kiosk: Kiosk):
    result = kiosk.choose_item("americano", selection={"temperature": "hot", "size": "large"})
    assert result.line is None and result.pending is not None
    assert result.pending.asking == EXTRAS
    with pytest.raises(KioskError, match="ask for size"):
        kiosk.choose_item("cafe_latte", selection={"temperature": "hot"})
        kiosk.finish_item("cafe_latte")


def test_items_without_extras_are_added_once_the_required_options_are_known(kiosk: Kiosk):
    assert kiosk.choose_item("chocolate_cookie").line is not None  # nothing to ask
    result = kiosk.choose_item("cold_brew", selection={"temperature": "ice"})
    assert result.pending is not None and result.pending.asking == "size"


def test_invalid_choice_keeps_the_previous_pending_item(kiosk: Kiosk):
    kiosk.choose_item("americano")
    with pytest.raises(KioskError):
        kiosk.choose_item("cold_brew", selection={"temperature": "hot"})
    assert kiosk.pending is not None and kiosk.pending.item.id == "americano"


def test_set_options_without_pending_item(kiosk: Kiosk):
    with pytest.raises(KioskError, match="choose_item"):
        kiosk.set_options({"temperature": "ice"})


def test_cancel_item(kiosk: Kiosk):
    kiosk.choose_item("americano")
    kiosk.cancel_item()
    assert kiosk.pending is None
    assert kiosk.order.is_empty


def test_choosing_another_item_replaces_the_pending_one(kiosk: Kiosk):
    kiosk.choose_item("americano")
    kiosk.choose_item("cafe_latte")
    assert kiosk.pending is not None and kiosk.pending.item.id == "cafe_latte"


# --- changing the order ------------------------------------------------------------------------


def test_change_line_options_keeps_the_other_choices_and_shows_the_option(kiosk: Kiosk):
    kiosk.show_menu(category="coffee")
    add(kiosk, "americano", temperature="ice", size="large")
    line = kiosk.change_line(1, selection={"size": "regular"})
    assert line is not None
    assert line.option_text == "ICE, Regular"
    # The size choices are on screen again, the new one marked (display: from the line).
    view = kiosk.view
    assert (view.screen, view.item_id, view.line, view.group) == (
        Screen.ITEM,
        "americano",
        1,
        "size",
    )
    kiosk.change_line(1, selection={"temperature": "ice", "size": "large"})  # ice: as it was
    assert kiosk.view.group == "size"
    kiosk.change_line(1, selection={"temperature": "hot", "shot": "extra_shot", "size": "regular"})
    assert kiosk.view.group == ""  # several changed: all options at a glance
    assert kiosk.order.line(1).option_text == "HOT, Regular, 샷 추가"


def test_edit_line_shows_an_ordered_item_again(kiosk: Kiosk):
    add(kiosk, "chocolate_cookie")
    add(kiosk, "cafe_latte", temperature="hot", size="regular")
    kiosk.edit_line(2)
    assert (kiosk.view.item_id, kiosk.view.line, kiosk.view.group) == ("cafe_latte", 2, "")
    kiosk.edit_line(2, "size")
    assert kiosk.view.group == "size"
    with pytest.raises(KioskError, match="has no size option"):
        kiosk.edit_line(1, "size")
    kiosk.change_line(1, quantity=0)  # removing the cookie renumbers the latte
    kiosk.edit_line(1, "temperature")
    kiosk.change_line(1, quantity=2)
    assert (kiosk.view.line, kiosk.view.group) == (1, "temperature")


def test_go_back_returns_to_the_previous_screens(kiosk: Kiosk):
    kiosk.set_dining(Dining.HERE)
    kiosk.show_categories()
    kiosk.show_menu(category="latte")
    kiosk.choose_item("cafe_latte")
    kiosk.set_options({"temperature": "hot"})  # option steps of one item are one screen
    kiosk.set_options({"size": "large"})
    kiosk.finish_item()
    assert kiosk.view.screen is Screen.MENU
    # Back to the latte, now an order line: its options at a glance.
    view = kiosk.go_back()
    assert (view.screen, view.item_id, view.line, view.group) == (Screen.ITEM, "cafe_latte", 1, "")
    assert kiosk.go_back().screen is Screen.MENU
    assert kiosk.go_back().screen is Screen.CATEGORIES
    with pytest.raises(KioskError, match="no previous screen"):
        kiosk.go_back()


def test_go_back_to_an_item_still_being_chosen(kiosk: Kiosk):
    kiosk.choose_item("americano", selection={"temperature": "ice"})
    kiosk.show_info("wifi")  # "와이파이 비번 뭐예요?" in between
    view = kiosk.go_back()
    assert (view.item_id, view.group, view.line) == ("americano", "size", 0)


def test_notes_for_the_staff(kiosk: Kiosk):
    kiosk.add_note("  아메리카노는 포장, 카페모카는 매장에서  ")
    kiosk.add_note("아메리카노는 포장, 카페모카는 매장에서")  # the same note once
    assert kiosk.order.notes == ["아메리카노는 포장, 카페모카는 매장에서"]
    with pytest.raises(KioskError, match="empty"):
        kiosk.add_note("   ")


def test_the_staff_question_comes_once_before_the_review(kiosk: Kiosk):
    order_ready(kiosk)
    assert kiosk.ask_staff_question()
    assert kiosk.view.screen is Screen.REVIEW  # the order is on screen meanwhile
    assert not kiosk.ask_staff_question()
    kiosk.review()


def test_paying_without_dining_shows_the_take_out_question(kiosk: Kiosk):
    add(kiosk, "chocolate_cookie")
    with pytest.raises(KioskError, match="eats here or takes out"):
        kiosk.review()
    assert kiosk.view.screen is Screen.DINING


def test_change_line_quantity_and_remove(kiosk: Kiosk):
    kiosk.choose_item("chocolate_cookie")
    kiosk.change_line(1, quantity=4)
    assert kiosk.order.line(1).quantity == 4
    assert kiosk.change_line(1, quantity=0) is None
    assert kiosk.order.is_empty


def test_cancel_order(kiosk: Kiosk):
    order_ready(kiosk)
    kiosk.cancel_order()
    assert kiosk.order.is_empty
    assert kiosk.phase is Phase.ORDERING
    assert kiosk.view.screen is Screen.DINING


# --- review and payment ------------------------------------------------------------------------


def test_review_needs_items_dining_and_no_pending_item(kiosk: Kiosk):
    with pytest.raises(KioskError, match="empty"):
        kiosk.review()
    kiosk.choose_item("chocolate_cookie")
    with pytest.raises(KioskError, match="eats here or takes out"):
        kiosk.review()
    kiosk.set_dining(Dining.HERE)
    kiosk.choose_item("americano")
    with pytest.raises(KioskError, match="still being chosen"):
        kiosk.review()


def test_review_returns_the_read_back_and_shows_it(kiosk: Kiosk):
    order_ready(kiosk)
    read_back = kiosk.review()
    assert (
        read_back
        == "주문 확인해 드릴게요. 아이스 아메리카노 레귤러 1잔, 포장으로 총 4,000원입니다."
    )
    assert kiosk.view.screen is Screen.REVIEW
    assert kiosk.review_is_current


def test_payment_needs_a_current_review(kiosk: Kiosk):
    order_ready(kiosk)
    with pytest.raises(KioskError, match="review"):
        kiosk.start_payment()
    kiosk.review()
    add(kiosk, "chocolate_cookie")  # the order changed after the review
    assert not kiosk.review_is_current
    with pytest.raises(KioskError, match="review"):
        kiosk.start_payment()


def test_payment_steps_to_done_with_an_order_number(menu, cafe):
    kiosk = Kiosk(menu, cafe, first_order_number=101)
    kiosk.start_session()
    order_ready(kiosk)
    kiosk.review()
    kiosk.start_payment()
    assert (kiosk.phase, kiosk.payment_step) == (Phase.PAYING, PaymentStep.INSERT_CARD)
    assert kiosk.view.screen is Screen.PAYMENT
    kiosk.advance_payment()
    assert kiosk.payment_step is PaymentStep.PROCESSING
    kiosk.advance_payment()
    assert (kiosk.phase, kiosk.payment_step) == (Phase.DONE, PaymentStep.APPROVED)
    assert kiosk.order_number == 101
    assert kiosk.view.screen is Screen.DONE


def test_order_is_locked_while_paying(kiosk: Kiosk):
    order_ready(kiosk)
    kiosk.review()
    kiosk.start_payment()
    for change in (
        lambda: kiosk.choose_item("chocolate_cookie"),
        lambda: kiosk.change_line(1, quantity=2),
        lambda: kiosk.cancel_order(),
        lambda: kiosk.show_menu(),
    ):
        with pytest.raises(KioskError, match="paying"):
            change()


def test_cancel_payment_only_before_processing(kiosk: Kiosk):
    order_ready(kiosk)
    kiosk.review()
    kiosk.start_payment()
    kiosk.cancel_payment()
    assert kiosk.phase is Phase.ORDERING
    assert kiosk.view.screen is Screen.REVIEW
    kiosk.start_payment()  # the review is still current: nothing changed
    kiosk.advance_payment()
    with pytest.raises(KioskError, match="already"):
        kiosk.cancel_payment()


def test_after_payment_only_info_is_shown(kiosk: Kiosk):
    order_ready(kiosk)
    kiosk.review()
    kiosk.start_payment()
    kiosk.advance_payment()
    kiosk.advance_payment()
    kiosk.show_info("pickup")  # "어디서 받아요?"
    with pytest.raises(KioskError, match="done"):
        kiosk.choose_item("chocolate_cookie")


def test_show_order_does_not_count_as_a_review(kiosk: Kiosk):
    order_ready(kiosk)
    kiosk.show_order()
    assert kiosk.view.screen is Screen.REVIEW
    assert not kiosk.review_is_current


def test_several_items_can_wait_for_options(kiosk: Kiosk):
    kiosk.choose_item("chocolate_cookie")
    kiosk.set_dining(Dining.TO_GO)
    kiosk.choose_item("green_grape_ade")
    kiosk.choose_item("americano", selection={"temperature": "ice"})
    assert [p.item.id for p in kiosk.pending_items] == ["green_grape_ade", "americano"]
    assert kiosk.view.item_id == "americano"  # the screen shows the one touched last
    with pytest.raises(KioskError, match="still being chosen: green_grape_ade, americano"):
        kiosk.review()
    kiosk.set_options({"size": "large"}, item_id="green_grape_ade")
    result = kiosk.finish_item("green_grape_ade")
    assert result.line is not None and result.line.item.id == "green_grape_ade"
    assert kiosk.view.item_id == "americano"  # the next one still waiting
    kiosk.set_options({"size": "large"})  # the last one by default
    assert kiosk.finish_item().line is not None
    assert kiosk.pending_items == []
    assert len(kiosk.order.lines) == 3


def test_choosing_a_waiting_item_again_starts_it_over(kiosk: Kiosk):
    kiosk.choose_item("cafe_latte", selection={"temperature": "hot"})
    kiosk.choose_item("cafe_latte")
    assert len(kiosk.pending_items) == 1
    assert kiosk.pending is not None and kiosk.pending.chosen == {}


def test_cancel_one_of_the_waiting_items(kiosk: Kiosk):
    kiosk.choose_item("cafe_latte")
    kiosk.choose_item("americano")
    kiosk.cancel_item("cafe_latte")
    assert [p.item.id for p in kiosk.pending_items] == ["americano"]
    with pytest.raises(KioskError, match="not being chosen"):
        kiosk.set_options({"size": "large"}, item_id="cafe_latte")
