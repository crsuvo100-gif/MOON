"""Agent Health Monitor (spec 19).

Per-agent health tracking: availability, latency, error state, resource usage.
Every agent exposes health status that the Main Brain uses for routing
decisions and failure detection.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class AgentHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class AgentHealth:
    """Per-agent health record (spec 19)."""
    agent_id: str
    status: AgentHealthStatus = AgentHealthStatus.UNKNOWN
    last_seen: float = 0.0
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    avg_latency_ms: float = 0.0
    last_error: str = ""
    consecutive_failures: int = 0
    max_consecutive_failures: int = 3
    # Resource usage
    total_tokens_used: int = 0
    total_tool_calls: int = 0
    # Timing
    started_at: float = field(default_factory=time.time)
    last_task_at: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 1.0
        return self.successful_tasks / self.total_tasks

    @property
    def is_available(self) -> bool:
        return self.status in (AgentHealthStatus.HEALTHY, AgentHealthStatus.DEGRADED)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "last_seen": self.last_seen,
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "success_rate": round(self.success_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "is_available": self.is_available,
            "total_tokens_used": self.total_tokens_used,
            "total_tool_calls": self.total_tool_calls,
            "uptime_seconds": round(self.uptime_seconds, 1),
        }

    def record_success(self, latency_ms: float = 0.0, tokens_used: int = 0) -> None:
        self.total_tasks += 1
        self.successful_tasks += 1
        self.consecutive_failures = 0
        self.last_seen = time.time()
        self.last_task_at = time.time()
        if latency_ms > 0:
            # Exponential moving average
            alpha = 0.3
            self.avg_latency_ms = (
                alpha * latency_ms + (1 - alpha) * self.avg_latency_ms
                if self.avg_latency_ms > 0
                else latency_ms
            )
        self.total_tokens_used += tokens_used
        self._update_status()

    def record_failure(self, error: str = "") -> None:
        self.total_tasks += 1
        self.failed_tasks += 1
        self.consecutive_failures += 1
        self.last_seen = time.time()
        self.last_task_at = time.time()
        self.last_error = error
        self._update_status()

    def record_tool_call(self) -> None:
        self.total_tool_calls += 1

    def _update_status(self) -> None:
        if self.consecutive_failures >= self.max_consecutive_failures:
            self.status = AgentHealthStatus.UNHEALTHY
        elif self.consecutive_failures > 0:
            self.status = AgentHealthStatus.DEGRADED
        elif self.total_tasks > 0:
            self.status = AgentHealthStatus.HEALTHY


class AgentHealthMonitor:
    """Monitors health of all registered agents (spec 19).

    The Main Brain queries this monitor to decide:
    - Which agent to route a task to
    - Whether an agent needs to be replaced
    - Whether to escalate to the user
    """

    def __init__(self) -> None:
        self._health: dict[str, AgentHealth] = {}
        self._lock = asyncio.Lock()

    async def register(self, agent_id: str) -> AgentHealth:
        """Register a new agent for health monitoring."""
        async with self._lock:
            if agent_id not in self._health:
                self._health[agent_id] = AgentHealth(agent_id=agent_id)
            return self._health[agent_id]

    async def unregister(self, agent_id: str) -> None:
        """Remove an agent from health monitoring."""
        async with self._lock:
            self._health.pop(agent_id, None)

    async def record_success(
        self, agent_id: str, *, latency_ms: float = 0.0, tokens_used: int = 0
    ) -> None:
        """Record a successful task completion."""
        async with self._lock:
            h = self._health.get(agent_id)
            if h:
                h.record_success(latency_ms=latency_ms, tokens_used=tokens_used)

    async def record_failure(self, agent_id: str, error: str = "") -> None:
        """Record a task failure."""
        async with self._lock:
            h = self._health.get(agent_id)
            if h:
                h.record_failure(error)

    async def record_tool_call(self, agent_id: str) -> None:
        """Record a tool call."""
        async with self._lock:
            h = self._health.get(agent_id)
            if h:
                h.record_tool_call()

    async def get_health(self, agent_id: str) -> AgentHealth | None:
        """Get health for a specific agent."""
        async with self._lock:
            return self._health.get(agent_id)

    async def get_all_health(self) -> dict[str, AgentHealth]:
        """Get health for all agents."""
        async with self._lock:
            return dict(self._health)

    async def get_available_agents(self) -> list[str]:
        """Get list of available agent IDs."""
        async with self._lock:
            return [
                aid for aid, h in self._health.items() if h.is_available
            ]

    async def get_unhealthy_agents(self) -> list[str]:
        """Get list of unhealthy agent IDs."""
        async with self._lock:
            return [
                aid for aid, h in self._health.items()
                if h.status == AgentHealthStatus.UNHEALTHY
            ]

    async def get_best_agent(self, capability: str | None = None) -> str | None:
        """Get the best available agent (highest success rate, lowest latency)."""
        async with self._lock:
            available = [
                h for h in self._health.values() if h.is_available
            ]
            if not available:
                return None
            # Sort by success rate (desc), then latency (asc)
            available.sort(
                key=lambda h: (-h.success_rate, h.avg_latency_ms)
            )
            return available[0].agent_id if available else None

    def snapshot(self) -> dict[str, Any]:
        """Get a snapshot of all agent health."""
        return {
            "agents": {aid: h.to_dict() for aid, h in self._health.items()},
            "total_agents": len(self._health),
            "available": sum(1 for h in self._health.values() if h.is_available),
            "unhealthy": sum(
                1 for h in self._health.values()
                if h.status == AgentHealthStatus.UNHEALTHY
            ),
        }


# Module-level singleton
_MONITOR: AgentHealthMonitor | None = None


def get_monitor() -> AgentHealthMonitor:
    global _MONITOR
    if _MONITOR is None:
        _MONITOR = AgentHealthMonitor()
    return _MONITOR


__all__ = [
    "AgentHealthStatus", "AgentHealth", "AgentHealthMonitor", "get_monitor",
]
