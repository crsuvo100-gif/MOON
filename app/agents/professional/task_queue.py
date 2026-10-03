"""Professional Task Queue — priority-based task scheduling.

Provides a priority queue for agent tasks with scheduling, deduplication,
rate limiting, and dependency management. Tasks are executed based on
priority, deadline, and resource availability.
"""

from __future__ import annotations

import asyncio
import heapq
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TaskPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass(order=True)
class QueuedTask:
    """A task in the priority queue."""
    priority: int
    created_at: float
    task_id: str = field(compare=False)
    prompt: str = field(compare=False)
    agent_name: str = field(compare=False, default="planning")
    status: TaskStatus = field(compare=False, default=TaskStatus.PENDING)
    deadline: float | None = field(compare=False, default=None)
    dependencies: list[str] = field(compare=False, default_factory=list)
    metadata: dict[str, Any] = field(compare=False, default_factory=dict)
    result: Any = field(compare=False, default=None)
    error: str | None = field(compare=False, default=None)
    started_at: float | None = field(compare=False, default=None)
    completed_at: float | None = field(compare=False, default=None)
    retry_count: int = field(compare=False, default=0)
    max_retries: int = field(compare=False, default=3)

    @property
    def is_ready(self) -> bool:
        return self.status == TaskStatus.PENDING

    @property
    def is_expired(self) -> bool:
        return self.deadline is not None and time.time() > self.deadline

    @property
    def wait_time(self) -> float:
        return time.time() - self.created_at

    @property
    def run_time(self) -> float | None:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        if self.started_at:
            return time.time() - self.started_at
        return None


class TaskQueue:
    """Priority task queue with scheduling and dependency management."""

    def __init__(self, *, max_concurrent: int = 3, default_timeout: float = 300.0) -> None:
        self._queue: list[QueuedTask] = []  # heap
        self._tasks: dict[str, QueuedTask] = {}  # by id
        self._completed: dict[str, QueuedTask] = {}
        self._max_concurrent = max_concurrent
        self._default_timeout = default_timeout
        self._running: set[str] = set()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()
        self._metrics: dict[str, int] = defaultdict(int)
        self._dedup_index: dict[str, str] = {}  # prompt hash -> task_id

    async def submit(
        self,
        prompt: str,
        *,
        priority: TaskPriority = TaskPriority.NORMAL,
        agent_name: str = "planning",
        deadline: float | None = None,
        dependencies: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        dedup: bool = True,
    ) -> str:
        """Submit a task to the queue.

        Returns:
            Task ID.
        """
        # Deduplication
        if dedup:
            prompt_key = prompt.strip().lower()[:200]
            if prompt_key in self._dedup_index:
                existing_id = self._dedup_index[prompt_key]
                if existing_id in self._tasks:
                    logger.debug("Deduplicated task: %s", existing_id)
                    self._metrics["deduplicated"] += 1
                    return existing_id

        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task = QueuedTask(
            priority=priority.value,
            created_at=time.time(),
            task_id=task_id,
            prompt=prompt,
            agent_name=agent_name,
            deadline=deadline,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )
        async with self._lock:
            heapq.heappush(self._queue, task)
            self._tasks[task_id] = task
            if dedup:
                self._dedup_index[prompt.strip().lower()[:200]] = task_id
        self._metrics["submitted"] += 1
        logger.info("Task submitted: %s (priority=%s, agent=%s)", task_id, priority.name, agent_name)
        return task_id

    async def get_next(self, *, timeout: float = 1.0) -> QueuedTask | None:
        """Get the next ready task from the queue.

        Returns:
            The next ready task, or None if no tasks are ready.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            async with self._lock:
                # Clean up expired tasks
                self._cleanup_expired()
                # Find next ready task
                for task in self._queue:
                    if task.status == TaskStatus.PENDING and self._deps_satisfied(task):
                        task.status = TaskStatus.SCHEDULED
                        self._running.add(task.task_id)
                        task.started_at = time.time()
                        self._metrics["started"] += 1
                        return task
            await asyncio.sleep(0.05)
        return None

    async def complete(self, task_id: str, result: Any = None) -> None:
        """Mark a task as completed."""
        async with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.completed_at = time.time()
                self._running.discard(task_id)
                self._completed[task_id] = task
                self._metrics["completed"] += 1
                logger.info("Task completed: %s (%.2fs)", task_id, task.run_time or 0)

    async def fail(self, task_id: str, error: str) -> None:
        """Mark a task as failed, with retry logic."""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.retry_count += 1
            if task.retry_count <= task.max_retries:
                task.status = TaskStatus.PENDING
                task.error = error
                task.priority = max(0, task.priority - 1)  # Boost priority on retry
                heapq.heappush(self._queue, task)
                self._metrics["retried"] += 1
                logger.warning("Task retry %d/%d: %s (%s)", task.retry_count, task.max_retries, task_id, error)
            else:
                task.status = TaskStatus.FAILED
                task.error = error
                task.completed_at = time.time()
                self._running.discard(task_id)
                self._completed[task_id] = task
                self._metrics["failed"] += 1
                logger.error("Task failed permanently: %s (%s)", task_id, error)

    async def cancel(self, task_id: str) -> bool:
        """Cancel a pending task."""
        async with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
                task.status = TaskStatus.CANCELLED
                self._running.discard(task_id)
                self._metrics["cancelled"] += 1
                return True
            return False

    def _deps_satisfied(self, task: QueuedTask) -> bool:
        """Check if all dependencies are completed."""
        for dep_id in task.dependencies:
            dep = self._tasks.get(dep_id)
            if not dep or dep.status != TaskStatus.COMPLETED:
                return False
        return True

    def _cleanup_expired(self) -> None:
        """Remove expired tasks from the queue."""
        now = time.time()
        expired = [t for t in self._queue if t.is_expired and t.status == TaskStatus.PENDING]
        for task in expired:
            task.status = TaskStatus.FAILED
            task.error = "Deadline exceeded"
            task.completed_at = now
            self._completed[task.task_id] = task
            self._metrics["expired"] += 1
        self._queue = [t for t in self._queue if t.status == TaskStatus.PENDING]
        heapq.heapify(self._queue)

    def get_status(self, task_id: str) -> TaskStatus | None:
        task = self._tasks.get(task_id)
        return task.status if task else None

    def get_result(self, task_id: str) -> Any | None:
        task = self._completed.get(task_id)
        return task.result if task else None

    def get_metrics(self) -> dict[str, Any]:
        return {
            **self._metrics,
            "queue_size": len(self._queue),
            "running": len(self._running),
            "completed_total": len(self._completed),
            "max_concurrent": self._max_concurrent,
        }

    async def shutdown(self) -> None:
        """Cancel all pending tasks."""
        async with self._lock:
            for task in self._queue:
                if task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.CANCELLED
            self._queue.clear()
            self._running.clear()
