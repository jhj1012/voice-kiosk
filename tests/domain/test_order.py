import pytest

from kiosk.domain.menu import KioskError, Menu
from kiosk.domain.order import MAX_QUANTITY, Dining, Order, OrderNumbers, won


def choices(menu: Menu, item_id: str, **selection):
    item = menu.item(item_id)
    return item, item.complete(menu.resolve(item, selection))


def test_add_merges_identical_lines(menu: Menu):
    order = Order()
    item, ice = choices(menu, "americano", temperature="ice", size="regular")
    order.add(item, ice)
    order.add(item, ice, 2)
    _, hot = choices(menu, "americano", temperature="hot", size="regular")
    order.add(item, hot)
    assert [line.quantity for line in order.lines] == [3, 1]
    assert order.total == 4 * 4000


def test_prices_include_options(menu: Menu):
    order = Order()
    item, chosen = choices(menu, "cafe_latte", temperature="ice", size="large", shot="extra_shot")
    line = order.add(item, chosen, 2)
    assert line.unit_price == 4500 + 500 + 600
    assert line.total == 2 * 5600
    assert line.option_text == "ICE, Large, 샷 추가"


def test_quantity_limits(menu: Menu):
    order = Order()
    item, chosen = choices(menu, "chocolate_cookie")
    for bad in (0, MAX_QUANTITY + 1):
        with pytest.raises(KioskError, match="quantity"):
            order.add(item, chosen, bad)
    order.add(item, chosen, MAX_QUANTITY)
    with pytest.raises(KioskError, match="quantity"):
        order.add(item, chosen, 1)
    assert order.lines[0].quantity == MAX_QUANTITY


def test_line_numbers_quantity_and_remove(menu: Menu):
    order = Order()
    order.add(*choices(menu, "chocolate_cookie"))
    order.add(*choices(menu, "espresso"))
    order.set_quantity(2, 3)
    assert order.line(2).quantity == 3
    order.set_quantity(1, 0)
    assert [line.item.id for line in order.lines] == ["espresso"]
    with pytest.raises(KioskError, match="no order line 2"):
        order.line(2)


def test_set_choices_merges_into_an_equal_line(menu: Menu):
    order = Order()
    item, ice = choices(menu, "americano", temperature="ice", size="regular")
    _, hot = choices(menu, "americano", temperature="hot", size="regular")
    order.add(item, ice, 2)
    order.add(item, hot, 1)
    merged = order.set_choices(2, ice)
    assert len(order.lines) == 1
    assert merged.quantity == 3


def test_every_change_increases_the_version(menu: Menu):
    order = Order()
    versions = [order.version]
    order.add(*choices(menu, "espresso"))
    versions.append(order.version)
    order.set_quantity(1, 2)
    versions.append(order.version)
    order.set_dining(Dining.TO_GO)
    versions.append(order.version)
    order.set_dining(Dining.TO_GO)  # no change
    assert order.version == versions[-1]
    order.clear()
    versions.append(order.version)
    assert versions == sorted(set(versions))


def test_read_back(menu: Menu):
    order = Order()
    order.add(*choices(menu, "americano", temperature="ice", size="large", shot="extra_shot"), 2)
    order.add(*choices(menu, "chocolate_cookie"))
    order.add(*choices(menu, "cold_brew", size="regular"))
    order.set_dining(Dining.TO_GO)
    assert order.read_back(menu) == (
        "주문 확인해 드릴게요. 아이스 아메리카노 라지(샷 추가) 2잔, 초코 쿠키 1개, "
        "콜드브루 레귤러 1잔, 포장으로 총 17,200원입니다."
    )
    order.set_dining(Dining.HERE)
    assert order.read_back(menu).endswith("1잔, 매장에서 드시고 총 17,200원입니다.")


def test_read_back_of_empty_order(menu: Menu):
    with pytest.raises(KioskError, match="empty"):
        Order().read_back(menu)


def test_order_numbers_and_won():
    numbers = OrderNumbers(7)
    assert [numbers.next(), numbers.next()] == [7, 8]
    assert won(17200) == "17,200원"


def test_lines_signature_ignores_dining(menu: Menu):
    order = Order()
    order.add(*choices(menu, "chocolate_cookie"))
    before = order.lines_signature
    order.set_dining(Dining.HERE)
    assert order.lines_signature == before
    order.set_quantity(1, 2)
    assert order.lines_signature == (("chocolate_cookie", (), 2),)
