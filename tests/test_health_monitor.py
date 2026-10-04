"""Tests for Agent Health Monitor (spec 19)."""
import pytest

from app.agents.health_monitor import (
    AgentHealth,
    AgentHealthMonitor,
    AgentHealthStatus,
    get_monitor,
)


class TestAgentHealth:
    def test_initial_state(self):
        h = AgentHealth(agent_id="coding")
        assert h.agent_id == "coding"
        assert h.status == AgentHealthStatus.UNKNOWN
        assert h.total_tasks == 0
        assert h.is_available is False  # UNKNOWN is not available

    def test_record_success(self):
        h = AgentHealth(agent_id="coding")
        h.record_success(latency_ms=100.0, tokens_used=500)
        assert h.total_tasks == 1
        assert h.successful_tasks == 1
        assert h.failed_tasks == 0
        assert h.consecutive_failures == 0
        assert h.status == AgentHealthStatus.HEALTHY
        assert h.is_available is True
        assert h.total_tokens_used == 500

    def test_record_failure(self):
        h = AgentHealth(agent_id="coding")
        h.record_failure(error="timeout")
        assert h.total_tasks == 1
        assert h.failed_tasks == 1
        assert h.consecutive_failures == 1
        assert h.status == AgentHealthStatus.DEGRADED
        assert h.last_error == "timeout"

    def test_consecutive_failures_to_unhealthy(self):
        h = AgentHealth(agent_id="coding", max_consecutive_failures=3)
        h.record_failure("e1")
        h.record_failure("e2")
        assert h.status == AgentHealthStatus.DEGRADED
        h.record_failure("e3")
        assert h.status == AgentHealthStatus.UNHEALTHY
        assert h.is_available is False

    def test_success_resets_failures(self):
        h = AgentHealth(agent_id="coding")
        h.record_failure("e1")
        h.record_failure("e2")
        h.record_success()
        assert h.consecutive_failures == 0
        assert h.status == AgentHealthStatus.HEALTHY

    def test_success_rate(self):
        h = AgentHealth(agent_id="coding")
        assert h.success_rate == 1.0  # No tasks = 100%
        h.record_success()
        h.record_failure()
        assert h.success_rate == 0.5

    def test_avg_latency_ema(self):
        h = AgentHealth(agent_id="coding")
        h.record_success(latency_ms=100.0)
        assert h.avg_latency_ms == 100.0
        h.record_success(latency_ms=200.0)
        # EMA: 0.3 * 200 + 0.7 * 100 = 130
        assert abs(h.avg_latency_ms - 130.0) < 0.1

    def test_to_dict(self):
        h = AgentHealth(agent_id="coding")
        h.record_success(latency_ms=50.0, tokens_used=100)
        d = h.to_dict()
        assert d["agent_id"] == "coding"
        assert d["status"] == "healthy"
        assert d["total_tasks"] == 1
        assert d["is_available"] is True
        assert d["total_tokens_used"] == 100


class TestAgentHealthMonitor:
    @pytest.fixture
    def monitor(self):
        return AgentHealthMonitor()

    @pytest.mark.asyncio
    async def test_register(self, monitor):
        h = await monitor.register("coding")
        assert h.agent_id == "coding"
        assert h.status == AgentHealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_unregister(self, monitor):
        await monitor.register("coding")
        await monitor.unregister("coding")
        assert await monitor.get_health("coding") is None

    @pytest.mark.asyncio
    async def test_record_success(self, monitor):
        await monitor.register("coding")
        await monitor.record_success("coding", latency_ms=100.0, tokens_used=500)
        h = await monitor.get_health("coding")
        assert h.total_tasks == 1
        assert h.status == AgentHealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_record_failure(self, monitor):
        await monitor.register("coding")
        await monitor.record_failure("coding", error="timeout")
        h = await monitor.get_health("coding")
        assert h.failed_tasks == 1
        assert h.status == AgentHealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_get_available_agents(self, monitor):
        await monitor.register("coding")
        await monitor.register("research")
        await monitor.record_success("coding")
        # research is UNKNOWN, not available
        available = await monitor.get_available_agents()
        assert "coding" in available
        assert "research" not in available

    @pytest.mark.asyncio
    async def test_get_unhealthy_agents(self, monitor):
        await monitor.register("coding")
        await monitor.register("research")
        h = await monitor.get_health("coding")
        h.consecutive_failures = 5
        h._update_status()
        unhealthy = await monitor.get_unhealthy_agents()
        assert "coding" in unhealthy
        assert "research" not in unhealthy

    @pytest.mark.asyncio
    async def test_get_best_agent(self, monitor):
        await monitor.register("coding")
        await monitor.register("research")
        await monitor.record_success("coding", latency_ms=100.0)
        await monitor.record_success("research", latency_ms=50.0)
        best = await monitor.get_best_agent()
        assert best == "research"  # Lower latency

    @pytest.mark.asyncio
    async def test_snapshot(self, monitor):
        await monitor.register("coding")
        await monitor.record_success("coding")
        snap = monitor.snapshot()
        assert snap["total_agents"] == 1
        assert snap["available"] == 1
        assert snap["unhealthy"] == 0
        assert "coding" in snap["agents"]


class TestHelpers:
    def test_get_monitor_singleton(self):
        m1 = get_monitor()
        m2 = get_monitor()
        assert m1 is m2
