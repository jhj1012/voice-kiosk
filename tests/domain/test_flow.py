import pytest

from kiosk.domain.flow import Kiosk, PaymentStep, Phase, Screen
from kiosk.domain.menu import KioskError
from kiosk.domain.order import Dining


def order_ready(kiosk: Kiosk) -> None:
    kiosk.choose_item("americano", selection={"temperature": "ice", "size": "regular"})
    kiosk.set_dining(Dining.TO_GO)


# --- session -----------------------------------------------------------------------------------


def test_idle_kiosk_refuses_orders(menu, cafe):
    kiosk = Kiosk(menu, cafe)
    assert kiosk.phase is Phase.IDLE
    assert kiosk.view.screen is Screen.ATTRACT
    with pytest.raises(KioskError, match="idle"):
        kiosk.choose_item("americano")


def test_session_starts_with_welcome_and_hanging_up_clears_everything(kiosk: Kiosk):
    assert kiosk.phase is Phase.ORDERING
    assert kiosk.view.screen is Screen.WELCOME
    order_ready(kiosk)
    kiosk.choose_item("cafe_latte")  # pending
    kiosk.end_session()
    assert kiosk.phase is Phase.IDLE
    assert kiosk.order.is_empty and kiosk.order.dining is None
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
    assert kiosk.view.title == "메뉴"
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


def test_show_item_and_info(kiosk: Kiosk):
    kiosk.show_item("cafe_mocha")
    assert (kiosk.view.screen, kiosk.view.item_id) == (Screen.ITEM, "cafe_mocha")
    kiosk.show_info("wifi")
    assert (kiosk.view.screen, kiosk.view.topic) == (Screen.INFO, "wifi")
    with pytest.raises(KioskError, match="valid:"):
        kiosk.show_info("sauna")


# --- choosing items ----------------------------------------------------------------------------


def test_item_with_all_required_options_is_added_at_once(kiosk: Kiosk):
    kiosk.show_menu(category="coffee")
    result = kiosk.choose_item(
        "americano", quantity=2, selection={"temperature": "ice", "size": "large"}
    )
    assert result.line is not None and result.line.quantity == 2
    assert kiosk.pending is None
    assert kiosk.view.screen is Screen.MENU  # back to where the customer was


def test_missing_required_options_are_asked_then_added(kiosk: Kiosk):
    result = kiosk.choose_item("americano", selection={"size": "large"})
    assert result.line is None
    assert [g.id for g in result.missing] == ["temperature"]
    assert (kiosk.view.screen, kiosk.view.item_id) == (Screen.ITEM, "americano")
    result = kiosk.set_options({"temperature": "hot"}, quantity=3)
    assert result.line is not None
    assert result.line.option_text == "HOT, Large"
    assert result.line.quantity == 3
    assert kiosk.pending is None


def test_items_without_required_options_need_no_question(kiosk: Kiosk):
    assert kiosk.choose_item("chocolate_cookie").line is not None
    assert kiosk.choose_item("cold_brew", selection={"temperature": "ice"}).missing[0].id == "size"


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


def test_change_line_options_keeps_the_other_choices(kiosk: Kiosk):
    kiosk.choose_item("americano", selection={"temperature": "ice", "size": "large"})
    line = kiosk.change_line(1, selection={"shot": "extra_shot"})
    assert line is not None
    assert line.option_text == "ICE, Large, 샷 추가"


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
    assert kiosk.view.screen is Screen.WELCOME


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
    kiosk.choose_item("chocolate_cookie")  # the order changed after the review
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
