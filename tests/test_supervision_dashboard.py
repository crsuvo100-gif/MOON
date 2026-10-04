"""Tests for Agent Supervision Dashboard (spec 41)."""
import pytest

from app.agents.supervision_dashboard import (
    AgentDashboardEntry,
    AgentStatus,
    AgentSupervisionDashboard,
    DashboardState,
    get_dashboard,
)


class TestAgentStatus:
    def test_all_statuses_exist(self):
        expected = {
            "idle", "planning", "executing", "waiting",
            "verifying", "completed", "failed", "cancelled",
        }
        actual = {s.value for s in AgentStatus}
        assert expected == actual


class TestAgentDashboardEntry:
    def test_create(self):
        e = AgentDashboardEntry(agent_id="coding", brain="ollama/llama3.1")
        assert e.agent_id == "coding"
        assert e.brain == "ollama/llama3.1"
        assert e.status == AgentStatus.IDLE

    def test_to_dict(self):
        e = AgentDashboardEntry(agent_id="coding", brain="test")
        d = e.to_dict()
        assert d["agent_id"] == "coding"
        assert d["brain"] == "test"
        assert d["status"] == "idle"


class TestAgentSupervisionDashboard:
    @pytest.fixture
    def dash(self):
        return AgentSupervisionDashboard()

    def test_update_main_brain(self, dash):
        dash.update_main_brain("planning", task="Fix bug")
        assert dash._state.main_brain_status == "planning"
        assert dash._state.main_brain_task == "Fix bug"

    def test_register_agent(self, dash):
        entry = dash.register_agent("coding", brain="ollama/llama3.1")
        assert entry.agent_id == "coding"
        assert entry.brain == "ollama/llama3.1"

    def test_update_agent(self, dash):
        dash.register_agent("coding")
        dash.update_agent(
            "coding",
            status=AgentStatus.EXECUTING,
            current_tool="terminal",
            progress="50%",
        )
        entry = dash._state.agents["coding"]
        assert entry.status == AgentStatus.EXECUTING
        assert entry.current_tool == "terminal"
        assert entry.progress == "50%"

    def test_set_verification_status(self, dash):
        dash.set_verification_status("verified")
        assert dash._state.verification_status == "verified"

    def test_set_final_result(self, dash):
        dash.set_final_result("Task complete")
        assert dash._state.final_result == "Task complete"

    def test_add_error(self, dash):
        dash.add_error("Tool failed")
        assert len(dash._state.errors) == 1

    def test_add_permission(self, dash):
        dash.add_permission("terminal:execute")
        assert len(dash._state.permissions) == 1

    def test_snapshot(self, dash):
        dash.register_agent("coding", brain="test")
        dash.update_main_brain("planning")
        snap = dash.snapshot()
        assert snap["main_brain_status"] == "planning"
        assert "coding" in snap["agents"]

    def test_render_text(self, dash):
        dash.register_agent("coding", brain="ollama/llama3.1")
        dash.update_agent("coding", status=AgentStatus.EXECUTING, current_tool="terminal")
        dash.update_main_brain("planning", task="Fix bug")
        text = dash.render_text()
        assert "MOON MULTI-AGENT SUPERVISION DASHBOARD" in text
        assert "coding" in text
        assert "planning" in text
        assert "Fix bug" in text

    def test_render_text_no_agents(self, dash):
        text = dash.render_text()
        assert "No agents registered" in text


class TestHelpers:
    def test_get_dashboard_singleton(self):
        d1 = get_dashboard()
        d2 = get_dashboard()
        assert d1 is d2
