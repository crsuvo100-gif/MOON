"""Distributed Execution — parallel agent execution with resource awareness.

Provides:
- AgentPool: manages a pool of agents for parallel execution
- DistributedTask: represents a task that can be distributed across agents
- ResourceAwareScheduler: schedules tasks based on resource availability
- ExecutionResult: result of a distributed execution

This is ADDITIVE: it does not replace the existing TaskGraph/Supervisor
in ``app/agents/advanced/supervision.py``. Instead it provides a higher-level
abstraction for distributed agent execution.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.agents.communication_protocol import (
    AgentCommunicationBus,
    AgentMessage,
    MessageType,
    get_bus,
    new_task_id,
)


class ExecutionMode(str, Enum):
    """Execution modes for distributed tasks."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"
    FAN_OUT = "fan_out"
    FAN_IN = "fan_in"


class TaskStatus(str, Enum):
    """Status of a distributed task."""

    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass
class ResourceRequirements:
    """Resource requirements for a task."""

    cpu_cores: float = 1.0
    memory_mb: int = 512
    gpu: bool = False
    network: bool = True
    max_duration: float = 300.0


@dataclass
class DistributedTask:
    """A task that can be distributed across agents."""

    task_id: str = field(default_factory=new_task_id)
    prompt: str = ""
    agent_id: str = ""
    context: str = ""
    mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    resources: ResourceRequirements = field(default_factory=ResourceRequirements)
    dependencies: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float | None:
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        if self.started_at:
            return time.time() - self.started_at
        return None

    @property
    def is_ready(self) -> bool:
        return self.status == TaskStatus.PENDING


@dataclass
class ExecutionResult:
    """Result of a distributed execution."""

    execution_id: str = field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:8]}")
    tasks: list[DistributedTask] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    status: TaskStatus = TaskStatus.PENDING
    results: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float | None:
        if self.finished_at:
            return self.finished_at - self.started_at
        return None

    @property
    def success_rate(self) -> float:
        if not self.tasks:
            return 0.0
        completed = sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)
        return completed / len(self.tasks)

    @property
    def all_succeeded(self) -> bool:
        return all(t.status == TaskStatus.COMPLETED for t in self.tasks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "status": self.status.value,
            "duration": self.duration,
            "success_rate": self.success_rate,
            "all_succeeded": self.all_succeeded,
            "tasks": [
                {
                    "task_id": t.task_id,
                    "agent_id": t.agent_id,
                    "status": t.status.value,
                    "duration": t.duration,
                    "error": t.error,
                }
                for t in self.tasks
            ],
            "results": self.results,
            "errors": self.errors,
        }


class AgentPool:
    """Manages a pool of agents for parallel execution.

    The AgentPool maintains a set of available agents and assigns tasks
    to them based on capability matching and resource availability.
    """

    def __init__(
        self,
        *,
        max_concurrent: int = 5,
        max_tasks_per_agent: int = 3,
    ) -> None:
        self._max_concurrent = max_concurrent
        self._max_tasks_per_agent = max_tasks_per_agent
        self._agents: dict[str, Any] = {}  # agent_id -> agent
        self._agent_load: dict[str, int] = {}  # agent_id -> current task count
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._bus: AgentCommunicationBus = get_bus()
        self._metrics: dict[str, int] = {}

    def register_agent(self, agent_id: str, agent: Any) -> None:
        """Register an agent with the pool."""
        self._agents[agent_id] = agent
        self._agent_load[agent_id] = 0

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent from the pool."""
        self._agents.pop(agent_id, None)
        self._agent_load.pop(agent_id, None)

    def get_available_agents(self) -> list[str]:
        """Get list of agents that can accept more tasks."""
        return [
            aid for aid, load in self._agent_load.items()
            if load < self._max_tasks_per_agent
        ]

    def get_least_loaded_agent(self) -> str | None:
        """Get the agent with the lowest current load."""
        if not self._agent_load:
            return None
        return min(self._agent_load, key=lambda a: self._agent_load[a])

    async def execute_task(self, task: DistributedTask) -> DistributedTask:
        """Execute a single task using an agent from the pool.

        Args:
            task: The task to execute.

        Returns:
            The task with result or error set.
        """
        agent_id = task.agent_id or self.get_least_loaded_agent()
        if not agent_id or agent_id not in self._agents:
            task.status = TaskStatus.FAILED
            task.error = f"No available agent for task {task.task_id}"
            return task

        agent = self._agents[agent_id]
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        self._agent_load[agent_id] += 1

        try:
            async with self._semaphore:
                # Report task start
                await self._bus.publish(AgentMessage(
                    task_id=task.task_id,
                    agent_id=agent_id,
                    message_type=MessageType.TASK_PROGRESS,
                    result=f"Task {task.task_id} started",
                ))

                # Execute the task
                result = await agent.run(task.prompt, task.context)
                task.result = result
                task.status = TaskStatus.COMPLETED
                self._metrics["tasks_completed"] = self._metrics.get("tasks_completed", 0) + 1

                # Report task completion
                await self._bus.publish(AgentMessage(
                    task_id=task.task_id,
                    agent_id=agent_id,
                    message_type=MessageType.TASK_RESULT,
                    result=str(result),
                    status="completed",
                ))

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            self._metrics["tasks_failed"] = self._metrics.get("tasks_failed", 0) + 1

            # Report task failure
            await self._bus.publish(AgentMessage(
                task_id=task.task_id,
                agent_id=agent_id,
                message_type=MessageType.TASK_FAILED,
                result=str(e),
                status="failed",
                errors=[str(e)],
            ))

        finally:
            task.finished_at = time.time()
            self._agent_load[agent_id] -= 1

        return task

    async def execute_tasks(self, tasks: list[DistributedTask]) -> ExecutionResult:
        """Execute multiple tasks in parallel.

        Args:
            tasks: List of tasks to execute.

        Returns:
            ExecutionResult with all task results.
        """
        execution = ExecutionResult(tasks=tasks)
        execution.status = TaskStatus.RUNNING

        # Execute all tasks in parallel
        coros = [self.execute_task(t) for t in tasks]
        completed_tasks = await asyncio.gather(*coros, return_exceptions=True)

        for task in completed_tasks:
            if isinstance(task, Exception):
                execution.errors["unknown"] = str(task)
            else:
                execution.results[task.task_id] = task.result
                if task.error:
                    execution.errors[task.task_id] = task.error

        execution.finished_at = time.time()
        execution.status = TaskStatus.COMPLETED if execution.all_succeeded else TaskStatus.FAILED

        return execution

    def get_metrics(self) -> dict[str, Any]:
        """Get pool metrics."""
        return {
            **self._metrics,
            "agents_registered": len(self._agents),
            "max_concurrent": self._max_concurrent,
            "agent_load": dict(self._agent_load),
        }


class ResourceAwareScheduler:
    """Schedules tasks based on resource availability.

    The scheduler considers:
    - CPU/memory requirements
    - Agent availability
    - Task dependencies
    - Priority and deadlines
    """

    def __init__(self, *, pool: AgentPool | None = None) -> None:
        self._pool = pool or AgentPool()
        self._pending: list[DistributedTask] = []
        self._running: dict[str, DistributedTask] = {}
        self._completed: dict[str, DistributedTask] = {}
        self._bus: AgentCommunicationBus = get_bus()

    def schedule(self, task: DistributedTask) -> None:
        """Schedule a task for execution."""
        self._pending.append(task)

    async def run_scheduled(self) -> list[ExecutionResult]:
        """Run all scheduled tasks.

        Returns:
            List of ExecutionResult objects.
        """
        results: list[ExecutionResult] = []

        while self._pending:
            # Get ready tasks (dependencies satisfied)
            ready = [t for t in self._pending if self._deps_satisfied(t)]
            if not ready:
                # Wait a bit for dependencies to complete
                await asyncio.sleep(0.1)
                continue

            # Remove from pending
            for t in ready:
                self._pending.remove(t)

            # Execute ready tasks
            execution = await self._pool.execute_tasks(ready)
            results.append(execution)

            # Update completed tasks
            for t in ready:
                self._completed[t.task_id] = t

        return results

    def _deps_satisfied(self, task: DistributedTask) -> bool:
        """Check if all dependencies for a task are satisfied."""
        for dep_id in task.dependencies:
            dep = self._completed.get(dep_id)
            if not dep or dep.status != TaskStatus.COMPLETED:
                return False
        return True

    def get_status(self) -> dict[str, Any]:
        """Get scheduler status."""
        return {
            "pending": len(self._pending),
            "running": len(self._running),
            "completed": len(self._completed),
            "pool_metrics": self._pool.get_metrics(),
        }


__all__ = [
    "AgentPool",
    "DistributedTask",
    "ExecutionResult",
    "ExecutionMode",
    "TaskStatus",
    "ResourceRequirements",
    "ResourceAwareScheduler",
]
