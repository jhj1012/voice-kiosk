"""Run the model's function calls on the kiosk and describe the result for the model.

Every call is validated by the domain (`KioskError`); mistakes come back as {"error": ...} so the
model can correct itself or tell the customer. Results use Korean names (what the model says),
not ids. Every result also has `next`: the kiosk's current question, in the words to say, which
the screen shows at the same time. The safety rules that need the conversation (paying,
cancelling everything) are applied before this, by the session.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from kiosk.assistant.tools import selection_from_args
from kiosk.domain.flow import EXTRAS, Ask, Draft, ItemResult, Kiosk, Phase, Screen, View
from kiosk.domain.menu import TEMPERATURE, KioskError, OptionChoice, OptionGroup
from kiosk.domain.order import CartLine, Dining, won_spoken

log = logging.getLogger(__name__)

Result = dict[str, Any]

DINING_QUESTION = "매장에서 드시고 가세요, 포장하세요?"
MENU_BOARD = "메뉴판에서 메뉴를 고르신 뒤 말씀해 주세요."
ANYTHING_ELSE = "더 필요하신 거 있으세요?"
EXTRAS_QUESTION = "추가하실 거 있으세요?"
STAFF_QUESTION = "직원에게 따로 전달할 말씀 있으세요?"
NOTED = "네, 알겠습니다. 해당 사항은 직원에게 전달하겠습니다."

ASK_EXTRAS = (
    "Do not read the extras out: the screen lists them. For what they want call set_options and "
    "ask '더 추가하실 거 있으세요?'; when they want nothing (more), call no_more_extras."
)
ASK_STAFF = (
    "Ask exactly this. If they have something, call note_for_staff. Then call pay again (they "
    "already asked to pay)."
)
SAY_READ_BACK = "Say the read_back now, word for word; nothing about the card yet."
LINE_SHOWN = "Shown again. If they want to change it, call change with line {line}."
CONFIRM_SAME = (
    "Their answer may be for {other} too. Ask this. Yes: call set_options with draft {draft} and "
    "the same {group}. No: {no}"
)
CONFIRM_NO_OTHER = "call set_options with draft {draft} and {group} {other} (the other choice)."
CONFIRM_NO_ASK = "ask '{question}'."
CONFIRM_NO_EXTRA = "it does not get it; nothing to call."
CONFIRM_SKIP = " If they already said which drink it was for, do not ask this; ask '{then}'."
HELD = "Not set for {other}: the customer did not say it was for both. Ask this first."
CONFIRM_LINE = (
    "Their answer may be for {other} too (line {line}, already in the order). Ask this. Yes: call "
    "change with line {line} and the same {group}. No: it does not get it; nothing to call."
)


class Actions:
    def __init__(self, kiosk: Kiosk) -> None:
        self.kiosk = kiosk
        self._handlers: dict[str, Callable[[dict[str, Any]], Result]] = {
            "show": self._show,
            "order": self._order_item,
            "set_options": self._set_options,
            "no_more_extras": self._no_more_extras,
            "set_dining": self._set_dining,
            "change": self._change,
            "go_back": self._go_back,
            "note_for_staff": self._note_for_staff,
            "pay": self._pay,
            "cancel_order": self._cancel_order,
        }

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def call(self, name: str, args: dict[str, Any] | None) -> Result:
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"unknown function {name!r}"}
        try:
            return handler(dict(args or {}))
        except KioskError as e:
            return {"error": str(e), **self._next()}
        except (TypeError, ValueError) as e:
            log.warning("bad arguments for %s: %s (%s)", name, args, e)
            return {"error": f"invalid arguments: {e}"}

    # --- display -----------------------------------------------------------------------------

    def _show(self, args: dict[str, Any]) -> Result:
        what = str(args.get("what", ""))
        kiosk = self.kiosk
        result: Result
        if what == "menu":
            shown = kiosk.show_menu(
                title=str(args.get("title") or ""),
                category=args.get("category") or None,
                item_ids=list(args.get("item_ids") or []),
                highlight_ids=list(args.get("highlight_ids") or []),
                exclude_allergens=list(args.get("exclude_allergens") or []),
            )
            if shown.categories:
                result = {
                    "shown": [c.name for c in kiosk.menu.categories],
                    "note": "the whole menu does not fit: the categories are shown instead",
                }
            else:
                result = {"shown": self._names(shown.item_ids)}
            if shown.not_shown:
                result["more_not_shown"] = shown.not_shown
            if shown.removed:
                result["left_out_for_allergens"] = self._names(shown.removed)
        elif what == "categories":
            kiosk.show_categories()
            result = {"shown": [c.name for c in kiosk.menu.categories]}
        elif what == "item":
            item = kiosk.show_item(str(args.get("item_id", "")))
            result = {"shown": item.name, "description": item.description}
        elif what == "info":
            topic_id = str(args.get("topic", ""))
            kiosk.show_info(topic_id)
            topic = kiosk.cafe.topic(topic_id)
            result = {"shown": topic.title, "text": topic.text}
        elif what == "order":
            kiosk.show_order()
            result = {"shown": "주문 내역", **self._order()}
        else:
            raise KioskError("what must be one of: menu, categories, item, info, order")
        return {**result, **self._next()}

    def _go_back(self, args: dict[str, Any]) -> Result:
        view = self.kiosk.go_back(str(args.get("to") or ""))
        return {"shown": self._describe(view), **self._next()}

    # --- ordering ----------------------------------------------------------------------------

    def _order_item(self, args: dict[str, Any]) -> Result:
        quantity = args.get("quantity")
        result = self.kiosk.order_item(
            str(args.get("item_id", "")),
            quantity=None if quantity is None else _int(quantity),
            selection=selection_from_args(self.kiosk.menu, args),
        )
        return self._item_result(result)

    def _set_options(self, args: dict[str, Any]) -> Result:
        quantity = args.get("quantity")
        draft = args.get("draft")
        name = self._target_name(args)
        result = self.kiosk.set_options(
            selection_from_args(self.kiosk.menu, args),
            quantity=None if quantity is None else _int(quantity),
            item_id=args.get("item_id") or None,
            draft_id=None if draft in (None, 0) else _int(draft),
        )
        if result.line is None and result.draft is None:
            return {"cancelled": name, **self._order(), **self._next()}
        return self._item_result(result)

    def _no_more_extras(self, args: dict[str, Any]) -> Result:
        return self._item_result(self.kiosk.no_more_extras(args.get("item_id") or None))

    def _set_dining(self, args: dict[str, Any]) -> Result:
        dining = Dining(str(args.get("dining", "")))
        self.kiosk.set_dining(dining)
        return {"dining": dining.label, **self._next()}

    def _change(self, args: dict[str, Any]) -> Result:
        quantity = args.get("quantity")
        number = _int(args.get("line", 0))
        before = self._spoken(self.kiosk.order.line(number))
        line = self.kiosk.change_line(
            number,
            quantity=None if quantity is None else _int(quantity),
            selection=selection_from_args(self.kiosk.menu, args),
        )
        if line is None:
            return {"removed": before, **self._order(), **self._next()}
        return {"changed": self._spoken(line), **self._order(), **self._next()}

    def _note_for_staff(self, args: dict[str, Any]) -> Result:
        self.kiosk.add_note(str(args.get("text", "")))
        return {"noted": self.kiosk.order.notes[-1], "say": NOTED, **self._next()}

    # --- paying ------------------------------------------------------------------------------

    def _pay(self, args: dict[str, Any]) -> Result:
        """The session checked that the customer asked to pay; it starts the card terminal once
        the read-back has been said."""
        try:
            step = self.kiosk.request_payment()
        except KioskError as e:
            return {"not_yet": str(e), **self._next()}
        if step is Ask.STAFF:
            return {"ask_first": STAFF_QUESTION, "next": ASK_STAFF}
        return {"read_back": self.kiosk.read_back, "next": SAY_READ_BACK}

    def _cancel_order(self, args: dict[str, Any]) -> Result:
        if self.kiosk.phase is Phase.PAYING:
            self.kiosk.cancel_payment()
            return {"payment_stopped": True, **self._next()}
        self.kiosk.cancel_order()
        return {"cancelled": "주문 전체", **self._next()}

    # --- results -----------------------------------------------------------------------------

    def _item_result(self, result: ItemResult) -> Result:
        out: Result = {}
        if result.line is not None:
            out["added"] = self._spoken(result.line)
            out.update(self._order())
        elif result.draft is not None:
            out["being_chosen"] = self._draft_text(result.draft)
        return {**out, **self._next()}

    def _next(self) -> Result:
        """The current question: what to ask now (the screen shows it too)."""
        kiosk = self.kiosk
        q = kiosk.question
        out: Result = {}
        if len(kiosk.drafts) > 1 or (kiosk.drafts and q.kind not in (Ask.OPTION, Ask.EXTRAS)):
            drafts = sorted(kiosk.drafts, key=lambda d: d.id)
            out["being_chosen"] = [self._draft_entry(d) for d in drafts]
        if q.kind is Ask.OPTION:
            draft = kiosk.draft(q.draft)
            group = draft.item.group(q.group) if draft else None
            if draft is not None and group is not None:
                return {**out, "ask": self._option_question(draft, group)}
        if q.kind is Ask.EXTRAS:
            draft = kiosk.draft(q.draft)
            name = draft.item.name if draft else ""
            ask = f"{name}에 {EXTRAS_QUESTION}" if name else EXTRAS_QUESTION
            return {**out, "ask": ask, "extras_note": ASK_EXTRAS}
        if q.kind is Ask.DINING:
            return {**out, "ask": DINING_QUESTION}
        if q.kind is Ask.MENU:
            empty = kiosk.order.is_empty and not kiosk.drafts
            return {**out, "ask": MENU_BOARD if empty else ANYTHING_ELSE}
        if q.kind is Ask.LINE:
            line = kiosk.order.line(q.line)
            return {
                **out,
                "line_shown": f"{q.line}. {self._spoken(line)}",
                "options": self._options(line),
                "note": LINE_SHOWN.format(line=q.line),
            }
        if q.kind is Ask.STAFF:
            return {**out, "ask": STAFF_QUESTION}
        if q.kind is Ask.REVIEW:
            return {**out, "read_back": kiosk.read_back}
        return out

    def _option_question(self, draft: Draft, group: OptionGroup) -> str:
        """e.g. "카페라떼 사이즈는 어떤 걸로 해 드릴까요?", "아메리카노는 따뜻하게 드릴까요, 차갑게
        드릴까요?" (with "차가운" in front when the same item is chosen more than once)."""
        name = draft.item.name
        same = [d for d in self.kiosk.drafts if d.item.id == draft.item.id]
        if len(same) > 1:
            said = [c.spoken for cs in draft.chosen.values() for c in cs if not c.is_none]
            name = " ".join([*said, name])
        if group.id == TEMPERATURE:
            return f"{name}{_topic(name)} 따뜻하게 드릴까요, 차갑게 드릴까요?"
        return f"{name} {group.name}{_topic(group.name)} 어떤 걸로 해 드릴까요?"

    def confirm_same(
        self, other: Draft, group: OptionGroup, choices: tuple[OptionChoice, ...], then: str = ""
    ) -> Result:
        """Ask whether an answer given for one drink is for `other` too (the same item, also
        missing `group`): "따뜻한 아메리카노도 레귤러로 해 드릴까요?"."""
        name = self._draft_name(other)
        if not group.required:  # an extra: "따뜻한 아메리카노에도 샷 추가 해 드릴까요?"
            extras = ", ".join(c.spoken for c in choices)
            note = CONFIRM_SAME.format(
                other=name, draft=other.id, group=group.id, no=CONFIRM_NO_EXTRA
            )
            if then:
                note += CONFIRM_SKIP.format(then=then)
            return {"ask": f"{name}에도 {extras} 해 드릴까요?", "confirm_note": note}
        value = choices[0].label or _with_ro(choices[0].spoken)
        rest = [c for c in group.choices if c not in choices]
        if len(rest) == 1:  # "아니" means the other one: no need to ask again
            no = CONFIRM_NO_OTHER.format(draft=other.id, group=group.id, other=rest[0].id)
        else:
            no = CONFIRM_NO_ASK.format(question=self._option_question(other, group))
        note = CONFIRM_SAME.format(other=name, draft=other.id, group=group.id, no=no)
        if then:
            note += CONFIRM_SKIP.format(then=then)
        return {"ask": f"{name}도 {value} 해 드릴까요?", "confirm_note": note}

    def held(self, other: Draft) -> str:
        return HELD.format(other=self._draft_name(other))

    def confirm_line(
        self, number: int, group: OptionGroup, choices: tuple[OptionChoice, ...], then: str = ""
    ) -> Result:
        """Ask whether an extra given for a drink being chosen is for the same item already in
        the order too: "따뜻한 레귤러 아메리카노에도 샷 추가 해 드릴까요?"."""
        name = self._line_name(self.kiosk.order.line(number))
        extras = ", ".join(c.spoken for c in choices)
        note = CONFIRM_LINE.format(other=name, line=number, group=group.id)
        if then:
            note += CONFIRM_SKIP.format(then=then)
        return {"ask": f"{name}에도 {extras} 해 드릴까요?", "confirm_note": note}

    def held_line(self, number: int) -> str:
        return HELD.format(other=self._line_name(self.kiosk.order.line(number)))

    def _line_name(self, line: CartLine) -> str:
        """e.g. "따뜻한 레귤러 아메리카노": an order line by its temperature and size."""
        said = [
            c.spoken
            for group in line.item.option_groups
            if group.required
            for c in line.chosen()[group.id]
        ]
        return " ".join([*said, line.item.name])

    def _draft_name(self, draft: Draft) -> str:
        """e.g. "따뜻한 아메리카노": what tells it apart from the same item chosen differently."""
        said = [c.spoken for cs in draft.chosen.values() for c in cs if not c.is_none]
        return " ".join([*said, draft.item.name])

    def _draft_text(self, draft: Draft) -> str:
        said = [c.spoken for cs in draft.chosen.values() for c in cs if not c.is_none]
        unit = self.kiosk.menu.unit(draft.item)
        return " ".join([*said, draft.item.name, f"{draft.quantity}{unit}"])

    def _draft_entry(self, draft: Draft) -> Result:
        return {
            "draft": draft.id,
            "item_id": draft.item.id,
            "what": self._draft_text(draft),
            "missing": [g.name for g in draft.missing]
            or (["extras"] if draft.asking == EXTRAS else []),
        }

    def _target_name(self, args: dict[str, Any]) -> str:
        try:
            draft = args.get("draft")
            found = self.kiosk.find_draft(
                args.get("item_id") or None, None, None if not draft else _int(draft)
            )
        except (KioskError, TypeError, ValueError):
            return ""
        return found.item.name

    def _options(self, line: CartLine) -> dict[str, str]:
        """An order line's options by name, e.g. {"온도": "차가운", "시럽": "없음"}."""
        return {
            group.name: ", ".join(c.spoken for c in line.chosen()[group.id]) or "없음"
            for group in line.item.option_groups
        }

    def _describe(self, view: View) -> str:
        """What a view shows, for the model."""
        menu = self.kiosk.menu
        if view.screen is Screen.ITEM:
            name = menu.item(view.item_id).name
            return f"{view.line}번 주문 {name}" if view.line else name
        if view.screen is Screen.MENU:
            return view.title or ", ".join(self._names(view.item_ids))
        if view.screen is Screen.INFO:
            return self.kiosk.cafe.topic(view.topic).title
        return {Screen.CATEGORIES: "메뉴 종류", Screen.REVIEW: "주문 내역"}.get(
            view.screen, view.screen.value
        )

    def _order(self) -> Result:
        order = self.kiosk.order
        return {
            "order": [
                f"{n}. {self._spoken(line)} {won_spoken(line.total)}"
                for n, line in enumerate(order.lines, start=1)
            ],
            "total": won_spoken(order.total),
        }

    def _spoken(self, line: CartLine) -> str:
        return line.spoken(self.kiosk.menu.unit(line.item))

    def _names(self, item_ids: tuple[str, ...]) -> list[str]:
        return [self.kiosk.menu.item(i).name for i in item_ids]


def _topic(word: str) -> str:
    """은 after a final consonant, 는 otherwise ("사이즈는", "카페라떼는", "온도는")."""
    last = word[-1] if word else ""
    if "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28:
        return "은"
    return "는"


def _with_ro(word: str) -> str:
    """으로 after a final consonant other than ㄹ, 로 otherwise ("레귤러로", "라지로")."""
    last = word[-1] if word else ""
    if "가" <= last <= "힣":
        final = (ord(last) - 0xAC00) % 28
        if final and final != 8:  # 8: ㄹ
            return f"{word}으로"
    return f"{word}로"


def _int(value: Any) -> int:
    """Whole numbers may arrive as floats (2.0) from JSON."""
    number = float(value)
    if not number.is_integer():
        raise ValueError(f"{value!r} is not a whole number")
    return int(number)
