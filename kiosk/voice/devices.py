"""Find the handset's microphone and earpiece among the PC's audio devices.

`uv run python -m kiosk.voice.devices` lists them, to fill in `audio.input_device` and
`audio.output_device` in configs/settings.local.yaml (a device index, or part of its name).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from typing import Any, Literal

Kind = Literal["input", "output"]


class AudioDeviceError(Exception):
    """The configured device does not exist or cannot be opened."""


def devices_of(devices: Iterable[Mapping[str, Any]], kind: Kind) -> list[tuple[int, str]]:
    """(index, name) of the devices that can record ("input") or play ("output")."""
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    return [(i, str(d.get("name", ""))) for i, d in enumerate(devices) if int(d.get(key, 0)) > 0]


def find_device(
    devices: Iterable[Mapping[str, Any]], wanted: int | str | None, kind: Kind
) -> int | None:
    """The device index for a setting: None (the system default), an index or a name part.

    A name may match several host APIs (MME, WASAPI, ...); the first match is used, which on
    Windows is MME: it converts sample rates itself.
    """
    if wanted is None or wanted == "":
        return None
    candidates = devices_of(devices, kind)
    if isinstance(wanted, int):
        if any(i == wanted for i, _ in candidates):
            return wanted
        raise AudioDeviceError(f"audio device {wanted} is not an {kind} device")
    for i, name in candidates:
        if wanted.lower() in name.lower():
            return i
    raise AudioDeviceError(f"no {kind} device whose name contains {wanted!r}")


def main() -> int:
    import sounddevice as sd

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    devices = sd.query_devices()
    default_in, default_out = sd.default.device
    for kind, default in (("input", default_in), ("output", default_out)):
        print(f"{kind} devices (audio.{kind}_device):")
        for i, name in devices_of(devices, kind):  # type: ignore[arg-type]
            api = sd.query_hostapis(devices[i]["hostapi"])["name"]
            mark = "  <- default" if i == default else ""
            print(f"  {i:3d}  {name}  [{api}]{mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
