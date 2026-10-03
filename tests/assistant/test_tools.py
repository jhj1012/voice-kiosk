from google.genai import types

from kiosk.assistant.tools import function_declarations, option_params, selection_from_args
from kiosk.domain.cafe import Cafe
from kiosk.domain.menu import Menu


def by_name(menu: Menu, cafe: Cafe) -> dict[str, dict]:
    return {d["name"]: d for d in function_declarations(menu, cafe)}


def test_declarations_are_valid_for_the_sdk(menu: Menu, cafe: Cafe):
    for declaration in function_declarations(menu, cafe):
        types.FunctionDeclaration.model_validate(declaration)


def test_enums_come_from_the_data(menu: Menu, cafe: Cafe):
    declarations = by_name(menu, cafe)
    item_enum = declarations["choose_item"]["parameters"]["properties"]["item_id"]["enum"]
    assert item_enum == [i.id for i in menu.items]
    topic_enum = declarations["show_info"]["parameters"]["properties"]["topic"]["enum"]
    assert topic_enum == [t.id for t in cafe.topics]
    menu_props = declarations["show_menu"]["parameters"]["properties"]
    assert menu_props["exclude_allergens"]["items"]["enum"] == ["milk", "soy", "wheat", "egg"]


def test_option_parameters_are_flat(menu: Menu):
    params = option_params(menu)
    assert params["temperature"]["enum"] == ["hot", "ice"]
    assert params["shot"]["enum"] == ["none", "extra_shot", "two_extra_shots", "decaf"]
    assert params["whipped_cream"]["type"] == "BOOLEAN"  # topping group with one choice
    assert params["tumbler"]["type"] == "BOOLEAN"
    assert "topping" not in params


def test_selection_from_args(menu: Menu):
    args = {
        "item_id": "cafe_latte",
        "quantity": 2,
        "temperature": "ice",
        "shot": "decaf",
        "whipped_cream": True,
        "tumbler": False,
    }
    assert selection_from_args(menu, args) == {
        "temperature": "ice",
        "shot": "decaf",
        "topping": ["whipped_cream"],
        "tumbler": [],
    }
    assert selection_from_args(menu, {"item_id": "americano"}) == {}
