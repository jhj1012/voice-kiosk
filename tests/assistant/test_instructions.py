from kiosk.assistant.instructions import GREETING_CUE, instructions, order_text
from kiosk.domain.flow import Kiosk


def test_instructions_contain_rules_menu_and_cafe(menu, cafe):
    text = instructions(menu, cafe)
    assert GREETING_CUE in text
    assert cafe.name in text
    for item in menu.items:
        assert f"- {item.id} {item.name}:" in text
    assert "- americano 아메리카노: 4,000원;" in text
    assert "RECOMMENDED" in text
    assert "served iced only" in text  # cold brew
    assert "allergens: 밀, 우유, 계란, 대두" in text  # cookie, in data order
    for topic in cafe.topics:
        assert f"- {topic.id} ({topic.title}):" in text
    assert "size (사이즈, REQUIRED): regular Regular, large Large +500원" in text


def test_current_order_is_added_after_a_reconnect(kiosk: Kiosk):
    kiosk.order_item("americano", 2, {"temperature": "ice", "size": "regular"})
    kiosk.no_more_extras()
    kiosk.add_note("얼음 적게")
    text = instructions(kiosk.menu, kiosk.cafe, kiosk.order)
    assert order_text(kiosk.menu, kiosk.order) in text
    assert "1. 차가운 아메리카노 레귤러 2잔 8,000원" in text
    assert "Notes for the staff: 얼음 적게" in text
    assert "## The customer's order so far" not in instructions(kiosk.menu, kiosk.cafe)


def test_drinks_being_chosen_are_added_after_a_reconnect(kiosk: Kiosk):
    kiosk.order_item("cafe_latte", 2, {"temperature": "hot"})
    text = instructions(kiosk.menu, kiosk.cafe, kiosk.order, kiosk.drafts)
    assert "- draft 1: cafe_latte 카페라떼 x2, missing 사이즈" in text


def test_the_unrelated_speech_rule_only_with_the_switch(menu, cafe):
    assert "## Speech that is not for you" not in instructions(menu, cafe)
    assert "## Speech that is not for you" in instructions(menu, cafe, ignore_unrelated=True)
    assert "stay_quiet" in instructions(menu, cafe)  # hesitation: always
