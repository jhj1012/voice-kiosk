"""Write frontend/src/dev/demo.json: fake event timelines for the display's demo mode.

The scenarios drive a real `Kiosk` and record the same events the server sends (built by
kiosk.server.events), so the display is developed against the real format:

    uv run python scripts/make_demo_events.py

Open the display with ?demo=order or ?demo=allergy (see docs/setup.md). Run this again after
changing the menu data or the event format.
"""

from __future__ import annotations

import json
import random
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from kiosk.config import DATA_DIR, REPO_ROOT
from kiosk.domain.flow import Kiosk
from kiosk.domain.loader import load_cafe, load_menu
from kiosk.domain.order import Dining
from kiosk.server.events import (
    Subtitles,
    image_urls,
    init_event,
    level_event,
    notice_event,
    state_event,
)

OUT = REPO_ROOT / "frontend" / "src" / "dev" / "demo.json"
LEVEL_EVERY_MS = 100


class Recorder:
    """Builds a timeline: [time in ms, event] pairs."""

    def __init__(self, kiosk: Kiosk, seed: int = 1) -> None:
        self.kiosk = kiosk
        self.t = 0
        self.events: list[list[Any]] = []
        self.seq = 0
        self.assistant = "idle"
        self.subtitles = Subtitles()
        self.random = random.Random(seed)

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append([self.t, event])

    def wait(self, ms: int) -> None:
        self.t += ms

    def state(self, assistant: str | None = None) -> None:
        if assistant is not None:
            self.assistant = assistant
        self.seq += 1
        self.emit(state_event(self.kiosk, self.assistant, self.seq))

    def do(self, action: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        action(*args, **kwargs)
        self.state()

    def customer(self, text: str, think_ms: int = 700) -> None:
        """The customer speaks: listening with mic levels, the transcript grows, then thinking."""
        self.state("listening")
        self.wait(300)
        self._speak("customer", text, ms_per_char=85, level="mic")
        self.state("thinking")
        self.wait(think_ms)

    def says(self, text: str, cut_after: float | None = None) -> None:
        """The assistant speaks; `cut_after` (0..1) interrupts it part way."""
        self.state("speaking")
        spoken = text if cut_after is None else text[: int(len(text) * cut_after)]
        self._speak("assistant", spoken, ms_per_char=95, level="out", final=cut_after is None)
        if cut_after is not None:
            self.emit(self.subtitles.event("assistant", spoken + "…", True))
        self.state("listening")
        self.wait(500)

    def _speak(self, speaker: str, text: str, ms_per_char: int, level: str, final=True) -> None:
        words = text.split(" ")
        shown = ""
        for i, word in enumerate(words):
            shown = f"{shown} {word}".strip()
            last = i == len(words) - 1
            duration = (len(word) + 1) * ms_per_char
            for _ in range(max(1, duration // LEVEL_EVERY_MS)):
                loud = self.random.uniform(0.35, 0.9)
                self.emit(level_event(loud if level == "mic" else 0, loud if level == "out" else 0))
                self.wait(LEVEL_EVERY_MS)
            self.emit(self.subtitles.event(speaker, shown, final and last))
        self.emit(level_event(0, 0))


def scenario_order(r: Recorder) -> None:
    k = r.kiosk
    r.state("idle")
    r.wait(2500)
    k.start_session()
    r.state("connecting")
    r.wait(700)
    r.state("thinking")
    r.wait(600)
    r.says("안녕하세요, 소리 카페입니다. 무엇을 드릴까요?")
    r.customer("메뉴 뭐 있어요?")
    recommended = [i.id for i in k.menu.items if i.recommended]
    r.do(k.show_menu, title="추천 메뉴", highlight_ids=recommended)
    r.says("아메리카노와 카페라떼, 아인슈페너를 추천해 드려요. 다른 메뉴도 화면에 있어요.")
    r.customer("아이스 아메리카노 라지로 두 잔 주세요")
    r.do(k.choose_item, "americano", 2, {"temperature": "ice", "size": "large"})
    r.says("아이스 아메리카노 라지 두 잔 담았어요. 더 필요하신 거 있으세요?")
    r.customer("카페라떼도 하나 주세요")
    r.do(k.choose_item, "cafe_latte")
    r.says("카페라떼는 따뜻하게 드릴까요, 아이스로 드릴까요?")
    r.customer("따뜻한 걸로요")
    r.do(k.set_options, {"temperature": "hot"})
    r.says("사이즈는 레귤러와 라지가 있어요.")
    r.customer("레귤러요")
    r.do(k.set_options, {"size": "regular"})
    r.says("따뜻한 카페라떼 레귤러 한 잔 담았어요. 더 필요하신 거 있으세요?")
    r.customer("아니요, 그게 다예요")
    r.says("매장에서 드시고 가세요, 포장하세요?")
    r.customer("포장이요")
    r.do(k.set_dining, Dining.TO_GO)
    read_back = k.review()
    r.state()
    r.says(f"{read_back} 카드를 단말기에 꽂아 주세요.")
    r.do(k.start_payment)
    r.wait(3000)
    r.do(k.advance_payment)
    r.wait(2000)
    r.do(k.advance_payment)
    r.wait(600)
    r.says(
        f"결제가 완료되었어요. 주문 번호는 {k.order_number}번이에요. 번호가 불리면 오른쪽 "
        "픽업대에서 받아 가세요. 수화기를 내려놓으셔도 돼요."
    )
    r.wait(4000)
    k.end_session()
    r.state("idle")
    r.wait(3000)


def scenario_allergy(r: Recorder) -> None:
    k = r.kiosk
    r.state("idle")
    r.wait(1500)
    k.start_session()
    r.state("connecting")
    r.wait(600)
    r.says("안녕하세요, 소리 카페입니다. 무엇을 드릴까요?")
    r.customer("우유 알레르기가 있는데 마실 만한 거 있어요?")
    r.do(
        k.show_menu,
        title="우유가 들어가지 않은 메뉴",
        exclude_allergens=["milk"],
        highlight_ids=["americano", "green_grape_ade"],
    )
    r.says(
        "아메리카노, 콜드브루, 청포도 에이드를 드실 수 있어요. 알레르기 정보는 참고용이니 "
        "심하시면 직원에게 꼭 확인해 주세요."
    )
    r.customer("청포도 에이드는 많이 달아요?")
    r.do(k.show_item, "green_grape_ade")
    r.says("네, 청포도 청이 들어가서 달콤하고 상큼한 편이에요. 카페인은 없어요.", cut_after=0.55)
    r.customer("그럼 와이파이 비밀번호는요?")
    r.do(k.show_info, "wifi")
    r.says("와이파이 이름은 SORI_CAFE, 비밀번호는 sori1234예요.")
    r.emit(notice_event("warn", "연결을 다시 시도하고 있어요"))
    r.wait(2200)
    r.emit(notice_event("info", ""))
    r.customer("청포도 에이드 라지로 하나 주세요")
    r.do(k.choose_item, "green_grape_ade", 1, {"size": "large"})
    r.says("청포도 에이드 라지 한 잔 담았어요. 더 필요하신 거 있으세요?")
    r.customer("아 잠깐만요, 일행한테 물어볼게요")
    r.says("네, 천천히 말씀해 주세요.")
    r.wait(1500)
    k.end_session()  # the customer hung up
    r.state("idle")
    r.wait(3000)


SCENARIOS: dict[str, tuple[str, Callable[[Recorder], None]]] = {
    "order": ("주문부터 결제까지", scenario_order),
    "allergy": ("알레르기 질문, 정보, 끼어들기, 연결 알림", scenario_allergy),
}


def build() -> dict[str, Any]:
    menu = load_menu(DATA_DIR / "menu.yaml")
    cafe = load_cafe(DATA_DIR / "cafe.yaml")
    scenarios = {}
    for name, (title, run) in SCENARIOS.items():
        recorder = Recorder(Kiosk(menu, cafe))
        run(recorder)
        scenarios[name] = {"title": title, "duration": recorder.t, "events": recorder.events}
    return {
        "init": init_event(menu, cafe, image_urls(menu, DATA_DIR / "images")),
        "scenarios": scenarios,
    }


def main() -> int:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(text + "\n", encoding="utf-8")
    for name, scenario in data["scenarios"].items():
        print(f"{name}: {len(scenario['events'])} events, {scenario['duration'] / 1000:.0f} s")
    print(f"wrote {Path(OUT).relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
