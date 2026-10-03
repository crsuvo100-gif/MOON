"""MOON Orchestrator package (spec section 6: orchestrator/).

This is a COMPATIBILITY LAYER. The real orchestrator lives at
``app.brain.orchestrator.Orchestrator`` and the runtime analysis modules live in
``app.runtime``. This package re-exports them at the spec-mandated path so the
directory structure (section 6) is satisfied WITHOUT duplicating or replacing
the working implementation. Each spec-named module also re-exports the real
runtime component.
"""

from __future__ import annotations

# The real Master Orchestrator (spec 9) -- single source of truth.
from app.brain.orchestrator import Orchestrator

# Real runtime components, surfaced at spec paths.
from app.runtime.task_analyzer import TaskAnalyzer, GoalSpec
from app.runtime.goal_manager import GoalManager, Goal
from app.runtime.agent_router import AgentRouter

__all__ = ["Orchestrator", "TaskAnalyzer", "GoalSpec", "GoalManager", "Goal", "AgentRouter"]
