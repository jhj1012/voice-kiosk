"""16-bit mono PCM helpers: loudness and sample-rate conversion (numpy)."""

from __future__ import annotations

import numpy as np

FULL_SCALE_RMS = 6000.0  # speech this loud (16-bit RMS) counts as level 1


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
