"""Read and validate `data/menu.yaml` and `data/cafe.yaml`, and find menu images.

Parsing (`parse_menu`, `parse_cafe`) works on plain dicts so it can be tested without files.
Mistakes in the data raise `DataError` with a message that says where the mistake is.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

import yaml

from kiosk.domain.cafe import Cafe, InfoTopic
from kiosk.domain.menu import (
    NONE_CHOICE_ID,
    TEMPERATURE,
    Allergen,
    Caffeine,
    Category,
    Menu,
    MenuItem,
    OptionChoice,
    OptionGroup,
    Temperature,
)

IMAGE_SUFFIXES = (".png", ".webp", ".jpg", ".jpeg")


class DataError(Exception):
    """menu.yaml or cafe.yaml is missing or has invalid values."""


def load_menu(path: Path) -> Menu:
    return parse_menu(_read_yaml(path))


def load_cafe(path: Path) -> Cafe:
    return parse_cafe(_read_yaml(path))


def find_image(images_dir: Path, item_id: str) -> Path | None:
    """The image file for an item (`<item_id>.png`, `.webp`, `.jpg` or `.jpeg`), if any."""
    for suffix in IMAGE_SUFFIXES:
        path = images_dir / f"{item_id}{suffix}"
        if path.is_file():
            return path
    return None


def parse_menu(data: dict[str, Any]) -> Menu:
    allergens = tuple(
        Allergen(id=_str(a, "id", "allergens"), name=_str(a, "name", "allergens"))
        for a in _list(data, "allergens", "menu")
    )
    _unique([a.id for a in allergens], "allergen")
    categories = tuple(
        Category(
            id=_str(c, "id", "categories"),
            name=_str(c, "name", "categories"),
            unit=_str(c, "unit", "categories"),
        )
        for c in _list(data, "categories", "menu")
    )
    _unique([c.id for c in categories], "category")
    groups = tuple(
        _group(g, {a.id for a in allergens}) for g in _list(data, "option_groups", "menu")
    )
    _unique([g.id for g in groups], "option group")
    by_id = {g.id: g for g in groups}
    items = tuple(
        _item(i, by_id, {c.id for c in categories}, {a.id for a in allergens})
        for i in _list(data, "items", "menu")
    )
    _unique([i.id for i in items], "item")
    if not items:
        raise DataError("menu: no items")
    return Menu(categories=categories, option_groups=groups, items=items, allergens=allergens)


def parse_cafe(data: dict[str, Any]) -> Cafe:
    topics = tuple(
        InfoTopic(
            id=_str(t, "id", "topics"),
            title=_str(t, "title", "topics"),
            text=_str(t, "text", "topics"),
            verified=_bool(t, "verified", "topics"),
        )
        for t in _list(data, "topics", "cafe")
    )
    _unique([t.id for t in topics], "cafe topic")
    return Cafe(
        name=_str(data, "name", "cafe"),
        topics=topics,
        verified=_bool(data, "verified", "cafe"),
    )


def _group(data: dict[str, Any], allergen_ids: set[str]) -> OptionGroup:
    group_id = _str(data, "id", "option_groups")
    where = f"option group {group_id!r}"
    required = _bool(data, "required", where)
    multi = _bool(data, "multi", where)
    choices = tuple(
        OptionChoice(
            group_id=group_id,
            id=_str(c, "id", where),
            name=_str(c, "name", where),
            price=_price(c, where),
            say=str(c.get("say", "")),
            allergens=_ids(c, "allergens", allergen_ids, where),
        )
        for c in _list(data, "choices", where)
    )
    if not choices:
        raise DataError(f"{where}: no choices")
    _unique([c.id for c in choices], f"choice in {where}")
    if required and multi:
        raise DataError(f"{where}: a required group must be single-select (multi: false)")
    if required and any(c.id == NONE_CHOICE_ID for c in choices):
        raise DataError(f"{where}: a required group cannot have a {NONE_CHOICE_ID!r} choice")
    return OptionGroup(
        id=group_id, name=_str(data, "name", where), required=required, multi=multi, choices=choices
    )


def _item(
    data: dict[str, Any],
    groups: dict[str, OptionGroup],
    category_ids: set[str],
    allergen_ids: set[str],
) -> MenuItem:
    item_id = _str(data, "id", "items")
    where = f"item {item_id!r}"
    category = _str(data, "category", where)
    if category not in category_ids:
        raise DataError(f"{where}: unknown category {category!r}")
    option_ids = _ids(data, "options", set(groups), where)
    temperature = data.get("temperature")
    if temperature is not None and temperature not in get_args(Temperature):
        raise DataError(f"{where}: temperature must be hot or ice")
    if temperature is not None and TEMPERATURE in option_ids:
        raise DataError(f"{where}: set temperature only for items without the temperature option")
    caffeine = data.get("caffeine", "none")
    if caffeine not in get_args(Caffeine):
        raise DataError(f"{where}: caffeine must be one of {', '.join(get_args(Caffeine))}")
    sweetness = data.get("sweetness", 0)
    if not isinstance(sweetness, int) or not 0 <= sweetness <= 3:
        raise DataError(f"{where}: sweetness must be 0..3")
    ingredients = data.get("ingredients", [])
    if not isinstance(ingredients, list) or not all(isinstance(i, str) for i in ingredients):
        raise DataError(f"{where}: ingredients must be a list of words")
    return MenuItem(
        id=item_id,
        name=_str(data, "name", where),
        category=category,
        price=_price(data, where),
        option_groups=tuple(groups[g] for g in option_ids),
        emoji=str(data.get("emoji", "")),
        temperature=temperature,
        description=str(data.get("description", "")),
        ingredients=tuple(ingredients),
        allergens=_ids(data, "allergens", allergen_ids, where),
        caffeine=caffeine,
        sweetness=sweetness,
        recommended=_bool(data, "recommended", where),
        verified=_bool(data, "verified", where),
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise DataError(f"data file not found: {path}")
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise DataError(f"{path.name}: not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise DataError(f"{path.name} must contain a mapping at the top level")
    return data


def _list(data: dict[str, Any], key: str, where: str) -> list[dict[str, Any]]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise DataError(f"{where}: {key} must be a list of entries")
    return value


def _str(data: dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DataError(f"{where}: {key} is missing or empty")
    return value.strip()


def _bool(data: dict[str, Any], key: str, where: str) -> bool:
    value = data.get(key, False)
    if not isinstance(value, bool):
        raise DataError(f"{where}: {key} must be true or false")
    return value


def _price(data: dict[str, Any], where: str) -> int:
    value = data.get("price")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DataError(f"{where}: price must be a whole number of won (0 or more)")
    return value


def _ids(data: dict[str, Any], key: str, known: set[str], where: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise DataError(f"{where}: {key} must be a list of ids")
    unknown = [v for v in value if v not in known]
    if unknown:
        raise DataError(f"{where}: unknown {key}: {', '.join(unknown)}")
    _unique(value, f"{key} entry in {where}")
    return tuple(value)


def _unique(ids: list[str], what: str) -> None:
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            raise DataError(f"duplicate {what} id {i!r}")
        seen.add(i)
