import copy

import pytest

from kiosk.domain.loader import DataError, find_image, parse_cafe, parse_menu

MINIMAL = {
    "allergens": [{"id": "milk", "name": "우유"}],
    "categories": [{"id": "coffee", "name": "커피", "unit": "잔"}],
    "option_groups": [
        {
            "id": "temperature",
            "name": "온도",
            "required": True,
            "multi": False,
            "choices": [{"id": "hot", "name": "HOT", "price": 0}],
        }
    ],
    "items": [
        {
            "id": "latte",
            "name": "라떼",
            "category": "coffee",
            "price": 4500,
            "options": ["temperature"],
            "allergens": ["milk"],
        }
    ],
}


def broken(change) -> dict:
    data = copy.deepcopy(MINIMAL)
    change(data)
    return data


def test_minimal_menu_parses():
    menu = parse_menu(MINIMAL)
    item = menu.item("latte")
    assert item.option_groups[0].id == "temperature"
    assert item.allergens == ("milk",)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["items"][0].update(category="tea"), "unknown category"),
        (lambda d: d["items"][0].update(options=["size"]), "unknown options: size"),
        (lambda d: d["items"][0].update(allergens=["nuts"]), "unknown allergens: nuts"),
        (lambda d: d["items"][0].update(price=-1), "price"),
        (lambda d: d["items"][0].update(price="4500"), "price"),
        (lambda d: d["items"][0].update(sweetness=5), "sweetness"),
        (lambda d: d["items"][0].update(caffeine="lots"), "caffeine"),
        (lambda d: d["items"][0].update(temperature="ice"), "only for items without"),
        (lambda d: d["items"][0].update(name=""), "name is missing"),
        (lambda d: d["items"].append(dict(d["items"][0])), "duplicate item id 'latte'"),
        (lambda d: d["option_groups"][0].update(multi=True), "single-select"),
        (lambda d: d["option_groups"][0]["choices"][0].update(id="none"), "cannot have"),
        (lambda d: d["option_groups"][0].update(choices=[]), "no choices"),
        (lambda d: d.update(items=[]), "no items"),
        (lambda d: d.update(items="latte"), "list of entries"),
    ],
)
def test_mistakes_are_reported(change, message):
    with pytest.raises(DataError, match=message):
        parse_menu(broken(change))


def test_cafe_parses_and_rejects_duplicates():
    data = {"name": "카페", "topics": [{"id": "wifi", "title": "와이파이", "text": "..."}]}
    assert parse_cafe(data).topic("wifi").title == "와이파이"
    data["topics"].append(dict(data["topics"][0]))
    with pytest.raises(DataError, match="duplicate cafe topic"):
        parse_cafe(data)


def test_find_image_prefers_png_and_ignores_other_items(tmp_path):
    assert find_image(tmp_path, "latte") is None
    (tmp_path / "latte.jpg").write_bytes(b"x")
    (tmp_path / "mocha.png").write_bytes(b"x")
    assert find_image(tmp_path, "latte") == tmp_path / "latte.jpg"
    (tmp_path / "latte.png").write_bytes(b"x")
    assert find_image(tmp_path, "latte") == tmp_path / "latte.png"
