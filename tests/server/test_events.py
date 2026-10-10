import os

from kiosk.domain.flow import Kiosk
from kiosk.domain.order import Dining
from kiosk.server.events import (
    Subtitles,
    avatar_urls,
    image_urls,
    init_event,
    level_event,
    state_event,
)


def test_init_event_carries_menu_cafe_and_images(menu, cafe):
    event = init_event(menu, cafe, {"americano": "/images/americano.png?v=1"})
    assert event["type"] == "init"
    assert event["cafe"]["name"] == cafe.name
    items = {i["id"]: i for i in event["menu"]["items"]}
    assert items["americano"]["image_url"] == "/images/americano.png?v=1"
    assert items["espresso"]["image_url"] is None
    assert items["cold_brew"]["temperature"] == "ice"
    assert items["chocolate_cookie"]["allergens"] == ["wheat", "milk", "egg", "soy"]
    size = next(g for g in event["menu"]["option_groups"] if g["id"] == "size")
    assert size["required"] and size["choices"][1] == {
        "id": "large",
        "name": "Large",
        "say": "라지",
        "price": 500,
    }


def test_image_urls(menu, tmp_path):
    (tmp_path / "americano.png").write_bytes(b"x")
    os.utime(tmp_path / "americano.png", (1000, 1000))
    assert image_urls(menu, tmp_path) == {"americano": "/images/americano.png?v=1000"}


def test_state_event_snapshot(kiosk: Kiosk):
    kiosk.show_menu(title="추천", item_ids=["americano", "cafe_latte"], highlight_ids=["americano"])
    kiosk.choose_item("americano", 2, {"temperature": "ice", "size": "large"})
    kiosk.choose_item("cafe_latte", selection={"temperature": "hot"})
    kiosk.set_dining(Dining.TO_GO)
    event = state_event(kiosk, "speaking", 7)
    assert event["seq"] == 7 and event["assistant"] == "speaking"
    assert event["phase"] == "ordering"
    assert event["view"] == {
        "screen": "item",
        "title": "",
        "item_ids": [],
        "highlight": [],
        "item_id": "cafe_latte",
        "topic": "",
    }
    assert event["pending"] == {
        "item_id": "cafe_latte",
        "quantity": 1,
        "chosen": {"temperature": ["hot"]},
        "missing": ["size"],
    }
    assert event["order"] == {
        "lines": [
            {
                "line": 1,
                "item_id": "americano",
                "name": "아메리카노",
                "options": "ICE, Large",
                "quantity": 2,
                "unit_price": 4500,
                "total": 9000,
            }
        ],
        "dining": "to_go",
        "count": 2,
        "total": 9000,
    }
    assert event["payment"] is None


def test_state_event_payment(kiosk: Kiosk):
    kiosk.choose_item("chocolate_cookie")
    kiosk.set_dining(Dining.HERE)
    kiosk.review()
    kiosk.start_payment()
    assert state_event(kiosk, "listening", 1)["payment"] == {
        "step": "insert_card",
        "order_number": None,
    }


def test_subtitle_ids_follow_utterances():
    subtitles = Subtitles()
    a = subtitles.event("assistant", "안녕", False)
    b = subtitles.event("assistant", "안녕하세요 ", False)
    c = subtitles.event("customer", "아이스", False)
    d = subtitles.event("assistant", "안녕하세요", True)
    e = subtitles.event("assistant", "네", True)
    assert [x["id"] for x in (a, b, c, d, e)] == [1, 1, 2, 1, 3]
    assert b["text"] == "안녕하세요"


def test_level_is_clamped():
    assert level_event(1.7, -0.2) == {"type": "level", "mic": 1.0, "out": 0.0}


def test_avatar_urls(tmp_path):
    (tmp_path / "idle.webm").write_bytes(b"v")
    (tmp_path / "talking.mp4").write_bytes(b"v")
    (tmp_path / "avatar.webp").write_bytes(b"i")
    urls = avatar_urls(tmp_path)
    assert urls["idle"].startswith("/avatar/idle.webm?v=")
    assert urls["talking"].startswith("/avatar/talking.mp4?v=")
    assert urls["still"].startswith("/avatar/avatar.webp?v=")
    assert urls["pick_up"] is None and urls["listening"] is None and urls["put_down"] is None
