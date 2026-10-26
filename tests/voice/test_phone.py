"""The phone as the handset, without a phone or a network."""

import asyncio

from kiosk.config import AudioConfig
from kiosk.voice.phone import PhoneHandset

FRAME = (1000).to_bytes(2, "little", signed=True) * 320  # 20 ms of 16 kHz audio


def drain(link) -> list:
    async def run():
        messages = []
        while link._messages:
            messages.append(await link.next())
        return messages

    return asyncio.run(run())


def test_microphone_frames_go_on_with_their_loudness():
    heard: list[bytes] = []
    phone = PhoneHandset(AudioConfig(), heard.append)
    link = phone.connect()
    phone.receive(link, FRAME)
    phone.receive(link, b"\x01")  # odd: not 16-bit audio
    phone.receive(link, b"")
    assert heard == [FRAME]
    assert phone.levels()[0] > 0


def test_audio_is_sent_in_order_and_clear_drops_what_was_not_sent():
    phone = PhoneHandset(AudioConfig(), lambda pcm: None)
    phone.write(b"\0\0")  # no phone yet: dropped
    link = phone.connect()
    phone.write(b"a" * 4)
    phone.write(b"b" * 4)
    assert drain(link) == [b"a" * 4, b"b" * 4]
    phone.write(b"c" * 4)
    phone.clear()
    phone.write(b"d" * 4)
    assert drain(link) == ["clear", b"d" * 4]


def test_the_phone_reports_what_its_speaker_plays():
    phone = PhoneHandset(AudioConfig(), lambda pcm: None)
    link = phone.connect()
    phone.receive(link, '{"out": 0.4}')
    assert phone.levels() == (0.0, 0.4)
    for bad in ('{"out": 7}', '{"out": "x"}', "nope", "[1]"):
        phone.receive(link, bad)
    assert phone.levels() == (0.0, 0.4)
    phone.clear()
    assert phone.levels() == (0.0, 0.0)


def test_a_newer_phone_replaces_the_older_one():
    heard: list[bytes] = []
    phone = PhoneHandset(AudioConfig(), heard.append)
    old = phone.connect()
    new = phone.connect()
    assert old.closed and not new.closed
    phone.receive(old, FRAME)
    assert heard == []
    assert asyncio.run(old.next()) is None
    phone.disconnect(old)  # the older one going away does not cut off the newer one
    assert phone.connected
    phone.disconnect(new)
    assert not phone.connected


def test_queued_audio_is_capped():
    phone = PhoneHandset(AudioConfig(output_rate=10), lambda pcm: None)  # a minute = 1200 bytes
    link = phone.connect()
    for _ in range(5):
        phone.write(b"x" * 400)
    assert sum(len(m) for m in drain(link)) <= 1200


def test_quiet_background_noise_is_sent_as_silence():
    heard: list[bytes] = []
    phone = PhoneHandset(AudioConfig(noise_gate_rms=500), heard.append)
    link = phone.connect()
    noise = (100).to_bytes(2, "little", signed=True) * 320
    phone.receive(link, noise)
    assert heard[-1] == bytes(640)
    assert phone.levels()[0] > 0  # the panel still shows what the microphone hears
    phone.receive(link, FRAME)
    assert heard[-1] == FRAME
