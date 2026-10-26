"""PCM helpers."""

from kiosk.voice.pcm import NoiseGate


def test_noise_gate_silences_quiet_audio_and_holds_after_speech():
    gate = NoiseGate(500, hold_s=0.04)  # two 20 ms frames
    quiet = (100).to_bytes(2, "little", signed=True) * 320
    loud = (3000).to_bytes(2, "little", signed=True) * 320
    assert gate(quiet, 16000) == bytes(640)
    assert gate(loud, 16000) == loud
    assert gate(quiet, 16000) == quiet  # held open: the end of the word
    assert gate(quiet, 16000) == quiet
    assert gate(quiet, 16000) == bytes(640)


def test_noise_gate_is_off_without_a_threshold():
    quiet = (100).to_bytes(2, "little", signed=True) * 320
    assert NoiseGate(None)(quiet, 16000) == quiet
