"""Microphone, earpiece and handset with a fake sounddevice module (no audio devices)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from kiosk.config import AudioConfig
from kiosk.voice.devices import AudioDeviceError, devices_of, find_device
from kiosk.voice.handset import Handset, Microphone, Speaker
from kiosk.voice.pcm import level, resample, rms

DEVICES = [
    {
        "name": "Microphone (USB Handset)",
        "max_input_channels": 1,
        "max_output_channels": 0,
        "default_samplerate": 48000.0,
    },
    {
        "name": "Earpiece (USB Handset)",
        "max_input_channels": 0,
        "max_output_channels": 1,
        "default_samplerate": 48000.0,
    },
]


class FakeStream:
    def __init__(self, sd: FakeSounddevice, **kwargs: Any) -> None:
        if kwargs["samplerate"] not in sd.rates:
            raise ValueError("Invalid sample rate")
        self.kwargs = kwargs
        self.started = self.closed = False
        sd.streams.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        self.closed = True


class FakeSounddevice:
    def __init__(self, rates=(16000, 24000, 48000)) -> None:
        self.rates = rates
        self.streams: list[FakeStream] = []

    def query_devices(self, device=None, kind=None):
        if device is None and kind is None:
            return DEVICES
        if device is None:
            return DEVICES[0 if kind == "input" else 1]
        return DEVICES[device]

    def RawInputStream(self, **kwargs):  # noqa: N802 (sounddevice's name)
        return FakeStream(self, **kwargs)

    def RawOutputStream(self, **kwargs):  # noqa: N802
        return FakeStream(self, **kwargs)


def tone(rate: int, ms: int, amplitude: int = 8000) -> bytes:
    t = np.arange(rate * ms // 1000) / rate
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.int16).tobytes()


# --- devices and pcm ---------------------------------------------------------------------------


def test_find_device():
    assert devices_of(DEVICES, "input") == [(0, "Microphone (USB Handset)")]
    assert find_device(DEVICES, None, "input") is None
    assert find_device(DEVICES, "handset", "output") == 1
    assert find_device(DEVICES, 0, "input") == 0
    with pytest.raises(AudioDeviceError):
        find_device(DEVICES, 1, "input")
    with pytest.raises(AudioDeviceError, match="speaker"):
        find_device(DEVICES, "speaker", "output")


def test_rms_level_and_resample():
    assert rms(b"") == 0.0
    loud = tone(16000, 20)
    assert 5000 < rms(loud) < 6000  # a sine's RMS is amplitude / sqrt(2)
    assert level(b"\xff\x7f" * 8) == 1.0
    assert len(resample(loud, 16000, 48000)) == len(loud) * 3
    assert len(resample(tone(48000, 20), 48000, 16000)) == len(loud)
    assert resample(loud, 16000, 16000) == loud


# --- microphone --------------------------------------------------------------------------------


def test_microphone_delivers_16k_frames():
    sd = FakeSounddevice()
    frames: list[bytes] = []
    mic = Microphone(AudioConfig(input_device="handset"), frames.append, sd)
    mic.open()
    stream = sd.streams[0]
    assert stream.kwargs["samplerate"] == 16000 and stream.kwargs["blocksize"] == 320
    assert stream.kwargs["device"] == 0 and stream.started
    stream.kwargs["callback"](tone(16000, 20), 320, None, None)
    assert len(frames[0]) == 640 and mic.level > 0.5
    mic.close()
    assert stream.closed


def test_microphone_resamples_when_the_device_refuses_16k():
    sd = FakeSounddevice(rates=(48000,))
    frames: list[bytes] = []
    Microphone(AudioConfig(), frames.append, sd).open()
    stream = sd.streams[-1]
    assert stream.kwargs["samplerate"] == 48000
    stream.kwargs["callback"](tone(48000, 20), 960, None, None)
    assert len(frames[0]) == 640  # 20 ms at 16 kHz


# --- earpiece ----------------------------------------------------------------------------------


def play(speaker: Speaker, sd: FakeSounddevice, frames: int) -> bytes:
    out = bytearray(frames * 2)
    sd.streams[-1].kwargs["callback"](out, frames, None, None)
    return bytes(out)


def test_speaker_plays_queued_audio_then_silence():
    sd = FakeSounddevice()
    speaker = Speaker(AudioConfig(), sd)
    speaker.open()
    speaker.write(b"\x01\x00" * 600)
    assert speaker.playing
    first = play(speaker, sd, 480)
    assert first == b"\x01\x00" * 480
    second = play(speaker, sd, 480)
    assert second == b"\x01\x00" * 120 + b"\x00\x00" * 360
    assert not speaker.playing


def test_speaker_clear_stops_at_once():
    sd = FakeSounddevice()
    speaker = Speaker(AudioConfig(), sd)
    speaker.open()
    speaker.write(tone(24000, 2000))
    play(speaker, sd, 480)
    assert speaker.level > 0
    speaker.clear()  # the customer interrupted
    assert not speaker.playing and speaker.level == 0
    assert play(speaker, sd, 480) == b"\x00" * 960


def test_speaker_resamples_for_a_48k_device():
    sd = FakeSounddevice(rates=(48000,))
    speaker = Speaker(AudioConfig(), sd)
    speaker.open()
    speaker.write(tone(24000, 20))  # 480 samples at 24 kHz
    assert play(speaker, sd, 960) != b"\x00" * 1920  # 960 samples at 48 kHz, all audio


# --- handset -----------------------------------------------------------------------------------


def test_echo_gate_silences_quiet_mic_audio_while_the_earpiece_plays():
    sd = FakeSounddevice()
    frames: list[bytes] = []
    handset = Handset(AudioConfig(echo_gate_rms=1000), frames.append, sd)
    handset.open()
    mic_callback = sd.streams[1].kwargs["callback"]
    leak = tone(16000, 20, amplitude=300)  # the earpiece heard faintly by the mic
    voice = tone(16000, 20, amplitude=8000)  # the customer speaking into the mic
    mic_callback(leak, 320, None, None)
    assert frames[-1] == leak  # nothing is playing: no gate
    handset.speaker.write(tone(24000, 500))
    mic_callback(leak, 320, None, None)
    assert frames[-1] == b"\x00" * 640
    mic_callback(voice, 320, None, None)
    assert frames[-1] == voice  # barge-in still works
    assert handset.levels()[0] > 0.5
    handset.close()
    assert all(s.closed for s in sd.streams)


def test_echo_gate_is_off_by_default():
    sd = FakeSounddevice()
    frames: list[bytes] = []
    handset = Handset(AudioConfig(), frames.append, sd)
    handset.open()
    handset.speaker.write(tone(24000, 500))
    leak = tone(16000, 20, amplitude=300)
    sd.streams[1].kwargs["callback"](leak, 320, None, None)
    assert frames[-1] == leak
