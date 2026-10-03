"""The kiosk's state for one customer at a time: phase, order, the item being chosen, and what
the display shows.

Phases: idle -> ordering -> paying (insert card -> processing) -> done -> idle. Lifting the
handset starts a session, hanging up ends it from any phase. Every method either changes the
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
    topic: str = ""  # info screen


@dataclass
class PendingItem:
    """The item the customer is choosing options for; added once every required one is known."""

    item: MenuItem
    quantity: int = 1
    chosen: Chosen = field(default_factory=dict)

    @property
    def missing(self) -> tuple[OptionGroup, ...]:
        return self.item.missing(self.chosen)


@dataclass(frozen=True)
class MenuShown:
    item_ids: tuple[str, ...]
    removed: tuple[str, ...]  # left out because they contain an excluded allergen


@dataclass(frozen=True)
class ItemResult:
    """`line` is set when the item went into the order, else `missing` lists what to ask."""

    line: CartLine | None
    missing: tuple[OptionGroup, ...] = ()


class Kiosk:
    def __init__(self, menu: Menu, cafe: Cafe, first_order_number: int = 1) -> None:
        self.menu = menu
        self.cafe = cafe
        self._numbers = OrderNumbers(first_order_number)
        self.revision = 0
        self.phase = Phase.IDLE
        self.order = Order()
        self.pending: PendingItem | None = None
        self.view = View()
        self.payment_step: PaymentStep | None = None
        self.order_number: int | None = None
        self.reviewed_version: int | None = None
        self._menu_view: View | None = None  # where to return after an item was added

    # --- session -----------------------------------------------------------------------------

    def start_session(self) -> None:
        """The handset was lifted."""
        if self.phase is not Phase.IDLE:
            raise KioskError("a session is already running")
        self._reset(Phase.ORDERING, View(screen=Screen.WELCOME))

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

    # --- choosing items ----------------------------------------------------------------------

    def choose_item(
        self, item_id: str, quantity: int = 1, selection: Selection | None = None
    ) -> ItemResult:
        """Start choosing an item. It is added at once if every required option is known."""
        self._require(Phase.ORDERING)
        item = self.menu.item(item_id)
        check_quantity(quantity)
        chosen = self.menu.resolve(item, selection or {})
        self.pending = PendingItem(item=item, quantity=quantity, chosen=chosen)
        return self._try_add()

    def set_options(
        self, selection: Selection | None = None, quantity: int | None = None
    ) -> ItemResult:
        """Add options (or change the quantity) of the item being chosen."""
        self._require(Phase.ORDERING)
        pending = self._pending()
        chosen = self.menu.resolve(pending.item, selection or {})
        if quantity is not None:
            check_quantity(quantity)
            pending.quantity = quantity
        pending.chosen.update(chosen)
        return self._try_add()

    def cancel_item(self) -> None:
        self._require(Phase.ORDERING)
        self._pending()
        self.pending = None
        self._set_view(self._menu_view or View(screen=Screen.WELCOME))

    # --- changing the order ------------------------------------------------------------------

    def change_line(
        self, number: int, quantity: int | None = None, selection: Selection | None = None
    ) -> CartLine | None:
        """Change a line's options and/or quantity. Quantity 0 removes it (returns None)."""
        self._require(Phase.ORDERING)
        line = self.order.line(number)
        if quantity == 0:
            self.order.remove(number)
            self._touch()
            return None
        if selection:
            chosen = line.chosen() | self.menu.resolve(line.item, selection)
            line = self.order.set_choices(number, line.item.complete(chosen))
        if quantity is not None:
            self.order.set_quantity(self.order.number_of(line), quantity)
        self._touch()
        return line

    def set_dining(self, dining: Dining) -> None:
        self._require(Phase.ORDERING)
        self.order.set_dining(dining)
        self._touch()

    def cancel_order(self) -> None:
        """Throw the whole order away (the assistant checks the customer's confirmation)."""
        self._require(Phase.ORDERING)
        self.order.clear()
        self.pending = None
        self.reviewed_version = None
        self._menu_view = None
        self._set_view(View(screen=Screen.WELCOME))

    def show_order(self) -> None:
        """Show the order (display only; a review before payment is `review`)."""
        self._require(Phase.ORDERING)
        self._set_view(View(screen=Screen.REVIEW))

    # --- review and payment ------------------------------------------------------------------

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

    def _try_add(self) -> ItemResult:
        pending = self._pending()
        missing = pending.missing
        if missing:
            self._set_view(View(screen=Screen.ITEM, item_id=pending.item.id))
            return ItemResult(line=None, missing=missing)
        line = self.order.add(pending.item, pending.item.complete(pending.chosen), pending.quantity)
        self.pending = None
        self._set_view(self._menu_view or View(screen=Screen.WELCOME))
        return ItemResult(line=line)

    def _check_ready_to_pay(self) -> None:
        if self.order.is_empty:
            raise KioskError("the order is empty")
        if self.pending is not None:
            raise KioskError(
                f"{self.pending.item.id} is still being chosen: finish it or cancel_item first"
            )
        if self.order.dining is None:
            raise KioskError("ask whether the customer eats here or takes out first")

    def _pending(self) -> PendingItem:
        if self.pending is None:
            raise KioskError("no item is being chosen; use choose_item")
        return self.pending

    def _require(self, *phases: Phase) -> None:
        if self.phase not in phases:
            raise KioskError(f"not possible while the kiosk is {self.phase.value}")

    def _set_view(self, view: View) -> None:
        self.view = view
        self._touch()

    def _touch(self) -> None:
        self.revision += 1

    def _reset(self, phase: Phase, view: View) -> None:
        self.phase = phase
        self.order = Order()
        self.pending = None
        self.payment_step = None
        self.order_number = None
        self.reviewed_version = None
        self._menu_view = None
        self._set_view(view)
