"""Typed developer mode in the terminal: one customer session with the real Live API.

    uv run python -m kiosk.assistant.chat

Type what the customer says (Korean). The assistant's audio is not played (milestone 7 adds the
handset); its words, function calls, the order and the payment steps are printed. Commands:
/order (show the order), /hangup (end the session and start a new one), /quit.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from kiosk.assistant.live import GeminiConnector
from kiosk.assistant.safety import Speaker
from kiosk.assistant.session import AssistantSession, SessionListener
from kiosk.config import load_config, load_env_file
from kiosk.domain.flow import Kiosk
from kiosk.domain.loader import load_cafe, load_menu
from kiosk.domain.order import won


class ConsoleListener(SessionListener):
    def __init__(self, kiosk: Kiosk) -> None:
        self.kiosk = kiosk
        self.finished = asyncio.Event()
        self.typed = ""  # the line just typed: not printed again as a subtitle
        self._last = ("", "", "")

    def on_state(self) -> None:
        k = self.kiosk
        view = k.view
        detail = view.title or view.item_id or view.topic
        step = k.payment_step.value if k.payment_step else ""
        summary = (k.phase.value, f"{view.screen.value} {detail}".strip(), step)
        if summary != self._last:
            self._last = summary
            number = f" #{k.order_number}" if k.order_number else ""
            print(f"  [{summary[0]} | screen: {summary[1]} {step}{number}]")

    def on_subtitle(self, speaker: Speaker, text: str, final: bool) -> None:
        if final and speaker == "assistant":
            print(f"assistant> {text.strip()}")
        elif final and speaker == "customer" and text.strip() != self.typed:
            print(f"customer (heard)> {text.strip()}")

    def on_notice(self, level: str, text: str) -> None:
        if text:
            print(f"  ({level}) {text}")

    def on_finished(self) -> None:
        self.finished.set()


def print_order(kiosk: Kiosk) -> None:
    order = kiosk.order
    for n, line in enumerate(order.lines, start=1):
        print(f"  {n}. {line.spoken(kiosk.menu.unit(line.item))}  {won(line.total)}")
    dining = order.dining.label if order.dining else "?"
    print(f"  dining {dining}, total {won(order.total)}")


async def run() -> int:
    load_env_file()
    config = load_config()
    key = os.environ.get(config.live.api_key_env, "").strip()
    if not key:
        print(f"Set {config.live.api_key_env} in .env first (see docs/setup.md).")
        return 1
    menu = load_menu(config.data_dir / "menu.yaml")
    cafe = load_cafe(config.data_dir / "cafe.yaml")
    connector = GeminiConnector(config.live, key)
    print(f"{config.live.model}, voice {config.live.voice or '(default)'}. /order /hangup /quit")
    line_task: asyncio.Task[str] | None = None  # one reader, kept across customers
    while True:
        kiosk = Kiosk(menu, cafe, config.flow.first_order_number)
        listener = ConsoleListener(kiosk)
        session = AssistantSession(kiosk, connector, config.flow, listener)
        if not await session.start():
            return 1
        try:
            while not listener.finished.is_set():
                if line_task is None or line_task.done():
                    line_task = asyncio.create_task(asyncio.to_thread(input))
                done_task = asyncio.create_task(listener.finished.wait())
                done, _ = await asyncio.wait(
                    {line_task, done_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if done_task in done:
                    print("  (done screen timed out: next customer)")
                    break
                done_task.cancel()
                text = line_task.result().strip()
                line_task = None
                if text == "/quit":
                    return 0
                if text == "/hangup":
                    break
                if text == "/order":
                    print_order(kiosk)
                    continue
                listener.typed = text
                await session.send_text(text)
        except (EOFError, KeyboardInterrupt):
            return 0
        finally:
            await session.stop()
        print("--- handset down; new customer ---")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
