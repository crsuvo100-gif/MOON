"""CYCLONE_TERMINAL_AI_V10 -- Cyclone REST router for MOON.

This module exposes the Cyclone API contract as a FastAPI router that mounts
into MOON's web backend.  Every Cyclone endpoint delegates the *thinking*
(LLM reply / voice) to MOON's ``Orchestrator.quick_reply`` so the two systems
run as one brain while the UI keeps Cyclone's terminal HUD surface.

Run standalone with the bundled Node server (``server.js``) or host through
MOON:  ``app/terminal_interface.py`` pulls the router in and mounts it at
``/cyclone`` (REST) plus the Cyclone UI under ``/cyclone/*``.  Browser
clients point ``apiBase`` at ``/cyclone/api`` (see cyclone/config.js).

No secrets.  Runtime state lives in ``.data/`` (JSON) next to this package.
"""

from __future__ import annotations

# Re-exports -------------------------------------------------------------
__all__ = ["get_cyclone_router", "get_cyclone_static_files",
           "set_orchestrator", "get_orchestrator", "CYCLONE_DIR"]

from .config import CYCLONE_DIR, REPO_ROOT, CYCLONE_ROOT
from .main import get_cyclone_router, get_cyclone_static_files
from .state import StateStore

__version__ = "3.0.0"

# Lazily-held MOON orchestrator reference (set by MOON at startup). ---------
_orchestrator = None


def set_orchestrator(orch) -> None:
    global _orchestrator
    _orchestrator = orch


def get_orchestrator():
    """Return the MOON Orchestrator (MOON must already be running)."""
    if _orchestrator is None:
        try:
            from app.terminal_interface import _get_orchestrator as _g
            return _g()
        except Exception:
            return None
    return _orchestrator
