"""The real data files (data/menu.yaml, data/cafe.yaml): valid, whatever the team puts in them.

The other tests use the fixed copy in tests/data, so editing the menu does not break them.
"""

import pytest

from kiosk.config import DATA_DIR
from kiosk.domain.check import report
from kiosk.domain.loader import load_menu
from kiosk.domain.menu import Menu


@pytest.fixture(scope="module")
def real_menu() -> Menu:
    return load_menu(DATA_DIR / "menu.yaml")


def test_only_temperature_and_size_are_required(real_menu: Menu):
    assert {g.id for g in real_menu.option_groups if g.required} == {"temperature", "size"}


def test_required_groups_list_the_words_for_them(real_menu: Menu):
    # Without them every temperature or size the model passes would count as a guess.
    for group in real_menu.option_groups:
        if group.required:
            assert group.words, group.id


def test_every_item_has_description_and_ingredients(real_menu: Menu):
    for item in real_menu.items:
        assert item.description, item.id
        assert item.ingredients, item.id


def test_items_without_temperature_option_say_how_they_are_served(real_menu: Menu):
    for item in real_menu.items:
        if item.group("temperature") is None and item.category != "dessert":
            assert item.temperature in ("hot", "ice"), item.id


def test_data_check_report_runs():
    assert report(DATA_DIR)[0].startswith("OK: ")
