"""Tests for spec 26/27/28: result aggregation + conflict resolution."""

from __future__ import annotations

from app.brain.aggregator import (
    AgentEnvelope,
    ConflictKind,
    ConflictResolver,
    ResultAggregator,
    VerificationStatus,
)


def _env(agent: str, result: str, **kw) -> AgentEnvelope:
    return AgentEnvelope(agent_id=agent, result=result, status=kw.pop("status", "completed"), **kw)


def test_aggregate_dedupes_and_ranks() -> None:
    """Near-identical results collapse; highest confidence becomes primary."""
    agg = ResultAggregator().aggregate([
        _env("coding", "the answer is 42", confidence=0.5, evidence=["ran test"]),
        _env("qa", "The answer is 42.", confidence=0.9, evidence=["pytest 5 passed"]),
        _env("review", "completely different take", confidence=0.6),
    ])
    assert agg.duplicates_removed == 1
    assert agg.primary == "The answer is 42."
    assert "pytest 5 passed" in agg.evidence
    assert set(agg.contributing_agents) == {"qa", "review"}


def test_conflict_failure_vs_success_is_never_verified() -> None:
    """Spec 27 worked example: coding says fixed, testing says tests fail."""
    agg = ResultAggregator().aggregate([
        _env("coding", "Bug fixed.", evidence=["edited app/x.py"]),
        AgentEnvelope(agent_id="testing", result="", status="failed",
                      errors=["tests still fail: 3 errors"]),
    ])
    assert agg.has_conflict
    assert any(c.kind == ConflictKind.FAILURE for c in agg.conflicts)
    # The Main Brain must NOT be told success.
    assert agg.status in (VerificationStatus.PARTIALLY_VERIFIED, VerificationStatus.UNVERIFIED)
    assert "testing" in agg.failed_agents


def test_contradiction_opposite_polarity_detected() -> None:
    agg = ResultAggregator().aggregate([
        _env("a", "the service is running and healthy", confidence=0.8, evidence=["curl 200"]),
        _env("b", "the service is not running, it is down", confidence=0.8, evidence=["curl failed"]),
    ])
    assert any(c.kind == ConflictKind.CONTRADICTION for c in agg.conflicts)


def test_no_conflict_when_agents_agree() -> None:
    agg = ResultAggregator().aggregate([
        _env("a", "the capital of France is Paris", confidence=0.9, evidence=["src1"]),
        _env("b", "The capital of France is Paris.", confidence=0.9, evidence=["src2"]),
    ])
    assert not agg.has_conflict
    assert agg.status == VerificationStatus.VERIFIED


def test_evidence_required_for_verified() -> None:
    """A confident claim with no evidence cannot be VERIFIED (spec 28)."""
    agg = ResultAggregator().aggregate([_env("a", "trust me", confidence=1.0)])
    assert agg.status == VerificationStatus.PARTIALLY_VERIFIED


def test_empty_results_fail() -> None:
    agg = ResultAggregator().aggregate([])
    assert agg.status == VerificationStatus.FAILED
    assert agg.primary == ""


def test_resolver_directive_requests_verification_on_contradiction() -> None:
    envs = [
        _env("a", "the patch fixes the vulnerability", confidence=0.9, evidence=["scan"]),
        _env("b", "the vulnerability is not fixed, still exploitable", confidence=0.9, evidence=["scan2"]),
    ]
    agg = ResultAggregator().aggregate(envs)
    directive = ConflictResolver().resolve(agg, envs)
    assert directive["requires_verification"] is True
    assert set(directive["request_from"]) == {"a", "b"}


def test_envelope_serialisation_is_protocol_shaped() -> None:
    d = _env("coding", "ok", task_id="t1", evidence=["e"], confidence=0.7).to_dict()
    for field in ("task_id", "agent_id", "status", "result", "evidence", "errors",
                  "warnings", "artifacts", "confidence", "next_action", "message_type"):
        assert field in d
