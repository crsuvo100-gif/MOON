"""Tests for Result Synthesis Pipeline (spec 39)."""
import pytest

from app.brain.synthesis import (
    ResultSynthesisPipeline,
    SynthesisResult,
    SynthesisStage,
    create_default_pipeline,
    normalize_results,
    extract_evidence,
    detect_conflicts,
    verify_results,
    synthesize_final,
)


class TestSynthesisStage:
    def test_all_stages_exist(self):
        expected = {
            "RAW_RESULTS", "NORMALIZATION", "EVIDENCE_EXTRACTION",
            "CONFLICT_DETECTION", "VERIFICATION", "SYNTHESIS", "FINAL_RESPONSE",
        }
        actual = {s.name for s in SynthesisStage}
        assert expected == actual


class TestNormalizeResults:
    def test_normalize(self):
        ctx = {
            "raw_results": [
                {"agent_id": "coding", "result": "Fixed", "confidence": 0.9, "evidence": ["test"]},
                {"agent_id": "testing", "result": "Pass", "confidence": 0.8, "evidence": ["pytest"]},
            ]
        }
        result = normalize_results(ctx)
        assert len(result["normalized_results"]) == 2
        assert result["normalized_results"][0]["agent_id"] == "coding"
        assert result["normalized_results"][0]["confidence"] == 0.9


class TestExtractEvidence:
    def test_extract(self):
        ctx = {
            "normalized_results": [
                {"agent_id": "a", "evidence": ["e1", "e2"]},
                {"agent_id": "b", "evidence": ["e2", "e3"]},
            ]
        }
        result = extract_evidence(ctx)
        assert len(result["evidence"]) == 3
        assert "e1" in result["evidence"]
        assert "e2" in result["evidence"]
        assert "e3" in result["evidence"]


class TestDetectConflicts:
    def test_no_conflict(self):
        ctx = {
            "normalized_results": [
                {"agent_id": "a", "result": "Fixed"},
                {"agent_id": "b", "result": "Confirmed"},
            ]
        }
        result = detect_conflicts(ctx)
        assert len(result["conflicts"]) == 0

    def test_detects_contradiction(self):
        ctx = {
            "normalized_results": [
                {"agent_id": "coding", "result": "Bug fixed"},
                {"agent_id": "testing", "result": "Tests failed"},
            ]
        }
        result = detect_conflicts(ctx)
        assert len(result["conflicts"]) == 1
        assert result["conflicts"][0]["type"] == "contradiction"


class TestVerifyResults:
    def test_no_results(self):
        ctx = {"normalized_results": [], "evidence": [], "conflicts": []}
        result = verify_results(ctx)
        assert result["verification_status"] == "failed"

    def test_conflicts(self):
        ctx = {
            "normalized_results": [{"agent_id": "a", "result": "x", "evidence": ["e"]}],
            "evidence": ["e"],
            "conflicts": [{"agents": ["a", "b"]}],
        }
        result = verify_results(ctx)
        assert result["verification_status"] == "partially_verified"

    def test_verified(self):
        ctx = {
            "normalized_results": [
                {"agent_id": "a", "result": "x", "evidence": ["e"]},
            ],
            "evidence": ["e"],
            "conflicts": [],
        }
        result = verify_results(ctx)
        assert result["verification_status"] == "verified"


class TestSynthesizeFinal:
    def test_synthesize(self):
        ctx = {
            "normalized_results": [
                {"agent_id": "coding", "result": "Fixed bug", "confidence": 0.9},
                {"agent_id": "testing", "result": "Tests pass", "confidence": 0.8},
            ],
            "evidence": ["test passed"],
            "conflicts": [],
            "query": "Fix the bug",
        }
        result = synthesize_final(ctx)
        assert "Fixed bug" in result["final_response"]
        assert "coding" in result["contributing_agents"]
        assert "testing" in result["contributing_agents"]

    def test_empty_results(self):
        ctx = {"normalized_results": [], "evidence": [], "conflicts": [], "query": ""}
        result = synthesize_final(ctx)
        assert result["final_response"] == "No results to synthesize."


class TestResultSynthesisPipeline:
    @pytest.fixture
    def pipeline(self):
        return create_default_pipeline()

    @pytest.mark.asyncio
    async def test_execute(self, pipeline):
        raw = [
            {"agent_id": "coding", "result": "Fixed", "confidence": 0.9, "evidence": ["test"]},
            {"agent_id": "testing", "result": "Pass", "confidence": 0.8, "evidence": ["pytest"]},
        ]
        result = await pipeline.execute(raw, query="Fix bug")
        assert isinstance(result, SynthesisResult)
        assert len(result.stages_completed) > 0
        assert result.verification_status in ("verified", "partially_verified")
        assert "Fixed" in result.final_response

    @pytest.mark.asyncio
    async def test_execute_empty(self, pipeline):
        result = await pipeline.execute([], query="test")
        assert isinstance(result, SynthesisResult)
        assert result.final_response == "No results to synthesize."

    def test_custom_stage(self):
        pipeline = ResultSynthesisPipeline()
        pipeline.add_stage("custom", lambda ctx: {"custom_key": "custom_value"})
        assert len(pipeline._stages) == 1


class TestSynthesisResult:
    def test_to_dict(self):
        r = SynthesisResult(
            final_response="test",
            stages_completed=["a", "b"],
            verification_status="verified",
            contributing_agents=["coding"],
        )
        d = r.to_dict()
        assert d["final_response"] == "test"
        assert d["verification_status"] == "verified"
        assert "coding" in d["contributing_agents"]
