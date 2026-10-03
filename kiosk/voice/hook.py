"""The handset's hook switch: lifted (off-hook) or put down (on-hook).

A real switch (a USB handset, a microcontroller) will implement `HookSwitch` later. Today it is
simulated: the display's Space key sends a `hook` event, which the server passes to
`SimulatedHook.set`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

Listener = Callable[[bool], None]  # called with True when lifted, False when put down


class HookSwitch(Protocol):
    @property
    def off_hook(self) -> bool:
        """True while the handset is lifted."""
        ...

    def subscribe(self, listener: Listener) -> None:
        """Call `listener` whenever the handset is lifted or put down."""
        ...


class SimulatedHook:
    """A hook switch set from outside (the display's Space key in developer mode)."""

    def __init__(self) -> None:
        self._off_hook = False
        self._listeners: list[Listener] = []

    @property
    def off_hook(self) -> bool:
        return self._off_hook

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def set(self, off_hook: bool) -> None:
        """Lift (True) or put down (False). Repeating the current position does nothing."""
        if off_hook == self._off_hook:
            return
        self._off_hook = off_hook
        for listener in list(self._listeners):
            listener(off_hook)
