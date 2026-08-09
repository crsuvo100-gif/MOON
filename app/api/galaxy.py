"""Galaxy websocket + REST for the knowledge-galaxy visualization."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.api.routes import get_orchestrator
from app.config.logging import get_logger

logger = get_logger(__name__)
galaxy_router = APIRouter()


@galaxy_router.get("/api/galaxy")
async def galaxy_data() -> JSONResponse:
    o = get_orchestrator()
    try:
        from app.knowledge.galaxy import GalaxyService

        gs = GalaxyService()
        # best-effort rebuild from the live tool registry
        registry = getattr(o._tools, "_registry", None)
        await gs.build(registry=registry)
        nodes = [{"id": n.id, "label": n.label, "kind": n.kind, "edges": n.edges} for n in gs.nodes()]
        return JSONResponse({"nodes": nodes})
    except Exception as exc:  # noqa: BLE001
        logger.warning("galaxy data failed: %s", exc)
        return JSONResponse({"nodes": []})


@galaxy_router.websocket("/ws/galaxy")
async def galaxy_ws(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            await ws.receive_text()
            o = get_orchestrator()
            nodes = []
            try:
                from app.knowledge.galaxy import GalaxyService

                gs = GalaxyService()
                await gs.build(getattr(o._tools, "_registry", None))
                nodes = [{"id": n.id, "label": n.label, "edges": n.edges} for n in gs.nodes()]
            except Exception:
                pass
            await ws.send_json({"type": "galaxy", "nodes": nodes})
    except WebSocketDisconnect:
        pass
