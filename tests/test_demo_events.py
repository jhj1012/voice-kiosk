"""frontend/src/dev/demo.json must match what scripts/make_demo_events.py writes today."""

import importlib.util
import json

from kiosk.config import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "make_demo_events.py"


def test_demo_events_are_up_to_date():
    spec = importlib.util.spec_from_file_location("make_demo_events", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    committed = json.loads(module.OUT.read_text(encoding="utf-8"))
    assert committed == module.build(), (
        "frontend/src/dev/demo.json is out of date: run uv run python scripts/make_demo_events.py"
    )
