"""Tests for End-to-End Multi-Agent Verification (spec 56)."""
import pytest

from app.brain.e2e_verification import (
    E2EVerificationPipeline,
    E2EVerificationResult,
    PipelineStageResult,
    PipelineStageStatus,
)


class TestPipelineStageStatus:
    def test_all_statuses(self):
        expected = {"pending", "running", "completed", "failed", "skipped"}
        actual = {s.value for s in PipelineStageStatus}
        assert expected == actual


class TestPipelineStageResult:
    def test_create(self):
        r = PipelineStageResult(name="test_stage")
        assert r.name == "test_stage"
        assert r.status == PipelineStageStatus.PENDING
        assert r.duration == 0.0

    def test_to_dict(self):
        r = PipelineStageResult(
            name="test",
            status=PipelineStageStatus.COMPLETED,
            result="ok",
        )
        d = r.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "completed"
        assert d["result"] == "ok"


class TestE2EVerificationResult:
    def test_to_dict(self):
        r = E2EVerificationResult(
            task="test task",
            success=True,
            final_response="done",
            evidence=["e1"],
        )
        d = r.to_dict()
        assert d["task"] == "test task"
        assert d["success"] is True
        assert d["final_response"] == "done"
        assert "e1" in d["evidence"]


class TestE2EVerificationPipeline:
    @pytest.fixture
    def pipeline(self):
        return E2EVerificationPipeline()

    @pytest.mark.asyncio
    async def test_verify_with_mock_orchestrator(self, pipeline):
        """Test with a mock orchestrator that has the expected attributes."""

        class MockOrchestrator:
            def __init__(self):
                self._agents = {"coding": object(), "testing": object()}
                self._tool_manager = type("TM", (), {"_tools": {"a": 1, "b": 2}})()

            def _split_subtasks(self, task):
                return ["subtask1", "subtask2"]

        result = await pipeline.verify(
            orchestrator=MockOrchestrator(),
            task="Fix the bug",
            agents=["coding", "testing"],
        )
        assert isinstance(result, E2EVerificationResult)
        assert result.task == "Fix the bug"
        assert len(result.stages) > 0
        # At least some stages should complete
        completed = [s for s in result.stages if s.status == PipelineStageStatus.COMPLETED]
        assert len(completed) > 0

    @pytest.mark.asyncio
    async def test_verify_without_orchestrator(self, pipeline):
        result = await pipeline.verify(
            orchestrator=None,
            task="test",
        )
        assert isinstance(result, E2EVerificationResult)
        assert result.success is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_verify_stages_present(self, pipeline):
        class MockOrchestrator:
            _agents = {}
            _tool_manager = None

            def _split_subtasks(self, task):
                return ["s1"]

        result = await pipeline.verify(
            orchestrator=MockOrchestrator(),
            task="test",
            agents=["coding"],
        )
        stage_names = [s.name for s in result.stages]
        # Should have these stages
        assert "main_brain_receive" in stage_names
        assert "task_planning" in stage_names
        assert "agent_selection" in stage_names
