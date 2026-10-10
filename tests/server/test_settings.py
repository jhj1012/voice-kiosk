"""The display settings file (no browser)."""

import json

from kiosk.server.settings import DisplaySettings


def test_settings_merge_and_survive_a_restart(tmp_path):
    path = tmp_path / "display.local.json"
    settings = DisplaySettings(path)
    assert settings.values == {}
    assert settings.update({"backdrop": "blur", "colors": {"bg": "#ffffff"}})
    assert settings.update({"subtitles": True})
    expected = {"backdrop": "blur", "colors": {"bg": "#ffffff"}, "subtitles": True}
    assert DisplaySettings(path).values == expected


def test_malformed_settings_are_refused(tmp_path):
    settings = DisplaySettings(tmp_path / "display.local.json")
    for bad in ["x", [1], {"a": [1, 2]}, {"a": {"b": {"c": 1}}}, {"a": "x" * 500}, {1: 2}]:
        assert not settings.update(bad)
    assert settings.values == {}
    assert not (tmp_path / "display.local.json").exists()


def test_a_broken_file_falls_back_to_the_defaults(tmp_path):
    path = tmp_path / "display.local.json"
    path.write_text("{not json", encoding="utf-8")
    assert DisplaySettings(path).values == {}
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    assert DisplaySettings(path).values == {}
