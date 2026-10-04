"""Tests for advanced conflict resolution — AdvancedConflictResolver."""

from __future__ import annotations

import pytest

from app.brain.advanced_conflict import (
    AdvancedConflictResolver,
    AdvancedConflict,
    AdjudicationResult,
    ConflictResolutionStrategy,
    ConflictSeverity,
    Evidence,
)
from app.brain.aggregator import (
    AgentEnvelope,
    AggregatedResult,
    Conflict,
    ConflictKind,
    ConflictResolver,
    ResultAggregator,
)


class TestConflictResolutionStrategy:
    """Test ConflictResolutionStrategy enum."""

    def test_values(self):
        assert ConflictResolutionStrategy.EVIDENCE_BASED.value == "evidence_based"
        assert ConflictResolutionStrategy.CONSENSUS.value == "consensus"
        assert ConflictResolutionStrategy.LLM_ADJUDICATION.value == "llm_adjudication"


class TestConflictSeverity:
    """Test ConflictSeverity enum."""

    def test_values(self):
        assert ConflictSeverity.CRITICAL.value == "critical"
        assert ConflictSeverity.HIGH.value == "high"
        assert ConflictSeverity.MEDIUM.value == "medium"
        assert ConflictSeverity.LOW.value == "low"
        assert ConflictSeverity.NONE.value == "none"


class TestEvidence:
    """Test Evidence dataclass."""

    def test_creation(self):
        ev = Evidence(
            source="agent_a",
            content="The sky is blue",
            confidence=0.9,
        )
        assert ev.source == "agent_a"
        assert ev.content == "The sky is blue"
        assert ev.confidence == 0.9


class TestAdvancedConflict:
    """Test AdvancedConflict dataclass."""

    def test_creation(self):
        base = Conflict(
            kind=ConflictKind.CONTRADICTION,
            agents=["agent_a", "agent_b"],
            detail="Contradiction detected",
        )
        ac = AdvancedConflict(
            base_conflict=base,
            severity=ConflictSeverity.HIGH,
            evidence_a=[Evidence(source="agent_a", content="A")],
            evidence_b=[Evidence(source="agent_b", content="B")],
        )
        assert ac.base_conflict.kind == ConflictKind.CONTRADICTION
        assert ac.severity == ConflictSeverity.HIGH
        assert ac.resolved is False
        assert ac.adjudication is None
        assert ac.resolution_strategy is None


class TestAdjudicationResult:
    """Test AdjudicationResult dataclass."""

    def test_creation(self):
        result = AdjudicationResult(
            winner="agent_a",
            loser="agent_b",
            reasoning="Higher confidence and more evidence",
            confidence=0.85,
        )
        assert result.winner == "agent_a"
        assert result.confidence == 0.85


class TestAdvancedConflictResolver:
    """Test AdvancedConflictResolver."""

    def test_creation_with_defaults(self):
        resolver = AdvancedConflictResolver()
        assert resolver._default_strategy == ConflictResolutionStrategy.EVIDENCE_BASED
        assert resolver._brain is None

    def test_creation_with_custom_strategy(self):
        resolver = AdvancedConflictResolver(
            default_strategy=ConflictResolutionStrategy.CONSENSUS,
        )
        assert resolver._default_strategy == ConflictResolutionStrategy.CONSENSUS

    def test_detect_advanced_empty(self):
        resolver = AdvancedConflictResolver()
        conflicts = resolver.detect_advanced([])
        assert conflicts == []

    def test_detect_advanced_no_conflict(self):
        resolver = AdvancedConflictResolver()
        envelopes = [
            AgentEnvelope(
                task_id="test",
                agent_id="agent_a",
                result="The sky is blue",
                evidence=["Scientific fact"],
                confidence=0.9,
            ),
        ]
        conflicts = resolver.detect_advanced(envelopes)
        assert isinstance(conflicts, list)

    def test_detect_advanced_with_contradiction(self):
        resolver = AdvancedConflictResolver()
        envelopes = [
            AgentEnvelope(
                task_id="test",
                agent_id="agent_a",
                result="The answer is 42",
                evidence=["Calculation"],
                confidence=0.9,
            ),
            AgentEnvelope(
                task_id="test",
                agent_id="agent_b",
                result="The answer is not 42",
                evidence=["Different calculation"],
                confidence=0.9,
            ),
        ]
        conflicts = resolver.detect_advanced(envelopes)
        assert isinstance(conflicts, list)

    def test_choose_strategy_evidence_based(self):
        resolver = AdvancedConflictResolver(
            default_strategy=ConflictResolutionStrategy.EVIDENCE_BASED,
        )
        base = Conflict(
            kind=ConflictKind.CONTRADICTION,
            agents=["agent_a", "agent_b"],
            detail="Test",
        )
        ac = AdvancedConflict(
            base_conflict=base,
            severity=ConflictSeverity.HIGH,
            evidence_a=[Evidence(source="agent_a", content="A")],
            evidence_b=[Evidence(source="agent_b", content="B")],
        )
        strategy = resolver._choose_strategy(ac)
        assert strategy == ConflictResolutionStrategy.EVIDENCE_BASED

    def test_choose_strategy_critical(self):
        resolver = AdvancedConflictResolver(
            default_strategy=ConflictResolutionStrategy.EVIDENCE_BASED,
        )
        base = Conflict(
            kind=ConflictKind.CONTRADICTION,
            agents=["agent_a", "agent_b"],
            detail="Test",
        )
        ac = AdvancedConflict(
            base_conflict=base,
            severity=ConflictSeverity.CRITICAL,
        )
        strategy = resolver._choose_strategy(ac)
        assert strategy == ConflictResolutionStrategy.LLM_ADJUDICATION

    def test_assess_severity_high(self):
        resolver = AdvancedConflictResolver()
        base = Conflict(
            kind=ConflictKind.CONTRADICTION,
            agents=["agent_a", "agent_b"],
            detail="Test",
        )
        envelopes = [
            AgentEnvelope(
                task_id="test",
                agent_id="agent_a",
                result="A",
                confidence=0.7,
            ),
            AgentEnvelope(
                task_id="test",
                agent_id="agent_b",
                result="B",
                confidence=0.7,
            ),
        ]
        severity = resolver._assess_severity(base, envelopes)
        assert severity == ConflictSeverity.HIGH

    def test_assess_severity_medium(self):
        resolver = AdvancedConflictResolver()
        base = Conflict(
            kind=ConflictKind.DIVERGENCE,
            agents=["agent_a", "agent_b"],
            detail="Test",
            severity=0.8,
        )
        envelopes = [
            AgentEnvelope(
                task_id="test",
                agent_id="agent_a",
                result="A",
                confidence=0.7,
            ),
            AgentEnvelope(
                task_id="test",
                agent_id="agent_b",
                result="B",
                confidence=0.7,
            ),
        ]
        severity = resolver._assess_severity(base, envelopes)
        assert severity == ConflictSeverity.MEDIUM

    def test_collect_evidence(self):
        resolver = AdvancedConflictResolver()
        envelopes = [
            AgentEnvelope(
                task_id="test",
                agent_id="agent_a",
                result="A",
                evidence=["Evidence 1", "Evidence 2"],
                confidence=0.9,
            ),
        ]
        evidence = resolver._collect_evidence("agent_a", envelopes)
        assert len(evidence) == 2
        assert evidence[0].source == "agent_a"

    def test_evidence_based_resolve(self):
        resolver = AdvancedConflictResolver()
        base = Conflict(
            kind=ConflictKind.CONTRADICTION,
            agents=["agent_a", "agent_b"],
            detail="Test",
        )
        ac = AdvancedConflict(
            base_conflict=base,
            severity=ConflictSeverity.HIGH,
            evidence_a=[Evidence(source="agent_a", content="A", confidence=0.9)],
            evidence_b=[Evidence(source="agent_b", content="B", confidence=0.3)],
        )
        result = resolver._evidence_based_resolve(ac)
        assert result is not None
        assert result == "agent_a"

    def test_merge_answers(self):
        resolver = AdvancedConflictResolver()
        base = Conflict(
            kind=ConflictKind.CONTRADICTION,
            agents=["agent_a", "agent_b"],
            detail="Test",
        )
        ac = AdvancedConflict(
            base_conflict=base,
            severity=ConflictSeverity.LOW,
        )
        envelopes = [
            AgentEnvelope(
                task_id="test",
                agent_id="agent_a",
                result="Answer A",
                confidence=0.7,
            ),
            AgentEnvelope(
                task_id="test",
                agent_id="agent_b",
                result="Answer B",
                confidence=0.7,
            ),
        ]
        result = resolver._merge_answers(ac, envelopes)
        assert result is not None
        assert "Answer A" in result
        assert "Answer B" in result

    def test_metrics(self):
        resolver = AdvancedConflictResolver()
        metrics = resolver.metrics
        assert isinstance(metrics, dict)
