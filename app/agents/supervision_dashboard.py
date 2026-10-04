"""Agent Supervision Dashboard (spec 41).

Terminal integration for multi-agent supervision. Displays:
    MOON STATUS, TASK, ACTENT, AGENT STATUS, BRAIN, TOOL, PROGRESS,
    PERMISSION, ERROR, VERIFICATION, FINAL RESULT

Example:
    MOON
    +-- Main Brain: planning
    +-- Coding Agent: executing
    +-- Coding Brain: active
    +-- Testing Agent: waiting
    +-- Security Agent: waiting
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING = "waiting"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentDashboardEntry:
    """One agent's status in the dashboard."""
    agent_id: str
    status: AgentStatus = AgentStatus.IDLE
    brain: str = ""
    current_tool: str = ""
    progress: str = ""
    task_id: str = ""
    started_at: float = 0.0
    last_update: float = field(default_factory=time.time)
    error: str = ""
    result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "brain": self.brain,
            "current_tool": self.current_tool,
            "progress": self.progress,
            "task_id": self.task_id,
            "elapsed": round(time.time() - self.started_at, 1) if self.started_at else 0,
            "last_update": self.last_update,
            "error": self.error,
            "result": self.result,
        }


@dataclass
class DashboardState:
    """Full dashboard state."""
    main_brain_status: str = "idle"
    main_brain_task: str = ""
    agents: dict[str, AgentDashboardEntry] = field(default_factory=dict)
    active_task_id: str = ""
    verification_status: str = "none"
    final_result: str = ""
    errors: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "main_brain_status": self.main_brain_status,
            "main_brain_task": self.main_brain_task,
            "active_task_id": self.active_task_id,
            "verification_status": self.verification_status,
            "final_result": self.final_result,
            "errors": self.errors,
            "permissions": self.permissions,
            "agents": {aid: a.to_dict() for aid, a in self.agents.items()},
        }


class AgentSupervisionDashboard:
    """Real-time multi-agent supervision dashboard (spec 41).

    The terminal/UI queries this dashboard to display:
    - Main Brain status
    - Per-agent status (idle, executing, waiting, etc.)
    - Brain/model per agent
    - Current tool per agent
    - Progress
    - Errors
    - Verification status
    - Final result
    """

    def __init__(self) -> None:
        self._state = DashboardState()
        self._lock = False  # Simple flag for thread safety

    def update_main_brain(self, status: str, task: str = "") -> None:
        """Update Main Brain status."""
        self._state.main_brain_status = status
        if task:
            self._state.main_brain_task = task

    def register_agent(self, agent_id: str, brain: str = "") -> AgentDashboardEntry:
        """Register an agent in the dashboard."""
        entry = AgentDashboardEntry(agent_id=agent_id, brain=brain)
        self._state.agents[agent_id] = entry
        return entry

    def update_agent(
        self,
        agent_id: str,
        *,
        status: AgentStatus | None = None,
        brain: str | None = None,
        current_tool: str | None = None,
        progress: str | None = None,
        task_id: str | None = None,
        error: str | None = None,
        result: str | None = None,
    ) -> None:
        """Update an agent's dashboard entry."""
        entry = self._state.agents.get(agent_id)
        if entry is None:
            entry = self.register_agent(agent_id)
        if status is not None:
            entry.status = status
        if brain is not None:
            entry.brain = brain
        if current_tool is not None:
            entry.current_tool = current_tool
        if progress is not None:
            entry.progress = progress
        if task_id is not None:
            entry.task_id = task_id
        if error is not None:
            entry.error = error
        if result is not None:
            entry.result = result
        entry.last_update = time.time()

    def set_verification_status(self, status: str) -> None:
        """Set verification status."""
        self._state.verification_status = status

    def set_final_result(self, result: str) -> None:
        """Set final result."""
        self._state.final_result = result

    def add_error(self, error: str) -> None:
        """Add an error to the dashboard."""
        self._state.errors.append(error)

    def add_permission(self, permission: str) -> None:
        """Add a permission request to the dashboard."""
        self._state.permissions.append(permission)

    def get_state(self) -> DashboardState:
        """Get current dashboard state."""
        return self._state

    def snapshot(self) -> dict[str, Any]:
        """Get a snapshot of the dashboard state."""
        return self._state.to_dict()

    def render_text(self) -> str:
        """Render dashboard as text for terminal display."""
        s = self._state
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("MOON MULTI-AGENT SUPERVISION DASHBOARD")
        lines.append("=" * 60)
        lines.append(f"Main Brain: {s.main_brain_status}")
        if s.main_brain_task:
            lines.append(f"  Task: {s.main_brain_task}")
        lines.append("")

        if s.agents:
            lines.append("AGENTS:")
            for agent_id, entry in s.agents.items():
                status_icon = {
                    AgentStatus.IDLE: "[ ]",
                    AgentStatus.PLANNING: "[P]",
                    AgentStatus.EXECUTING: "[>]",
                    AgentStatus.WAITING: "[w]",
                    AgentStatus.VERIFYING: "[V]",
                    AgentStatus.COMPLETED: "[X]",
                    AgentStatus.FAILED: "[!]",
                    AgentStatus.CANCELLED: "[C]",
                }.get(entry.status, "[?]")
                lines.append(f"  {status_icon} {agent_id}: {entry.status.value}")
                if entry.brain:
                    lines.append(f"      Brain: {entry.brain}")
                if entry.current_tool:
                    lines.append(f"      Tool: {entry.current_tool}")
                if entry.progress:
                    lines.append(f"      Progress: {entry.progress}")
                if entry.error:
                    lines.append(f"      Error: {entry.error}")
        else:
            lines.append("No agents registered.")

        lines.append("")
        lines.append(f"Verification: {s.verification_status}")
        if s.final_result:
            lines.append(f"Final Result: {s.final_result[:200]}")
        if s.errors:
            lines.append(f"Errors: {len(s.errors)}")
            for err in s.errors[-3:]:
                lines.append(f"  - {err}")
        lines.append("=" * 60)
        return "\n".join(lines)


# Module-level singleton
_DASHBOARD: AgentSupervisionDashboard | None = None


def get_dashboard() -> AgentSupervisionDashboard:
    global _DASHBOARD
    if _DASHBOARD is None:
        _DASHBOARD = AgentSupervisionDashboard()
    return _DASHBOARD


__all__ = [
    "AgentStatus", "AgentDashboardEntry", "DashboardState",
    "AgentSupervisionDashboard", "get_dashboard",
]
