"""The web server with FastAPI's test client (no real network, no browser)."""

from __future__ import annotations

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from kiosk.assistant.instructions import GREETING_CUE
from kiosk.assistant.live import AudioOut, Interrupted, OutputText, TurnComplete
from kiosk.config import AudioConfig, FlowConfig
from kiosk.domain.flow import Kiosk
from kiosk.server.app import create_app
from kiosk.server.controller import KioskController
from kiosk.server.hub import Hub
from kiosk.voice.hook import SimulatedHook
from kiosk.voice.phone import PhoneHandset
from tests.fakes import FakeConnector


def make(menu, cafe, tmp_path, dist=True, phone=False):
    dist_dir = tmp_path / "dist"
    images = tmp_path / "images"
    images.mkdir()
    (images / "americano.png").write_bytes(b"png")
    if dist:
        dist_dir.mkdir()
        (dist_dir / "index.html").write_text("<p>display</p>", encoding="utf-8")
    connector = FakeConnector()
    controller = KioskController(
        Kiosk(menu, cafe), connector, FlowConfig(), Hub(), SimulatedHook(), images
    )
    handset = None
    if phone:  # as `python -m kiosk --phone` wires it
        handset = PhoneHandset(AudioConfig(), controller.microphone_frame)
        controller.audio_out, controller.audio_stop = handset.write, handset.clear
        controller.levels = handset.levels
    return create_app(controller, dist_dir, images, phone=handset), connector


def until(socket, kind: str, **match):
    while True:
        event = socket.receive_json()
        if event["type"] == kind and all(event.get(k) == v for k, v in match.items()):
            return event


def test_display_files_and_images(menu, cafe, tmp_path):
    app, _ = make(menu, cafe, tmp_path)
    with TestClient(app) as client:
        assert "display" in client.get("/").text
        assert client.get("/images/americano.png").content == b"png"
        assert client.get("/images/nope.png").status_code == 404


def test_unbuilt_display_explains_what_to_do(menu, cafe, tmp_path):
    app, _ = make(menu, cafe, tmp_path, dist=False)
    with TestClient(app) as client:
        assert "npm --prefix frontend run build" in client.get("/").text


def test_websocket_init_hook_text_and_events(menu, cafe, tmp_path):
    app, connector = make(menu, cafe, tmp_path)
    with TestClient(app) as client, client.websocket_connect("/ws") as socket:
        init = socket.receive_json()
        assert init["type"] == "init"
        assert init["menu"]["items"][1]["image_url"].startswith("/images/americano.png")
        assert socket.receive_json() == {"type": "settings", "values": {}}
        assert socket.receive_json() == {"type": "setup", "api_key": "ok"}
        assert socket.receive_json()["phase"] == "idle"

        socket.send_json({"type": "hook", "off_hook": True})
        until(socket, "state", phase="ordering")
        socket.send_json({"type": "dev_text", "text": "메뉴 뭐 있어요?"})
        until(socket, "subtitle", speaker="customer", text="메뉴 뭐 있어요?")
        assert connector.conn.texts == [GREETING_CUE, "메뉴 뭐 있어요?"]

        client.portal.call(connector.conn.push, OutputText("추천 메뉴예요"), TurnComplete())
        until(socket, "subtitle", speaker="assistant", text="추천 메뉴예요", final=True)

        socket.send_json({"type": "hook", "off_hook": False})
        until(socket, "state", phase="idle")
        assert connector.conn.closed


def test_api_key_form_only_from_this_computer(menu, cafe, tmp_path):
    app, _ = make(menu, cafe, tmp_path)
    with TestClient(app, client=("192.168.0.7", 5000)) as client:
        response = client.post("/api/key", json={"key": "AIza" + "x" * 35})
        assert response.status_code == 403


def test_api_key_form(menu, cafe, tmp_path):
    app, _ = make(menu, cafe, tmp_path)
    with TestClient(app, client=("127.0.0.1", 5000)) as client:
        assert client.post("/api/key", json={"nope": 1}).status_code == 400
        # No key handling configured in this app: nothing is checked or saved.
        assert client.post("/api/key", json={"key": "x"}).json() == {"result": "unavailable"}


def test_avatar_files_are_served_with_their_types(menu, cafe, tmp_path):
    avatar = tmp_path / "avatar"
    avatar.mkdir()
    (avatar / "idle.webm").write_bytes(b"webm")
    (avatar / "avatar.webp").write_bytes(b"webp")
    controller = KioskController(
        Kiosk(menu, cafe), FakeConnector(), FlowConfig(), Hub(), SimulatedHook(), tmp_path
    )
    app = create_app(controller, tmp_path / "dist", tmp_path, avatar)
    with TestClient(app) as client:
        assert client.get("/avatar/idle.webm").headers["content-type"] == "video/webm"
        assert client.get("/avatar/avatar.webp").headers["content-type"] == "image/webp"


PHONE = "wss://testserver"  # the phone's listener is HTTPS


def test_the_phone_is_told_it_is_the_phone(menu, cafe, tmp_path):
    app, _ = make(menu, cafe, tmp_path, phone=True)
    with TestClient(app) as client:
        with client.websocket_connect(f"{PHONE}/ws") as socket:
            assert socket.receive_json()["phone"] is True
        with client.websocket_connect("/ws") as socket:  # the laptop's own display
            assert socket.receive_json()["phone"] is False


def test_phone_audio_in_and_out(menu, cafe, tmp_path):
    app, connector = make(menu, cafe, tmp_path, phone=True)
    frame = b"\x10\x00" * 320
    with (
        TestClient(app) as client,
        client.websocket_connect(f"{PHONE}/ws") as display,
        client.websocket_connect(f"{PHONE}/ws/audio") as audio,
    ):
        display.send_json({"type": "hook", "off_hook": True})  # the tap
        until(display, "state", phase="ordering")
        audio.send_bytes(frame)
        audio.send_text('{"out": 0.5}')
        until(display, "level", out=0.5)
        assert frame in connector.conn.audio

        client.portal.call(connector.conn.push, AudioOut(b"\x01\x00" * 240))
        assert audio.receive_bytes() == b"\x01\x00" * 240
        client.portal.call(connector.conn.push, Interrupted())
        assert audio.receive_text() == "clear"


def test_phone_audio_only_in_phone_mode_and_over_https(menu, cafe, tmp_path):
    for phone, url in [(False, f"{PHONE}/ws/audio"), (True, "/ws/audio")]:
        folder = tmp_path / str(phone)
        folder.mkdir()
        app, _ = make(menu, cafe, folder, phone=phone)
        with TestClient(app) as client, pytest.raises(WebSocketDisconnect) as closed:
            client.websocket_connect(url).__enter__()
        assert closed.value.code == 1008


def test_the_api_key_cannot_be_set_over_the_phones_https(menu, cafe, tmp_path):
    app, _ = make(menu, cafe, tmp_path, phone=True)
    with TestClient(app, base_url="https://testserver", client=("127.0.0.1", 5000)) as client:
        assert client.post("/api/key", json={"key": "k" * 40}).status_code == 403
