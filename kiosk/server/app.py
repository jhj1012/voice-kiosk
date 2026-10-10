"""The web server: the display's WebSocket, the built display, the menu images and the API key
form (`POST /api/key`, accepted only from this computer)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from kiosk.server.controller import KioskController
from kiosk.server.events import Event

log = logging.getLogger(__name__)

LOCAL_CLIENTS = {"127.0.0.1", "::1", "localhost"}

NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>Voice Kiosk</title>
<p style="font-family:sans-serif">The display is not built yet. Run
<code>npm --prefix frontend run build</code> and reload, or use the development server
(<code>npm --prefix frontend run dev</code>, then open http://localhost:5173).</p>"""


def create_app(
    controller: KioskController, dist_dir: Path, images_dir: Path, avatar_dir: Path | None = None
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
        try:
            for event in controller.init_events():
                await queue.put(event)
            while True:
                await controller.handle_client(await socket.receive_json())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            sender.cancel()
            controller.hub.disconnect(queue)
            log.info("display disconnected")

    @app.post("/api/key")
    async def api_key(request: Request) -> JSONResponse:
        """The API key typed on the display. Only this computer may set it; the answer never
        contains the key."""
        if request.client is None or request.client.host not in LOCAL_CLIENTS:
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


async def _send_all(socket: WebSocket, queue: asyncio.Queue[Event]) -> None:
    with contextlib.suppress(Exception):  # the display went away
        while True:
            await socket.send_json(await queue.get())
