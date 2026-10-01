"""Planner (spec sections 11, 6: orchestrator/planner.py).

MOON's orchestrator already builds dependency-aware execution via the planner
module. This compatibility module re-exports the real planner so it is reachable
at the spec path. If the runtime planner is unavailable it degrades cleanly.
"""

from __future__ import annotations

try:
    from app.brain.planner import Planner  # type: ignore
except Exception:  # noqa: BLE001
    Planner = None  # pragma: no cover - optional in this layout

__all__ = ["Planner"]
