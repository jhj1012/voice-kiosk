"""The handset's button on the laptop (USB mode: the handset plugged into the laptop).

A headset's button reaches Windows as the media play / pause key. A low-level keyboard hook
(Windows' own API through ctypes, no package) sees it before any music app does: the kiosk takes
it as "start / end the conversation" and swallows it, so nothing starts playing. A double press
is "next track": swallowed too, nothing else. Other systems: the hook does nothing.

    uv run python -m kiosk.voice.mediakey    # press the handset's button: is it seen?
"""

from __future__ import annotations

import contextlib
import ctypes
import logging
import sys
import threading
import time
from collections.abc import Callable
from ctypes import wintypes

log = logging.getLogger(__name__)

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
SWALLOWED = {VK_MEDIA_NEXT_TRACK, VK_MEDIA_PREV_TRACK, VK_MEDIA_STOP, VK_MEDIA_PLAY_PAUSE}
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012
GAP_S = 0.8  # one press may arrive as more than one key event


class _KeyInfo(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class PressGate:
    """Lets one press through, then none for `gap_s`."""

    def __init__(self, gap_s: float = GAP_S, clock: Callable[[], float] = time.monotonic) -> None:
        self.gap_s = gap_s
        self._clock = clock
        self._last = -1e9

    def __call__(self) -> bool:
        now = self._clock()
        if now - self._last < self.gap_s:
            return False
        self._last = now
        return True


class MediaKeys:
    """Calls `on_press` (from its own thread) when the handset's button is pressed."""

    def __init__(self, on_press: Callable[[], None]) -> None:
        self.on_press = on_press
        self._gate = PressGate()
        self._thread: threading.Thread | None = None
        self._thread_id = 0

    def key(self, vk: int, down: bool) -> bool:
        """One key event: True if the kiosk takes (and swallows) it."""
        if vk not in SWALLOWED:
            return False
        if down and vk == VK_MEDIA_PLAY_PAUSE and self._gate():
            log.info("handset button")
            self.on_press()
        return True

    def start(self) -> bool:
        """Start watching. False where there is no such hook (not Windows)."""
        if sys.platform != "win32":
            return False
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait(2)
        return True

    def close(self) -> None:
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _run(self, ready: threading.Event) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hook_proc = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )
        user32.CallNextHookEx.argtypes = [
            wintypes.HHOOK,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            hook_proc,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK

        def on_key(code: int, wparam: int, lparam: int) -> int:
            if code >= 0:
                info = ctypes.cast(lparam, ctypes.POINTER(_KeyInfo)).contents
                try:
                    taken = self.key(info.vkCode, wparam in (WM_KEYDOWN, WM_SYSKEYDOWN))
                except Exception:  # never let an error break the keyboard
                    log.exception("handset button")
                    taken = False
                if taken:
                    return 1
            return user32.CallNextHookEx(None, code, wparam, lparam)

        callback = hook_proc(on_key)  # kept alive while the hook runs
        self._thread_id = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, callback, None, 0)
        ready.set()
        if not hook:
            log.warning("could not watch the handset button (error %d)", kernel32.GetLastError())
            return
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(hook)


def main() -> int:
    """Shows each press of the handset's button for a minute (plug the handset in first)."""
    presses = 0

    def pressed() -> None:
        nonlocal presses
        presses += 1
        print(f"  수화기 버튼: {presses}번째 ({time.strftime('%H:%M:%S')})")

    keys = MediaKeys(pressed)
    if not keys.start():
        print("이 기능은 Windows에서만 돼요.")
        return 1
    print("수화기를 노트북에 꽂고 수화기 버튼을 눌러 보세요. 1분 동안 기다려요 (Ctrl+C로 끝).")
    with contextlib.suppress(KeyboardInterrupt):
        time.sleep(60)
    keys.close()
    print("눌린 횟수:", presses, "(0이면 이 수화기의 버튼은 노트북에서 미디어 키로 오지 않아요)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
