"""The kiosk's state for one customer at a time: phase, order, the item being chosen, and what
the display shows.

Phases: idle -> ordering -> paying (insert card -> processing) -> done -> idle. Lifting the
handset starts a session (the screen asks: here or to go?), hanging up ends it from any phase.

An item is chosen in steps: each required option (one at a time, in the item's order), then its
extras (shots, syrups, ...), then `finish_item` adds it. Items without extras are added as soon
as the required options are known. The views the customer saw are remembered, so `go_back`
returns to the previous one. Every method either changes the
state or raises `KioskError` with a message for the model; `revision` counts the changes so the
server knows when to push a new snapshot.

Rules that need the conversation (did the customer ask to pay? did they say yes?) are checked by
the assistant; the rules here only need the state itself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from kiosk.domain.cafe import Cafe
from kiosk.domain.menu import (
    Chosen,
    KioskError,
    Menu,
    MenuItem,
    OptionGroup,
    item_allergens,
)
from kiosk.domain.order import CartLine, Dining, Order, OrderNumbers, check_quantity

Selection = Mapping[str, str | Sequence[str]]  # option group id -> choice id(s)


class Phase(StrEnum):
    IDLE = "idle"
    ORDERING = "ordering"
    PAYING = "paying"
    DONE = "done"


class PaymentStep(StrEnum):
    INSERT_CARD = "insert_card"
    PROCESSING = "processing"
    APPROVED = "approved"


class Screen(StrEnum):
    ATTRACT = "attract"
    DINING = "dining"  # here or to go?
    WELCOME = "welcome"
    MENU = "menu"
    CATEGORIES = "categories"
    ITEM = "item"
    INFO = "info"
    REVIEW = "review"
    PAYMENT = "payment"
    DONE = "done"


@dataclass(frozen=True)
class View:
    """What the display shows. The assistant chooses it through the show_* actions."""

    screen: Screen = Screen.ATTRACT
    title: str = ""
    item_ids: tuple[str, ...] = ()  # menu screen: the items to show, in order
    highlight: tuple[str, ...] = ()  # menu screen: recommended items among them
    item_id: str = ""  # item screen
    # item screen: the option group listed (a group id, EXTRAS for the item's extras, or "" for
    # none: the facts, or an order line's options at a glance)
    group: str = ""
    line: int = 0  # item screen: the order line shown (from 1), 0 = not an order line
    topic: str = ""  # info screen


EXTRAS = "extras"  # View.group: the item's extras (shots, syrups, ...), all at once
HISTORY = 20  # views remembered for go_back
# Views worth going back to (not the start, the take-out question, payment or done).
_REMEMBERED = {Screen.MENU, Screen.CATEGORIES, Screen.ITEM, Screen.INFO, Screen.REVIEW}


@dataclass
class PendingItem:
    """The item the customer is choosing options for: required ones first, then its extras."""

    item: MenuItem
    quantity: int = 1
    chosen: Chosen = field(default_factory=dict)
    extras_done: bool = False  # the customer said they want no (more) extras

    @property
    def missing(self) -> tuple[OptionGroup, ...]:
        return self.item.missing(self.chosen)

    @property
    def extras(self) -> tuple[OptionGroup, ...]:
        return tuple(g for g in self.item.option_groups if not g.required)

    @property
    def asking(self) -> str:
        """What is asked now: a required group's id, EXTRAS, or "" (ready to be added)."""
        if self.missing:
            return self.missing[0].id
        if self.extras and not self.extras_done:
            return EXTRAS
        return ""


@dataclass(frozen=True)
class MenuShown:
    item_ids: tuple[str, ...]
    removed: tuple[str, ...]  # left out because they contain an excluded allergen


@dataclass(frozen=True)
class ItemResult:
    """`line` is set when the item went into the order; otherwise `pending` is the item still
    being chosen, and `pending.asking` says what to ask next."""

    line: CartLine | None
    missing: tuple[OptionGroup, ...] = ()
    pending: PendingItem | None = None


class Kiosk:
    def __init__(self, menu: Menu, cafe: Cafe, first_order_number: int = 1) -> None:
        self.menu = menu
        self.cafe = cafe
        self._numbers = OrderNumbers(first_order_number)
        self.revision = 0
        self.phase = Phase.IDLE
        self.order = Order()
        # Items waiting for required options ("라떼 하나랑 아메리카노 하나" waits for both).
        self.pending_items: list[PendingItem] = []
        self.view = View()
        self.payment_step: PaymentStep | None = None
        self.order_number: int | None = None
        self.reviewed_version: int | None = None
        self.staff_asked = False  # "직원에게 전달할 말씀 있으세요?" was asked before payment
        self._menu_view: View | None = None  # where to return after an item was added
        self._history: list[View] = []  # views to go back to, oldest first

    # --- session -----------------------------------------------------------------------------

    def start_session(self) -> None:
        """The handset was lifted."""
        if self.phase is not Phase.IDLE:
            raise KioskError("a session is already running")
        self._reset(Phase.ORDERING, View(screen=Screen.DINING))

    def end_session(self) -> None:
        """The handset was put down (or the done screen timed out): forget everything."""
        self._reset(Phase.IDLE, View())

    # --- display -----------------------------------------------------------------------------

    def show_menu(
        self,
        title: str = "",
        category: str | None = None,
        item_ids: Sequence[str] = (),
        highlight_ids: Sequence[str] = (),
        exclude_allergens: Sequence[str] = (),
    ) -> MenuShown:
        """Show a chosen set of items (or a category, or everything) under a heading."""
        self._require(Phase.ORDERING)
        if item_ids:
            items = [self.menu.item(i) for i in dict.fromkeys(item_ids)]
        elif category:
            items = list(self.menu.items_in(category))
        else:
            items = list(self.menu.items)
        excluded = {self.menu.allergen(a).id for a in exclude_allergens}
        shown = tuple(i.id for i in items if not excluded & item_allergens(i))
        removed = tuple(i.id for i in items if i.id not in shown)
        highlight = tuple(self.menu.item(i).id for i in highlight_ids)
        if not title:
            title = self.menu.category(category).name if category else ""
        view = View(
            screen=Screen.MENU,
            title=title,
            item_ids=shown,
            highlight=tuple(i for i in highlight if i in shown),
        )
        self._menu_view = view
        self._set_view(view)
        return MenuShown(item_ids=shown, removed=removed)

    def show_categories(self) -> None:
        """Show the kinds of menu (커피, 라떼, ...) so the customer can pick one."""
        self._require(Phase.ORDERING)
        self._set_view(View(screen=Screen.CATEGORIES))

    def show_item(self, item_id: str) -> MenuItem:
        """Show one item's details without ordering it."""
        self._require(Phase.ORDERING)
        item = self.menu.item(item_id)
        self._set_view(View(screen=Screen.ITEM, item_id=item.id))
        return item

    def show_info(self, topic_id: str) -> None:
        """Show a cafe-info card. Also allowed after payment ("화장실 어디예요?")."""
        self._require(Phase.ORDERING, Phase.DONE)
        topic = self.cafe.topic(topic_id)
        self._set_view(View(screen=Screen.INFO, topic=topic.id))

    def go_back(self) -> View:
        """Show the previous view again ("이전 화면"). An item chosen since is shown as its
        order line."""
        self._require(Phase.ORDERING)
        while self._history:
            view = self._revive(self._history.pop())
            if view is not None and view != self.view:
                self._set_view(view, remember=False)
                return view
        raise KioskError("there is no previous screen")

    def edit_line(self, number: int, group_id: str = "") -> CartLine:
        """Show an order line's options again: one group's choices, or all of them at a
        glance (no `group_id`). Change them with `change_line`."""
        self._require(Phase.ORDERING)
        line = self.order.line(number)
        if group_id and line.item.group(group_id) is None:
            groups = ", ".join(g.id for g in line.item.option_groups) or "none"
            raise KioskError(f"{line.item.id} has no {group_id} option (it has: {groups})")
        self._show_line(line, group_id)
        return line

    # --- choosing items ----------------------------------------------------------------------

    @property
    def pending(self) -> PendingItem | None:
        """The item being chosen that the screen shows (the one touched last)."""
        return self.pending_items[-1] if self.pending_items else None

    def choose_item(
        self, item_id: str, quantity: int = 1, selection: Selection | None = None
    ) -> ItemResult:
        """Start choosing an item. It is added at once if every required option is known;
        otherwise it waits (next to others still waiting) until `set_options` completes it.
        Choosing an item that is already waiting starts it over."""
        self._require(Phase.ORDERING)
        item = self.menu.item(item_id)
        check_quantity(quantity)
        chosen = self.menu.resolve(item, selection or {})
        self.pending_items = [p for p in self.pending_items if p.item.id != item.id]
        pending = PendingItem(item=item, quantity=quantity, chosen=chosen)
        self.pending_items.append(pending)
        return self._try_add(pending)

    def set_options(
        self,
        selection: Selection | None = None,
        quantity: int | None = None,
        item_id: str | None = None,
    ) -> ItemResult:
        """Add options (or change the quantity) of an item being chosen (the last one, unless
        `item_id` says which)."""
        self._require(Phase.ORDERING)
        pending = self.pending_item(item_id)
        chosen = self.menu.resolve(pending.item, selection or {})
        if quantity is not None:
            check_quantity(quantity)
            pending.quantity = quantity
        pending.chosen.update(chosen)
        # The item answered last is the one on screen.
        self.pending_items.remove(pending)
        self.pending_items.append(pending)
        return self._try_add(pending)

    def cancel_item(self, item_id: str | None = None) -> None:
        """Drop an item being chosen (the last one, unless `item_id` says which)."""
        self._require(Phase.ORDERING)
        self.pending_items.remove(self.pending_item(item_id))
        self._show_after_choosing()

    def finish_item(self, item_id: str | None = None) -> ItemResult:
        """The customer wants no (more) extras: add the item (the last one, unless `item_id`)."""
        self._require(Phase.ORDERING)
        pending = self.pending_item(item_id)
        if pending.missing:
            names = ", ".join(g.id for g in pending.missing)
            raise KioskError(f"{pending.item.id}: ask for {names} first")
        pending.extras_done = True
        return self._try_add(pending)

    def pending_item(self, item_id: str | None = None) -> PendingItem:
        if not self.pending_items:
            raise KioskError("no item is being chosen; use choose_item")
        if not item_id:
            return self.pending_items[-1]
        for pending in self.pending_items:
            if pending.item.id == item_id:
                return pending
        waiting = ", ".join(p.item.id for p in self.pending_items)
        raise KioskError(f"{item_id} is not being chosen (waiting: {waiting})")

    # --- changing the order ------------------------------------------------------------------

    def change_line(
        self, number: int, quantity: int | None = None, selection: Selection | None = None
    ) -> CartLine | None:
        """Change a line's options and/or quantity. Quantity 0 removes it (returns None)."""
        self._require(Phase.ORDERING)
        line = self.order.line(number)
        if quantity == 0:
            self.order.remove(number)
            if self.view.line:
                self._set_view(self._menu_view or View(screen=Screen.WELCOME), remember=False)
            self._touch()
            return None
        resolved = self.menu.resolve(line.item, selection or {})
        if resolved:
            line = self.order.set_choices(number, line.item.complete(line.chosen() | resolved))
        if quantity is not None:
            self.order.set_quantity(self.order.number_of(line), quantity)
        if resolved:
            # The changed option is on screen again, with the new choice marked.
            self._show_line(line, next(iter(resolved)) if len(resolved) == 1 else "")
        elif self.view.line:
            self._show_line(line, self.view.group)  # its number may have changed
        self._touch()
        return line

    def set_dining(self, dining: Dining) -> None:
        self._require(Phase.ORDERING)
        self.order.set_dining(dining)
        if self.view.screen is Screen.DINING:
            self._set_view(View(screen=Screen.WELCOME), remember=False)
        self._touch()

    def add_note(self, text: str) -> None:
        """A request the kiosk cannot handle itself, passed on to the staff."""
        self._require(Phase.ORDERING)
        self.order.add_note(text)
        self._touch()

    def cancel_order(self) -> None:
        """Throw the whole order away (the assistant checks the customer's confirmation)."""
        self._require(Phase.ORDERING)
        self.order.clear()
        self.pending_items = []
        self.reviewed_version = None
        self.staff_asked = False
        self._menu_view = None
        self._history = []
        self._set_view(View(screen=Screen.DINING), remember=False)

    def show_order(self) -> None:
        """Show the order (display only; a review before payment is `review`)."""
        self._require(Phase.ORDERING)
        self._set_view(View(screen=Screen.REVIEW))

    # --- review and payment ------------------------------------------------------------------

    def ask_staff_question(self) -> bool:
        """Before the first review: True once, when the assistant should ask whether there is
        anything for the staff (the screen shows the order meanwhile)."""
        self._require(Phase.ORDERING)
        self._check_ready_to_pay()
        if self.staff_asked:
            return False
        self.staff_asked = True
        self._set_view(View(screen=Screen.REVIEW))
        return True

    def review(self) -> str:
        """Show the order for review and return the read-back the assistant must say."""
        self._require(Phase.ORDERING)
        self._check_ready_to_pay()
        read_back = self.order.read_back(self.menu)
        self.reviewed_version = self.order.version
        self._set_view(View(screen=Screen.REVIEW))
        return read_back

    @property
    def review_is_current(self) -> bool:
        """True if the order was reviewed and has not changed since."""
        return self.reviewed_version == self.order.version

    def start_payment(self) -> None:
        self._require(Phase.ORDERING)
        self._check_ready_to_pay()
        if not self.review_is_current:
            raise KioskError("review the order (review_order) before payment")
        self.phase = Phase.PAYING
        self.payment_step = PaymentStep.INSERT_CARD
        self._set_view(View(screen=Screen.PAYMENT))

    def advance_payment(self) -> None:
        """The simulated terminal moves on: card inserted -> processing -> approved (done)."""
        self._require(Phase.PAYING)
        if self.payment_step is PaymentStep.INSERT_CARD:
            self.payment_step = PaymentStep.PROCESSING
            self._touch()
        else:
            self.payment_step = PaymentStep.APPROVED
            self.order_number = self._numbers.next()
            self.phase = Phase.DONE
            self._set_view(View(screen=Screen.DONE))

    def cancel_payment(self) -> None:
        """Back to ordering while the terminal still waits for the card."""
        self._require(Phase.PAYING)
        if self.payment_step is not PaymentStep.INSERT_CARD:
            raise KioskError("the payment is already being processed")
        self.phase = Phase.ORDERING
        self.payment_step = None
        self._set_view(View(screen=Screen.REVIEW))

    # --- helpers -----------------------------------------------------------------------------

    def _try_add(self, pending: PendingItem) -> ItemResult:
        if pending.asking:
            self._show_pending(pending)
            return ItemResult(line=None, missing=pending.missing, pending=pending)
        line = self.order.add(pending.item, pending.item.complete(pending.chosen), pending.quantity)
        self.pending_items.remove(pending)
        self._show_after_choosing()
        return ItemResult(line=line)

    def _show_pending(self, pending: PendingItem) -> None:
        self._set_view(View(screen=Screen.ITEM, item_id=pending.item.id, group=pending.asking))

    def _show_line(self, line: CartLine, group_id: str = "") -> None:
        number = self.order.number_of(line)
        self._set_view(View(screen=Screen.ITEM, item_id=line.item.id, group=group_id, line=number))

    def _show_after_choosing(self) -> None:
        """The next item still waiting for options, or back to the menu."""
        if self.pending_items:
            self._show_pending(self.pending_items[-1])
        else:
            self._set_view(self._menu_view or View(screen=Screen.WELCOME))

    def _revive(self, view: View) -> View | None:
        """A remembered view as it can be shown now. An item chosen since then is shown as its
        order line (its options at a glance, or the same option group)."""
        if view.screen is not Screen.ITEM:
            return view
        for pending in self.pending_items:
            if pending.item.id == view.item_id:
                return View(screen=Screen.ITEM, item_id=pending.item.id, group=pending.asking)
        numbers = [n for n, ln in enumerate(self.order.lines, 1) if ln.item.id == view.item_id]
        if view.line in numbers:
            numbers = [view.line]
        if numbers:
            group = "" if view.group == EXTRAS else view.group
            return View(screen=Screen.ITEM, item_id=view.item_id, group=group, line=numbers[-1])
        return View(screen=Screen.ITEM, item_id=view.item_id)

    def _check_ready_to_pay(self) -> None:
        if self.order.is_empty:
            raise KioskError("the order is empty")
        if self.pending_items:
            waiting = ", ".join(p.item.id for p in self.pending_items)
            raise KioskError(
                f"still being chosen: {waiting}; finish them (finish_item) or cancel_item first"
            )
        if self.order.dining is None:
            self._set_view(View(screen=Screen.DINING))  # the screen asks along
            raise KioskError("ask whether the customer eats here or takes out first")

    def _require(self, *phases: Phase) -> None:
        if self.phase not in phases:
            raise KioskError(f"not possible while the kiosk is {self.phase.value}")

    def _set_view(self, view: View, remember: bool = True) -> None:
        """Show `view`; the one shown before is remembered for go_back when the customer
        moves to something else (not between the option steps of the same item)."""
        old = self.view
        if remember and old.screen in _REMEMBERED and not _same_place(old, view):
            self._history = [*self._history, old][-HISTORY:]
        self.view = view
        self._touch()

    def _touch(self) -> None:
        self.revision += 1

    def _reset(self, phase: Phase, view: View) -> None:
        self.phase = phase
        self.order = Order()
        self.pending_items = []
        self.payment_step = None
        self.order_number = None
        self.reviewed_version = None
        self.staff_asked = False
        self._menu_view = None
        self._history = []
        self._set_view(view, remember=False)


def _same_place(a: View, b: View) -> bool:
    """The same thing on screen, perhaps another of its option steps."""
    where = (a.screen, a.item_id, a.line, a.topic, a.title, a.item_ids)
    return where == (b.screen, b.item_id, b.line, b.topic, b.title, b.item_ids)
