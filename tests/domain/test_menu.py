import pytest

from kiosk.domain.menu import KioskError, Menu, item_allergens


def ids(chosen):
    return {g: tuple(c.id for c in cs) for g, cs in chosen.items()}


def test_resolve_valid_selection(menu: Menu):
    item = menu.item("cafe_latte")
    chosen = menu.resolve(item, {"temperature": "ice", "topping": ["whipped_cream"]})
    assert ids(chosen) == {"temperature": ("ice",), "topping": ("whipped_cream",)}


@pytest.mark.parametrize(
    ("item_id", "selection", "message"),
    [
        ("americano", {"temperature": "warm"}, "no choice 'warm'"),
        ("americano", {"topping": ["whipped_cream"]}, "americano has no topping option"),
        ("americano", {"sauce": "x"}, "there is no option 'sauce'"),
        ("cold_brew", {"temperature": "hot"}, r"served iced only"),
        ("espresso", {"temperature": "ice"}, r"served hot only"),
        ("flat_white", {"size": "large"}, "has no size option"),
        ("cafe_latte", {"topping": ["whipped_cream", "whipped_cream"]}, "chosen twice"),
        ("americano", {"temperature": ["hot", "ice"]}, "exactly one"),
    ],
)
def test_resolve_rejects(menu: Menu, item_id, selection, message):
    with pytest.raises(KioskError, match=message):
        menu.resolve(menu.item(item_id), selection)


def test_resolve_accepts_how_an_item_is_served_anyway(menu: Menu):
    # "아이스 콜드브루", "레귤러 플랫화이트": nothing to choose, but not a mistake either.
    assert menu.resolve(menu.item("cold_brew"), {"temperature": "ice"}) == {}
    assert menu.resolve(menu.item("flat_white"), {"size": "regular"}) == {}


def test_missing_and_complete(menu: Menu):
    item = menu.item("americano")
    chosen = menu.resolve(item, {"size": "large"})
    assert [g.id for g in item.missing(chosen)] == ["temperature"]
    with pytest.raises(KioskError, match="choose temperature"):
        item.complete(chosen)
    chosen |= menu.resolve(item, {"temperature": "ice"})
    choices = item.complete(chosen)
    # Item order, with defaults for optional single groups and nothing for optional multi groups.
    assert [(c.group_id, c.id) for c in choices] == [
        ("temperature", "ice"),
        ("size", "large"),
        ("shot", "none"),
        ("syrup", "none"),
    ]


def test_item_without_options_is_complete(menu: Menu):
    assert menu.item("chocolate_cookie").complete({}) == ()


def test_allergens_include_options(menu: Menu):
    ice_cream = menu.item("vanilla_ice_cream")
    americano = menu.item("americano")
    whipped = menu.option_group("topping").choice("whipped_cream")
    assert item_allergens(americano) == frozenset()
    assert item_allergens(ice_cream, [whipped]) == {"milk"}


def test_lookups_raise_kiosk_errors(menu: Menu):
    for lookup in (menu.item, menu.category, menu.option_group, menu.allergen):
        with pytest.raises(KioskError):
            lookup("nope")
