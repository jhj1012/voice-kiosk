import pytest

from kiosk.assistant.safety import (
    Transcript,
    amounts,
    asks_to_pay,
    confirmed_cancel,
    customer_asked_to_pay,
    is_no,
    is_yes,
    item_words,
    mention_start,
    mostly_foreign,
    parse_korean_number,
    said_amount,
    unheard_required,
    wants_to_stop,
)
from kiosk.domain.menu import Menu

# --- transcript --------------------------------------------------------------------------------


def test_transcript_joins_pieces_until_closed():
    t = Transcript()
    t.add("customer", "아이스 ")
    t.add("customer", "아메리카노")
    t.add("assistant", "네")
    assert [(u.speaker, u.text) for u in t.entries] == [
        ("customer", "아이스 아메리카노"),
        ("assistant", "네"),
    ]
    t.close("assistant")
    t.add("assistant", "다음")
    assert len(t.entries) == 3


def test_typed_text_is_its_own_closed_utterance():
    t = Transcript()
    t.add("customer", "하나", typed=True)
    t.add("customer", "둘", typed=True)
    assert [u.text for u in t.entries] == ["하나", "둘"]
    assert not t.entries[0].open


def test_mark_and_customer_since():
    t = Transcript()
    t.add("customer", "첫째")
    t.close()
    t.add("assistant", "네")
    t.close()
    t.add("customer", "둘째")
    assert t.mark == 2
    assert [u.text for u in t.customer_since(t.mark)] == ["둘째"]
    assert t.assistant_before(t.entries[2]).text == "네"


# --- intents -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("customer", "assistant", "expected"),
    [
        ("결제할게요", "", True),
        ("계산해 주세요", "", True),
        ("카드로 할게요", "", True),
        ("이게 다예요", "", True),
        ("이대로 주문할게요", "", True),
        ("아니요 없어요", "더 필요하신 메뉴 있으신가요?", True),
        ("없어요", "추가로 주문하실 거 있으세요?", True),
        ("네", "결제 도와드릴까요?", True),
        ("포장이요", "매장에서 드시고 가세요, 포장하세요?", False),
        ("아니요", "따뜻하게 드릴까요?", False),
        ("네", "더 필요하신 메뉴 있으신가요?", False),
        ("결제는 나중에 할게요", "", False),
        ("아직 결제 안 할래요", "", False),
        ("아이스 아메리카노 주세요", "", False),
    ],
)
def test_asks_to_pay(customer, assistant, expected):
    assert asks_to_pay(customer, assistant) is expected


@pytest.mark.parametrize("text", ["네", "네, 취소해 주세요", "예", "응 그래", "좋아요", "맞아요"])
def test_yes(text):
    assert is_yes(text)


@pytest.mark.parametrize("text", ["아니요", "네? 잠깐만요", "음", "어... 아니 말고요", ""])
def test_not_yes(text):
    assert not is_yes(text)


def test_no():
    assert is_no("아니요, 없어요")
    assert is_no("괜찮아요")
    assert not is_no("네")


def conversation(*turns: tuple[str, str]) -> Transcript:
    t = Transcript()
    for speaker, text in turns:
        t.add(speaker, text)  # type: ignore[arg-type]
        t.close()
    return t


def test_pay_request_counts_only_after_the_last_item_change():
    t = conversation(("customer", "결제할게요"), ("assistant", "포장하세요?"))
    assert customer_asked_to_pay(t, since=0)
    t.add("customer", "아 쿠키도 하나 주세요")
    t.close()
    assert not customer_asked_to_pay(t, since=t.mark)  # the cookie came after "결제할게요"


def test_pay_request_and_item_in_the_same_sentence():
    t = conversation(("customer", "쿠키 하나 주시고 결제할게요"))
    assert customer_asked_to_pay(t, since=t.mark)


def test_cancel_needs_a_yes_to_a_cancel_question():
    assert not confirmed_cancel(conversation(("customer", "다 취소해 주세요")))
    assert confirmed_cancel(
        conversation(
            ("customer", "다 취소해 주세요"),
            ("assistant", "주문을 모두 취소할까요?"),
            ("customer", "네"),
        )
    )
    assert not confirmed_cancel(
        conversation(("assistant", "주문을 모두 취소할까요?"), ("customer", "아니요"))
    )
    assert not confirmed_cancel(conversation(("assistant", "포장하세요?"), ("customer", "네")))


# --- required options must be heard ------------------------------------------------------------


def test_unheard_required(menu: Menu):
    latte = menu.item("cafe_latte")
    selection = {"temperature": "ice", "size": "large", "shot": "extra_shot"}
    groups = unheard_required(latte, selection, ["카페라떼 아이스로 주세요"])
    assert [g.id for g in groups] == ["size"]  # shots are extras: not checked


@pytest.mark.parametrize(
    ("said", "selection"),
    [
        ("아아 하나요", {"temperature": "ice"}),
        ("뜨거운 걸로", {"temperature": "hot"}),
        ("제일 큰 거요", {"size": "large"}),
        ("작은 사이즈요", {"size": "regular"}),
        ("사이즈는 아무거나 괜찮아요", {"size": "regular"}),
        ("ICE 라지", {"temperature": "ice", "size": "large"}),
        # "아이스요, 크게요" as the transcription wrote it (docs/live-check.md)
        ("I see. 크게요.", {"temperature": "ice", "size": "large"}),
        ("아이세요. 크게요.", {"temperature": "ice", "size": "large"}),
        ("아이셀", {"temperature": "ice"}),
    ],
)
def test_aliases_count_as_heard(menu: Menu, said, selection):
    assert unheard_required(menu.item("americano"), selection, [said]) == []


def test_values_already_chosen_are_not_new(menu: Menu):
    americano = menu.item("americano")
    already = {"temperature": ("ice",), "size": ("large",)}
    selection = {"temperature": "ice", "size": "large"}
    assert unheard_required(americano, selection, ["샷 추가해 주세요"], already) == []
    selection = {"temperature": "hot", "size": "large"}
    assert [g.id for g in unheard_required(americano, selection, ["샷"], already)] == [
        "temperature"
    ]


def test_options_the_item_does_not_have_are_left_to_the_domain(menu: Menu):
    assert unheard_required(menu.item("cold_brew"), {"temperature": "ice"}, []) == []


# --- read-back amounts -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("만 이천칠백", 12700),
        ("사천오백", 4500),
        ("만 천오백", 11500),
        ("이만 삼천", 23000),
        ("1만 2천", 12000),
        ("11,500", 11500),
        ("구백", 900),
        ("십만", 100000),
    ],
)
def test_parse_korean_number(text, number):
    assert parse_korean_number(text) == number


def test_amounts_in_a_read_back():
    text = "아이스 아메리카노 라지 2잔, 포장으로 총 13,500원입니다. 카드를 꽂아 주세요."
    assert amounts(text) == {13500}
    assert said_amount("총 만 삼천오백 원입니다", 13500)
    assert not said_amount("총 만 삼천 원입니다", 13500)
    assert not said_amount("주문 확인해 드릴게요", 13500)


def test_mostly_foreign():
    assert mostly_foreign("क्रांतिकारी रूप से आगे")
    assert mostly_foreign("### 2. व्यावहारिक बदलाव (Practical Actions)")
    assert mostly_foreign("ハッピラテ")
    assert not mostly_foreign("와이파이 이름은 SORI_CAFE예요.")
    assert not mostly_foreign("13,500원")


def test_mention_start_finds_where_an_item_was_named(menu: Menu):
    t = conversation(
        ("customer", "청포도 에이드 하나랑 아메리카노 하나 주세요"),
        ("assistant", "사이즈는요?"),
        ("customer", "아메리카노는 아이스요"),
        ("assistant", "네"),
        ("customer", "둘 다 라지로요"),
    )
    assert mention_start(t, menu.item("americano")) == 2
    assert mention_start(t, menu.item("green_grape_ade")) == 0
    assert mention_start(t, menu.item("cafe_latte")) == 4  # never named: the latest words


def test_item_words(menu: Menu):
    assert item_words(menu.item("green_grape_ade")) == ["청포도에이드", "청포도", "에이드"]
    assert item_words(menu.item("chocolate_cookie")) == ["초코쿠키"]


@pytest.mark.parametrize(
    ("text", "stop"),
    [
        ("잠깐만요", True),
        ("아니요", True),
        ("취소해 주세요", True),
        ("샷 추가로 바꿀래요", True),
        ("네", False),
        ("얼마라고요?", False),
        ("결제할게요", False),
    ],
)
def test_wants_to_stop(text, stop):
    assert wants_to_stop(text) is stop
