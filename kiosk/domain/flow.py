"""The kiosk's state for one customer at a time: the order, the drinks still being chosen, the
current question, and what the display shows.

Phases: idle -> ordering -> paying (insert card -> processing) -> done -> idle. Lifting the
handset starts a session, hanging up ends it from any phase.

The **current question** (`Kiosk.question`) is decided here, from the state: here or to go,
then each drink's missing required options one at a time, each item's extras (once), what else
they would like, and when they pay: anything for the staff, then the read-back. The display
shows it and the assistant is told to ask it, so the two always match. The assistant's actions
are not tied to it: a customer may say more than was asked ("아메리카노 아이스로, 카페라떼는
따뜻한 걸로"), and every action can change any drink; afterwards the question is decided again.

Every view the customer saw is remembered, so `go_back` returns to the previous one (or to a
named item); it only changes the screen and the question, never the order.

Every method either changes the state (and `revision`) or raises `KioskError` with a message
for the model. Rules that need the conversation (did the customer ask to pay? did they say yes
to cancelling?) are checked by the assistant session.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

from kiosk.domain.cafe import Cafe
from kiosk.domain.menu import Chosen, KioskError, Menu, MenuItem, OptionGroup, item_allergens
from kiosk.domain.order import CartLine, Dining, Order, OrderNumbers, check_quantity

Selection = Mapping[str, str | Sequence[str]]  # option group id -> choice id(s)

EXTRAS = "extras"  # View.group / Question.group: the item's extras, all at once
HISTORY = 30  # views remembered for go_back
MAX_SHOWN = 5  # menu items on one screen: one column that still fits over the avatar


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
    WELCOME = "welcome"  # "메뉴판에서 메뉴를 고른 뒤 말씀해 주세요"
    MENU = "menu"
    CATEGORIES = "categories"
    ITEM = "item"
    INFO = "info"
    REVIEW = "review"
    PAYMENT = "payment"
    DONE = "done"


class Ask(StrEnum):
    """What the customer is asked now."""

    DINING = "dining"  # here or to go
    MENU = "menu"  # what they would like (from the menu board) / anything else
    OPTION = "option"  # a required option of a drink being chosen
    EXTRAS = "extras"  # an item's extras, once per item: "추가하실 거 있으세요?"
    LINE = "line"  # an order line shown again (go_back): change it if they want
    STAFF = "staff"  # before the read-back: "직원에게 따로 전달할 말씀 있으세요?"
    REVIEW = "review"  # the read-back
    NONE = "none"  # not ordering (idle, paying, done)


@dataclass(frozen=True)
class Question:
    kind: Ask
    draft: int = 0  # OPTION / EXTRAS: the drink being chosen
    item_id: str = ""
    group: str = ""  # OPTION: the option group; LINE: the group shown, or "" for all
    line: int = 0  # LINE: the order line (from 1)


@dataclass(frozen=True)
class View:
    """What the display shows: what the assistant chose (show), or the current question."""

    screen: Screen = Screen.ATTRACT
    title: str = ""
    item_ids: tuple[str, ...] = ()  # menu screen: the items to show, in order
    highlight: tuple[str, ...] = ()  # menu screen: recommended items among them
    item_id: str = ""  # item screen
    # item screen: the option group listed (a group id, EXTRAS, or "" for none: the item's
    # facts, or an order line's options at a glance)
    group: str = ""
    line: int = 0  # item screen: the order line shown (from 1)
    draft: int = 0  # item screen: the drink being chosen
    topic: str = ""  # info screen


# Views worth going back to (not the start, the take-out question, payment or done).
_REMEMBERED = {Screen.MENU, Screen.CATEGORIES, Screen.ITEM, Screen.INFO, Screen.REVIEW}


@dataclass
class Draft:
    """A drink being chosen: its required options first, then (first of its item) its extras."""

    id: int
    item: MenuItem
    quantity: int = 1
    chosen: Chosen = field(default_factory=dict)
    ask_extras: bool = True  # "추가하실 거 있으세요?": asked once per item (its first drink)
    extras_done: bool = False

    @property
    def missing(self) -> tuple[OptionGroup, ...]:
        return self.item.missing(self.chosen)

    @property
    def extras(self) -> tuple[OptionGroup, ...]:
        return tuple(g for g in self.item.option_groups if not g.required)

    @property
    def asking(self) -> str:
        """What is still asked: a required group's id, EXTRAS, or "" (ready to be added)."""
        if self.missing:
            return self.missing[0].id
        if self.ask_extras and self.extras and not self.extras_done:
            return EXTRAS
        return ""


@dataclass(frozen=True)
class MenuShown:
    item_ids: tuple[str, ...]
    removed: tuple[str, ...]  # left out because they contain an excluded allergen
    not_shown: int = 0  # more items that fit but not on one screen (MAX_SHOWN)
    categories: bool = False  # the whole menu was asked for: the categories are shown instead


@dataclass(frozen=True)
class ItemResult:
    """`line` is set when the drink went into the order; otherwise `draft` is still being
    chosen (or was cancelled, then both are None)."""

    line: CartLine | None = None
    draft: Draft | None = None


class Kiosk:
    def __init__(
        self,
        menu: Menu,
        cafe: Cafe,
        first_order_number: int = 1,
        rng: random.Random | None = None,
    ) -> None:
        self.menu = menu
        self.cafe = cafe
        self._rng = rng or random.Random()  # picks the items shown when too many fit
        self._numbers = OrderNumbers(first_order_number)
        self.revision = 0
        self.phase = Phase.IDLE
        self.order = Order()
        self.drafts: list[Draft] = []  # touched last at the end
        self.view = View()
        self.payment_step: PaymentStep | None = None
        self.order_number: int | None = None
        self.reviewed_version: int | None = None
        self.staff_asked = False  # the staff question comes once, before the first read-back
        self.read_back = ""  # the current read-back (Ask.REVIEW)
        self._stage: Ask | None = None  # STAFF / REVIEW while paying is being prepared
        self._focus: Question | None = None  # set by go_back until the customer answers
        self._asked = 0  # the drink asked about: it stays asked until it needs nothing more
        self._next_draft = 1
        self._added: dict[int, CartLine] = {}  # draft id -> the line it became
        self._menu_view: View | None = None  # where to return after a drink was added
        self._history: list[View] = []

    # --- session -----------------------------------------------------------------------------

    def start_session(self) -> None:
        """The handset was lifted: the first question is here or to go."""
        if self.phase is not Phase.IDLE:
            raise KioskError("a session is already running")
        self._reset(Phase.ORDERING)
        self._sync()

    def end_session(self) -> None:
        """The handset was put down (or the done screen timed out): forget everything."""
        self._reset(Phase.IDLE)
        self._set_view(View(), remember=False)

    # --- the current question ----------------------------------------------------------------

    @property
    def question(self) -> Question:
        if self.phase is not Phase.ORDERING:
            return Question(Ask.NONE)
        if self._focus is not None:
            return self._focus
        if self._stage is not None:
            return Question(self._stage)
        draft = self.asking_draft
        if draft is not None:
            kind = Ask.EXTRAS if draft.asking == EXTRAS else Ask.OPTION
            group = "" if kind is Ask.EXTRAS else draft.asking
            return Question(kind, draft=draft.id, item_id=draft.item.id, group=group)
        if self.order.dining is None and self.order.is_empty:
            return Question(Ask.DINING)
        return Question(Ask.MENU)

    @property
    def asking_draft(self) -> Draft | None:
        """The drink asked about. It stays asked while it needs something, even when the
        customer answers about another drink in between; then the next one, in the order they
        were ordered."""
        asked = self.draft(self._asked)
        if asked is not None and asked.asking:
            return asked
        return next((d for d in sorted(self.drafts, key=lambda d: d.id) if d.asking), None)

    @property
    def pending(self) -> Draft | None:
        """The drink the screen shows (being chosen), if any."""
        if self.view.draft:
            return self.draft(self.view.draft)
        return self.asking_draft

    def draft(self, draft_id: int) -> Draft | None:
        return next((d for d in self.drafts if d.id == draft_id), None)

    # --- display -----------------------------------------------------------------------------

    def show_menu(
        self,
        title: str = "",
        category: str | None = None,
        item_ids: Sequence[str] = (),
        highlight_ids: Sequence[str] = (),
        exclude_allergens: Sequence[str] = (),
    ) -> MenuShown:
        """Show a chosen set of items (or a category, or the items without some allergens)
        under a heading. The whole menu does not fit: its categories are shown instead. At
        most MAX_SHOWN items are shown: the highlighted ones, then others picked at random."""
        self._require(Phase.ORDERING)
        if item_ids:
            items = [self.menu.item(i) for i in dict.fromkeys(item_ids)]
        elif category:
            items = list(self.menu.items_in(category))
        elif exclude_allergens:
            items = list(self.menu.items)
        else:
            self.show_categories()
            return MenuShown(item_ids=(), removed=(), categories=True)
        excluded = {self.menu.allergen(a).id for a in exclude_allergens}
        fitting = tuple(i.id for i in items if not excluded & item_allergens(i))
        removed = tuple(i.id for i in items if i.id not in fitting)
        highlight = tuple(self.menu.item(i).id for i in highlight_ids)
        shown = self._pick(fitting, highlight)
        if not title:
            title = self.menu.category(category).name if category else ""
        view = View(
            screen=Screen.MENU,
            title=title,
            item_ids=shown,
            highlight=tuple(i for i in highlight if i in shown),
        )
        self._menu_view = view
        self._show(view)
        return MenuShown(item_ids=shown, removed=removed, not_shown=len(fitting) - len(shown))

    def _pick(self, item_ids: tuple[str, ...], highlight: tuple[str, ...]) -> tuple[str, ...]:
        """At most MAX_SHOWN of the items, in their order: the highlighted ones first, then
        others at random."""
        if len(item_ids) <= MAX_SHOWN:
            return item_ids
        first = [i for i in item_ids if i in highlight][:MAX_SHOWN]
        rest = [i for i in item_ids if i not in first]
        picked = set(first) | set(self._rng.sample(rest, MAX_SHOWN - len(first)))
        return tuple(i for i in item_ids if i in picked)

    def show_categories(self) -> None:
        """Show the kinds of menu (커피, 라떼, ...) so the customer can pick one."""
        self._require(Phase.ORDERING)
        self._show(View(screen=Screen.CATEGORIES))

    def show_item(self, item_id: str) -> MenuItem:
        """Show one item's facts without ordering it."""
        self._require(Phase.ORDERING)
        item = self.menu.item(item_id)
        self._show(View(screen=Screen.ITEM, item_id=item.id))
        return item

    def show_info(self, topic_id: str) -> None:
        """Show a cafe-info card. Also allowed after payment ("화장실 어디예요?")."""
        self._require(Phase.ORDERING, Phase.DONE)
        topic = self.cafe.topic(topic_id)
        view = View(screen=Screen.INFO, topic=topic.id)
        if self.phase is Phase.DONE:
            self._set_view(view)
        else:
            self._show(view)

    def show_order(self) -> None:
        """Show the order (display only; the review before payment is `request_payment`)."""
        self._require(Phase.ORDERING)
        self._show(View(screen=Screen.REVIEW))

    def go_back(self, to: str = "") -> View:
        """Show the previous view again ("뒤로"), or the latest one of item `to` ("아까 라떼 화면").
        A drink added since comes back as its order line. Changes nothing in the order."""
        self._require(Phase.ORDERING)
        history = list(self._history)
        while history:
            view = self._revive(history.pop())
            if view is None or view == self.view:
                continue
            if to and to not in (view.item_id, view.screen.value):
                continue
            self._history = history
            self._focus = self._question_for(view)
            self._set_view(view, remember=False)
            return view
        if to:
            raise KioskError(f"{to} was not shown before")
        raise KioskError("there is no previous screen")

    # --- choosing drinks ---------------------------------------------------------------------

    def order_item(
        self, item_id: str, quantity: int | None = None, selection: Selection | None = None
    ) -> ItemResult:
        """A new drink. If the same item is already being chosen with options that fit, it is
        updated instead; with fewer cups than it has and some options, those cups are split off
        as a drink of their own ("세 잔 중 하나는 차갑게")."""
        self._require(Phase.ORDERING)
        item = self.menu.item(item_id)
        if quantity is not None:
            check_quantity(quantity)
        chosen = self.menu.resolve(item, selection or {})
        target = _fitting([d for d in self.drafts if d.item.id == item.id], chosen)
        if target is not None and chosen and quantity is not None and quantity < target.quantity:
            draft = self._split_off(target, quantity, chosen)
        elif target is not None:
            draft = target
            draft.chosen.update(chosen)
            if quantity is not None:
                draft.quantity = quantity
            self._touch_draft(draft)
        else:
            draft = self._new_draft(item, quantity or 1, chosen)
        return self._after_draft(draft)

    def set_options(
        self,
        selection: Selection | None = None,
        quantity: int | None = None,
        item_id: str | None = None,
        draft_id: int | None = None,
    ) -> ItemResult:
        """Options (required or extras) or the number of cups of a drink being chosen.
        Quantity 0 cancels it. Options with fewer cups than it has go to only that many cups
        ("두 잔 중 하나만 라지로"): they are split off as a drink of their own, as with order."""
        self._require(Phase.ORDERING)
        draft = self.find_draft(item_id, selection, draft_id)
        chosen = self.menu.resolve(draft.item, selection or {})
        if chosen and quantity and quantity < draft.quantity:
            check_quantity(quantity)
            return self._after_draft(self._split_off(draft, quantity, chosen))
        if quantity == 0:
            self.drafts.remove(draft)
            self._focus = None
            self._changed()
            self._sync()
            return ItemResult()
        if quantity is not None:
            check_quantity(quantity)
            draft.quantity = quantity
        draft.chosen.update(chosen)
        self._touch_draft(draft)
        return self._after_draft(draft)

    def _split_off(self, draft: Draft, cups: int, chosen: Selection) -> Draft:
        """`cups` of `draft` as a drink of their own, with `chosen` on top of its options.

        An option every cup already has is a correction ("샷 추가" went to all three, then "하나만
        샷 추가해 줘"): only the split-off cups keep it; the rest lose it again (an extra goes back
        to none, a temperature or size is asked again)."""
        draft.quantity -= cups
        new = self._new_draft(draft.item, cups, {**draft.chosen, **chosen})
        new.ask_extras = draft.ask_extras
        for group_id, choices in chosen.items():
            if tuple(draft.chosen.get(group_id, ())) == tuple(choices):
                del draft.chosen[group_id]
        return new

    def no_more_extras(self, item_id: str | None = None, draft_id: int | None = None) -> ItemResult:
        """ "추가하실 거 있으세요?" - "없어요": the drink goes into the order."""
        self._require(Phase.ORDERING)
        candidates = [
            d
            for d in self.drafts
            if (not item_id or d.item.id == item_id) and (not draft_id or d.id == draft_id)
        ]
        ready = [d for d in candidates if d.asking == EXTRAS]
        draft = ready[-1] if ready else self.find_draft(item_id, None, draft_id)
        if draft.missing:
            names = ", ".join(g.id for g in draft.missing)
            raise KioskError(f"{draft.item.id}: {names} not chosen yet; ask for that first")
        draft.extras_done = True
        # Cups split off the same drink ("하나만 라지로") had the same question: one "없어요" is
        # for all of them, so it is not asked once per cup.
        for other in [d for d in self.drafts if d is not draft and d.item.id == draft.item.id]:
            if other.ask_extras:
                other.extras_done = True
                if not other.asking:
                    self._add_line(other)
        return self._after_draft(draft)

    def find_draft(
        self,
        item_id: str | None = None,
        selection: Selection | None = None,
        draft_id: int | None = None,
    ) -> Draft:
        """The drink being chosen that an answer is for: by number, or by item (when the same
        item is there more than once, the one the options fit, the asked one first), else the one
        asked about. A number whose drink already has another temperature or size is taken as a
        slip when another drink of that item still needs it ("나머지는 차갑게" sent to the drink
        just made hot)."""
        if not self.drafts:
            raise KioskError("no drink is being chosen; use order")
        if draft_id:
            draft = self.draft(draft_id)
            if draft is None:
                raise KioskError(f"there is no drink {draft_id} being chosen")
            required = {
                g: c
                for g, c in self.menu.resolve(draft.item, selection or {}).items()
                if (group := draft.item.group(g)) is not None and group.required
            }
            if any(
                draft.chosen.get(g) and tuple(draft.chosen[g]) != c for g, c in required.items()
            ):
                others = [d for d in self.drafts if d.item.id == draft.item.id and d is not draft]
                better = _fitting(others, required, filling_only=True)
                if better is not None:
                    return better
            return draft
        if not item_id:
            return self.asking_draft or self.drafts[-1]
        same = [d for d in self.drafts if d.item.id == item_id]
        if not same:
            waiting = ", ".join(d.item.id for d in self.drafts)
            raise KioskError(f"{item_id} is not being chosen (being chosen: {waiting})")
        if len(same) > 1 and selection:
            chosen = self.menu.resolve(same[0].item, selection)
            return _fitting(same, chosen, prefer=self.asking_draft) or same[-1]
        return next((d for d in reversed(same) if d.asking), same[-1])

    # --- changing the order ------------------------------------------------------------------

    def change_line(
        self, number: int, quantity: int | None = None, selection: Selection | None = None
    ) -> CartLine | None:
        """Change a line's options and/or quantity. Quantity 0 removes it (returns None). The
        option that changed is shown again, with the new choice marked."""
        self._require(Phase.ORDERING)
        line = self.order.line(number)
        if quantity == 0:
            self.order.remove(number)
            self._focus = None
            self._changed()
            if self.view.line:
                self._set_view(self._menu_view or View(screen=Screen.WELCOME), remember=False)
            self._sync()
            return None
        resolved = self.menu.resolve(line.item, selection or {})
        before = line.chosen()
        # Models often repeat options that stay the same: only real changes count.
        changed = [g for g, choices in resolved.items() if before.get(g) != choices] or [*resolved]
        if resolved:
            line = self.order.set_choices(number, line.item.complete(before | resolved))
        if quantity is not None:
            self.order.set_quantity(self.order.number_of(line), quantity)
        self._focus = None
        self._changed()
        group = changed[0] if len(changed) == 1 else ""
        if resolved or self.view.line:
            self._show_line(line, group if resolved else self.view.group)
        self._sync()
        return line

    def set_dining(self, dining: Dining) -> None:
        self._require(Phase.ORDERING)
        self.order.set_dining(dining)
        if self._focus is not None and self._focus.kind is Ask.DINING:
            self._focus = None
        if self._stage is not None:  # paying was waiting for it: go on from the start
            self._stage = None
        self._sync()
        self._touch()

    def add_note(self, text: str) -> None:
        """A request the kiosk cannot handle itself, passed on to the staff."""
        self._require(Phase.ORDERING)
        self.order.add_note(text)
        self._touch()

    def cancel_order(self) -> None:
        """Throw the whole order away (the session checks the customer's confirmation)."""
        self._require(Phase.ORDERING)
        self._reset(Phase.ORDERING)
        self._sync()

    # --- review and payment ------------------------------------------------------------------

    def request_payment(self) -> Ask:
        """The customer asked to pay (checked by the session). Returns what comes next: the
        staff question (once), else the read-back (`read_back`). Raises if something is
        missing; the question then asks for it (a drink's option, or here or to go)."""
        self._require(Phase.ORDERING)
        self._focus = None
        if self.order.is_empty and not self.drafts:
            raise KioskError("the order is empty")
        if self.drafts:
            self._sync()
            waiting = ", ".join(d.item.id for d in self.drafts)
            raise KioskError(f"still being chosen: {waiting}; finish them first")
        if self.order.dining is None:
            self._focus = Question(Ask.DINING)
            self._sync()
            raise KioskError("ask whether the customer eats here or takes out first")
        if not self.staff_asked:
            self.staff_asked = True
            self._stage = Ask.STAFF
        else:
            self._stage = Ask.REVIEW
            self.read_back = self.order.read_back(self.menu)
            self.reviewed_version = self.order.version
        self._sync()
        self._touch()
        return self._stage

    @property
    def review_is_current(self) -> bool:
        """True if the order was read back and has not changed since."""
        return self.reviewed_version == self.order.version

    def start_payment(self) -> None:
        self._require(Phase.ORDERING)
        if self.drafts or self.order.is_empty or self.order.dining is None:
            raise KioskError("the order is not ready for payment")
        if not self.review_is_current:
            raise KioskError("read the order back (request_payment) before payment")
        self._stage = None
        self.phase = Phase.PAYING
        self.payment_step = PaymentStep.INSERT_CARD
        self._set_view(View(screen=Screen.PAYMENT), remember=False)

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
            self._set_view(View(screen=Screen.DONE), remember=False)

    def cancel_payment(self) -> None:
        """Back to ordering while the terminal still waits for the card."""
        self._require(Phase.PAYING)
        if self.payment_step is not PaymentStep.INSERT_CARD:
            raise KioskError("the payment is already being processed")
        self.phase = Phase.ORDERING
        self.payment_step = None
        self._stage = None
        self._set_view(View(screen=Screen.REVIEW), remember=False)

    # --- helpers -----------------------------------------------------------------------------

    def _new_draft(self, item: MenuItem, quantity: int, chosen: Chosen) -> Draft:
        # The extras question once per item: 카페라떼 once, 아메리카노 once (split cups share it).
        first = not any(d.item.id == item.id for d in self.drafts) and not any(
            line.item.id == item.id for line in self.order.lines
        )
        draft = Draft(self._next_draft, item, quantity, dict(chosen), ask_extras=first)
        self._next_draft += 1
        self.drafts.append(draft)
        return draft

    def _touch_draft(self, draft: Draft) -> None:
        self.drafts.remove(draft)
        self.drafts.append(draft)

    def _after_draft(self, draft: Draft) -> ItemResult:
        """A drink changed: into the order if nothing is left to ask; then the next question."""
        self._focus = None
        self._changed()
        line = self._add_line(draft) if not draft.asking and draft in self.drafts else None
        self._sync()
        return ItemResult(line=line, draft=None if line else draft)

    def _add_line(self, draft: Draft) -> CartLine:
        """A finished drink into the order."""
        line = self.order.add(draft.item, draft.item.complete(draft.chosen), draft.quantity)
        self.drafts.remove(draft)
        self._added[draft.id] = line
        return line

    def _changed(self) -> None:
        """The order or a drink changed: paying must be asked for again."""
        self._stage = None

    def _question_for(self, view: View) -> Question | None:
        """The question a view (gone back to) asks."""
        if view.screen is not Screen.ITEM:
            return None
        if view.draft and self.draft(view.draft) is not None:
            kind = Ask.EXTRAS if view.group == EXTRAS else Ask.OPTION
            if kind is Ask.OPTION and not view.group:
                return None
            return Question(
                kind, view.draft, view.item_id, "" if kind is Ask.EXTRAS else view.group
            )
        if view.line:
            return Question(Ask.LINE, item_id=view.item_id, group=view.group, line=view.line)
        return None

    def _sync(self) -> None:
        """Show what the current question needs (the assistant's own views stay otherwise)."""
        q = self.question
        self._asked = q.draft if q.kind in (Ask.OPTION, Ask.EXTRAS) else 0
        if q.kind in (Ask.OPTION, Ask.EXTRAS):
            group = EXTRAS if q.kind is Ask.EXTRAS else q.group
            self._set_view(View(screen=Screen.ITEM, item_id=q.item_id, group=group, draft=q.draft))
        elif q.kind is Ask.DINING:
            self._set_view(View(screen=Screen.DINING))
        elif q.kind in (Ask.STAFF, Ask.REVIEW):
            self._set_view(View(screen=Screen.REVIEW))
        elif q.kind is Ask.MENU and self.view.screen in (Screen.DINING, Screen.ITEM, Screen.REVIEW):
            if self.view.screen is Screen.ITEM and (self.view.line or not self.view.draft):
                return  # an order line or an item's facts the assistant showed
            self._set_view(self._menu_view or View(screen=Screen.WELCOME))
        elif q.kind is Ask.MENU and self.view.screen is Screen.ATTRACT:
            self._set_view(View(screen=Screen.WELCOME))

    def _show(self, view: View) -> None:
        """A view the assistant chose."""
        self._focus = None
        self._set_view(view)

    def _show_line(self, line: CartLine, group_id: str = "") -> None:
        number = self.order.number_of(line)
        self._set_view(View(screen=Screen.ITEM, item_id=line.item.id, group=group_id, line=number))

    def _revive(self, view: View) -> View | None:
        """A remembered view as it can be shown now: a drink added since is shown as its order
        line (its options at a glance, or the same option group)."""
        if view.screen is not Screen.ITEM or not view.draft:
            if view.line and view.line > len(self.order.lines):
                return None
            return view
        if self.draft(view.draft) is not None:
            return view
        line = self._added.get(view.draft)
        if line is not None and line in self.order.lines:
            group = "" if view.group == EXTRAS else view.group
            return replace(view, group=group, line=self.order.number_of(line), draft=0)
        return None

    def _require(self, *phases: Phase) -> None:
        if self.phase not in phases:
            raise KioskError(f"not possible while the kiosk is {self.phase.value}")

    def _set_view(self, view: View, remember: bool = True) -> None:
        """Show `view`; the one shown before is remembered for go_back."""
        old = self.view
        if remember and old.screen in _REMEMBERED and old != view:
            self._history = [*self._history, old][-HISTORY:]
        if view != old:
            self.view = view
        self._touch()

    def _touch(self) -> None:
        self.revision += 1

    def _reset(self, phase: Phase) -> None:
        self.phase = phase
        self.order = Order()
        self.drafts = []
        self.payment_step = None
        self.order_number = None
        self.reviewed_version = None
        self.staff_asked = False
        self.read_back = ""
        self._stage = None
        self._focus = None
        self._asked = 0
        self._added = {}
        self._menu_view = None
        self._history = []
        self._touch()


def _fitting(
    entries: list[Draft],
    chosen: Chosen,
    *,
    prefer: Draft | None = None,
    filling_only: bool = False,
) -> Draft | None:
    """The drink whose options do not contradict `chosen`, preferably one still missing some
    of them, then `prefer` (the one asked about); else the one touched last (None if none fits,
    or with `filling_only` none still missing them)."""
    fits = [
        d
        for d in entries
        if all(not d.chosen.get(g) or tuple(d.chosen[g]) == tuple(c) for g, c in chosen.items())
    ]
    filling = [d for d in fits if any(not d.chosen.get(g) for g in chosen)]
    best = filling if filling or filling_only else fits
    if prefer is not None and prefer in best:
        return prefer
    return (best or [None])[-1]
