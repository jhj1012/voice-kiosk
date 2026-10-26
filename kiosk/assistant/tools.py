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
    """The option parameters shared by order, set_options and change."""
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


STAY_QUIET = "stay_quiet"
WHAT_TO_SHOW = ["menu", "categories", "item", "info", "order"]
SCREENS_TO_GO_BACK_TO = ["menu", "categories", "item", "info", "review"]


def function_declarations(menu: Menu, cafe: Cafe) -> list[dict[str, Any]]:
    """The assistant's eleven functions. They are named by what they change, not by the question
    asked: one sentence may need several ("아메리카노 아이스로, 카페라떼는 따뜻한 걸로" is two
    order calls), all in the same turn."""
    item_ids = [i.id for i in menu.items]
    quantity = {"type": "INTEGER", "description": "Number of cups / pieces (1-20)."}
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
            "show",
            "Show something on the screen (display only): 'menu' (item_ids, a category, or "
            "items without allergens; at most five unless a whole category), 'categories' (the "
            "kinds of menu), 'item' (one item's facts), 'info' (a cafe topic), 'order' (the "
            "order so far).",
            {
                "what": _enum(WHAT_TO_SHOW),
                "item_ids": _array(item_ids, "menu: exactly these items, in this order."),
                "category": _enum([c.id for c in menu.categories], "menu: this category."),
                "highlight_ids": _array(item_ids, "menu: items to highlight (recommended)."),
                "exclude_allergens": _array(
                    [a.id for a in menu.allergens],
                    "menu: leave out items with these allergens (filtered from the data).",
                ),
                "title": {
                    "type": "STRING",
                    "description": "menu: a short Korean caption only when it explains a filter, "
                    "e.g. '우유가 들어가지 않은 메뉴'.",
                },
                "item_id": _enum(item_ids, "item: which item."),
                "topic": _enum([t.id for t in cafe.topics], "info: which topic."),
            },
            ["what"],
        ),
        declare(
            "order",
            "The customer wants a drink or dessert: start choosing it, with every option and the "
            "number they said. Several items, or one item in parts ('세 잔 중 하나는 차갑게, 두 "
            "잔은 따뜻하게'), are one call each, in the same turn.",
            {"item_id": _enum(item_ids), "quantity": quantity, **options},
            ["item_id"],
        ),
        declare(
            "set_options",
            "Options (required or extras) or the number of an item being chosen, whatever was "
            "asked: '라떼는 차갑게요' while the americano is asked is set_options for the latte. "
            "'둘 다 라지요' is one call per item. Quantity 0 cancels it.",
            {
                "item_id": _enum(item_ids, "Which item; default: the one asked about."),
                "draft": {
                    "type": "INTEGER",
                    "description": "Which one, when the same item is being chosen more than "
                    "once (the number from a result); otherwise leave out.",
                },
                "quantity": {"type": "INTEGER", "description": "Number; 0 cancels it."},
                **options,
            },
        ),
        declare(
            "no_more_extras",
            "'추가하실 거 있으세요?' - '없어요' (or '괜찮아요', '그냥 주세요'): the item goes into "
            "the order.",
            {"item_id": _enum(item_ids, "Which item; default: the one asked about.")},
        ),
        declare(
            "set_dining",
            "Here (매장) or to go (포장).",
            {"dining": _enum([d.value for d in Dining])},
            ["dining"],
        ),
        declare(
            "change",
            "Change an item already in the order (its line number from a result): options "
            "and/or quantity; quantity 0 removes it. The screen shows the changed option.",
            {
                "line": {"type": "INTEGER", "description": "Order line number, from 1."},
                "quantity": {"type": "INTEGER", "description": "New quantity; 0 removes it."},
                **options,
            },
            ["line"],
        ),
        declare(
            "go_back",
            "Show the previous screen again ('뒤로', '이전 화면'), or with `to` the latest screen "
            "of an item or a kind of screen ('아까 라떼 화면 보여 주세요'). Changes nothing in "
            "the order.",
            {"to": _enum([*item_ids, *SCREENS_TO_GO_BACK_TO], "Go back to this; default: one.")},
        ),
        declare(
            "note_for_staff",
            "Pass a request the kiosk cannot do itself to the staff (how to make or serve "
            "something: '아메리카노는 포장, 카페모카는 매장에서', '얼음 적게'). Not for items or "
            "options that are not on the menu.",
            {"text": {"type": "STRING", "description": "The request, short, in Korean."}},
            ["text"],
        ),
        declare(
            "pay",
            "The customer asked to pay ('결제할게요', or '없어요' to '더 필요하신 거 있으세요?'). "
            "The result says what comes next: the staff question (then call pay again), or the "
            "read_back to say word for word. Call it again after the staff question.",
        ),
        declare(
            "cancel_order",
            "Throw away the whole order, only after the customer said yes to '주문을 모두 "
            "취소할까요?'. While the card terminal waits, it stops the payment instead.",
        ),
        declare(
            STAY_QUIET,
            "The words were not meant to be answered: hesitation ('음…', '어…', '잠깐만요', '뭐 "
            "먹지…'), or (when allowed) talk to someone else. Say nothing and wait.",
        )
        | {"behavior": "NON_BLOCKING"},  # answered silently: no reply follows
    ]
