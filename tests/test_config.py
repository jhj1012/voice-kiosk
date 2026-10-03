import os
from pathlib import Path

import pytest

from kiosk.config import CONFIG_DIR, ConfigError, load_config, load_env_file


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_shared_settings_load():
    config = load_config(CONFIG_DIR)
    assert config.live.model
    assert config.audio.input_rate == 16000
    assert config.audio.output_rate == 24000


def test_local_file_overrides_shared(tmp_path):
    write(tmp_path / "settings.yaml", "live:\n  model: a\naudio:\n  input_device: null\n")
    write(tmp_path / "settings.local.yaml", "audio:\n  input_device: Headset\n")
    config = load_config(tmp_path)
    assert config.live.model == "a"
    assert config.audio.input_device == "Headset"


def test_unknown_setting_is_an_error(tmp_path):
    write(tmp_path / "settings.yaml", "audio:\n  input_devise: 1\n")
    with pytest.raises(ConfigError, match="input_devise"):
        load_config(tmp_path)


def test_invalid_frame_size(tmp_path):
    write(tmp_path / "settings.yaml", "audio:\n  frame_ms: 25\n")
    with pytest.raises(ConfigError, match="frame_ms"):
        load_config(tmp_path)


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path)


def test_env_file_does_not_override_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("KIOSK_TEST_A", "from-env")
    monkeypatch.delenv("KIOSK_TEST_B", raising=False)
    env = tmp_path / ".env"
    write(env, "# comment\nKIOSK_TEST_A=from-file\nexport KIOSK_TEST_B='quoted'\n")
    assert load_env_file(env) == ["KIOSK_TEST_B"]

    assert os.environ["KIOSK_TEST_A"] == "from-env"
    assert os.environ["KIOSK_TEST_B"] == "quoted"
    monkeypatch.delenv("KIOSK_TEST_B")
