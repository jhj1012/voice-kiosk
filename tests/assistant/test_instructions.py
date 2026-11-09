from kiosk.assistant.instructions import (
    GREETING_CUE,
    instructions,
    order_text,
    transcription_vocabulary,
)
from kiosk.domain.flow import Kiosk


def test_instructions_contain_rules_menu_and_cafe(menu, cafe):
    text = instructions(menu, cafe)
    assert GREETING_CUE in text
    assert cafe.name in text
    for item in menu.items:
        assert f"- {item.id} {item.name}:" in text
    assert "- americano 아메리카노: 사천 원;" in text
    assert "RECOMMENDED" in text
    assert "served iced only" in text  # cold brew
    assert "allergens: 밀, 우유, 계란, 대두" in text  # cookie, in data order
    for topic in cafe.topics:
        assert f"- {topic.id} ({topic.title}):" in text
    assert "size (사이즈, REQUIRED): regular Regular (355ml (12온스)), large Large +오백 원" in text
    assert "whipped_cream 휘핑 추가 +오백 원 (생크림 휘핑; allergens: 우유)" in text


def test_current_order_is_added_after_a_reconnect(kiosk: Kiosk):
    kiosk.order_item("americano", 2, {"temperature": "ice", "size": "regular"})
    kiosk.no_more_extras()
    kiosk.add_note("얼음 적게")
    text = instructions(kiosk.menu, kiosk.cafe, kiosk.order)
    assert order_text(kiosk.menu, kiosk.order) in text
    assert "1. 차가운 아메리카노 레귤러 2잔 팔천 원" in text
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


def test_the_transcription_expects_the_kiosks_own_words(menu):
    words = transcription_vocabulary(menu)
    assert {"직원", "직원 호출", "아메리카노", "라지"} <= set(words)
    assert words == sorted(set(words))


def test_rules_for_the_staff_and_general_questions(menu, cafe):
    text = instructions(menu, cafe)
    assert '"직원 호출"' in text and "Never order anything for it." in text
    assert "Words that sound like 직원 (직업" in text
    assert "answer briefly with common knowledge" in text
