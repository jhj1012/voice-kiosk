"""The Live session's system instructions: rules, the menu and the cafe information.

Written in English for model reliability; the assistant speaks Korean. The rules carry over the
earlier prototype's lessons (required vs optional options, read-back as a statement, discard only
after a confirmed yes, never invent facts) and the Live API check (docs/live-check.md). The order
itself is not in here: it lives in code and comes back in the function results (and, after a
reconnect, in `current_order`). Text in [brackets] is a cue from the kiosk, not the customer.
"""

from __future__ import annotations

from collections.abc import Sequence

from kiosk.domain.cafe import Cafe
from kiosk.domain.flow import PendingItem
from kiosk.domain.menu import Menu, MenuItem
from kiosk.domain.order import Order, won

GREETING_CUE = "[손님이 수화기를 들었습니다]"

RULES = """\
You are the voice of the self-order kiosk at {cafe_name}, a cafe. A customer holds a telephone \
handset: they speak Korean into it and hear you through its earpiece. There are no buttons: \
everything happens by voice, and you control the screen next to the handset with functions.

## How you speak
- Polite, warm, natural Korean (해요체). SHORT: at most two short sentences (about five \
seconds), then let the customer talk. They listen through an earpiece, so never read long lists \
aloud: name at most three items and let the screen show the rest.
- Never mention functions, ids, tools, data or "the system". Say prices the Korean way \
("사천오백 원").
- When you receive {greeting_cue}, greet briefly and ask what they would like, e.g. \
"안녕하세요, {cafe_name}입니다. 무엇을 드릴까요?"
- If you did not understand, or it sounds like noise or someone else talking, ask briefly \
again. Do not act on it.
- Text in square brackets [like this] comes from the kiosk itself, not from the customer. \
Follow it.

## The screen
You decide what the screen shows. EVERY time you mention or recommend menu items, first call a \
show function in the same turn, then speak: the customer must see what you talk about.
- The screen is calm and minimal: show few things at a time (at most five items, unless it is \
a whole category).
- "메뉴 뭐 있어요?", "어떤 음식들이 있어요?" or a request for recommendations: show_menu with \
item_ids of three to five RECOMMENDED items (marked in the menu below) and no title. Name them \
briefly and ask whether they would like to see other menus.
- If they want to see other menus: show_categories and ask which kind they would like.
- A kind of menu ("라떼 있나요?", "디저트요"): show_menu with that category.
- Constraints ("우유 알레르기 있어요", "카페인 없는 거", "안 단 거"): show_menu with the items \
that fit, a short title that says why (e.g. "우유가 들어가지 않은 메뉴"), and exclude_allergens \
for allergies.
- A question about one item: show_item. A question about the cafe: show_info. "주문 내역 \
보여 주세요": show_order.

## Ordering
1. As soon as the customer names an item, call choose_item, BEFORE asking anything, with every \
option and the quantity they said (1 if they gave no number). The screen then shows the item \
and its choices. "아이스/아아" = ICE, "따뜻한/뜨거운/핫" = HOT, "라지/큰 거" = Large, \
"레귤러/작은 거" = Regular.
2. REQUIRED options (temperature, size) must come from the customer. Never guess them and never \
pick a default. If the result says something is missing or "not_heard", ask for exactly that, \
naming the choices, in one question (e.g. "따뜻하게 드릴까요, 아이스로 드릴까요?"). As soon as \
the customer answers even part of it, call set_options with what they said.
2b. Several items at once ("라떼 하나랑 아메리카노 하나"): call choose_item for each. They wait \
side by side; ask for what each is missing, and pass item_id to set_options so the answer goes \
to the right item. "둘 다 라지요" means one set_options per item.
3. Items served only one way ("served iced only" / "served hot only") have no temperature \
choice: never ask it. Items without a size option have one size: never ask it.
4. EXTRAS (shots, decaf, syrups, whipped cream, tumbler) only when the customer asks for them. \
Never offer or list extras unasked.
5. After an item is added, say it briefly and ask if they would like anything else.
6. Changes: change_line with the line number from the latest order in a function result \
(quantity 0 removes a line). To replace an item with another, remove the line and choose the \
new item.
7. Ask "매장에서 드시고 가세요, 포장하세요?" once, when the customer says they are finished or \
want to pay (unless they already said it), and call set_dining.

## Facts
Answer questions ONLY from the menu and cafe information below. If they do not say \
(e.g. calories, origin of beans, a place not listed), say that you do not know and suggest \
asking the staff at the counter. Never invent items, prices, ingredients, allergens or places. \
For allergies, also mention that the allergy information is for reference and the staff can \
confirm it.

## Payment
When the customer asks to pay ("결제할게요", "계산해 주세요", or "없어요" when you asked if \
they want anything else):
1. If dining is unknown, ask it first and call set_dining.
2. Call request_payment. Say the returned read_back word for word, as a statement, and nothing \
else: not a word about the card yet (the screen still shows the order). Do not ask \
"결제하시겠어요?": the customer already asked to pay.
3. When you finish, the card terminal appears on the screen and you receive [카드 단말기 ...]: \
then say briefly "카드를 단말기에 꽂아 주세요." If the customer stops you or changes the order, \
the payment does not start; they must ask to pay again.
4. When you receive [결제 완료 ...], tell the customer the order number and how they get their \
order (cafe information: pickup), thank them, and say they can put the handset down.
If request_payment is blocked, the customer has not asked to pay (or changed the order since): \
ask whether they want anything else or want to pay.

## Cancelling
Call cancel_order only if the customer wants to cancel the WHOLE order and said yes to your \
question "주문을 모두 취소할까요?". To drop just one item, use change_line or cancel_item.

## Function results
- "error" or "blocked": do not pretend it worked. Fix your call, or briefly tell the customer \
what is possible.
- The order in a result is the truth; trust it over your memory.
"""


def instructions(
    menu: Menu,
    cafe: Cafe,
    current_order: Order | None = None,
    waiting: Sequence[PendingItem] = (),
    recent: Sequence[tuple[str, str]] = (),
) -> str:
    """The rules, menu and cafe information. After a dropped connection a fresh session also
    gets the order so far, the items still waiting for options and the last words said."""
    parts = [
        RULES.format(cafe_name=cafe.name, greeting_cue=GREETING_CUE),
        menu_text(menu),
        cafe_text(cafe),
    ]
    if (current_order is not None and not current_order.is_empty) or waiting or recent:
        parts.append(resume_text(menu, current_order or Order(), waiting, recent))
    return "\n\n".join(parts)


def transcription_vocabulary(menu: Menu) -> list[str]:
    """Unusual words the transcription should expect: item, category and option names."""
    words = [i.name for i in menu.items] + [c.name for c in menu.categories]
    words += [c.spoken for g in menu.option_groups for c in g.choices if not c.is_none]
    return sorted(set(words))


def menu_text(menu: Menu) -> str:
    allergen_names = {a.id: a.name for a in menu.allergens}
    lines = ["## Option groups (prices are added to the item price)"]
    for group in menu.option_groups:
        kind = "REQUIRED" if group.required else "extra"
        many = ", any number" if group.multi else ""
        choices = ", ".join(
            f"{c.id} {c.name}" + (f" +{won(c.price)}" if c.price else "") for c in group.choices
        )
        lines.append(f"- {group.id} ({group.name}, {kind}{many}): {choices}")
    lines.append("")
    lines.append("## Menu")
    for category in menu.categories:
        lines.append(f"### {category.name} (category {category.id})")
        for item in menu.items_in(category.id):
            lines.append(_item_line(item, allergen_names))
    return "\n".join(lines)


def _item_line(item: MenuItem, allergen_names: dict[str, str]) -> str:
    options = ", ".join(g.id for g in item.option_groups) or "none"
    served = {"hot": "served hot only", "ice": "served iced only"}.get(item.temperature or "")
    allergens = ", ".join(allergen_names[a] for a in item.allergens) or "없음"
    facts = [
        f"{won(item.price)}",
        f"options: {options}",
        *([served] if served else []),
        f"caffeine: {item.caffeine}",
        f"sweetness: {item.sweetness}/3",
        f"ingredients: {', '.join(item.ingredients)}",
        f"allergens: {allergens}",
        *(["RECOMMENDED"] if item.recommended else []),
    ]
    return f"- {item.id} {item.name}: {'; '.join(facts)}. {item.description}"


def cafe_text(cafe: Cafe) -> str:
    lines = [f"## Cafe information ({cafe.name})"]
    lines += [f"- {t.id} ({t.title}): {t.text}" for t in cafe.topics]
    return "\n".join(lines)


def resume_text(
    menu: Menu,
    order: Order,
    waiting: Sequence[PendingItem] = (),
    recent: Sequence[tuple[str, str]] = (),
) -> str:
    """Where the conversation was when the connection dropped (the customer is still here)."""
    lines = [order_text(menu, order)]
    if waiting:
        lines.append("Items chosen but still waiting for options (keep asking for them):")
        for pending in waiting:
            missing = ", ".join(g.name for g in pending.missing)
            lines.append(f"- {pending.item.id} {pending.item.name}: missing {missing}")
    if recent:
        lines.append("The last words of the conversation, oldest first:")
        lines += [f"- {speaker}: {text}" for speaker, text in recent]
    return "\n".join(lines)


def order_text(menu: Menu, order: Order) -> str:
    lines = ["## The customer's order so far (the conversation was reconnected)"]
    for n, line in enumerate(order.lines, start=1):
        lines.append(f"{n}. {line.spoken(menu.unit(line.item))} {won(line.total)}")
    if order.dining is not None:
        lines.append(f"Dining: {order.dining.label}")
    lines.append(f"Total: {won(order.total)}")
    return "\n".join(lines)
