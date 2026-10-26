"""The web server: the display's WebSocket, the built display, the menu images and the API key
form (`POST /api/key`, accepted only from this computer).

In phone mode the same app is also served over HTTPS to the phone; a display connected that way
is told it is the phone, and its microphone and speaker use `/ws/audio`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import mimetypes
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from kiosk.server.controller import KioskController
from kiosk.server.events import Event
from kiosk.voice.phone import PhoneHandset, PhoneLink

log = logging.getLogger(__name__)

LOCAL_CLIENTS = {"127.0.0.1", "::1", "localhost"}

# Windows' own list may lack these (the avatar's clips and images).
for _type, _suffix in [("image/webp", ".webp"), ("video/webm", ".webm"), ("video/mp4", ".mp4")]:
    mimetypes.add_type(_type, _suffix)

NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>Voice Kiosk</title>
<p style="font-family:sans-serif">The display is not built yet. Run
<code>npm --prefix frontend run build</code> and reload, or use the development server
(<code>npm --prefix frontend run dev</code>, then open http://localhost:5173).</p>"""


def create_app(
    controller: KioskController,
    dist_dir: Path,
    images_dir: Path,
    avatar_dir: Path | None = None,
    phone: PhoneHandset | None = None,
) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        asyncio.get_running_loop().set_exception_handler(_ignore_connection_resets)
        await controller.start()
        yield
        await controller.close()  # hang up when the server stops

    app = FastAPI(title="voice-kiosk", lifespan=lifespan)

    @app.websocket("/ws")
    async def display(socket: WebSocket) -> None:
        await socket.accept()
        queue = controller.hub.connect()
        log.info("display connected (%d)", controller.hub.displays)
        sender = asyncio.create_task(_send_all(socket, queue))
        is_phone = phone is not None and socket.url.scheme == "wss"
        try:
            for event in controller.init_events(phone=is_phone):
                await queue.put(event)
            while True:
                await controller.handle_client(await socket.receive_json())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            sender.cancel()
            controller.hub.disconnect(queue)
            log.info("display disconnected")

    @app.websocket("/ws/audio")
    async def phone_audio(socket: WebSocket) -> None:
        """The phone's microphone and speaker (phone mode, over HTTPS only)."""
        if phone is None or socket.url.scheme != "wss":
            await socket.close(code=1008)
            return
        await socket.accept()
        link = phone.connect()
        sender = asyncio.create_task(_send_audio(socket, link))
        try:
            while True:
                message = await socket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                data = message.get("bytes")
                phone.receive(link, data if data is not None else message.get("text") or "")
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            phone.disconnect(link)
            sender.cancel()

    @app.post("/api/key")
    async def api_key(request: Request) -> JSONResponse:
        """The API key typed on the display. Only this computer's own display may set it (not
        the phone, not over the phone's HTTPS); the answer never contains the key."""
        local = request.client is not None and request.client.host in LOCAL_CLIENTS
        if not local or request.url.scheme == "https":
            return JSONResponse({"result": "forbidden"}, status_code=403)
        try:
            body = await request.json()
        except ValueError:
            body = None
        key = body.get("key") if isinstance(body, dict) else None
        if not isinstance(key, str):
            return JSONResponse({"result": "invalid"}, status_code=400)
        return JSONResponse({"result": await controller.set_api_key(key)})

    app.mount("/images", StaticFiles(directory=images_dir, check_dir=False), name="images")
    if avatar_dir is not None:
        app.mount("/avatar", StaticFiles(directory=avatar_dir, check_dir=False), name="avatar")
    if (dist_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="display")
    else:

        @app.get("/")
        async def not_built() -> HTMLResponse:
            return HTMLResponse(NOT_BUILT)

    return app


def _ignore_connection_resets(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    """On Windows a browser closing a tab logs a ConnectionResetError traceback from asyncio's
    proactor; it is harmless, so only that one is silenced."""
    if isinstance(context.get("exception"), ConnectionResetError):
        return
    loop.default_exception_handler(context)


async def _send_audio(socket: WebSocket, link: PhoneLink) -> None:
    with contextlib.suppress(Exception):  # the phone went away
        while (message := await link.next()) is not None:
            if isinstance(message, bytes):
                await socket.send_bytes(message)
            else:
                await socket.send_text(message)
        await socket.close()  # replaced by a newer phone


async def _send_all(socket: WebSocket, queue: asyncio.Queue[Event]) -> None:
    with contextlib.suppress(Exception):  # the display went away
        while True:
            await socket.send_json(await queue.get())
