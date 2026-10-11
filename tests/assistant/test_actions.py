import pytest

from kiosk.assistant.actions import (
    ASK_EXTRAS,
    ASK_ONE,
    ASK_STAFF,
    NOTED,
    STAFF_QUESTION,
    Actions,
)
from kiosk.domain.flow import Kiosk, Phase, Screen


@pytest.fixture
def actions(kiosk: Kiosk) -> Actions:
    return Actions(kiosk)


def test_options_are_asked_one_at_a_time_then_the_extras(actions: Actions):
    result = actions.call("choose_item", {"item_id": "americano", "quantity": 2.0})
    assert result == {
        "not_added_yet": "아메리카노",
        "ask": {"option": "온도", "choices": ["따뜻한", "아이스"]},
        "next": ASK_ONE,
    }
    result = actions.call("set_options", {"temperature": "ice", "size": "large"})
    assert result == {
        "not_added_yet": "아메리카노",
        "extras": [
            {"option": "텀블러", "choices": ["텀블러 사용"]},
            {
                "option": "커피 샷",
                "choices": ["샷 추가 (+600원)", "2샷 추가 (+1,200원)", "디카페인 (+1,000원)"],
            },
            {
                "option": "시럽",
                "choices": [
                    "바닐라 시럽 (+500원)",
                    "카라멜 시럽 (+500원)",
                    "헤이즐넛 시럽 (+500원)",
                    "라이트 바닐라 시럽 (+500원)",
                ],
            },
        ],
        "chosen": ["아이스", "라지"],
        "next": ASK_EXTRAS,
    }
    assert "extras" in actions.call("set_options", {"syrup": "vanilla"})
    result = actions.call("finish_item", {})
    assert result == {
        "added": "아이스 아메리카노 라지(바닐라 시럽) 2잔",
        "order": ["1. 아이스 아메리카노 라지(바닐라 시럽) 2잔 10,000원"],
        "total": "10,000원",
    }


def test_edit_line_and_go_back(actions: Actions, kiosk: Kiosk):
    actions.call("show_menu", {"category": "latte"})
    actions.call("choose_item", {"item_id": "cafe_latte", "temperature": "hot", "size": "regular"})
    actions.call("finish_item", {})
    result = actions.call("edit_line", {"line": 1, "option": "size"})
    assert result == {
        "shown": "따뜻한 카페라떼 레귤러 1잔",
        "options": {
            "온도": "따뜻한",
            "사이즈": "레귤러",
            "텀블러": "없음",
            "커피 샷": "기본",
            "시럽": "없음",
            "토핑": "없음",
        },
    }
    assert (kiosk.view.line, kiosk.view.group) == (1, "size")
    assert actions.call("go_back", {}) == {"shown": "라떼"}
    assert "error" in actions.call("edit_line", {"line": 2})


def test_note_for_staff(actions: Actions, kiosk: Kiosk):
    result = actions.call("note_for_staff", {"text": "아메리카노는 포장, 카페모카는 매장에서"})
    assert result == {"noted": "아메리카노는 포장, 카페모카는 매장에서", "say": NOTED}
    assert "error" in actions.call("note_for_staff", {"text": " "})


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


def test_request_payment_asks_for_the_staff_then_reviews_the_order(actions: Actions, kiosk: Kiosk):
    actions.call("choose_item", {"item_id": "chocolate_cookie"})
    assert "error" in actions.call("request_payment", {})  # dining not known yet
    assert kiosk.view.screen is Screen.DINING
    actions.call("set_dining", {"dining": "here"})
    result = actions.call("request_payment", {})
    assert result == {"ask_first": STAFF_QUESTION, "next": ASK_STAFF}
    result = actions.call("request_payment", {})
    assert result == {
        "read_back": "주문 확인해 드릴게요. 초코 쿠키 1개, 매장에서 드시고 총 2,500원입니다."
    }
    assert kiosk.review_is_current
    assert kiosk.phase is Phase.ORDERING  # the session starts the terminal after the read-back


def test_show_order(actions: Actions, kiosk: Kiosk):
    actions.call("choose_item", {"item_id": "chocolate_cookie"})
    assert actions.call("show_order", {})["order"] == ["1. 초코 쿠키 1개 2,500원"]
    assert not kiosk.review_is_current


def test_cancel_payment(actions: Actions, kiosk: Kiosk):
    actions.call("choose_item", {"item_id": "chocolate_cookie"})
    actions.call("set_dining", {"dining": "here"})
    actions.call("request_payment", {})  # the staff question
    actions.call("request_payment", {})
    kiosk.start_payment()
    assert actions.call("cancel_payment", {}) == {"ok": True}
    assert kiosk.phase is Phase.ORDERING


def test_every_declared_function_has_a_handler(actions: Actions, menu, cafe):
    from kiosk.assistant.tools import function_declarations

    assert {d["name"] for d in function_declarations(menu, cafe)} == actions.names
