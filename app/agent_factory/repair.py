"""Agent Factory: Repair component (spec 29 / agent_factory/repair.py).

Re-exports the RepairAgent implemented in ``reviewer.py`` so the spec's
component layout is satisfied without duplicating logic.
"""

from __future__ import annotations

from app.agent_factory.reviewer import RepairAgent  # noqa: F401

__all__ = ["RepairAgent"]
