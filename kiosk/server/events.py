"""The WebSocket events for the display, built from the kiosk's state (pure, tested).

Backend -> display:
- `init`: the menu and cafe information, once per connection (items carry `image_url` when an
  image file exists in data/images/).
- `state`: a full snapshot of what to show: phase, assistant state, view, pending item, order,
  payment. Always complete, so the display can (re)connect at any time.
- `subtitle`: what the customer said / the assistant says. `id` changes with each new utterance;
  the same id with more text updates it, `final` ends it.
- `level`: microphone and speaker loudness (0..1), for the assistant animation.
- `notice`: a short message for the screen (empty text clears it).

Display -> backend (developer mode): `hook`, `dev_text`, `dev_mute`. See docs/architecture.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kiosk.domain.cafe import Cafe
from kiosk.domain.flow import Kiosk
from kiosk.domain.loader import find_image
from kiosk.domain.menu import Menu

Event = dict[str, Any]


def image_urls(menu: Menu, images_dir: Path) -> dict[str, str]:
    """`/images/<file>?v=<mtime>` for each item with an image (the version busts caches)."""
    urls = {}
    for item in menu.items:
        path = find_image(images_dir, item.id)
        if path is not None:
            urls[item.id] = f"/images/{path.name}?v={int(path.stat().st_mtime)}"
    return urls


def init_event(menu: Menu, cafe: Cafe, images: dict[str, str] | None = None) -> Event:
    images = images or {}
    return {
        "type": "init",
        "cafe": {
            "name": cafe.name,
            "topics": [{"id": t.id, "title": t.title, "text": t.text} for t in cafe.topics],
        },
        "menu": {
            "categories": [{"id": c.id, "name": c.name, "unit": c.unit} for c in menu.categories],
            "allergens": [{"id": a.id, "name": a.name} for a in menu.allergens],
            "option_groups": [
                {
                    "id": g.id,
                    "name": g.name,
                    "required": g.required,
                    "multi": g.multi,
                    "choices": [
                        {"id": c.id, "name": c.name, "say": c.spoken, "price": c.price}
                        for c in g.choices
                    ],
                }
                for g in menu.option_groups
            ],
            "items": [
                {
                    "id": i.id,
                    "name": i.name,
                    "category": i.category,
                    "price": i.price,
                    "emoji": i.emoji,
                    "image_url": images.get(i.id),
                    "description": i.description,
                    "ingredients": list(i.ingredients),
                    "allergens": list(i.allergens),
                    "caffeine": i.caffeine,
                    "sweetness": i.sweetness,
                    "recommended": i.recommended,
                    "temperature": i.temperature,
                    "options": [g.id for g in i.option_groups],
                }
                for i in menu.items
            ],
        },
    }


def state_event(kiosk: Kiosk, assistant: str, seq: int) -> Event:
    view = kiosk.view
    order = kiosk.order
    pending = kiosk.pending
    return {
        "type": "state",
        "seq": seq,
        "phase": kiosk.phase.value,
        "assistant": assistant,
        "view": {
            "screen": view.screen.value,
            "title": view.title,
            "item_ids": list(view.item_ids),
            "highlight": list(view.highlight),
            "item_id": view.item_id,
            "topic": view.topic,
        },
        "pending": None
        if pending is None
        else {
            "item_id": pending.item.id,
            "quantity": pending.quantity,
            "chosen": {g: [c.id for c in cs] for g, cs in pending.chosen.items()},
            "missing": [g.id for g in pending.missing],
        },
        "order": {
            "lines": [
                {
                    "line": n,
                    "item_id": line.item.id,
                    "name": line.item.name,
                    "options": line.option_text,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "total": line.total,
                }
                for n, line in enumerate(order.lines, start=1)
            ],
            "dining": order.dining.value if order.dining else None,
            "count": sum(line.quantity for line in order.lines),
            "total": order.total,
        },
        "payment": None
        if kiosk.payment_step is None
        else {"step": kiosk.payment_step.value, "order_number": kiosk.order_number},
    }


class Subtitles:
    """Turns (speaker, text, final) updates into subtitle events with utterance ids."""

    def __init__(self) -> None:
        self._next = 0
        self._open: dict[str, int] = {}  # speaker -> id of the utterance still growing

    def event(self, speaker: str, text: str, final: bool) -> Event:
        utterance_id = self._open.get(speaker)
        if utterance_id is None:
            self._next += 1
            utterance_id = self._next
        if final:
            self._open.pop(speaker, None)
        else:
            self._open[speaker] = utterance_id
        return {
            "type": "subtitle",
            "id": utterance_id,
            "speaker": speaker,
            "text": text.strip(),
            "final": final,
        }


def level_event(mic: float, out: float) -> Event:
    return {"type": "level", "mic": _unit(mic), "out": _unit(out)}


def _unit(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 3)


def notice_event(level: str, text: str) -> Event:
    return {"type": "notice", "level": level, "text": text}
