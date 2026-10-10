"""Run the kiosk: `uv run python -m kiosk`, then open the display (http://127.0.0.1:8765).

`--open` opens the display in its own Edge window once the server is ready, `--kiosk` full
screen (the launchers `Start Kiosk.bat` and `Start Kiosk (full screen).bat` use them).
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from kiosk.assistant.live import GeminiConnector, LiveConnector, check_api_key
from kiosk.config import CONFIG_DIR, REPO_ROOT, Config, load_config, load_env_file, save_env_value
from kiosk.domain.flow import Kiosk
from kiosk.domain.loader import load_cafe, load_menu
from kiosk.server.app import create_app
from kiosk.server.controller import ApiKeys, KioskController, MissingKeyConnector
from kiosk.server.hub import Hub
from kiosk.server.settings import DisplaySettings
from kiosk.voice.handset import Handset
from kiosk.voice.hook import SimulatedHook

LOG_DIR = REPO_ROOT / "logs"
EDGE_PATHS = [
    Path(os.environ.get(var, "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    for var in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")
    if os.environ.get(var)
]


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
    parser.add_argument("--open", action="store_true", help="open the display in an Edge window")
    parser.add_argument("--kiosk", action="store_true", help="open the display full screen")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    setup_logging()
    load_env_file()
    config = load_config()
    menu = load_menu(config.data_dir / "menu.yaml")
    cafe = load_cafe(config.data_dir / "cafe.yaml")

    host = args.host or config.server.host
    port = args.port or config.server.port
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}"
    if is_running(host, port):
        print(f"The kiosk is already running: {url}")
        if args.open or args.kiosk:
            open_display(url, args.kiosk)
        return 0

    key = os.environ.get(config.live.api_key_env, "").strip()
    connector: LiveConnector
    if key:
        connector = GeminiConnector(config.live, key)
    else:
        print("No Gemini API key yet: the display asks for one.")
        connector = MissingKeyConnector(config.live.api_key_env)
    keys = ApiKeys(
        check=lambda k: check_api_key(config.live, k),
        save=lambda k: save_env_value(config.live.api_key_env, k),
        connector=lambda k: GeminiConnector(config.live, k),
    )

    controller = KioskController(
        Kiosk(menu, cafe, config.flow.first_order_number),
        connector,
        config.flow,
        Hub(),
        SimulatedHook(),
        config.data_dir / "images",
        keys=keys,
        avatar_dir=config.data_dir / "avatar",
        settings=DisplaySettings(CONFIG_DIR / "display.local.json"),
    )
    handset = open_handset(config, controller) if config.audio.enabled else None
    app = create_app(
        controller,
        REPO_ROOT / "frontend" / "dist",
        config.data_dir / "images",
        config.data_dir / "avatar",
    )
    print(f"Kiosk running: open {url}  (F2: developer panel, Space: handset)")
    print("Close this window (or press Ctrl+C) to stop the kiosk.")
    if args.open or args.kiosk:
        threading.Thread(
            target=open_when_ready, args=(host, port, url, args.kiosk), daemon=True
        ).start()
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        if handset is not None:
            handset.close()
    return 0


def is_running(host: str, port: int) -> bool:
    """Something already answers on the kiosk's port (e.g. the kiosk started twice)."""
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1" if host in ("0.0.0.0", "::") else host, port)) == 0


def open_when_ready(host: str, port: int, url: str, full_screen: bool) -> None:
    for _ in range(100):
        if is_running(host, port):
            open_display(url, full_screen)
            return
        time.sleep(0.1)


def open_display(url: str, full_screen: bool) -> None:
    """The display in Edge: its own window, or full screen (kiosk mode, Alt+F4 closes it)."""
    edge = shutil.which("msedge") or next((str(p) for p in EDGE_PATHS if p.exists()), None)
    if edge is None:
        webbrowser.open(url)
        return
    if full_screen:
        # A separate profile, so kiosk mode works even while Edge is already open.
        profile = Path(os.environ.get("LOCALAPPDATA", LOG_DIR)) / "voice-kiosk" / "edge"
        args = [f"--kiosk={url}", "--edge-kiosk-type=fullscreen", f"--user-data-dir={profile}"]
    else:
        args = [f"--app={url}", "--window-size=640,1080"]
    subprocess.Popen([edge, *args, "--no-first-run"])


def open_handset(config: Config, controller: KioskController) -> Handset | None:
    """The handset's microphone and earpiece; without them the kiosk works with typed input."""
    handset = Handset(config.audio, on_frame=controller.microphone_frame)
    try:
        handset.open()
    except Exception as e:
        print(f"Warning: no audio ({e}); typed input only. See audio in configs/settings.yaml.")
        return None
    controller.audio_out = handset.speaker.write
    controller.audio_stop = handset.speaker.clear
    controller.levels = handset.levels
    print(f"Microphone: {handset.microphone.name}")
    print(f"Earpiece:   {handset.speaker.name}")
    return handset


if __name__ == "__main__":
    sys.exit(main())
