"""Run the model's function calls on the kiosk and describe the result for the model.

Every call is validated by the domain (`KioskError`); mistakes come back as {"error": ...} so the
model can correct itself or tell the customer. Results use Korean names (what the model says),
not ids. The safety rules that need the conversation are applied before this, by the session
(`session.py`, with the checks in `safety.py`).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from kiosk.assistant.tools import selection_from_args
from kiosk.domain.flow import EXTRAS, ItemResult, Kiosk, PendingItem, Screen, View
from kiosk.domain.menu import KioskError, OptionGroup
from kiosk.domain.order import CartLine, Dining, won

log = logging.getLogger(__name__)

Result = dict[str, Any]

# The screen shows one question at a time and marks each answer as soon as it is set.
ASK_ONE = (
    "Ask only this, naming the choices. When the customer answers, call set_options at once "
    "(with anything else they said too); the result says what to ask next."
)
ASK_EXTRAS = (
    "Ask briefly '추가하실 거 있으세요?' without reading the extras out (the screen lists "
    "them). For what they want, call set_options and ask '더 추가하실 거 있으세요?'. When they "
    "want nothing (more), call finish_item: only then is the item in the order."
)
STAFF_QUESTION = "직원에게 따로 전달할 말씀 있으세요?"
ASK_STAFF = (
    "Before the read-back, ask exactly this. If they have something, call note_for_staff. Then "
    "call request_payment again (they already asked to pay)."
)
NOTED = "네, 알겠습니다. 해당 사항은 직원에게 전달하겠습니다."


class Actions:
    def __init__(self, kiosk: Kiosk) -> None:
        self.kiosk = kiosk
        self._handlers: dict[str, Callable[[dict[str, Any]], Result]] = {
            "show_menu": self._show_menu,
            "show_categories": self._show_categories,
            "show_item": self._show_item,
            "show_info": self._show_info,
            "choose_item": self._choose_item,
            "set_options": self._set_options,
            "finish_item": self._finish_item,
            "cancel_item": self._cancel_item,
            "edit_line": self._edit_line,
            "go_back": self._go_back,
            "note_for_staff": self._note_for_staff,
            "change_line": self._change_line,
            "set_dining": self._set_dining,
            "show_order": self._show_order,
            "request_payment": self._request_payment,
            "cancel_payment": self._cancel_payment,
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
            return {"error": str(e)}
        except (TypeError, ValueError) as e:
            log.warning("bad arguments for %s: %s (%s)", name, args, e)
            return {"error": f"invalid arguments: {e}"}

    # --- display -----------------------------------------------------------------------------

    def _show_menu(self, args: dict[str, Any]) -> Result:
        shown = self.kiosk.show_menu(
            title=str(args.get("title") or ""),
            category=args.get("category") or None,
            item_ids=list(args.get("item_ids") or []),
            highlight_ids=list(args.get("highlight_ids") or []),
            exclude_allergens=list(args.get("exclude_allergens") or []),
        )
        result: Result = {"shown": self._names(shown.item_ids)}
        if shown.removed:
            result["left_out_for_allergens"] = self._names(shown.removed)
        return result

    def _show_categories(self, args: dict[str, Any]) -> Result:
        self.kiosk.show_categories()
        return {"shown": [c.name for c in self.kiosk.menu.categories]}

    def _show_item(self, args: dict[str, Any]) -> Result:
        item = self.kiosk.show_item(str(args.get("item_id", "")))
        return {"shown": item.name}

    def _show_info(self, args: dict[str, Any]) -> Result:
        topic_id = str(args.get("topic", ""))
        self.kiosk.show_info(topic_id)
        topic = self.kiosk.cafe.topic(topic_id)
        return {"shown": topic.title, "text": topic.text}

    # --- ordering ----------------------------------------------------------------------------

    def _choose_item(self, args: dict[str, Any]) -> Result:
        menu = self.kiosk.menu
        result = self.kiosk.choose_item(
            str(args.get("item_id", "")),
            quantity=_int(args.get("quantity", 1)),
            selection=selection_from_args(menu, args),
        )
        return self._item_result(result)

    def _set_options(self, args: dict[str, Any]) -> Result:
        quantity = args.get("quantity")
        result = self.kiosk.set_options(
            selection_from_args(self.kiosk.menu, args),
            quantity=None if quantity is None else _int(quantity),
            item_id=args.get("item_id") or None,
        )
        return self._item_result(result)

    def _finish_item(self, args: dict[str, Any]) -> Result:
        return self._item_result(self.kiosk.finish_item(args.get("item_id") or None))

    def _cancel_item(self, args: dict[str, Any]) -> Result:
        self.kiosk.cancel_item(args.get("item_id") or None)
        return {"ok": True, **self._order(), **self._waiting()}

    def _edit_line(self, args: dict[str, Any]) -> Result:
        line = self.kiosk.edit_line(_int(args.get("line", 0)), str(args.get("option") or ""))
        return {"shown": self._spoken(line), "options": self._options(line)}

    def _go_back(self, args: dict[str, Any]) -> Result:
        return {"shown": self._describe(self.kiosk.go_back())}

    def _note_for_staff(self, args: dict[str, Any]) -> Result:
        self.kiosk.add_note(str(args.get("text", "")))
        return {"noted": self.kiosk.order.notes[-1], "say": NOTED}

    def _change_line(self, args: dict[str, Any]) -> Result:
        quantity = args.get("quantity")
        number = _int(args.get("line", 0))
        before = self.kiosk.order.line(number).spoken(self._unit(self.kiosk.order.line(number)))
        line = self.kiosk.change_line(
            number,
            quantity=None if quantity is None else _int(quantity),
            selection=selection_from_args(self.kiosk.menu, args),
        )
        if line is None:
            return {"removed": before, **self._order()}
        return {"changed": self._spoken(line), **self._order()}

    def _set_dining(self, args: dict[str, Any]) -> Result:
        dining = Dining(str(args.get("dining", "")))
        self.kiosk.set_dining(dining)
        return {"dining": dining.label}

    # --- review and payment ------------------------------------------------------------------

    def _show_order(self, args: dict[str, Any]) -> Result:
        self.kiosk.show_order()
        return {"shown": True, **self._order()}

    def _request_payment(self, args: dict[str, Any]) -> Result:
        """The review before payment. The session checks that the customer asked to pay, and
        starts the terminal (`Kiosk.start_payment`) once the read-back has been said."""
        if self.kiosk.ask_staff_question():
            return {"ask_first": STAFF_QUESTION, "next": ASK_STAFF}
        return {"read_back": self.kiosk.review()}

    def _cancel_payment(self, args: dict[str, Any]) -> Result:
        self.kiosk.cancel_payment()
        return {"ok": True}

    def _cancel_order(self, args: dict[str, Any]) -> Result:
        self.kiosk.cancel_order()
        return {"ok": True, "order": []}

    # --- helpers -----------------------------------------------------------------------------

    def _item_result(self, result: ItemResult) -> Result:
        if result.line is not None:
            return {"added": self._spoken(result.line), **self._order(), **self._waiting()}
        pending = result.pending
        assert pending is not None
        if pending.asking == EXTRAS:
            chosen = [c.spoken for cs in pending.chosen.values() for c in cs if not c.is_none]
            question: Result = {
                "extras": [_question(g, extra=True) for g in pending.extras],
                **({"chosen": chosen} if chosen else {}),
                "next": ASK_EXTRAS,
            }
        else:
            group = pending.item.group(pending.asking)
            assert group is not None
            question = {"ask": _question(group), "next": ASK_ONE}
        return {"not_added_yet": pending.item.name, **question, **self._waiting(besides=pending)}

    def _options(self, line: CartLine) -> dict[str, str]:
        """An order line's options by name, e.g. {"온도": "아이스", "시럽": "없음"}."""
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

    def _waiting(self, besides: PendingItem | None = None) -> Result:
        """Other items still waiting for options, so the model does not forget them."""
        waiting = [p for p in self.kiosk.pending_items if p is not besides]
        if not waiting:
            return {}
        return {
            "still_waiting_for_options": [
                {"item_id": p.item.id, "name": p.item.name, "missing": [g.name for g in p.missing]}
                for p in waiting
            ]
        }

    def _order(self) -> Result:
        order = self.kiosk.order
        return {
            "order": [
                f"{n}. {self._spoken(line)} {won(line.total)}"
                for n, line in enumerate(order.lines, start=1)
            ],
            "total": won(order.total),
        }

    def _spoken(self, line: CartLine) -> str:
        return line.spoken(self._unit(line))

    def _unit(self, line: CartLine) -> str:
        return self.kiosk.menu.unit(line.item)

    def _names(self, item_ids: tuple[str, ...]) -> list[str]:
        return [self.kiosk.menu.item(i).name for i in item_ids]


def _question(group: OptionGroup, extra: bool = False) -> Result:
    choices = [c for c in group.choices if not (extra and c.is_none)]
    return {
        "option": group.name,
        "choices": [f"{c.spoken} (+{won(c.price)})" if c.price else c.spoken for c in choices],
    }


def _int(value: Any) -> int:
    """Whole numbers may arrive as floats (2.0) from JSON."""
    number = float(value)
    if not number.is_integer():
        raise ValueError(f"{value!r} is not a whole number")
    return int(number)
