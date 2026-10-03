"""The customer's order: cart lines, dine-in or take-out, and the read-back before payment.

Adapted from the earlier prototype's cart logic. Lines are numbered from 1 for the model and the
display. Every change increases `version`, so a review can tell whether the order changed since.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import StrEnum

from kiosk.domain.menu import SIZE, TEMPERATURE, KioskError, Menu, MenuItem, OptionChoice

MAX_QUANTITY = 20


class Dining(StrEnum):
    HERE = "here"
    TO_GO = "to_go"

    @property
    def label(self) -> str:
        return "매장" if self is Dining.HERE else "포장"


def won(amount: int) -> str:
    """Format a price, e.g. 4500 -> "4,500원"."""
    return f"{amount:,}원"


def check_quantity(quantity: int) -> None:
    if not 1 <= quantity <= MAX_QUANTITY:
        raise KioskError(f"quantity must be 1..{MAX_QUANTITY}, got {quantity}")


@dataclass
class CartLine:
    item: MenuItem
    choices: tuple[OptionChoice, ...]
    quantity: int

    @property
    def unit_price(self) -> int:
        return self.item.price + sum(c.price for c in self.choices)

    @property
    def total(self) -> int:
        return self.unit_price * self.quantity

    @property
    def option_text(self) -> str:
        """Short option summary for the screen, e.g. "ICE, Large, 샷 추가"."""
        return ", ".join(c.name for c in self.choices if not c.is_none)

    def chosen(self) -> dict[str, tuple[OptionChoice, ...]]:
        """The line's choices by group id."""
        return {
            group.id: tuple(c for c in self.choices if c.group_id == group.id)
            for group in self.item.option_groups
        }

    def spoken(self, unit: str) -> str:
        """How the line is read aloud, e.g. "아이스 아메리카노 라지(샷 추가) 2잔"."""
        temperature = [c.spoken for c in self.choices if c.group_id == TEMPERATURE]
        size = [c.spoken for c in self.choices if c.group_id == SIZE]
        extras = [
            c.spoken
            for c in self.choices
            if c.group_id not in (TEMPERATURE, SIZE) and not c.is_none
        ]
        text = " ".join([*temperature, self.item.name, *size])
        if extras:
            text += f"({', '.join(extras)})"
        return f"{text} {self.quantity}{unit}"


@dataclass
class Order:
    lines: list[CartLine] = field(default_factory=list)
    dining: Dining | None = None
    version: int = 0

    def add(self, item: MenuItem, choices: tuple[OptionChoice, ...], quantity: int = 1) -> CartLine:
        """Add an item. An identical item+options line is merged by increasing its quantity."""
        check_quantity(quantity)
        for line in self.lines:
            if line.item == item and line.choices == choices:
                check_quantity(line.quantity + quantity)
                line.quantity += quantity
                self._changed()
                return line
        line = CartLine(item, choices, quantity)
        self.lines.append(line)
        self._changed()
        return line

    def line(self, number: int) -> CartLine:
        if not 1 <= number <= len(self.lines):
            raise KioskError(f"there is no order line {number} (the order has {len(self.lines)})")
        return self.lines[number - 1]

    def set_quantity(self, number: int, quantity: int) -> None:
        """Set a line's quantity. Zero removes the line."""
        line = self.line(number)
        if quantity == 0:
            self.remove(number)
            return
        check_quantity(quantity)
        line.quantity = quantity
        self._changed()

    def set_choices(self, number: int, choices: tuple[OptionChoice, ...]) -> CartLine:
        """Change a line's options. If it now equals another line, the two are merged."""
        line = self.line(number)
        twin = next(
            (
                o
                for o in self.lines
                if o is not line and o.item == line.item and o.choices == choices
            ),
            None,
        )
        if twin is not None:
            check_quantity(twin.quantity + line.quantity)
            twin.quantity += line.quantity
            self.lines.remove(line)
            self._changed()
            return twin
        line.choices = choices
        self._changed()
        return line

    def remove(self, number: int) -> None:
        self.lines.remove(self.line(number))
        self._changed()

    def set_dining(self, dining: Dining) -> None:
        if dining != self.dining:
            self.dining = dining
            self._changed()

    def clear(self) -> None:
        """Start a brand new order."""
        self.lines.clear()
        self.dining = None
        self._changed()

    @property
    def is_empty(self) -> bool:
        return not self.lines

    @property
    def total(self) -> int:
        return sum(line.total for line in self.lines)

    def number_of(self, line: CartLine) -> int:
        return self.lines.index(line) + 1

    def read_back(self, menu: Menu) -> str:
        """The statement read to the customer before payment (not a question)."""
        if self.is_empty:
            raise KioskError("the order is empty")
        items = ", ".join(line.spoken(menu.unit(line.item)) for line in self.lines)
        total = f"총 {won(self.total)}입니다."
        if self.dining is Dining.HERE:
            total = f"매장에서 드시고 {total}"
        elif self.dining is Dining.TO_GO:
            total = f"포장으로 {total}"
        return f"주문 확인해 드릴게요. {items}, {total}"

    def _changed(self) -> None:
        self.version += 1


class OrderNumbers:
    """Hands out increasing order numbers."""

    def __init__(self, start: int = 1) -> None:
        self._counter = itertools.count(start)

    def next(self) -> int:
        return next(self._counter)
