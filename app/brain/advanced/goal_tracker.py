"""Goal tracking and progress monitoring for agent cognition.

Tracks hierarchical goals (long-term → short-term → tasks), monitors progress,
detects stalls, and provides actionable feedback.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class GoalStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    STALLED = "stalled"
    ABANDONED = "abandoned"


@dataclass
class Goal:
    """A tracked goal with progress monitoring."""
    id: str
    description: str
    parent_id: str | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    progress: float = 0.0  # 0..1
    subgoals: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def is_terminal(self) -> bool:
        return self.status in (GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.ABANDONED)


class GoalTracker:
    """Tracks hierarchical goals and monitors progress.

    Supports goal decomposition (parent → subgoals → tasks),
    progress tracking, stall detection, and completion callbacks.
    """

    def __init__(self, *, stall_threshold_seconds: float = 300.0) -> None:
        self._goals: dict[str, Goal] = {}
        self._stall_threshold = stall_threshold_seconds
        self._lock = asyncio.Lock()

    async def create_goal(
        self,
        *,
        goal_id: str,
        description: str,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Goal:
        """Create a new goal."""
        async with self._lock:
            goal = Goal(
                id=goal_id,
                description=description,
                parent_id=parent_id,
                metadata=metadata or {},
            )
            self._goals[goal_id] = goal
            if parent_id and parent_id in self._goals:
                self._goals[parent_id].subgoals.append(goal_id)
            return goal

    async def update_progress(
        self,
        goal_id: str,
        *,
        progress: float | None = None,
        status: GoalStatus | None = None,
        task_id: str | None = None,
    ) -> Goal | None:
        """Update a goal's progress or status."""
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None:
                return None
            if progress is not None:
                goal.progress = max(0.0, min(1.0, progress))
            if status is not None:
                goal.status = status
                if status == GoalStatus.COMPLETED:
                    goal.completed_at = time.time()
                    goal.progress = 1.0
            if task_id and task_id not in goal.tasks:
                goal.tasks.append(task_id)
            goal.updated_at = time.time()
            # Propagate progress to parent
            if goal.parent_id and goal.parent_id in self._goals:
                await self._recompute_parent_progress(goal.parent_id)
            return goal

    async def get_goal(self, goal_id: str) -> Goal | None:
        """Get a goal by ID."""
        async with self._lock:
            return self._goals.get(goal_id)

    async def get_active_goals(self) -> list[Goal]:
        """Get all active goals."""
        async with self._lock:
            return [g for g in self._goals.values() if g.status == GoalStatus.ACTIVE]

    async def get_stalled_goals(self) -> list[Goal]:
        """Get goals that appear stalled (no update for a while)."""
        async with self._lock:
            now = time.time()
            return [
                g for g in self._goals.values()
                if g.status == GoalStatus.ACTIVE
                and (now - g.updated_at) > self._stall_threshold
            ]

    async def get_progress_summary(self) -> dict[str, Any]:
        """Get a summary of all goal progress."""
        async with self._lock:
            total = len(self._goals)
            completed = sum(1 for g in self._goals.values() if g.status == GoalStatus.COMPLETED)
            failed = sum(1 for g in self._goals.values() if g.status == GoalStatus.FAILED)
            active = sum(1 for g in self._goals.values() if g.status == GoalStatus.ACTIVE)
            stalled = sum(1 for g in self._goals.values() if g.status == GoalStatus.STALLED)
            avg_progress = (
                sum(g.progress for g in self._goals.values()) / total if total > 0 else 0.0
            )
            return {
                "total": total,
                "completed": completed,
                "failed": failed,
                "active": active,
                "stalled": stalled,
                "avg_progress": avg_progress,
            }

    async def mark_stalled(self) -> list[str]:
        """Mark stalled goals and return their IDs."""
        async with self._lock:
            stalled = await self.get_stalled_goals()
            for goal in stalled:
                goal.status = GoalStatus.STALLED
                goal.updated_at = time.time()
            return [g.id for g in stalled]

    async def complete_goal(self, goal_id: str) -> Goal | None:
        """Mark a goal as completed."""
        return await self.update_progress(goal_id, status=GoalStatus.COMPLETED)

    async def fail_goal(self, goal_id: str) -> Goal | None:
        """Mark a goal as failed."""
        return await self.update_progress(goal_id, status=GoalStatus.FAILED)

    async def _recompute_parent_progress(self, parent_id: str) -> None:
        """Recompute parent progress from subgoals."""
        parent = self._goals.get(parent_id)
        if not parent or not parent.subgoals:
            return
        subgoals = [self._goals[sid] for sid in parent.subgoals if sid in self._goals]
        if subgoals:
            parent.progress = sum(g.progress for g in subgoals) / len(subgoals)
            parent.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        """Serialize all goals to a dict."""
        return {
            gid: {
                "id": g.id,
                "description": g.description,
                "parent_id": g.parent_id,
                "status": g.status.value,
                "progress": g.progress,
                "subgoals": g.subgoals,
                "tasks": g.tasks,
                "created_at": g.created_at,
                "updated_at": g.updated_at,
            }
            for gid, g in self._goals.items()
        }
