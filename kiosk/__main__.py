"""Run the kiosk: `uv run python -m kiosk`, then open the display (http://127.0.0.1:8765)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

import uvicorn

from kiosk.assistant.live import GeminiConnector, LiveConnector
from kiosk.config import REPO_ROOT, load_config, load_env_file
from kiosk.domain.flow import Kiosk
from kiosk.domain.loader import load_cafe, load_menu
from kiosk.server.app import create_app
from kiosk.server.controller import KioskController, MissingKeyConnector
from kiosk.server.hub import Hub
from kiosk.voice.hook import SimulatedHook

LOG_DIR = REPO_ROOT / "logs"


def setup_logging() -> None:
    """Conversation and function calls go to logs/ (git-ignored, text only); warnings to the
    console."""
    LOG_DIR.mkdir(exist_ok=True)
    file = logging.FileHandler(LOG_DIR / f"kiosk-{time.strftime('%Y%m%d')}.log", encoding="utf-8")
    file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    logging.basicConfig(level=logging.INFO, handlers=[file, console])
    for noisy in ("httpx", "websockets", "google_genai", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="default: server.host in configs/settings.yaml")
    parser.add_argument("--port", type=int, help="default: server.port in configs/settings.yaml")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    setup_logging()
    load_env_file()
    config = load_config()
    menu = load_menu(config.data_dir / "menu.yaml")
    cafe = load_cafe(config.data_dir / "cafe.yaml")

    key = os.environ.get(config.live.api_key_env, "").strip()
    connector: LiveConnector
    if key:
        connector = GeminiConnector(config.live, key)
    else:
        print(f"Warning: {config.live.api_key_env} is not set; conversations will not start.")
        connector = MissingKeyConnector(config.live.api_key_env)

    controller = KioskController(
        Kiosk(menu, cafe, config.flow.first_order_number),
        connector,
        config.flow,
        Hub(),
        SimulatedHook(),
        config.data_dir / "images",
    )
    app = create_app(controller, REPO_ROOT / "frontend" / "dist", config.data_dir / "images")
    host = args.host or config.server.host
    port = args.port or config.server.port
    print(f"Kiosk running: open http://{host}:{port}  (F2: developer panel, Space: handset)")
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
