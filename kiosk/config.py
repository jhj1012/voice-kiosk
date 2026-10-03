"""Load `configs/settings.yaml` into typed settings.

The file may have a git-ignored `settings.local.yaml` sibling whose values are merged on top, so
a teammate can pick their own audio devices or model without touching the shared file. Secrets
(the Gemini API key) come from environment variables, or from a git-ignored `.env` file in the
repository root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "configs"
DATA_DIR = REPO_ROOT / "data"
ENV_FILE = REPO_ROOT / ".env"


class ConfigError(Exception):
    """A config file is missing or has invalid values."""


@dataclass(frozen=True)
class LiveConfig:
    """The Gemini Live API session (one per customer)."""

    model: str = "gemini-3.8-live"
    voice: str = ""  # a prebuilt voice name; empty = the model's default
    api_key_env: str = "GEMINI_API_KEY"  # environment variable that holds the API key
    language: str = "ko-KR"  # speech and transcription language
    vocabulary: bool = True  # bias the transcription towards menu and option names
    # Server-side voice detection (milestone 3: short answers were missed with the defaults).
    start_sensitivity: str = "high"  # high | low | "" (the API's default)
    end_sensitivity: str = ""  # high | low | ""
    prefix_padding_ms: int | None = 300  # audio kept before detected speech
    silence_duration_ms: int | None = None  # silence that ends speech; None = the API's default


@dataclass(frozen=True)
class AudioConfig:
    """The handset: devices are None (Windows default), an index or part of the name."""

    input_device: int | str | None = None
    output_device: int | str | None = None
    input_rate: int = 16000  # what the Live API expects
    output_rate: int = 24000  # what the Live API sends
    frame_ms: int = 20


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass(frozen=True)
class FlowConfig:
    """Timings of the simulated payment and the done screen, in seconds."""

    insert_card_s: float = 3.0
    processing_s: float = 2.0
    done_return_s: float = 8.0
    first_order_number: int = 1


@dataclass(frozen=True)
class Config:
    live: LiveConfig = field(default_factory=LiveConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    flow: FlowConfig = field(default_factory=FlowConfig)
    data_dir: Path = DATA_DIR


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return `base` updated with `override`; nested dicts are merged key by key."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml(path: Path) -> dict[str, Any]:
    """Read `path` and merge its `*.local.yaml` sibling on top, if it exists."""
    data = _read_yaml(path)
    local = path.with_name(f"{path.stem}.local{path.suffix}")
    if local.exists():
        data = deep_merge(data, _read_yaml(local))
    return data


def load_config(config_dir: Path = CONFIG_DIR, data_dir: Path = DATA_DIR) -> Config:
    settings = load_yaml(config_dir / "settings.yaml")
    config = Config(
        live=_build(LiveConfig, settings.get("live", {}), "live"),
        audio=_build(AudioConfig, settings.get("audio", {}), "audio"),
        server=_build(ServerConfig, settings.get("server", {}), "server"),
        flow=_build(FlowConfig, settings.get("flow", {}), "flow"),
        data_dir=data_dir,
    )
    _check(config)
    return config


def load_env_file(path: Path = ENV_FILE) -> list[str]:
    """Set environment variables from `KEY=value` lines in `path`, if the file exists.

    Variables that are already set win. Returns the names that were set (never the values).
    """
    if not path.exists():
        return []
    loaded = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        key = key.removeprefix("export ").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def _check(config: Config) -> None:
    if not config.live.model:
        raise ConfigError("settings.yaml: live.model must be set")
    for name in ("start_sensitivity", "end_sensitivity"):
        if getattr(config.live, name) not in ("", "high", "low"):
            raise ConfigError(f"settings.yaml: live.{name} must be high, low or empty")
    audio = config.audio
    if audio.input_rate < 8000 or audio.output_rate < 8000 or audio.frame_ms not in (10, 20, 30):
        raise ConfigError("settings.yaml: audio needs rates >= 8000 and frame_ms 10/20/30")
    flow = config.flow
    if min(flow.insert_card_s, flow.processing_s, flow.done_return_s) < 0:
        raise ConfigError("settings.yaml: flow times must not be negative")
    if not 1 <= config.server.port <= 65535:
        raise ConfigError("settings.yaml: server.port must be 1..65535")


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def _build[T](cls: type[T], values: dict[str, Any], where: str) -> T:
    """Create a config dataclass from `values`; unknown keys are an error (typos)."""
    if not isinstance(values, dict):
        raise ConfigError(f"settings.yaml: {where} must be a mapping")
    known = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    unknown = sorted(set(values) - known)
    if unknown:
        raise ConfigError(f"settings.yaml: unknown {where} setting(s): {', '.join(unknown)}")
    try:
        return cls(**{k: v for k, v in values.items() if v is not None})
    except TypeError as e:
        raise ConfigError(f"settings.yaml: {where}: {e}") from e
