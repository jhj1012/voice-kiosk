"""The handset's microphone and earpiece, through `sounddevice` (PortAudio).

- `Microphone` delivers 20 ms frames of 16 kHz 16-bit mono PCM (the Live API's input) to a
  callback, from PortAudio's audio thread.
- `Speaker` plays 24 kHz 16-bit mono PCM (the Live API's output) from a buffer that `clear()`
  empties at once (barge-in, hang-up).
- `Handset` combines both and can gate the microphone while the earpiece plays
  (`audio.echo_gate_rms`), in case the earpiece leaks into the microphone.

If a device refuses the Live API's rate, its own rate is used and the audio is resampled. The
`sounddevice` module can be passed in, so tests run without audio devices.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from kiosk.config import AudioConfig
from kiosk.voice.devices import AudioDeviceError, find_device
from kiosk.voice.pcm import level, resample, rms

log = logging.getLogger(__name__)

MAX_BUFFERED_S = 60.0  # the assistant's audio arrives faster than it plays; keep up to a minute


def _sounddevice(sd: Any) -> Any:
    if sd is not None:
        return sd
    try:
        import sounddevice
    except (ImportError, OSError) as e:
        raise AudioDeviceError(f"sounddevice (PortAudio) is not available: {e}") from e
    return sounddevice


def _open(sd: Any, factory: str, device: int | None, rate: int, frame_ms: int, **kwargs: Any):
    stream = getattr(sd, factory)(
        samplerate=rate,
        blocksize=rate * frame_ms // 1000,
        channels=1,
        dtype="int16",
        device=device,
        **kwargs,
    )
    stream.start()
    return stream


def _open_at(sd: Any, factory: str, device: int | None, wanted: int, frame_ms: int, **kwargs):
    """Open at the wanted rate, else at the device's own rate. Returns (stream, rate)."""
    try:
        return _open(sd, factory, device, wanted, frame_ms, **kwargs), wanted
    except Exception as e:
        info = sd.query_devices(device, "input" if "Input" in factory else "output")
        native = int(info.get("default_samplerate") or 0)
        if not native or native == wanted:
            raise AudioDeviceError(f"could not open the audio device: {e}") from e
        log.info("%d Hz refused (%s); using %d Hz and resampling", wanted, e, native)
        return _open(sd, factory, device, native, frame_ms, **kwargs), native


class Microphone:
    def __init__(
        self, config: AudioConfig, on_frame: Callable[[bytes], None], sd: Any = None
    ) -> None:
        self.config = config
        self.on_frame = on_frame
        self.level = 0.0
        self.name = ""
        self._sd = sd
        self._stream: Any = None
        self._rate = config.input_rate

    def open(self) -> None:
        sd = _sounddevice(self._sd)
        device = find_device(sd.query_devices(), self.config.input_device, "input")
        self.name = str(sd.query_devices(device, "input")["name"])
        self._stream, self._rate = _open_at(
            sd,
            "RawInputStream",
            device,
            self.config.input_rate,
            self.config.frame_ms,
            callback=self._on_audio,
        )
        log.info("microphone: %s, %d Hz", self.name, self._rate)

    def close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()

    def _on_audio(self, data: Any, frames: int, time_info: Any, status: Any) -> None:
        """PortAudio's thread: one frame of microphone audio."""
        pcm = resample(bytes(data), self._rate, self.config.input_rate)
        self.level = level(pcm)
        self.on_frame(pcm)


class Speaker:
    def __init__(self, config: AudioConfig, sd: Any = None) -> None:
        self.config = config
        self.level = 0.0
        self.name = ""
        self._sd = sd
        self._stream: Any = None
        self._rate = config.output_rate
        self._buffer = bytearray()
        self._lock = threading.Lock()

    @property
    def playing(self) -> bool:
        with self._lock:
            return bool(self._buffer)

    def open(self) -> None:
        sd = _sounddevice(self._sd)
        device = find_device(sd.query_devices(), self.config.output_device, "output")
        self.name = str(sd.query_devices(device, "output")["name"])
        self._stream, self._rate = _open_at(
            sd,
            "RawOutputStream",
            device,
            self.config.output_rate,
            self.config.frame_ms,
            callback=self._fill,
        )
        log.info("earpiece: %s, %d Hz", self.name, self._rate)

    def close(self) -> None:
        self.clear()
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()

    def write(self, pcm: bytes) -> None:
        """Queue 24 kHz audio to play."""
        pcm = resample(pcm, self.config.output_rate, self._rate)
        limit = int(MAX_BUFFERED_S * self._rate) * 2
        with self._lock:
            self._buffer.extend(pcm)
            if len(self._buffer) > limit:
                del self._buffer[: len(self._buffer) - limit]

    def clear(self) -> None:
        """Stop at once: drop everything not played yet."""
        with self._lock:
            self._buffer.clear()
        self.level = 0.0

    def _fill(self, out: Any, frames: int, time_info: Any, status: Any) -> None:
        """PortAudio's thread: the next block to play (silence when nothing is queued)."""
        need = frames * 2
        with self._lock:
            chunk = bytes(self._buffer[:need])
            del self._buffer[:need]
        self.level = level(chunk) if chunk else 0.0
        out[:] = chunk.ljust(need, b"\0")


class Handset:
    """The microphone and the earpiece of the handset."""

    def __init__(
        self, config: AudioConfig, on_frame: Callable[[bytes], None], sd: Any = None
    ) -> None:
        self.config = config
        self._on_frame = on_frame
        self.speaker = Speaker(config, sd)
        self.microphone = Microphone(config, self._from_microphone, sd)
        self._silence = b"\0" * (config.input_rate * config.frame_ms // 1000 * 2)

    def open(self) -> None:
        self.speaker.open()
        try:
            self.microphone.open()
        except Exception:
            self.speaker.close()
            raise

    def close(self) -> None:
        self.microphone.close()
        self.speaker.close()

    def levels(self) -> tuple[float, float]:
        """(microphone, earpiece) loudness, 0..1."""
        return self.microphone.level, self.speaker.level

    def _from_microphone(self, pcm: bytes) -> None:
        gate = self.config.echo_gate_rms
        if gate and self.speaker.playing and rms(pcm) < gate:
            pcm = self._silence[: len(pcm)]  # earpiece leaking into the mic: send silence
        self._on_frame(pcm)
