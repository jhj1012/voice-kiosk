"""The display's settings from the developer panel (F2): colours, the choices' background,
subtitles on or off.

The backend keeps them in a git-ignored file, so every display and every browser profile gets
the same ones (the full-screen launcher uses its own Edge profile, which would not see settings
saved in the browser). Only their shape is checked here; the display knows what they mean.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MAX_BYTES = 20_000
MAX_TEXT = 200

Value = bool | int | float | str


class DisplaySettings:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.values: dict[str, Any] = self._load()

    def update(self, values: Any) -> bool:
        """Merge `values` (top-level keys replace earlier ones) and save. False if malformed."""
        if not _valid(values):
            log.warning("ignored malformed display settings")
            return False
        merged = {**self.values, **values}
        text = json.dumps(merged, ensure_ascii=False, indent=1)
        if len(text.encode()) > MAX_BYTES:
            log.warning("ignored display settings: too large")
            return False
        self.values = merged
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(text + "\n", encoding="utf-8", newline="\n")
        temporary.replace(self.path)
        return True

    def reset(self) -> None:
        self.values = {}
        self.path.unlink(missing_ok=True)

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            log.warning("could not read %s (%s); using the defaults", self.path, e)
            return {}
        return data if _valid(data) else {}


def _valid(values: Any) -> bool:
    """A flat object of simple values, or objects of simple values (e.g. the colours)."""
    if not isinstance(values, dict):
        return False
    for key, value in values.items():
        if not isinstance(key, str) or len(key) > MAX_TEXT:
            return False
        if isinstance(value, dict):
            if not all(isinstance(k, str) and _simple(v) for k, v in value.items()):
                return False
        elif not _simple(value):
            return False
    return True


def _simple(value: Any) -> bool:
    if isinstance(value, str):
        return len(value) <= MAX_TEXT
    return isinstance(value, bool | int | float)
