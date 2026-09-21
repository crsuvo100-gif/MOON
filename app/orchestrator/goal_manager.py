"""Goal Manager (spec sections 6, 34: orchestrator/goal_manager.py).

Re-exports the real GoalManager/Goal from app.runtime.goal_manager.
"""

from app.runtime.goal_manager import GoalManager, Goal  # noqa: F401

__all__ = ["GoalManager", "Goal"]
