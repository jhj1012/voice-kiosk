"""Safety rules that need the conversation. They run in code before a function call is executed,
because prompt rules alone are not enough (see docs/live-check.md):

- Pay only after the customer asked to pay in their own words ("결제할게요", or "없어요" to "더
  필요하신 거 있으세요?"), with the items unchanged since; the read-back must be said before the
  card terminal starts (`said_amount`).
- Throw the whole order away only right after the customer said yes to a cancel question.

- A required option (temperature, size) the customer did not mention at all, while the screen
  was not asking for it, is a guess: it is left out and the kiosk asks (`guessed_groups`).
  Answers to the question on screen are always taken, whatever the words, so misheard answers
  ("라디오" for 라지요) are not refused and nothing is asked twice.

The customer's words are the input transcription (or typed text), which arrives before the
function call. All of this is pure and tested without a network.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from kiosk.domain.menu import MenuItem, OptionGroup

Speaker = Literal["customer", "assistant"]


def normalize(text: str) -> str:
    """Lowercase without spaces and punctuation, so "결제 할게요" matches "결제할게요"."""
    return re.sub(r"[^0-9a-z가-힣]", "", text.lower())


_LETTER = re.compile(r"[^\W\d_]")
_EXPECTED_LETTER = re.compile(r"[a-zA-Z가-힣ᄀ-ᇿ㄰-㆏]")


def mostly_foreign(text: str) -> bool:
    """True if over a fifth of the letters are neither Korean nor Latin: a transcription
    hallucination (e.g. a Hindi paragraph appended to a Korean greeting, or "ハッピラテ")."""
    letters = _LETTER.findall(text)
    if not letters:
        return False
    foreign = sum(1 for ch in letters if not _EXPECTED_LETTER.match(ch))
    return foreign * 5 > len(letters)


# The model's own thoughts said out loud: an English sentence ("*   Wait for user preference
# about additions.", "The customer said ..."), or list markup. A Korean kiosk says at most a
# word or two in Latin letters ("Wi-Fi", a password, "OK").
_THINKING_ALOUD = re.compile(
    r"[A-Za-z]{2,}(?:[\s,.'’:;-]+[A-Za-z]{2,}){2,}"  # three English words in a row
    r"|\*\s+[A-Za-z]|\*\*|(?:^|\n)\s*#"  # markdown: "*   Wait", "**", "# "
)


def thinking_aloud(text: str) -> int | None:
    """Where the model starts saying its own thoughts (in English, or markup), or None."""
    found = _THINKING_ALOUD.search(text)
    return found.start() if found else None


# --- transcript --------------------------------------------------------------------------------


@dataclass(eq=False)  # one utterance, not its words: "아니" twice are two different answers
class Utterance:
    speaker: Speaker
    text: str = ""
    typed: bool = False
    open: bool = True  # still growing (transcription arrives in pieces)
    ignored: bool = False  # not meant for the kiosk (stay_quiet): does not count for anything


@dataclass
class Transcript:
    """What was said in this session, in order. Kiosk cues ([...]) are not part of it."""

    entries: list[Utterance] = field(default_factory=list)

    def add(self, speaker: Speaker, text: str, *, typed: bool = False) -> Utterance:
        """Append text; it continues the last utterance if that is the same speaker and open."""
        last = self.entries[-1] if self.entries else None
        if last is not None and last.open and last.speaker == speaker and not typed:
            last.text += text
            return last
        utterance = Utterance(speaker, text, typed=typed, open=not typed)
        self.entries.append(utterance)
        return utterance

    def close(self, speaker: Speaker | None = None) -> Utterance | None:
        """End the open utterance (of `speaker`, if given); returns it if one was closed."""
        for utterance in reversed(self.entries):
            if utterance.open and (speaker is None or utterance.speaker == speaker):
                utterance.open = False
                return utterance
        return None

    @property
    def mark(self) -> int:
        """Index of the latest customer utterance (or 0): "from here on" for `customer_since`."""
        for i in range(len(self.entries) - 1, -1, -1):
            if self.entries[i].speaker == "customer":
                return i
        return len(self.entries)

    def customer_since(self, index: int) -> list[Utterance]:
        return [
            u
            for u in self.entries[index:]
            if u.speaker == "customer" and u.text.strip() and not u.ignored
        ]

    def last_customer(self) -> Utterance | None:
        return next(
            (u for u in reversed(self.entries) if u.speaker == "customer" and not u.ignored), None
        )

    def assistant_before(self, utterance: Utterance) -> Utterance | None:
        """What the assistant said last before `utterance`."""
        index = self.entries.index(utterance)
        return next((u for u in reversed(self.entries[:index]) if u.speaker == "assistant"), None)

    def assistant_since(self, index: int) -> str:
        return " ".join(u.text for u in self.entries[index:] if u.speaker == "assistant")


# --- what the customer means -------------------------------------------------------------------

_PAY = re.compile(
    r"결제|계산|카드로|카드요|카드할|페이|이게다|그게다|이거면돼|그거면돼|이대로|다됐|끝이에요|끝났"
    r"|주문할게요|주문완료|주문끝"
)
_NOT_PAY = re.compile(r"결제(안|말고|하지|는나중|전에)|계산(안|말고|하지)|아직")
_ANYTHING_ELSE = re.compile(r"더(필요|주문|드실|하실|원하|추가)|추가로|다른(메뉴|거|것|건)")
# "추가하실 거 있으세요?" asks about an item's extras: "없어요" there is not "that's all". (A
# question about more menu items, "더 추가하실 메뉴 있으세요?", still is.)
_EXTRAS_QUESTION = re.compile(r"추가하실|추가할|옵션|샷|시럽|텀블러|토핑|휘핑")
_ITEMS_QUESTION = re.compile(r"메뉴|주문|결제|계산")
_PAY_QUESTION = re.compile(r"결제|계산")
_CANCEL_QUESTION = re.compile(r"취소")
_YES = re.compile(r"^(네|넵|예|응|어|그래|좋아|맞아|부탁|그렇게|오케이|ok|yes|당연|물론|취소해)")
_NO = re.compile(r"^(아니|아뇨|노|no|없어|없습니다|없고|없네|괜찮|됐어|됐습니다|그게다|이게다|끝)")
_HESITATE = re.compile(r"아니|잠깐|잠시만|말고|안돼|안할|하지마")


_STOP = re.compile(r"잠깐|잠시|아니|아뇨|취소|말고|그만|안할|하지마|바꿀|바꿔|변경|다시")


def wants_to_stop(text: str) -> bool:
    """ "잠깐만요", "아니요", "취소해 주세요", "바꿀래요": the customer does not want to go on."""
    return bool(_STOP.search(normalize(text)))


def is_yes(text: str) -> bool:
    t = normalize(text)
    return bool(_YES.match(t)) and not _HESITATE.search(t)


def is_no(text: str) -> bool:
    return bool(_NO.match(normalize(text)))


def last_question(text: str) -> str:
    """The last question in what the assistant said: "샷 추가했습니다. 더 필요하신 거 있으세요?"
    asks about more items, not about extras."""
    questions = [q for q in re.findall(r"[^.?!。]*\?", text) if q.strip()]
    return questions[-1] if questions else text


def asks_to_pay(customer: str, assistant_before: str = "") -> bool:
    """Does this customer utterance ask to pay (given what the assistant had just asked)?"""
    c = normalize(customer)
    a = normalize(last_question(assistant_before))
    if _PAY.search(c) and not _NOT_PAY.search(c):
        return True
    extras_only = _EXTRAS_QUESTION.search(a) and not _ITEMS_QUESTION.search(a)
    if _ANYTHING_ELSE.search(a) and not extras_only and is_no(customer):
        return True  # "더 필요하신 거 있으세요?" - "아니요, 없어요"
    return bool(_PAY_QUESTION.search(a) and is_yes(customer))  # "결제 도와드릴까요?" - "네"


# Words that make an answer meant for every drink being chosen ("둘 다 레귤러요", "셋 다").
_FOR_ALL = re.compile(
    r"(둘|셋|넷|다섯|[두세네]\s*(잔|개)|[2-9]\s*(잔|개)?)\s*(다|모두|전부)"
    r"|모두|전부|다\s*같이|똑같|같은\s*걸로|같게"
    r"|(^|\s)다\s+(?!됐|돼|했|끝|왔)"  # "다 레귤러로" (not "다음에요", "다 됐어요")
)


def meant_for_all(text: str) -> bool:
    """The customer said their answer is for every drink ("둘 다", "셋 다", "전부", "똑같이")."""
    return bool(_FOR_ALL.search(text))


# "두 잔만 아이스로", "하나만 라지로": only that many cups; the rest get the other choice.
_ONLY_SOME = re.compile(
    r"(하나|한\s*(잔|개)|둘|두\s*(잔|개)|셋|세\s*(잔|개)|넷|네\s*(잔|개)|\d+\s*(잔|개)?)\s*만"
)


def only_some(text: str) -> bool:
    """The customer said "N만": only that many cups get it ("두 잔만 아이스로")."""
    return bool(_ONLY_SOME.search(text))


# "추가는 없어요", "그냥 주세요", "괜찮아요": nothing (more) to add.
_NOTHING_MORE = re.compile(r"없|괜찮|그냥|됐|안\s*(해|넣)")


def wants_nothing_more(text: str) -> bool:
    """The customer said they want nothing (more) added ("추가는 없어요", "그냥 주세요")."""
    return bool(_NOTHING_MORE.search(text))


def customer_asked_to_pay(transcript: Transcript, since: int) -> bool:
    """True if a customer utterance from `since` on (always including the latest) asks to pay."""
    utterances = transcript.customer_since(since)
    latest = transcript.last_customer()
    if latest is not None and latest not in utterances:
        utterances.append(latest)
    for utterance in utterances:
        before = transcript.assistant_before(utterance)
        if asks_to_pay(utterance.text, before.text if before else ""):
            return True
    return False


def confirmed_cancel(transcript: Transcript) -> bool:
    """The latest customer words are a yes to the assistant's question about cancelling."""
    latest = transcript.last_customer()
    if latest is None or not is_yes(latest.text):
        return False
    before = transcript.assistant_before(latest)
    return before is not None and bool(_CANCEL_QUESTION.search(normalize(before.text)))


# --- guessed options ---------------------------------------------------------------------------


def guessed_groups(
    item: MenuItem,
    selection: Mapping[str, str | Sequence[str]],
    words: str,
    asked: str = "",
) -> list[OptionGroup]:
    """Required groups in `selection` that look guessed: not the group the screen asks (`asked`)
    and not mentioned at all in the customer's `words` (none of the group's `words`)."""
    text = normalize(words)
    guessed = []
    for group_id in selection:
        group = item.group(group_id)
        if group is None or not group.required or group_id == asked or not group.words:
            continue
        if not any(normalize(w) in text for w in group.words):
            guessed.append(group)
    return guessed


# --- the read-back -----------------------------------------------------------------------------

_DIGITS = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_SMALL_UNITS = {"십": 10, "백": 100, "천": 1000}
_AMOUNT = re.compile(r"[0-9,일이삼사오육칠팔구십백천만\s]+(?=\s*원)")


def parse_korean_number(text: str) -> int | None:
    """ "만 이천칠백" -> 12700, "사천오백" -> 4500, "1만 2천" -> 12000, "11,500" -> 11500."""
    tokens = re.findall(r"[0-9][0-9,]*|[일이삼사오육칠팔구십백천만]", text)
    if not tokens:
        return None
    total = section = number = 0
    for token in tokens:
        if token[0].isdigit():
            number = int(token.replace(",", ""))
        elif token in _DIGITS:
            number = _DIGITS[token]
        elif token in _SMALL_UNITS:
            section += (number or 1) * _SMALL_UNITS[token]
            number = 0
        else:  # 만
            total += ((section + number) or 1) * 10000
            section = number = 0
    return total + section + number


def amounts(text: str) -> set[int]:
    """Every amount of won in `text`, written in digits or in Korean words."""
    found = set()
    for match in _AMOUNT.finditer(text):
        value = parse_korean_number(match.group())
        if value is not None:
            found.add(value)
    return found


def said_amount(text: str, amount: int) -> bool:
    return amount in amounts(text)
