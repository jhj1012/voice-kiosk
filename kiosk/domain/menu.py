"""The menu: categories, option groups and items, as loaded from `data/menu.yaml`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

NONE_CHOICE_ID = "none"
TEMPERATURE = "temperature"
SIZE = "size"
REGULAR_SIZE = "regular"

Temperature = Literal["hot", "ice"]
Caffeine = Literal["none", "low", "medium", "high"]
Chosen = dict[str, tuple["OptionChoice", ...]]  # group id -> chosen choices


class KioskError(Exception):
    """A request the kiosk cannot carry out. The message is meant for the model (English)."""


@dataclass(frozen=True)
class Allergen:
    id: str
    name: str


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    unit: str  # counting word for quantities, e.g. "잔" or "개"


@dataclass(frozen=True)
class OptionChoice:
    """One selectable value inside an option group, e.g. "Large" (+500원)."""

    group_id: str
    id: str
    name: str
    price: int = 0
    say: str = ""  # how it is read aloud; defaults to the name
    allergens: tuple[str, ...] = ()

    @property
    def is_none(self) -> bool:
        """True for "no change" choices such as "기본" or "없음"."""
        return self.id == NONE_CHOICE_ID

    @property
    def spoken(self) -> str:
        return self.say or self.name


@dataclass(frozen=True)
class OptionGroup:
    """A set of choices. Single-select groups need exactly one choice; multi groups zero or more.

    Required groups have no default: the customer must choose. Optional single-select groups
    default to their first choice (e.g. "기본"), optional multi groups to nothing.
    """

    id: str
    name: str
    required: bool
    multi: bool
    choices: tuple[OptionChoice, ...]

    @property
    def default(self) -> tuple[OptionChoice, ...]:
        if self.required or self.multi:
            return ()
        return (self.choices[0],)

    def choice(self, choice_id: str) -> OptionChoice:
        for choice in self.choices:
            if choice.id == choice_id:
                return choice
        valid = ", ".join(c.id for c in self.choices)
        raise KioskError(f"{self.id} has no choice {choice_id!r} (valid: {valid})")


@dataclass(frozen=True)
class MenuItem:
    id: str
    name: str
    category: str
    price: int
    option_groups: tuple[OptionGroup, ...] = ()
    emoji: str = ""
    temperature: Temperature | None = None  # how it is served, if it has no temperature option
    description: str = ""
    ingredients: tuple[str, ...] = ()
    allergens: tuple[str, ...] = ()
    caffeine: Caffeine = "none"
    sweetness: int = 0
    recommended: bool = False
    verified: bool = False

    def group(self, group_id: str) -> OptionGroup | None:
        return next((g for g in self.option_groups if g.id == group_id), None)

    @property
    def required_groups(self) -> tuple[OptionGroup, ...]:
        return tuple(g for g in self.option_groups if g.required)

    def missing(self, chosen: Mapping[str, Sequence[OptionChoice]]) -> tuple[OptionGroup, ...]:
        """Required groups that have no choice yet."""
        return tuple(g for g in self.required_groups if not chosen.get(g.id))

    def complete(self, chosen: Mapping[str, Sequence[OptionChoice]]) -> tuple[OptionChoice, ...]:
        """All choices for a cart line: the chosen ones plus defaults, in the item's order."""
        missing = self.missing(chosen)
        if missing:
            raise KioskError(f"{self.id}: choose {', '.join(g.id for g in missing)} first")
        choices: list[OptionChoice] = []
        for group in self.option_groups:
            choices.extend(chosen.get(group.id, group.default))
        return tuple(choices)


@dataclass(frozen=True)
class Menu:
    categories: tuple[Category, ...]
    option_groups: tuple[OptionGroup, ...]
    items: tuple[MenuItem, ...]
    allergens: tuple[Allergen, ...] = ()

    def item(self, item_id: str) -> MenuItem:
        for item in self.items:
            if item.id == item_id:
                return item
        raise KioskError(f"there is no menu item {item_id!r}")

    def category(self, category_id: str) -> Category:
        for category in self.categories:
            if category.id == category_id:
                return category
        raise KioskError(f"there is no category {category_id!r}")

    def option_group(self, group_id: str) -> OptionGroup:
        for group in self.option_groups:
            if group.id == group_id:
                return group
        raise KioskError(f"there is no option {group_id!r}")

    def allergen(self, allergen_id: str) -> Allergen:
        for allergen in self.allergens:
            if allergen.id == allergen_id:
                return allergen
        raise KioskError(f"there is no allergen {allergen_id!r}")

    def items_in(self, category_id: str) -> tuple[MenuItem, ...]:
        self.category(category_id)
        return tuple(item for item in self.items if item.category == category_id)

    def unit(self, item: MenuItem) -> str:
        return self.category(item.category).unit

    def resolve(self, item: MenuItem, selection: Mapping[str, str | Sequence[str]]) -> Chosen:
        """Turn {group id: choice id(s)} into choices of `item`, checking that they apply.

        A temperature or size the item has no option for is accepted only if it matches how
        the item is served anyway (e.g. ICE for an iced-only item, Regular for one size).
        """
        chosen: Chosen = {}
        for group_id, value in selection.items():
            ids = (value,) if isinstance(value, str) else tuple(value)
            group = item.group(group_id)
            if group is None:
                self.option_group(group_id)  # unknown option ids get their own message
                if self._served_as(item, group_id, ids):
                    continue
                raise KioskError(f"{item.id} has no {group_id} option{self._served_note(item)}")
            choices = tuple(group.choice(i) for i in ids)
            if len(set(choices)) != len(choices):
                raise KioskError(f"{item.id}: {group_id} chosen twice")
            if not group.multi and len(choices) != 1:
                raise KioskError(f"{item.id}: choose exactly one {group_id}")
            chosen[group_id] = choices
        return chosen

    @staticmethod
    def _served_as(item: MenuItem, group_id: str, ids: tuple[str, ...]) -> bool:
        if group_id == TEMPERATURE:
            return item.temperature is not None and ids == (item.temperature,)
        return group_id == SIZE and ids == (REGULAR_SIZE,)

    @staticmethod
    def _served_note(item: MenuItem) -> str:
        if item.temperature == "ice":
            return " (served iced only)"
        if item.temperature == "hot":
            return " (served hot only)"
        return ""


def item_allergens(item: MenuItem, choices: Sequence[OptionChoice] = ()) -> frozenset[str]:
    """Allergen ids of an item with the given options (e.g. whipped cream adds milk)."""
    return frozenset(item.allergens).union(*(c.allergens for c in choices))
