"""Cross-session continuity -- maintain memory across restarts.

Professional AI assistants remember what happened in previous sessions.
This module persists key session state (recent tasks, lessons learned,
active goals) to disk and restores it on startup, so MOON can maintain
continuity across restarts.

Stored in: app/logs/session_continuity.json
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)

_CONTINUITY_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "session_continuity.json"


@dataclass
class SessionSnapshot:
    """A snapshot of the current session's memory state."""
    session_id: str
    started_at: float
    ended_at: float = 0.0
    task_count: int = 0
    lessons_learned: list[str] = field(default_factory=list)
    active_goals: list[str] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)
    last_task: str = ""
    last_result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionSnapshot:
        return cls(
            session_id=data.get("session_id", ""),
            started_at=data.get("started_at", 0.0),
            ended_at=data.get("ended_at", 0.0),
            task_count=data.get("task_count", 0),
            lessons_learned=list(data.get("lessons_learned", [])),
            active_goals=list(data.get("active_goals", [])),
            key_facts=list(data.get("key_facts", [])),
            last_task=data.get("last_task", ""),
            last_result=data.get("last_result", ""),
        )


class SessionContinuity:
    """Manages cross-session memory continuity.

    On startup:
    1. Load previous session snapshot
    2. Surface key lessons and facts from previous sessions
    3. Start a new session snapshot

    On shutdown:
    1. Save current session state
    2. Archive old snapshots (keep last 10)
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _CONTINUITY_PATH
        self._current: SessionSnapshot | None = None
        self._previous: list[SessionSnapshot] = []
        self._max_history = 10

    async def setup(self, session_id: str = "") -> None:
        """Initialize session continuity: load previous, start new."""
        self._load_previous()
        self._current = SessionSnapshot(
            session_id=session_id or f"session_{int(time.time())}",
            started_at=time.time(),
        )
        logger.info(
            "Session continuity: started %s (%d previous sessions loaded)",
            self._current.session_id,
            len(self._previous),
        )

    def _load_previous(self) -> None:
        """Load previous session snapshots from disk."""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._previous = [SessionSnapshot.from_dict(d) for d in data[-self._max_history:]]
            elif isinstance(data, dict):
                self._previous = [SessionSnapshot.from_dict(data)]
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Failed to load session continuity: %s", exc)
            self._previous = []

    async def shutdown(self) -> None:
        """Save current session state and archive."""
        if self._current is None:
            return
        self._current.ended_at = time.time()
        self._previous.append(self._current)
        # Keep only the most recent N snapshots
        self._previous = self._previous[-self._max_history:]
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = [s.to_dict() for s in self._previous]
            self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("Session continuity: saved %d snapshots", len(self._previous))
        except Exception as exc:
            logger.warning("Failed to save session continuity: %s", exc)

    def record_task(self, task: str, result: str, lesson: str = "") -> None:
        """Record a task in the current session."""
        if self._current is None:
            return
        self._current.task_count += 1
        self._current.last_task = task[:200]
        self._current.last_result = result[:500]
        if lesson:
            self._current.lessons_learned.append(lesson)

    def record_fact(self, fact: str) -> None:
        """Record a key fact in the current session."""
        if self._current is None:
            return
        self._current.key_facts.append(fact[:200])

    def record_goal(self, goal: str) -> None:
        """Record an active goal in the current session."""
        if self._current is None:
            return
        self._current.active_goals.append(goal[:200])

    def get_continuity_context(self) -> list[dict[str, Any]]:
        """Get context from previous sessions for continuity.

        Returns:
            List of dicts with lessons, facts, and goals from previous sessions.
        """
        context: list[dict[str, Any]] = []
        for snap in self._previous[-5:]:  # Last 5 sessions
            for lesson in snap.lessons_learned[-3:]:  # Last 3 lessons per session
                context.append({
                    "type": "lesson",
                    "content": lesson,
                    "session": snap.session_id,
                    "timestamp": snap.ended_at,
                })
            for fact in snap.key_facts[-3:]:  # Last 3 facts per session
                context.append({
                    "type": "fact",
                    "content": fact,
                    "session": snap.session_id,
                    "timestamp": snap.ended_at,
                })
            for goal in snap.active_goals[-2:]:  # Last 2 goals per session
                context.append({
                    "type": "goal",
                    "content": goal,
                    "session": snap.session_id,
                    "timestamp": snap.ended_at,
                })
        return context

    def get_previous_lessons(self, k: int = 5) -> list[str]:
        """Get the most recent lessons from previous sessions."""
        lessons: list[str] = []
        for snap in reversed(self._previous):
            for lesson in reversed(snap.lessons_learned):
                lessons.append(lesson)
                if len(lessons) >= k:
                    return lessons
        return lessons

    def stats(self) -> dict[str, Any]:
        """Return session continuity statistics."""
        return {
            "current_session": self._current.session_id if self._current else None,
            "previous_sessions": len(self._previous),
            "total_tasks": sum(s.task_count for s in self._previous) + (self._current.task_count if self._current else 0),
            "total_lessons": sum(len(s.lessons_learned) for s in self._previous) + (len(self._current.lessons_learned) if self._current else 0),
        }
