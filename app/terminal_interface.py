"""terminal_interface.py -- MOON's OWN terminal interface (additive).

A self-contained local terminal UI for MOON: a centered animated avatar +
chat + cognition panels, served over HTTP, with a WebSocket that streams MOON's
real brain output. Uses the existing Orchestrator (no modification of MOON core).

Run:  python main.py terminal     (serves http://127.0.0.1:8777)
Or:    uvicorn app.terminal_interface:app --port 8777

The frontend (web/moon_terminal.html) is served at GET / and connects to /ws.
An animated avatar is rendered from web/avatar.svg (or web/avatar.gif if you
drop one in). MOON's brain is the orchestrator already built in this project.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
TERMINAL_HTML = WEB_DIR / "moon_terminal.html"
AVATAR_SVG = WEB_DIR / "avatar.svg"
AVATAR_GIF = WEB_DIR / "avatar.gif"

app = FastAPI(title="MOON Terminal")

# ---- shared orchestrator (lazy, one per process) ----
_ORCH = None
_ORCH_LOCK = asyncio.Lock()


async def _get_orchestrator():
    global _ORCH
    if _ORCH is not None:
        return _ORCH
    async with _ORCH_LOCK:
        if _ORCH is None:
            from app.brain.orchestrator import Orchestrator
            from app.config.settings import get_settings
            from app.config.env_guard import decontaminate_pythonpath
            decontaminate_pythonpath()
            o = Orchestrator(get_settings())
            await o.setup()
            _ORCH = o
        return _ORCH


def _stream_text(text: str):
    """Yield words for a live typing effect (real content, not simulated)."""
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.02)


@app.get("/")
async def terminal_page() -> HTMLResponse:
    if TERMINAL_HTML.exists():
        return HTMLResponse(TERMINAL_HTML.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>MOON Terminal</h1><p>moon_terminal.html missing.</p>")


@app.get("/avatar.svg")
async def avatar_svg():
    if AVATAR_SVG.exists():
        return FileResponse(str(AVATAR_SVG), media_type="image/svg+xml")
    return HTMLResponse("<svg/>", status_code=404)


@app.get("/avatar.gif")
async def avatar_gif():
    if AVATAR_GIF.exists():
        return FileResponse(str(AVATAR_GIF), media_type="image/gif")
    # fallback to svg if no gif provided
    if AVATAR_SVG.exists():
        return FileResponse(str(AVATAR_SVG), media_type="image/svg+xml")
    return HTMLResponse("<svg/>", status_code=404)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        await ws.send_json({"type": "ready", "message": "MOON terminal connected."})
        orch = await _get_orchestrator()
        while True:
            data = await ws.receive_json()
            action = data.get("action")
            if action == "send_message":
                text = data.get("text", "").strip()
                if not text:
                    continue
                await ws.send_json({"type": "assistant_start"})
                # unlock phrase handling is inside the orchestrator/lock already
                from app.models.task import Task
                task = Task.create(text, agent_name="auto")
                t0 = time.time()
                try:
                    result_task = await orch.run_task(task)
                    answer = result_task.result or "(no response)"
                except Exception as e:  # noqa: BLE001
                    answer = f"[MOON error: {e}]"
                # stream the real answer word-by-word
                for chunk in _stream_text(answer):
                    await ws.send_json({"type": "assistant_chunk", "content": chunk})
                await ws.send_json({
                    "type": "assistant_done",
                    "elapsed": round(time.time() - t0, 2),
                })
            elif action == "get_history":
                await ws.send_json({"type": "history", "messages": []})
            else:
                await ws.send_json({"type": "unknown", "action": action})
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        try:
            await ws.close()
        except Exception:
            pass
