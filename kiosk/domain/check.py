"""`uv run python -m kiosk.domain.check`: check data/menu.yaml and data/cafe.yaml after editing.

Prints mistakes (and exits with 1), the facts nobody has verified yet, and which items have an
image in data/images/.
"""

from __future__ import annotations

import sys
from pathlib import Path

from kiosk.config import DATA_DIR
from kiosk.domain.loader import IMAGE_SUFFIXES, DataError, find_image, load_cafe, load_menu
from kiosk.domain.order import won


def report(data_dir: Path) -> list[str]:
    """The report as lines. Raises DataError if the data is invalid."""
    menu = load_menu(data_dir / "menu.yaml")
    cafe = load_cafe(data_dir / "cafe.yaml")
    images_dir = data_dir / "images"
    lines = [
        f"OK: {len(menu.items)} items in {len(menu.categories)} categories, "
        f"{len(cafe.topics)} cafe info topics ({cafe.name})",
        "",
        "Not verified yet (invented for the demo; please check):",
    ]
    unverified = [f"  item {i.id} ({i.name}, {won(i.price)})" for i in menu.items if not i.verified]
    unverified += [f"  cafe topic {t.id} ({t.title})" for t in cafe.topics if not t.verified]
    if not cafe.verified:
        unverified.append(f"  cafe name ({cafe.name})")
    lines += unverified or ["  nothing"]
    lines += ["", f"Images in {images_dir}:"]
    for item in menu.items:
        image = find_image(images_dir, item.id)
        lines.append(f"  {item.id}: {image.name if image else '(none: emoji placeholder)'}")
    item_ids = {i.id for i in menu.items}
    if images_dir.is_dir():
        for path in sorted(images_dir.iterdir()):
            if path.suffix.lower() in IMAGE_SUFFIXES and path.stem not in item_ids:
                lines.append(f"  WARNING: {path.name} matches no item id")
    return lines


def main() -> int:
    try:
        lines = report(DATA_DIR)
    except DataError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
