"""Run the model's function calls on the kiosk and describe the result for the model.

Every call is validated by the domain (`KioskError`); mistakes come back as {"error": ...} so the
model can correct itself or tell the customer. Results use Korean names (what the model says),
not ids. The safety rules that need the conversation are applied before this, in `safety.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from kiosk.assistant.tools import selection_from_args
from kiosk.domain.flow import ItemResult, Kiosk
from kiosk.domain.menu import KioskError, OptionGroup
from kiosk.domain.order import CartLine, Dining, won

log = logging.getLogger(__name__)

Result = dict[str, Any]


class Actions:
    def __init__(self, kiosk: Kiosk) -> None:
        self.kiosk = kiosk
        self._handlers: dict[str, Callable[[dict[str, Any]], Result]] = {
            "show_menu": self._show_menu,
            "show_item": self._show_item,
            "show_info": self._show_info,
            "choose_item": self._choose_item,
            "set_options": self._set_options,
            "cancel_item": self._cancel_item,
            "change_line": self._change_line,
            "set_dining": self._set_dining,
            "review_order": self._review_order,
            "start_payment": self._start_payment,
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
        )
        return self._item_result(result)

    def _cancel_item(self, args: dict[str, Any]) -> Result:
        self.kiosk.cancel_item()
        return {"ok": True, **self._order()}

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

    def _review_order(self, args: dict[str, Any]) -> Result:
        return {"read_back": self.kiosk.review()}

    def _start_payment(self, args: dict[str, Any]) -> Result:
        self.kiosk.start_payment()
        return {"status": "the card terminal is waiting for the card"}

    def _cancel_payment(self, args: dict[str, Any]) -> Result:
        self.kiosk.cancel_payment()
        return {"ok": True}

    def _cancel_order(self, args: dict[str, Any]) -> Result:
        self.kiosk.cancel_order()
        return {"ok": True, "order": []}

    # --- helpers -----------------------------------------------------------------------------

    def _item_result(self, result: ItemResult) -> Result:
        if result.line is not None:
            return {"added": self._spoken(result.line), **self._order()}
        pending = self.kiosk.pending
        assert pending is not None
        return {
            "not_added_yet": pending.item.name,
            "ask": [_question(g) for g in result.missing],
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


def _question(group: OptionGroup) -> Result:
    return {
        "option": group.name,
        "choices": [
            f"{c.spoken} (+{won(c.price)})" if c.price else c.spoken for c in group.choices
        ],
    }


def _int(value: Any) -> int:
    """Whole numbers may arrive as floats (2.0) from JSON."""
    number = float(value)
    if not number.is_integer():
        raise ValueError(f"{value!r} is not a whole number")
    return int(number)
