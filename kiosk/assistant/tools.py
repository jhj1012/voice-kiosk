"""Function declarations for the Live session, built from the menu data.

Options are flat parameters, which models fill in more reliably than nested maps:
- a single-select group becomes an enum parameter named after the group (`temperature`, `size`,
  `shot`, `syrup`),
- a multi-select group with one choice becomes a boolean named after the choice (`tumbler`,
  `whipped_cream`),
- a multi-select group with several choices becomes an array of enums named after the group.
`selection_from_args` turns those parameters back into {group id: choice id(s)}.
"""

from __future__ import annotations

from typing import Any

from kiosk.domain.cafe import Cafe
from kiosk.domain.menu import Menu, OptionGroup
from kiosk.domain.order import Dining

Schema = dict[str, Any]


def _enum(values: list[str], description: str = "") -> Schema:
    schema: Schema = {"type": "STRING", "enum": values}
    if description:
        schema["description"] = description
    return schema


def _array(values: list[str], description: str) -> Schema:
    items = {"type": "STRING", "enum": values}
    return {"type": "ARRAY", "items": items, "description": description}


def _option_param(group: OptionGroup) -> tuple[str, Schema]:
    ids = [c.id for c in group.choices]
    if not group.multi:
        return group.id, _enum(ids, f"{group.name} ({'required' if group.required else 'extra'})")
    if len(ids) == 1:
        return ids[0], {"type": "BOOLEAN", "description": f"{group.choices[0].name} (extra)"}
    return group.id, _array(ids, f"{group.name} (extra)")


def option_params(menu: Menu) -> dict[str, Schema]:
    """The option parameters shared by choose_item, set_options and change_line."""
    return dict(_option_param(g) for g in menu.option_groups)


def selection_from_args(menu: Menu, args: dict[str, Any]) -> dict[str, str | list[str]]:
    """{group id: choice id(s)} from the option parameters in a function call's arguments."""
    selection: dict[str, str | list[str]] = {}
    for group in menu.option_groups:
        ids = [c.id for c in group.choices]
        if group.multi and len(ids) == 1:
            if ids[0] in args:
                selection[group.id] = [ids[0]] if args[ids[0]] else []
        elif group.id in args and args[group.id] is not None:
            value = args[group.id]
            selection[group.id] = list(value) if isinstance(value, list) else str(value)
    return selection


def function_declarations(menu: Menu, cafe: Cafe) -> list[dict[str, Any]]:
    item_ids = [i.id for i in menu.items]
    quantity = {"type": "INTEGER", "description": "Number of this item (1-20)."}
    options = option_params(menu)

    def declare(name: str, description: str, properties: Schema | None = None, required=()):
        declaration: dict[str, Any] = {"name": name, "description": description}
        if properties:
            declaration["parameters"] = {
                "type": "OBJECT",
                "properties": properties,
                "required": list(required),
            }
        return declaration

    return [
        declare(
            "show_menu",
            "Show menu items on the screen. You choose what fits the conversation: a few "
            "recommendations, a category, or any set of items (e.g. items without an allergen). "
            "Show at most five items unless it is a whole category. Display only.",
            {
                "title": {
                    "type": "STRING",
                    "description": "Short Korean caption ONLY when it explains a filter, e.g. "
                    "'우유가 들어가지 않은 메뉴'. Leave it out for recommendations.",
                },
                "category": _enum([c.id for c in menu.categories], "Show this category."),
                "item_ids": _array(item_ids, "Show exactly these items, in this order."),
                "highlight_ids": _array(item_ids, "Shown items to highlight (recommended)."),
                "exclude_allergens": _array(
                    [a.id for a in menu.allergens],
                    "Leave out items containing these allergens (filtered from the data).",
                ),
            },
        ),
        declare(
            "show_categories",
            "Show the kinds of menu (커피, 라떼, 티·에이드, 디저트) when the customer wants to see "
            "other menus, then ask which kind they would like.",
        ),
        declare(
            "show_item",
            "Show one item (picture, ingredients, allergens) without ordering it. The screen "
            "shows no description: tell it yourself when asked.",
            {"item_id": _enum(item_ids)},
            ["item_id"],
        ),
        declare(
            "show_info",
            "Show a card with cafe information (Wi-Fi, restroom, hours, ...).",
            {"topic": _enum([t.id for t in cafe.topics])},
            ["topic"],
        ),
        declare(
            "choose_item",
            "The customer wants this item. Pass every option the customer said. The result "
            "says what to ask next: one required option at a time, then the item's extras "
            "(the screen shows exactly that). Items without extras are added as soon as the "
            "required options are known.",
            {"item_id": _enum(item_ids), "quantity": quantity, **options},
            ["item_id"],
        ),
        declare(
            "set_options",
            "Give options (required ones or extras) or a new quantity for an item chosen but "
            "not added yet. When several items wait (e.g. '라떼 하나랑 아메리카노 하나'), say "
            "which with item_id; call it once per item when one answer covers several "
            "('둘 다 라지요').",
            {
                "item_id": _enum(item_ids, "Which waiting item; default: the one chosen last."),
                "quantity": quantity,
                **options,
            },
        ),
        declare(
            "finish_item",
            "The customer wants no (more) extras for the item being chosen ('없어요', '그냥 "
            "주세요'): adds it to the order.",
            {"item_id": _enum(item_ids, "Which waiting item; default: the one chosen last.")},
        ),
        declare(
            "cancel_item",
            "Drop an item being chosen (not added yet).",
            {"item_id": _enum(item_ids, "Which waiting item; default: the one chosen last.")},
        ),
        declare(
            "edit_line",
            "Show an ordered item's options on the screen again, e.g. '아까 라떼 옵션 다시 "
            "보여 주세요' or before changing one. Display only; change them with change_line.",
            {
                "line": {"type": "INTEGER", "description": "Order line number, from 1."},
                "option": _enum(
                    [g.id for g in menu.option_groups],
                    "Show only this option's choices; leave out to show all options.",
                ),
            },
            ["line"],
        ),
        declare(
            "go_back",
            "Show the previous screen again ('이전 화면', '뒤로', '아까 화면 보여 주세요').",
        ),
        declare(
            "note_for_staff",
            "Pass a request the kiosk cannot handle itself to the staff (how to make or serve "
            "something, e.g. '아메리카노는 포장, 카페모카는 매장에서', '얼음 적게'). It is shown "
            "with the order. Not for items or options that are not on the menu.",
            {"text": {"type": "STRING", "description": "The request, short, in Korean."}},
            ["text"],
        ),
        declare(
            "change_line",
            "Change an order line: its options and/or quantity. Quantity 0 removes the line. "
            "The screen shows the changed option again.",
            {
                "line": {"type": "INTEGER", "description": "Order line number, from 1."},
                "quantity": {"type": "INTEGER", "description": "New quantity; 0 removes it."},
                **options,
            },
            ["line"],
        ),
        declare(
            "set_dining",
            "Whether the customer eats here (매장) or takes out (포장).",
            {"dining": _enum([d.value for d in Dining])},
            ["dining"],
        ),
        declare("show_order", "Show the whole order on the screen (display only)."),
        declare(
            "request_payment",
            "The customer asked to pay. The first time it returns ask_first: ask that, then "
            "call it again. Then it shows the order for review and returns the read_back: say "
            "it word for word and nothing about the card. When you finish, the card terminal "
            "appears and you are told to ask for the card.",
        ),
        declare("cancel_payment", "Stop the payment while the terminal waits for the card."),
        declare(
            "cancel_order",
            "Throw away the whole order. Only after the customer said yes to your question "
            "whether to cancel everything.",
        ),
    ]
