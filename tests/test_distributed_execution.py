"""Tests for distributed execution — AgentPool, DistributedTask, ResourceAwareScheduler."""

from __future__ import annotations

import asyncio

import pytest

from app.brain.distributed_execution import (
    AgentPool,
    DistributedTask,
    ExecutionResult,
    ExecutionMode,
    TaskStatus,
    ResourceRequirements,
    ResourceAwareScheduler,
)


class TestDistributedTask:
    """Test DistributedTask dataclass."""

    def test_task_creation(self):
        task = DistributedTask(prompt="Test prompt", agent_id="test_agent")
        assert task.prompt == "Test prompt"
        assert task.agent_id == "test_agent"
        assert task.status == TaskStatus.PENDING
        assert task.task_id is not None

    def test_task_duration(self):
        task = DistributedTask()
        assert task.duration is None
        task.started_at = 1000.0
        task.finished_at = 1005.0
        assert task.duration == 5.0

    def test_task_is_ready(self):
        task = DistributedTask()
        assert task.is_ready is True
        task.status = TaskStatus.RUNNING
        assert task.is_ready is False

    def test_task_dependencies(self):
        task = DistributedTask(dependencies=["task_1", "task_2"])
        assert len(task.dependencies) == 2


class TestResourceRequirements:
    """Test ResourceRequirements dataclass."""

    def test_defaults(self):
        req = ResourceRequirements()
        assert req.cpu_cores == 1.0
        assert req.memory_mb == 512
        assert req.gpu is False
        assert req.network is True
        assert req.max_duration == 300.0

    def test_custom(self):
        req = ResourceRequirements(cpu_cores=4.0, memory_mb=2048, gpu=True)
        assert req.cpu_cores == 4.0
        assert req.memory_mb == 2048
        assert req.gpu is True


class TestExecutionResult:
    """Test ExecutionResult dataclass."""

    def test_creation(self):
        result = ExecutionResult()
        assert result.execution_id is not None
        assert result.status == TaskStatus.PENDING
        assert result.success_rate == 0.0

    def test_success_rate(self):
        result = ExecutionResult(
            tasks=[
                DistributedTask(status=TaskStatus.COMPLETED),
                DistributedTask(status=TaskStatus.FAILED),
                DistributedTask(status=TaskStatus.COMPLETED),
            ]
        )
        assert result.success_rate == pytest.approx(0.667, rel=0.01)

    def test_all_succeeded(self):
        result = ExecutionResult(
            tasks=[
                DistributedTask(status=TaskStatus.COMPLETED),
                DistributedTask(status=TaskStatus.COMPLETED),
            ]
        )
        assert result.all_succeeded is True

    def test_to_dict(self):
        result = ExecutionResult(
            tasks=[DistributedTask(status=TaskStatus.COMPLETED)],
            results={"task_1": "result_1"},
        )
        d = result.to_dict()
        assert d["execution_id"] is not None
        assert d["status"] == "pending"
        assert len(d["tasks"]) == 1


class TestAgentPool:
    """Test AgentPool."""

    def test_creation(self):
        pool = AgentPool(max_concurrent=3)
        assert pool._max_concurrent == 3

    def test_register_agent(self):
        pool = AgentPool()
        pool.register_agent("agent_1", object())
        assert "agent_1" in pool._agents

    def test_unregister_agent(self):
        pool = AgentPool()
        pool.register_agent("agent_1", object())
        pool.unregister_agent("agent_1")
        assert "agent_1" not in pool._agents

    def test_get_available_agents(self):
        pool = AgentPool(max_tasks_per_agent=2)
        pool.register_agent("agent_1", object())
        pool.register_agent("agent_2", object())
        available = pool.get_available_agents()
        assert len(available) == 2

    def test_get_least_loaded_agent(self):
        pool = AgentPool()
        pool.register_agent("agent_1", object())
        pool.register_agent("agent_2", object())
        pool._agent_load["agent_1"] = 2
        pool._agent_load["agent_2"] = 1
        assert pool.get_least_loaded_agent() == "agent_2"

    def test_get_metrics(self):
        pool = AgentPool()
        pool.register_agent("agent_1", object())
        metrics = pool.get_metrics()
        assert metrics["agents_registered"] == 1
        assert metrics["max_concurrent"] == 5


class TestResourceAwareScheduler:
    """Test ResourceAwareScheduler."""

    def test_creation(self):
        scheduler = ResourceAwareScheduler()
        assert scheduler is not None

    def test_schedule(self):
        scheduler = ResourceAwareScheduler()
        task = DistributedTask(prompt="Test")
        scheduler.schedule(task)
        assert len(scheduler._pending) == 1

    def test_deps_satisfied(self):
        scheduler = ResourceAwareScheduler()
        task = DistributedTask(dependencies=["dep_1"])
        assert scheduler._deps_satisfied(task) is False

        # Add completed dependency
        dep = DistributedTask(task_id="dep_1", status=TaskStatus.COMPLETED)
        scheduler._completed["dep_1"] = dep
        assert scheduler._deps_satisfied(task) is True

    def test_get_status(self):
        scheduler = ResourceAwareScheduler()
        status = scheduler.get_status()
        assert "pending" in status
        assert "running" in status
        assert "completed" in status


class TestExecutionMode:
    """Test ExecutionMode enum."""

    def test_values(self):
        assert ExecutionMode.SEQUENTIAL.value == "sequential"
        assert ExecutionMode.PARALLEL.value == "parallel"
        assert ExecutionMode.PIPELINE.value == "pipeline"
        assert ExecutionMode.FAN_OUT.value == "fan_out"
        assert ExecutionMode.FAN_IN.value == "fan_in"


class TestTaskStatus:
    """Test TaskStatus enum."""

    def test_values(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.SCHEDULED.value == "scheduled"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"
        assert TaskStatus.TIMED_OUT.value == "timed_out"
