"""The real data files: valid, and identical in items/prices/options to the earlier prototype."""

from kiosk.config import DATA_DIR
from kiosk.domain.check import report
from kiosk.domain.menu import Menu

# Items, prices and option groups of the earlier prototype's menu.json (must not drift).
OLD_ITEMS = {
    "espresso": ("에스프레소", "coffee", 3300, ["shot"]),
    "americano": (
        "아메리카노",
        "coffee",
        4000,
        ["temperature", "size", "tumbler", "shot", "syrup"],
    ),
    "cold_brew": ("콜드브루", "coffee", 4500, ["size", "tumbler", "syrup"]),
    "halmega_coffee": ("할메가커피", "coffee", 2500, ["size", "tumbler", "shot"]),
    "cafe_latte": (
        "카페라떼",
        "latte",
        4500,
        ["temperature", "size", "tumbler", "shot", "syrup", "topping"],
    ),
    "cafe_mocha": (
        "카페모카",
        "latte",
        5000,
        ["temperature", "size", "tumbler", "shot", "topping"],
    ),
    "flat_white": ("플랫화이트", "latte", 4800, ["temperature", "tumbler", "shot"]),
    "einspanner": ("아인슈페너", "latte", 5200, ["tumbler", "shot"]),
    "green_grape_ade": ("청포도 에이드", "tea_ade", 3500, ["size", "tumbler"]),
    "chamomile_tea": ("캐모마일 티", "tea_ade", 3800, ["temperature", "size", "tumbler"]),
    "vanilla_ice_cream": ("바닐라 아이스크림", "dessert", 3000, ["topping"]),
    "chocolate_cookie": ("초코 쿠키", "dessert", 2500, []),
}
OLD_CHOICES = {
    "temperature": {"hot": 0, "ice": 0},
    "size": {"regular": 0, "large": 500},
    "tumbler": {"tumbler": 0},
    "shot": {"none": 0, "extra_shot": 600, "two_extra_shots": 1200, "decaf": 1000},
    "syrup": {"none": 0, "vanilla": 500, "caramel": 500, "hazelnut": 500, "light_vanilla": 500},
    "topping": {"whipped_cream": 500},
}
OLD_MULTI = {"tumbler", "topping"}


def test_items_prices_and_options_match_the_prototype(menu: Menu):
    actual = {
        i.id: (i.name, i.category, i.price, [g.id for g in i.option_groups]) for i in menu.items
    }
    assert actual == OLD_ITEMS


def test_option_choices_and_prices_match_the_prototype(menu: Menu):
    actual = {g.id: {c.id: c.price for c in g.choices} for g in menu.option_groups}
    assert actual == OLD_CHOICES
    assert {g.id for g in menu.option_groups if g.multi} == OLD_MULTI


def test_only_temperature_and_size_are_required(menu: Menu):
    assert {g.id for g in menu.option_groups if g.required} == {"temperature", "size"}


def test_every_item_has_description_and_ingredients(menu: Menu):
    for item in menu.items:
        assert item.description, item.id
        assert item.ingredients, item.id


def test_items_without_temperature_option_say_how_they_are_served(menu: Menu):
    for item in menu.items:
        if item.group("temperature") is None and item.category != "dessert":
            assert item.temperature in ("hot", "ice"), item.id


def test_data_check_report_runs():
    lines = report(DATA_DIR)
    assert lines[0].startswith("OK: 12 items")
