from kiosk.voice.mediakey import (
    VK_MEDIA_NEXT_TRACK,
    VK_MEDIA_PLAY_PAUSE,
    MediaKeys,
    PressGate,
)


def test_play_pause_is_one_press_and_media_keys_are_swallowed():
    presses = []
    keys = MediaKeys(lambda: presses.append(1))
    keys._gate = PressGate(0.8, clock=iter([0.0, 0.3, 2.0]).__next__)
    assert keys.key(VK_MEDIA_PLAY_PAUSE, down=True)  # a press
    assert keys.key(VK_MEDIA_PLAY_PAUSE, down=False)  # its release: swallowed, nothing more
    assert keys.key(VK_MEDIA_PLAY_PAUSE, down=True)  # 0.3 s later: the same press
    assert keys.key(VK_MEDIA_PLAY_PAUSE, down=True)  # 2 s later: the next press
    assert presses == [1, 1]
    assert keys.key(VK_MEDIA_NEXT_TRACK, down=True)  # a double press: swallowed, no press
    assert presses == [1, 1]
    assert not keys.key(0x41, down=True)  # "A": not ours
