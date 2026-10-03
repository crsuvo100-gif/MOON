"""coordination.py — multi-agent coordination protocols.

Professional AI assistants coordinate multiple agents working on
complex tasks. This module provides coordination protocols including:
- Contract net protocol (task auction)
- Blackboard coordination (shared state)
- Hierarchical delegation (manager-worker)
- Peer-to-peer negotiation
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CoordinationMode(str, Enum):
    HIERARCHICAL = "hierarchical"  # manager delegates to workers
    CONTRACT_NET = "contract_net"  # auction-based task assignment
    BLACKBOARD = "blackboard"  # shared state coordination
    PEER_TO_PEER = "peer_to_peer"  # direct agent negotiation


@dataclass
class TaskAnnouncement:
    task_id: str
    description: str
    requirements: list[str]
    deadline: float
    priority: int = 5  # 1-10
    assigned_to: str = ""
    status: str = "open"  # open, assigned, in_progress, completed, failed


@dataclass
class Bid:
    task_id: str
    agent_id: str
    cost: float  # estimated cost (lower is better)
    capability_match: float  # 0-1 how well agent matches requirements
    timestamp: float = field(default_factory=time.time)


@dataclass
class CoordinationEvent:
    event_type: str
    task_id: str
    agent_id: str
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)


class CoordinationProtocol:
    """Multi-agent coordination using configurable protocols.

    Supports hierarchical delegation, contract net (auction), blackboard,
    and peer-to-peer modes. Agents can announce tasks, bid on them,
    and coordinate through a central protocol manager.
    """

    def __init__(
        self,
        mode: CoordinationMode = CoordinationMode.HIERARCHICAL,
        *,
        max_concurrent_tasks: int = 10,
        task_timeout: float = 300.0,
    ) -> None:
        self.mode = mode
        self._max_concurrent = max_concurrent_tasks
        self._task_timeout = task_timeout
        self._tasks: dict[str, TaskAnnouncement] = {}
        self._bids: dict[str, list[Bid]] = {}
        self._events: list[CoordinationEvent] = []
        self._agent_capabilities: dict[str, list[str]] = {}
        self._agent_load: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def register_agent(self, agent_id: str, capabilities: list[str]) -> None:
        self._agent_capabilities[agent_id] = capabilities
        self._agent_load[agent_id] = 0

    def unregister_agent(self, agent_id: str) -> None:
        self._agent_capabilities.pop(agent_id, None)
        self._agent_load.pop(agent_id, None)

    async def announce_task(
        self,
        description: str,
        requirements: list[str],
        *,
        priority: int = 5,
        deadline: float | None = None,
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        task = TaskAnnouncement(
            task_id=task_id,
            description=description,
            requirements=requirements,
            deadline=deadline or (time.time() + self._task_timeout),
            priority=priority,
        )
        async with self._lock:
            self._tasks[task_id] = task
            self._bids[task_id] = []

        await self._emit_event("task_announced", task_id, "system", {
            "description": description,
            "requirements": requirements,
            "priority": priority,
        })

        # Auto-assign based on mode
        if self.mode == CoordinationMode.CONTRACT_NET:
            await self._run_auction(task_id)
        elif self.mode == CoordinationMode.HIERARCHICAL:
            await self._auto_assign(task_id)

        return task_id

    async def submit_bid(
        self,
        task_id: str,
        agent_id: str,
        cost: float,
        capability_match: float,
    ) -> bool:
        async with self._lock:
            if task_id not in self._tasks:
                return False
            task = self._tasks[task_id]
            if task.status != "open":
                return False

            bid = Bid(
                task_id=task_id,
                agent_id=agent_id,
                cost=cost,
                capability_match=capability_match,
            )
            self._bids[task_id].append(bid)
            return True

    async def _run_auction(self, task_id: str) -> None:
        """Contract net: assign to best bid (lowest cost, highest capability)."""
        async with self._lock:
            bids = self._bids.get(task_id, [])
            if not bids:
                return

            # Score: capability_match / cost (higher is better)
            best_bid = max(bids, key=lambda b: b.capability_match / max(0.1, b.cost))
            task = self._tasks[task_id]
            task.assigned_to = best_bid.agent_id
            task.status = "assigned"
            self._agent_load[best_bid.agent_id] = self._agent_load.get(best_bid.agent_id, 0) + 1

        await self._emit_event("task_assigned", task_id, best_bid.agent_id, {
            "mode": "contract_net",
            "cost": best_bid.cost,
            "capability_match": best_bid.capability_match,
        })

    async def _auto_assign(self, task_id: str) -> None:
        """Hierarchical: assign to least-loaded capable agent."""
        async with self._lock:
            task = self._tasks[task_id]
            requirements = set(task.requirements)

            # Find capable agents
            capable = []
            for agent_id, caps in self._agent_capabilities.items():
                if requirements.issubset(set(caps)):
                    load = self._agent_load.get(agent_id, 0)
                    capable.append((load, agent_id))

            if not capable:
                # Fallback: assign to least-loaded agent
                if self._agent_load:
                    agent_id = min(self._agent_load, key=lambda k: self._agent_load[k])
                    task.assigned_to = agent_id
                    task.status = "assigned"
                    self._agent_load[agent_id] += 1
                    await self._emit_event("task_assigned", task_id, agent_id, {
                        "mode": "hierarchical_fallback",
                    })
                return

            capable.sort()
            agent_id = capable[0][1]
            task.assigned_to = agent_id
            task.status = "assigned"
            self._agent_load[agent_id] += 1

        await self._emit_event("task_assigned", task_id, agent_id, {
            "mode": "hierarchical",
        })

    async def start_task(self, task_id: str, agent_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.assigned_to != agent_id:
                return False
            task.status = "in_progress"
        await self._emit_event("task_started", task_id, agent_id)
        return True

    async def complete_task(
        self,
        task_id: str,
        agent_id: str,
        result: str = "",
    ) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.assigned_to != agent_id:
                return False
            task.status = "completed"
            self._agent_load[agent_id] = max(0, self._agent_load.get(agent_id, 1) - 1)
        await self._emit_event("task_completed", task_id, agent_id, {"result": result[:200]})
        return True

    async def fail_task(self, task_id: str, agent_id: str, reason: str = "") -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.assigned_to != agent_id:
                return False
            task.status = "failed"
            self._agent_load[agent_id] = max(0, self._agent_load.get(agent_id, 1) - 1)
        await self._emit_event("task_failed", task_id, agent_id, {"reason": reason})
        return True

    async def get_task(self, task_id: str) -> TaskAnnouncement | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def get_agent_tasks(self, agent_id: str) -> list[TaskAnnouncement]:
        async with self._lock:
            return [t for t in self._tasks.values() if t.assigned_to == agent_id]

    async def get_open_tasks(self) -> list[TaskAnnouncement]:
        async with self._lock:
            return [t for t in self._tasks.values() if t.status == "open"]

    async def _emit_event(
        self,
        event_type: str,
        task_id: str,
        agent_id: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        event = CoordinationEvent(
            event_type=event_type,
            task_id=task_id,
            agent_id=agent_id,
            timestamp=time.time(),
            data=data or {},
        )
        self._events.append(event)
        if len(self._events) > 1000:
            self._events = self._events[-1000:]

    def get_events(self, *, limit: int = 100) -> list[CoordinationEvent]:
        return self._events[-limit:]

    def stats(self) -> dict[str, Any]:
        total = len(self._tasks)
        by_status: dict[str, int] = {}
        for t in self._tasks.values():
            by_status[t.status] = by_status.get(t.status, 0) + 1
        return {
            "mode": self.mode.value,
            "total_tasks": total,
            "by_status": by_status,
            "total_agents": len(self._agent_capabilities),
            "agent_loads": dict(self._agent_load),
            "total_events": len(self._events),
        }
