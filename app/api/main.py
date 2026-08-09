"""FastAPI app entrypoint -- single UI (Neural Brain Command Center)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.galaxy import galaxy_router
from app.api.routes import routes_router
from app.config.logging import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)
WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"
UI_FILE = WEB_DIR / "moon_brain.html"
GALAXY_FILE = WEB_DIR / "galaxy.html"

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")

app.include_router(routes_router)
app.include_router(galaxy_router)
app.mount("/static", StaticFiles(directory=str(WEB_DIR), html=False), name="static")


@app.get("/")
@app.get("/orb")  # legacy alias -> the single Command Center UI
@app.get("/brain")
async def brain_ui() -> FileResponse:
    return FileResponse(str(UI_FILE))

@app.get("/galaxy")
async def galaxy_ui() -> FileResponse:
    return FileResponse(str(GALAXY_FILE))


@app.get("/health")
async def health() -> JSONResponse:
    from app.api.routes import _ORCH

    return JSONResponse(
        {
            "status": "ok",
            "model": settings.model_name,
            "agents": len(_ORCH._agents) if _ORCH else 0,
        }
    )
