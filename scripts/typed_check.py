"""Typed conversations through the real Live API: ordering several drinks of one item.

The team's cases for "which drink is an answer for" (docs/conversation-rules.md, section 4),
typed instead of spoken: much faster than scripts/voice_demo.py (about 45 s a case) and enough
to check the rules in kiosk/assistant/answers.py with the real model. Each case types the
customer's lines, each once the assistant has finished its reply, and compares the order at the
end.

    uv run python scripts/typed_check.py                 # every case
    uv run python scripts/typed_check.py six-only,line-no
    uv run python scripts/typed_check.py list

Needs GEMINI_API_KEY. Not a test: it talks to Google and its answers vary (a FAIL is worth a
look in logs/typed_check.log, not always a bug).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kiosk.assistant.live import GeminiConnector  # noqa: E402
from kiosk.assistant.safety import Speaker  # noqa: E402
from kiosk.assistant.session import (  # noqa: E402
    AssistantSession,
    AssistantState,
    SessionListener,
)
from kiosk.config import REPO_ROOT, load_config, load_env_file  # noqa: E402
from kiosk.domain.flow import Kiosk  # noqa: E402
from kiosk.domain.loader import load_cafe, load_menu  # noqa: E402

REPLY_TIMEOUT_S = 20.0  # longest wait for the assistant to finish a reply
SETTLE_S = 0.8  # after it went quiet (another sentence may follow at once)

ICED_AND_HOT = "아이스 아메리카노 하나랑 핫 아메리카노 하나 주세요"

# name: (what it checks, the customer's lines, the order at the end as
# "temperature size extras": quantity; extras "-" for none)
CASES: dict[str, tuple[str, list[str], dict[str, int]]] = {
    "check-yes": (
        "an answer that may be for both: asked, 네",
        ["포장이요", ICED_AND_HOT, "레귤러요", "네", "없어요"],
        {"ice regular -": 1, "hot regular -": 1},
    ),
    "check-no": (
        "asked, 아니: the other size (라지가 아니면 레귤러)",
        ["포장이요", ICED_AND_HOT, "레귤러요", "아니요", "없어요"],
        {"ice regular -": 1, "hot large -": 1},
    ),
    "both": (
        '"둘 다": no question',
        ["포장이요", ICED_AND_HOT, "둘 다 레귤러요", "없어요"],
        {"ice regular -": 1, "hot regular -": 1},
    ),
    "each": (
        "a different answer for each drink",
        ["포장이요", ICED_AND_HOT, "아이스는 레귤러, 핫은 라지로 주세요", "없어요"],
        {"ice regular -": 1, "hot large -": 1},
    ),
    "one-go": (
        "everything in one sentence",
        ["포장이요", "아이스 아메리카노 레귤러 하나랑 핫 아메리카노 라지 하나 주세요", "없어요"],
        {"ice regular -": 1, "hot large -": 1},
    ),
    "six-only": (
        '"2개만 아이스로": the other four are hot; "다 레귤러로" for all',
        ["포장이요", "아메리카노 6잔", "2개만 아이스로", "다 레귤러로", "없어요"],
        {"ice regular -": 2, "hot regular -": 4},
    ),
    "one-large": (
        '"하나만 라지로" of two: the other is regular',
        ["포장이요", "따뜻한 아메리카노 두 잔이요", "하나만 라지로 해줘", "없어요"],
        {"hot large -": 1, "hot regular -": 1},
    ),
    "one-shot": (
        '"하나만 샷 추가" of three',
        ["포장이요", "따뜻한 아메리카노 레귤러 세 잔", "하나만 샷 추가해줘", "없어"],
        {"hot regular extra_shot": 1, "hot regular -": 2},
    ),
    "shot-corrected": (
        "a shot for all three, then only one of them",
        [
            "포장이요",
            "따뜻한 아메리카노 레귤러 세 잔",
            "샷 추가",
            "아니 그중에 하나만 샷 추가해줘",
            "그것 말곤 없어",
        ],
        {"hot regular extra_shot": 1, "hot regular -": 2},
    ),
    "line-yes": (
        "an extra for the one already in the order: asked, 응",
        ["매장이요", ICED_AND_HOT, "둘 다 레귤러요", "샷추가 해줘", "응", "없어요"],
        {"ice regular extra_shot": 1, "hot regular extra_shot": 1},
    ),
    "line-no": (
        "an extra for the one already in the order: asked, 아니",
        ["매장이요", ICED_AND_HOT, "둘 다 레귤러요", "샷추가 해줘", "아니", "없어요"],
        {"ice regular extra_shot": 1, "hot regular -": 1},
    ),
    "extras-wait": (
        "the extras question waits for the answer",
        ["포장이요", "따뜻한 아메리카노 레귤러 하나요", "샷 추가요", "없어요"],
        {"hot regular extra_shot": 1},
    ),
    "extras-upfront": (
        '"추가는 없어요" said before the question',
        ["포장이요", "따뜻한 아메리카노 레귤러로 하나, 추가는 없어요"],
        {"hot regular -": 1},
    ),
}


class Quiet(SessionListener):
    """Prints what the assistant says and counts its replies."""

    def __init__(self) -> None:
        self.replies = 0

    def on_subtitle(self, speaker: Speaker, text: str, final: bool) -> None:
        if final and speaker == "assistant" and text.strip():
            self.replies += 1
            print(f"      kiosk: {text.strip()}")


async def replied(session: AssistantSession, listener: Quiet, before: int) -> None:
    """Until the assistant said something new and is listening again (or a timeout)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + REPLY_TIMEOUT_S
    while loop.time() < deadline:
        if listener.replies > before and session.state is AssistantState.LISTENING:
            await asyncio.sleep(SETTLE_S)
            if session.state is AssistantState.LISTENING:
                return
        await asyncio.sleep(0.1)


def order_of(kiosk: Kiosk) -> dict[str, int]:
    """The order as "temperature size extras": quantity (drinks still being chosen count too)."""
    found: Counter[str] = Counter()
    drinks = [(line.chosen(), line.quantity) for line in kiosk.order.lines]
    drinks += [(d.chosen, d.quantity) for d in kiosk.drafts]
    for chosen, quantity in drinks:
        temperature = chosen.get("temperature", ())
        size = chosen.get("size", ())
        extras = [c.id for g, cs in chosen.items() if g not in ("temperature", "size") for c in cs]
        extras = [e for e in extras if e != "none"]
        key = " ".join(
            [
                temperature[0].id if temperature else "?",
                size[0].id if size else "?",
                "+".join(sorted(extras)) or "-",
            ]
        )
        found[key] += quantity
    return dict(found)


async def run_case(name: str, lines: list[str], expected: dict[str, int]) -> bool:
    config = load_config()
    kiosk = Kiosk(
        load_menu(config.data_dir / "menu.yaml"), load_cafe(config.data_dir / "cafe.yaml")
    )
    connector = GeminiConnector(config.live, os.environ[config.live.api_key_env])
    listener = Quiet()
    session = AssistantSession(kiosk, connector, config.flow, listener)
    if not await session.start():
        print("    could not connect")
        return False
    try:
        await replied(session, listener, 0)  # the greeting
        for text in lines:
            print(f"    > {text}")
            before = listener.replies
            await session.send_text(text)
            await replied(session, listener, before)
        got = order_of(kiosk)  # before hanging up, which clears the order
        choosing = bool(kiosk.drafts)
    finally:
        await session.stop()
    ok = got == expected and not choosing
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(
            f"    expected {expected}\n    got      {got}"
            + ("  (still choosing)" if choosing else "")
        )
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "cases", nargs="?", default="all", help="'all', names separated by commas, or 'list'"
    )
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.cases == "list":
        for name, (what, _, _) in CASES.items():
            print(f"  {name:15} {what}")
        return 0
    names = list(CASES) if args.cases == "all" else args.cases.split(",")
    unknown = [n for n in names if n not in CASES]
    if unknown:
        print(f"unknown: {', '.join(unknown)} (see 'list')")
        return 2
    load_env_file()
    log_file = REPO_ROOT / "logs" / "typed_check.log"
    log_file.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, mode="w", encoding="utf-8")],
    )
    for noisy in ("httpx", "websockets", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    print(f"  log: {log_file}")
    results = {}
    for name in names:
        what, lines, expected = CASES[name]
        print(f"=== {name}: {what}")
        results[name] = asyncio.run(run_case(name, lines, expected))
    print("=== cases")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"  {sum(results.values())}/{len(results)} cases passed")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
