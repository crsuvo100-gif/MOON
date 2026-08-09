"""REST + WebSocket routes for MOON."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.config.logging import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)
routes_router = APIRouter()

_ORCH = None  # populated on startup


def get_orchestrator():
    """Return the orchestrator created at startup (assumes setup completed)."""
    global _ORCH
    if _ORCH is None:
        # Defensive: build + setup synchronously is not possible inside a loop,
        # but startup always runs first, so this should not happen in practice.
        from app.brain.orchestrator import Orchestrator

        _ORCH = Orchestrator(get_settings())
    return _ORCH


@routes_router.on_event("startup")
async def _startup() -> None:
    global _ORCH
    from app.brain.orchestrator import Orchestrator

    _ORCH = Orchestrator(get_settings())
    await _ORCH.setup()
    logger.info("API startup complete")


@routes_router.get("/stats")
async def stats() -> JSONResponse:
    o = get_orchestrator()
    return JSONResponse(
        {
            "model": get_settings().model_name,
            "agents": len(o._agents),
            "memory": "durable" if o._memory else "none",
        }
    )


@routes_router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    o = get_orchestrator()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
                text = data.get("text", "")
            except Exception:
                text = raw
            notice = o._lock.observe(text)
            if notice is not None:
                await ws.send_json({"type": "text", "text": notice})
                await ws.send_json({"type": "done"})
                continue
            await ws.send_json({"type": "step", "label": "thinking"})
            reply = await o.quick_reply(text)
            await ws.send_json({"type": "step", "label": "speaking"})
            await ws.send_json({"type": "text", "text": reply})
            try:
                from app.voice import Voice

                v = Voice()
                audio = await v.speak(reply)
                if audio:
                    await ws.send_json({"type": "audio", "audio": audio, "format": "wav"})
            except Exception as exc:  # noqa: BLE001
                logger.debug("voice skipped: %s", exc)
            await ws.send_json({"type": "done"})
    except WebSocketDisconnect:
        logger.info("ws disconnected")
    except Exception as exc:  # noqa: BLE001
        logger.warning("ws error: %s", exc)
        try:
            await ws.send_json({"type": "done"})
        except Exception:
            pass
