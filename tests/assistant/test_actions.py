import pytest

from kiosk.assistant.actions import (
    ANYTHING_ELSE,
    ASK_STAFF,
    DINING_QUESTION,
    MENU_BOARD,
    NOTED,
    STAFF_QUESTION,
    Actions,
)
from kiosk.domain.flow import Kiosk, Phase, Screen


@pytest.fixture
def actions(kiosk: Kiosk) -> Actions:
    return Actions(kiosk)


def test_every_result_says_the_next_question(actions: Actions):
    assert actions.call("show", {"what": "categories"})["ask"] == DINING_QUESTION
    assert actions.call("set_dining", {"dining": "to_go"}) == {"dining": "포장", "ask": MENU_BOARD}


def test_options_are_asked_one_at_a_time_without_choices_or_prices(actions: Actions):
    actions.call("set_dining", {"dining": "here"})
    result = actions.call("order", {"item_id": "americano", "quantity": 2.0})
    assert result == {
        "being_chosen": "아메리카노 2잔",
        "ask": "아메리카노는 따뜻하게 드릴까요, 차갑게 드릴까요?",
    }
    result = actions.call("set_options", {"temperature": "ice"})
    assert result["ask"] == "아메리카노 사이즈는 어떤 걸로 해 드릴까요?"
    result = actions.call("set_options", {"size": "large"})
    assert result["ask"] == "아메리카노에 추가하실 거 있으세요?" and "extras_note" in result
    actions.call("set_options", {"syrup": "vanilla"})
    result = actions.call("no_more_extras", {})
    assert result == {
        "added": "차가운 아메리카노 라지(바닐라 시럽) 2잔",
        "order": ["1. 차가운 아메리카노 라지(바닐라 시럽) 2잔 10,000원"],
        "total": "10,000원",
        "ask": ANYTHING_ELSE,
    }


def test_two_items_in_one_sentence(actions: Actions):
    # "아메리카노 아이스로, 그리고 카페라떼는 따뜻한 걸로 주세요": two calls in one turn.
    actions.call("order", {"item_id": "americano", "temperature": "ice"})
    result = actions.call("order", {"item_id": "cafe_latte", "temperature": "hot"})
    assert result["ask"] == "아메리카노 사이즈는 어떤 걸로 해 드릴까요?"  # in the order said
    whats = [d["what"] for d in result["being_chosen"]]
    assert whats == ["차가운 아메리카노 1잔", "따뜻한 카페라떼 1잔"]
    # "둘 다 라지요"
    actions.call("set_options", {"item_id": "americano", "size": "large"})
    result = actions.call("set_options", {"item_id": "cafe_latte", "size": "large"})
    assert result["added"] == "따뜻한 카페라떼 라지 1잔"  # not the first item: no extras


def test_parts_of_one_item_are_named_by_their_options(actions: Actions):
    actions.call("order", {"item_id": "chocolate_cookie"})
    actions.call("order", {"item_id": "americano", "quantity": 3})
    actions.call("order", {"item_id": "americano", "quantity": 1, "temperature": "ice"})
    result = actions.call("order", {"item_id": "americano", "quantity": 2, "temperature": "hot"})
    assert result["ask"] == "따뜻한 아메리카노 사이즈는 어떤 걸로 해 드릴까요?"  # the first part
    assert [d["draft"] for d in result["being_chosen"]] == [2, 3]


def test_quantity_zero_cancels_an_item_being_chosen(actions: Actions):
    actions.call("order", {"item_id": "cafe_latte"})
    result = actions.call("set_options", {"item_id": "cafe_latte", "quantity": 0})
    assert result["cancelled"] == "카페라떼" and result["order"] == []


def test_mistakes_come_back_as_errors(actions: Actions):
    assert "error" in actions.call("order", {"item_id": "pizza"})
    assert "error" in actions.call("order", {"item_id": "americano", "quantity": 1.5})
    assert "error" in actions.call("set_dining", {"dining": "car"})
    assert "error" in actions.call("show", {"what": "nothing"})
    assert actions.call("fly", {}) == {"error": "unknown function 'fly'"}


def test_change_reports_what_was_removed(actions: Actions):
    actions.call("order", {"item_id": "chocolate_cookie", "quantity": 2})
    result = actions.call("change", {"line": 1, "quantity": 0})
    assert result["removed"] == "초코 쿠키 2개" and result["order"] == []


def test_show_menu_reports_items_left_out(actions: Actions):
    result = actions.call(
        "show",
        {
            "what": "menu",
            "title": "우유 없는 디저트",
            "category": "dessert",
            "exclude_allergens": ["milk"],
        },
    )
    assert result["shown"] == []
    assert result["left_out_for_allergens"] == ["바닐라 아이스크림", "초코 쿠키"]


def test_show_item_gives_the_description_to_say(actions: Actions):
    result = actions.call("show", {"what": "item", "item_id": "green_grape_ade"})
    assert result["shown"] == "청포도 에이드" and result["description"]


def test_show_info_returns_the_text(actions: Actions):
    result = actions.call("show", {"what": "info", "topic": "wifi"})
    assert result["shown"] == "와이파이" and "sori1234" in result["text"]


def test_going_back_to_an_order_line(actions: Actions, kiosk: Kiosk):
    actions.call("show", {"what": "menu", "category": "latte"})
    actions.call("order", {"item_id": "cafe_latte", "temperature": "hot", "size": "regular"})
    actions.call("no_more_extras", {})
    result = actions.call("go_back", {"to": "cafe_latte"})
    assert result["shown"] == "1번 주문 카페라떼"
    assert result["line_shown"] == "1. 따뜻한 카페라떼 레귤러 1잔"
    assert result["options"]["사이즈"] == "레귤러" and "change" in result["note"]
    assert "error" in actions.call("go_back", {"to": "einspanner"})


def test_note_for_staff(actions: Actions):
    result = actions.call("note_for_staff", {"text": "아메리카노는 포장, 카페모카는 매장에서"})
    assert result["noted"] == "아메리카노는 포장, 카페모카는 매장에서" and result["say"] == NOTED
    assert "error" in actions.call("note_for_staff", {"text": " "})


def test_pay_asks_for_what_is_missing_then_the_staff_then_reads_back(
    actions: Actions, kiosk: Kiosk
):
    actions.call("order", {"item_id": "chocolate_cookie"})
    result = actions.call("pay", {})
    assert "not_yet" in result and result["ask"] == DINING_QUESTION
    assert kiosk.view.screen is Screen.DINING
    actions.call("set_dining", {"dining": "here"})
    assert actions.call("pay", {}) == {"ask_first": STAFF_QUESTION, "next": ASK_STAFF}
    result = actions.call("pay", {})
    assert result["read_back"] == (
        "주문 확인해 드릴게요. 초코 쿠키 1개, 매장에서 드시고 총 2,500원입니다."
    )
    assert kiosk.review_is_current and kiosk.phase is Phase.ORDERING  # the session goes on


def test_pay_with_an_item_still_being_chosen(actions: Actions):
    actions.call("order", {"item_id": "chocolate_cookie"})
    actions.call("set_dining", {"dining": "here"})
    actions.call("order", {"item_id": "cafe_latte"})
    result = actions.call("pay", {})
    assert "not_yet" in result and result["ask"].startswith("카페라떼는 따뜻하게")


def test_cancel_order_stops_a_payment_or_cancels_everything(actions: Actions, kiosk: Kiosk):
    actions.call("order", {"item_id": "chocolate_cookie"})
    actions.call("set_dining", {"dining": "here"})
    actions.call("pay", {})
    actions.call("pay", {})
    kiosk.start_payment()
    assert actions.call("cancel_order", {})["payment_stopped"] is True
    assert kiosk.phase is Phase.ORDERING and not kiosk.order.is_empty
    assert actions.call("cancel_order", {})["cancelled"] == "주문 전체"
    assert kiosk.order.is_empty


def test_every_declared_function_has_a_handler(actions: Actions, menu, cafe):
    from kiosk.assistant.tools import STAY_QUIET, function_declarations

    declared = {d["name"] for d in function_declarations(menu, cafe)}
    assert declared == actions.names | {STAY_QUIET}  # stay_quiet: the session mutes the turn
