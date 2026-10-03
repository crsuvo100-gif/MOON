"""state_manager.py — agent state persistence and recovery.

Professional AI assistants maintain persistent state across sessions.
This module provides state serialization, checkpointing, and recovery
so agents can resume work after interruptions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    agent_id: str
    task_id: str
    state: str  # "idle", "planning", "executing", "waiting", "learning", "reviewing"
    context: dict[str, Any] = field(default_factory=dict)
    progress: float = 0.0  # 0-1
    current_step: str = ""
    completed_steps: list[str] = field(default_factory=list)
    pending_steps: list[str] = field(default_factory=list)
    tool_results: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "state": self.state,
            "context": self.context,
            "progress": self.progress,
            "current_step": self.current_step,
            "completed_steps": self.completed_steps,
            "pending_steps": self.pending_steps,
            "tool_results": self.tool_results,
            "timestamp": self.timestamp,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentState:
        return cls(
            agent_id=d["agent_id"],
            task_id=d["task_id"],
            state=d["state"],
            context=d.get("context", {}),
            progress=d.get("progress", 0.0),
            current_step=d.get("current_step", ""),
            completed_steps=d.get("completed_steps", []),
            pending_steps=d.get("pending_steps", []),
            tool_results=d.get("tool_results", {}),
            timestamp=d.get("timestamp", time.time()),
            version=d.get("version", 1),
        )


class AgentStateManager:
    """Manages agent state persistence and recovery.

    Serializes agent state to disk, supports checkpointing at key
    points, and can recover agent state after interruptions.
    State is stored as JSON files in a configurable directory.
    """

    def __init__(self, state_dir: str | Path | None = None) -> None:
        if state_dir is None:
            state_dir = Path(__file__).resolve().parent.parent.parent / "data" / "agent_states"
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._states: dict[str, AgentState] = {}
        self._lock = asyncio.Lock()

    def _state_file(self, agent_id: str, task_id: str) -> Path:
        return self._state_dir / f"{agent_id}_{task_id}.json"

    async def save_state(self, state: AgentState) -> None:
        """Save agent state to disk."""
        async with self._lock:
            state.timestamp = time.time()
            state.version += 1
            self._states[f"{state.agent_id}:{state.task_id}"] = state

            try:
                file_path = self._state_file(state.agent_id, state.task_id)
                file_path.write_text(json.dumps(state.to_dict(), indent=2, default=str))
            except Exception as exc:
                logger.warning("Failed to save state for %s: %s", state.agent_id, exc)

    async def load_state(self, agent_id: str, task_id: str) -> AgentState | None:
        """Load agent state from disk."""
        key = f"{agent_id}:{task_id}"
        async with self._lock:
            if key in self._states:
                return self._states[key]

            try:
                file_path = self._state_file(agent_id, task_id)
                if file_path.exists():
                    data = json.loads(file_path.read_text())
                    state = AgentState.from_dict(data)
                    self._states[key] = state
                    return state
            except Exception as exc:
                logger.warning("Failed to load state for %s: %s", agent_id, exc)
            return None

    async def update_progress(
        self,
        agent_id: str,
        task_id: str,
        progress: float,
        *,
        current_step: str = "",
        completed_step: str = "",
    ) -> None:
        """Update agent progress."""
        async with self._lock:
            key = f"{agent_id}:{task_id}"
            state = self._states.get(key)
            if state:
                state.progress = max(0.0, min(1.0, progress))
                if current_step:
                    state.current_step = current_step
                if completed_step and completed_step not in state.completed_steps:
                    state.completed_steps.append(completed_step)
                    if completed_step in state.pending_steps:
                        state.pending_steps.remove(completed_step)
                state.timestamp = time.time()
                await self.save_state(state)

    async def add_tool_result(
        self,
        agent_id: str,
        task_id: str,
        tool_name: str,
        result: Any,
    ) -> None:
        """Add a tool result to agent state."""
        async with self._lock:
            key = f"{agent_id}:{task_id}"
            state = self._states.get(key)
            if state:
                state.tool_results[tool_name] = result
                state.timestamp = time.time()
                await self.save_state(state)

    async def get_state(self, agent_id: str, task_id: str) -> AgentState | None:
        async with self._lock:
            return self._states.get(f"{agent_id}:{task_id}")

    async def get_all_states(self) -> list[AgentState]:
        async with self._lock:
            return list(self._states.values())

    async def get_active_agents(self) -> list[str]:
        """Get list of agents with non-terminal state."""
        async with self._lock:
            active = []
            for key, state in self._states.items():
                if state.state not in ("idle", "terminated"):
                    active.append(state.agent_id)
            return active

    async def cleanup_old_states(self, *, max_age_hours: float = 24.0) -> int:
        """Remove states older than max_age_hours. Returns count removed."""
        async with self._lock:
            now = time.time()
            to_remove = []
            for key, state in self._states.items():
                age_hours = (now - state.timestamp) / 3600
                if age_hours > max_age_hours:
                    to_remove.append(key)
            for key in to_remove:
                del self._states[key]
            return len(to_remove)

    async def delete_state(self, agent_id: str, task_id: str) -> bool:
        async with self._lock:
            key = f"{agent_id}:{task_id}"
            if key in self._states:
                del self._states[key]
            try:
                file_path = self._state_file(agent_id, task_id)
                if file_path.exists():
                    file_path.unlink()
                    return True
            except Exception as exc:
                logger.warning("Failed to delete state file: %s", exc)
            return False

    def stats(self) -> dict[str, Any]:
        total = len(self._states)
        by_state: dict[str, int] = {}
        for state in self._states.values():
            by_state[state.state] = by_state.get(state.state, 0) + 1
        return {
            "total_states": total,
            "by_state": by_state,
            "state_dir": str(self._state_dir),
        }
