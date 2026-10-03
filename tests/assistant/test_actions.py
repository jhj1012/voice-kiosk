import pytest

from kiosk.assistant.actions import Actions
from kiosk.domain.flow import Kiosk, Phase


@pytest.fixture
def actions(kiosk: Kiosk) -> Actions:
    return Actions(kiosk)


def test_choose_item_with_all_options_adds_it(actions: Actions):
    result = actions.call(
        "choose_item",
        {"item_id": "americano", "quantity": 2.0, "temperature": "ice", "size": "large"},
    )
    assert result == {
        "added": "아이스 아메리카노 라지 2잔",
        "order": ["1. 아이스 아메리카노 라지 2잔 9,000원"],
        "total": "9,000원",
    }


def test_missing_options_come_back_as_questions(actions: Actions):
    result = actions.call("choose_item", {"item_id": "cafe_latte"})
    assert result == {
        "not_added_yet": "카페라떼",
        "ask": [
            {"option": "온도", "choices": ["따뜻한", "아이스"]},
            {"option": "사이즈", "choices": ["레귤러", "라지 (+500원)"]},
        ],
    }
    result = actions.call("set_options", {"temperature": "hot", "size": "regular"})
    assert result["added"] == "따뜻한 카페라떼 레귤러 1잔"


def test_mistakes_come_back_as_errors(actions: Actions):
    assert "error" in actions.call("choose_item", {"item_id": "pizza"})
    assert "error" in actions.call("choose_item", {"item_id": "americano", "quantity": 1.5})
    assert "error" in actions.call("set_dining", {"dining": "car"})
    assert actions.call("fly", {}) == {"error": "unknown function 'fly'"}


def test_change_line_reports_what_was_removed(actions: Actions):
    actions.call("choose_item", {"item_id": "chocolate_cookie", "quantity": 2})
    result = actions.call("change_line", {"line": 1, "quantity": 0})
    assert result == {"removed": "초코 쿠키 2개", "order": [], "total": "0원"}


def test_show_menu_reports_items_left_out(actions: Actions):
    result = actions.call(
        "show_menu",
        {"title": "우유 없는 디저트", "category": "dessert", "exclude_allergens": ["milk"]},
    )
    assert result == {"shown": [], "left_out_for_allergens": ["바닐라 아이스크림", "초코 쿠키"]}


def test_show_info_returns_the_text(actions: Actions):
    result = actions.call("show_info", {"topic": "wifi"})
    assert result["shown"] == "와이파이"
    assert "sori1234" in result["text"]


def test_review_and_payment(actions: Actions, kiosk: Kiosk):
    actions.call("choose_item", {"item_id": "chocolate_cookie"})
    assert "error" in actions.call("start_payment", {})
    actions.call("set_dining", {"dining": "here"})
    result = actions.call("review_order", {})
    assert result == {
        "read_back": "주문 확인해 드릴게요. 초코 쿠키 1개, 매장에서 드시고 총 2,500원입니다."
    }
    assert "status" in actions.call("start_payment", {})
    assert kiosk.phase is Phase.PAYING
    assert actions.call("cancel_payment", {}) == {"ok": True}


def test_every_declared_function_has_a_handler(actions: Actions, menu, cafe):
    from kiosk.assistant.tools import function_declarations

    assert {d["name"] for d in function_declarations(menu, cafe)} == actions.names
