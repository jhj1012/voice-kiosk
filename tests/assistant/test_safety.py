import pytest

from kiosk.assistant.safety import (
    Transcript,
    amounts,
    asks_to_pay,
    confirmed_cancel,
    customer_asked_to_pay,
    guessed_groups,
    is_no,
    is_yes,
    mostly_foreign,
    parse_korean_number,
    said_amount,
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


@pytest.mark.parametrize(
    "assistant",
    ["추가하실 거 있으세요?", "더 추가하실 거 있으세요?", "샷이나 시럽 더 추가하실 건가요?"],
)
def test_no_to_the_extras_question_is_not_asking_to_pay(assistant):
    assert not asks_to_pay("없어요", assistant)
    assert asks_to_pay("없어요, 결제할게요", assistant)


def test_no_to_more_menu_items_still_is():
    assert asks_to_pay("없어", "더 추가하실 메뉴가 있으신가요, 아니면 결제를 진행할까요?")


@pytest.mark.parametrize(
    ("words", "selection", "asked", "guessed"),
    [
        (
            "아메리카노 세 잔, 하나는 차갑게",
            {"temperature": "ice", "size": "regular"},
            "",
            ["size"],
        ),
        ("카페라떼 하나 주세요", {"temperature": "ice"}, "", ["temperature"]),
        ("카페라떼 하나 주세요", {"temperature": "ice"}, "temperature", []),  # asked: taken
        ("라디오", {"size": "large"}, "size", []),
        ("아이스 아메리카노 큰 거요", {"temperature": "ice", "size": "large"}, "", []),
        ("다뜻한 카페라떼 레귤러요", {"temperature": "hot", "size": "regular"}, "", []),
        ("샷 추가요", {"shot": "extra_shot"}, "", []),  # extras are never guesses
    ],
)
def test_guessed_groups(menu: Menu, words, selection, asked, guessed):
    item = menu.item("americano")
    assert [g.id for g in guessed_groups(item, selection, words, asked)] == guessed


def test_only_the_last_question_counts_for_paying():
    from kiosk.assistant.safety import asks_to_pay

    # Team log: "샷 추가했습니다" in front made the "아니" look like an answer about extras.
    said = "따뜻한 아메리카노 라지 사이즈에 샷 추가했습니다. 더 필요하신 거 있으세요?"
    assert asks_to_pay("아니", said)
    assert not asks_to_pay("아니", "샷 추가했어요. 더 추가하실 거 있으세요?")


# What the customer's words mean for which drinks (answers.py): each phrase, and what it is not.
WORDS = [
    # meant_for_all: the answer is for every drink being chosen
    ("meant_for_all", "둘 다 레귤러요", True),
    ("meant_for_all", "셋 다 레귤러로", True),
    ("meant_for_all", "세 잔 다요", True),
    ("meant_for_all", "3잔 다 라지", True),
    ("meant_for_all", "전부 샷 추가", True),
    ("meant_for_all", "똑같이요", True),
    ("meant_for_all", "다 레귤러로", True),
    ("meant_for_all", "레귤러요", False),
    ("meant_for_all", "하나만 라지로", False),
    ("meant_for_all", "다음에요", False),
    ("meant_for_all", "다 됐어요", False),
    # only_some: only that many cups get it ("만")
    ("only_some", "2개만 아이스로", True),
    ("only_some", "두 잔만 아이스로", True),
    ("only_some", "하나만 라지로 해줘", True),
    ("only_some", "한 잔만 차갑게", True),
    ("only_some", "두 잔은 아이스로", False),
    ("only_some", "레귤러만 돼요?", False),
    ("only_some", "아메리카노 두 잔이요", False),
    # wants_nothing_more: nothing (more) to add
    ("wants_nothing_more", "추가는 없어요", True),
    ("wants_nothing_more", "그냥 주세요", True),
    ("wants_nothing_more", "괜찮아요", True),
    ("wants_nothing_more", "샷 추가요", False),
]


@pytest.mark.parametrize(("function", "words", "expected"), WORDS)
def test_what_the_words_mean(function, words, expected):
    from kiosk.assistant import safety

    assert getattr(safety, function)(words) is expected
