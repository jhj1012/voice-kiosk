"""16-bit mono PCM helpers: loudness, a noise gate and sample-rate conversion (numpy)."""

from __future__ import annotations

import numpy as np

FULL_SCALE_RMS = 6000.0  # speech this loud (16-bit RMS) counts as level 1


class NoiseGate:
    """Sends quiet microphone audio as silence, so background noise does not count as speech.

    A frame quieter than `threshold` (16-bit RMS) becomes silence, unless a louder one came less
    than `hold_s` ago: the ends of words and soft sounds between loud ones stay. None = off.
    """

    def __init__(self, threshold: float | None, hold_s: float = 0.5) -> None:
        self.threshold = threshold
        self.hold_s = hold_s
        self._open_for = 0.0  # seconds the gate stays open

    def __call__(self, pcm: bytes, rate: int) -> bytes:
        if not self.threshold or not pcm:
            return pcm
        seconds = len(pcm) / 2 / rate
        if rms(pcm) >= self.threshold:
            self._open_for = self.hold_s
            return pcm
        if self._open_for > 1e-9:
            self._open_for -= seconds
            return pcm
        return bytes(len(pcm))


def rms(pcm: bytes) -> float:
    samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype=np.int16)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


def level(pcm: bytes) -> float:
    """0..1 loudness for the display's animation."""
    return min(1.0, rms(pcm) / FULL_SCALE_RMS)


def resample(pcm: bytes, from_rate: int, to_rate: int) -> bytes:
    """Linear resampling. Good enough for speech, and only used when a device cannot open the
    Live API's rates itself (16 kHz in, 24 kHz out)."""
    if from_rate == to_rate or not pcm:
        return pcm
    samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype=np.int16).astype(np.float32)
    count = max(1, round(samples.size * to_rate / from_rate))
    positions = np.linspace(0, samples.size - 1, count)
    out = np.interp(positions, np.arange(samples.size), samples)
    return np.clip(np.round(out), -32768, 32767).astype(np.int16).tobytes()
