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


async def _moon_status(orch) -> dict:
    """Real MOON status for the terminal HUD (no simulation)."""
    import os as _os
    try:
        n_agents = len(orch._agents)
    except Exception:
        n_agents = 0
    try:
        reg = getattr(orch._tools, "_registry", None)
        tools = list(reg.tool_names) if reg and hasattr(reg, "tool_names") else []
    except Exception:
        tools = []
    ltm_count = 0
    try:
        ltm = orch._memory._ltm if orch._memory else None
        if ltm is not None and hasattr(ltm, "path") and _os.path.exists(ltm.path):
            with open(ltm.path) as fh:
                ltm_count = sum(1 for _ in fh)
    except Exception:
        ltm_count = 0
    return {
        "version": "2.1.0",
        "model": orch._settings.model_name,
        "locked": orch._lock.locked,
        "agents": n_agents,
        "tools": tools,
        "n_tools": len(tools),
        "long_term_entries": ltm_count,
        "uptime": _os.path.exists("/proc/uptime") and open("/proc/uptime").read().split()[0] or "0",
    }


@app.get("/status")
async def status():
    orch = await _get_orchestrator()
    return await _moon_status(orch)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        await ws.send_json({"type": "ready", "message": "MOON terminal connected."})
        orch = await _get_orchestrator()

        async def stream_event(ev: dict):
            # surface MOON's real workflow through the avatar (her "body")
            try:
                await ws.send_json({"type": "workflow", "stage": ev.get("stage"), "detail": ev.get("detail", "")})
            except Exception:
                pass

        while True:
            data = await ws.receive_json()
            action = data.get("action")

            if action == "wake":
                # Wake word "Moon": avatar opens her eyes / enters listening state.
                # Wake does NOT unlock -- only "love you 3000 Moon" unlocks.
                await ws.send_json({"type": "wake", "message": "🌙 MOON is listening...", "locked": orch._lock.locked})
                continue

            if action == "send_message":
                text = data.get("text", "").strip()
                if not text:
                    continue
                # The unlock phrase "love you 3000 Moon" (case-insensitive) is
                # handled inside the orchestrator's lock -- it unlocks MOON herself.
                await ws.send_json({"type": "assistant_start"})
                if orch._lock.locked:
                    await ws.send_json({"type": "workflow", "stage": "locked", "detail": "awaiting unlock"})
                from app.models.task import Task
                task = Task.create(text, agent_name="auto")
                t0 = time.time()
                try:
                    result_task = await orch.run_task(task, on_event=stream_event)
                    answer = result_task.result or "(no response)"
                except Exception as e:  # noqa: BLE001
                    answer = f"[MOON error: {e}]"
                await ws.send_json({"type": "workflow", "stage": "speaking", "detail": "forming response"})
                for chunk in _stream_text(answer):
                    await ws.send_json({"type": "assistant_chunk", "content": chunk})
                await ws.send_json({
                    "type": "assistant_done",
                    "elapsed": round(time.time() - t0, 2),
                    "locked": orch._lock.locked,
                })
            elif action == "run":
                # Quick-action buttons: command preset routed through MOON's brain.
                cmd = (data.get("command") or "").strip()
                if not cmd:
                    continue
                await ws.send_json({"type": "assistant_start"})
                from app.models.task import Task
                task = Task.create(cmd, agent_name="auto")
                t0 = time.time()
                try:
                    result_task = await orch.run_task(task, on_event=stream_event)
                    answer = result_task.result or "(no response)"
                except Exception as e:  # noqa: BLE001
                    answer = f"[MOON error: {e}]"
                await ws.send_json({"type": "workflow", "stage": "speaking", "detail": "forming response"})
                for chunk in _stream_text(answer):
                    await ws.send_json({"type": "assistant_chunk", "content": chunk})
                await ws.send_json({"type": "assistant_done", "elapsed": round(time.time() - t0, 2), "locked": orch._lock.locked})
            elif action == "status":
                await ws.send_json({"type": "status", **(await _moon_status(orch))})
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
