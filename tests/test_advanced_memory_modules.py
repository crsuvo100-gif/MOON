"""Tests for advanced memory modules — reasoning, conflict resolution,
importance scoring, temporal reasoning, lifecycle, summarization,
clustering, and recommendations."""

from __future__ import annotations

import time

import pytest

from app.memory.advanced.reasoning import (
    MemoryReasoningEngine,
    ReasoningResult,
    ReasoningChain,
)
from app.memory.advanced.conflict_resolver import (
    ConflictResolver,
    Conflict,
    Resolution,
)
from app.memory.advanced.importance_scorer import (
    ImportanceScorer,
    ImportanceScore,
)
from app.memory.advanced.temporal_reasoning import (
    TemporalReasoner,
    TemporalFact,
    TemporalDiff,
)
from app.memory.advanced.lifecycle import (
    LifecycleManager,
    LifecycleAction,
    LifecycleReport,
)
from app.memory.advanced.summarization import (
    MemorySummarizer,
    MemorySummary,
)
from app.memory.advanced.clustering import (
    MemoryClustering,
    MemoryCluster,
)
from app.memory.advanced.recommendation import (
    MemoryRecommender,
    MemoryRecommendation,
)


# ── Reasoning Engine Tests ──

class TestReasoningResult:
    def test_creation(self):
        r = ReasoningResult(
            conclusion="The API uses JWT tokens",
            reasoning_type="deductive",
            confidence=0.85,
            premises=["All APIs use auth", "This is an API"],
        )
        assert r.conclusion == "The API uses JWT tokens"
        assert r.reasoning_type == "deductive"
        assert r.confidence == 0.85
        assert len(r.premises) == 2

    def test_to_dict(self):
        r = ReasoningResult(
            conclusion="Test",
            reasoning_type="inductive",
            confidence=0.7,
        )
        d = r.to_dict()
        assert d["conclusion"] == "Test"
        assert d["reasoning_type"] == "inductive"
        assert d["confidence"] == 0.7


class TestReasoningChain:
    def test_creation(self):
        steps = [
            ReasoningResult("Step 1", "deductive", 0.9),
            ReasoningResult("Step 2", "deductive", 0.8),
        ]
        chain = ReasoningChain(
            steps=steps,
            final_conclusion="Final answer",
            overall_confidence=0.85,
        )
        assert len(chain.steps) == 2
        assert chain.final_conclusion == "Final answer"
        assert chain.overall_confidence == 0.85


class TestMemoryReasoningEngine:
    def test_creation(self):
        engine = MemoryReasoningEngine()
        assert engine._reasoning_count == 0

    def test_reason_deductive(self):
        engine = MemoryReasoningEngine()
        results = engine.reason("All authenticated endpoints require JWT tokens", mode="deductive")
        assert isinstance(results, list)

    def test_reason_inductive(self):
        engine = MemoryReasoningEngine()
        results = engine.reason("User login failed with 401", mode="inductive")
        assert isinstance(results, list)

    def test_reason_abductive(self):
        engine = MemoryReasoningEngine()
        results = engine.reason("The API returned 500 errors", mode="abductive")
        assert isinstance(results, list)

    def test_reason_chain(self):
        engine = MemoryReasoningEngine()
        chain = engine.reason_chain("Is this a recurring problem?")
        assert isinstance(chain, ReasoningChain)
        assert chain.overall_confidence >= 0.0

    def test_stats(self):
        engine = MemoryReasoningEngine()
        engine.reason("test query", mode="deductive")
        stats = engine.stats()
        assert stats["reasoning_count"] == 1


# ── Conflict Resolver Tests ──

class TestConflict:
    def test_creation(self):
        c = Conflict(
            memory_id_a="mem_1",
            memory_id_b="mem_2",
            content_a="The sky is blue",
            content_b="The sky is green",
            conflict_type="contradiction",
            severity=0.8,
        )
        assert c.memory_id_a == "mem_1"
        assert c.memory_id_b == "mem_2"
        assert c.conflict_type == "contradiction"


class TestResolution:
    def test_creation(self):
        conflict = Conflict("mem_1", "mem_2", "A", "B", "contradiction", 0.5)
        r = Resolution(
            conflict=conflict,
            strategy="newest",
            winner_id="mem_2",
            loser_id="mem_1",
        )
        assert r.strategy == "newest"
        assert r.winner_id == "mem_2"


class TestConflictResolver:
    def test_creation(self):
        resolver = ConflictResolver()
        assert resolver._conflict_count == 0
        assert resolver._resolution_count == 0

    def test_detect_conflicts_no_manager(self):
        resolver = ConflictResolver()
        conflicts = resolver.detect_conflicts(query="test")
        assert conflicts == []

    def test_detect_conflicts_with_query(self):
        resolver = ConflictResolver()
        conflicts = resolver.detect_conflicts(query="API endpoint")
        assert isinstance(conflicts, list)

    def test_resolve_conflicts_empty(self):
        resolver = ConflictResolver()
        resolutions = resolver.resolve_conflicts([], strategy="newest")
        assert resolutions == []

    def test_resolve_conflicts_with_conflicts(self):
        resolver = ConflictResolver()
        conflict = Conflict(
            memory_id_a="1",
            memory_id_b="2",
            content_a="Old value",
            content_b="New value",
            conflict_type="contradiction",
            severity=0.8,
        )
        resolutions = resolver.resolve_conflicts([conflict], strategy="newest")
        assert len(resolutions) == 1
        assert resolutions[0].strategy == "newest"
        assert resolutions[0].winner_id is not None

    def test_auto_resolve_no_manager(self):
        resolver = ConflictResolver()
        resolutions = resolver.auto_resolve(query="test")
        assert isinstance(resolutions, list)

    def test_stats(self):
        resolver = ConflictResolver()
        conflict = Conflict("1", "2", "A", "B", "contradiction", 0.5)
        resolver.resolve_conflicts([conflict], strategy="newest")
        stats = resolver.stats()
        assert stats["conflicts_resolved"] == 1


# ── Importance Scorer Tests ──

class TestImportanceScore:
    def test_creation(self):
        s = ImportanceScore(
            memory_id="mem_1",
            overall=0.85,
        )
        assert s.memory_id == "mem_1"
        assert s.overall == 0.85

    def test_to_dict(self):
        s = ImportanceScore(memory_id="1", overall=0.5)
        d = s.to_dict()
        assert d["memory_id"] == "1"
        assert d["overall"] == 0.5


class TestImportanceScorer:
    def test_creation(self):
        scorer = ImportanceScorer()
        assert scorer._score_count == 0

    def test_score_memory_no_manager(self):
        scorer = ImportanceScorer()
        result = scorer.score_memory("nonexistent")
        assert result is None

    def test_rank_memories_no_manager(self):
        scorer = ImportanceScorer()
        ranked = scorer.rank_memories()
        assert ranked == []

    def test_get_important_memories_no_manager(self):
        scorer = ImportanceScorer()
        result = scorer.get_important_memories()
        assert result == []

    def test_get_important_tags(self):
        scorer = ImportanceScorer()
        tags = scorer.get_important_tags()
        assert isinstance(tags, list)
        assert "security" in tags

    def test_stats(self):
        scorer = ImportanceScorer()
        stats = scorer.stats()
        assert "score_count" in stats
        assert "weights" in stats


# ── Temporal Reasoner Tests ──

class TestTemporalFact:
    def test_creation(self):
        f = TemporalFact(
            content="The API was deployed",
            valid_from=time.time() - 86400,
            confidence=0.9,
        )
        assert f.content == "The API was deployed"
        assert f.is_current is True

    def test_is_current_past(self):
        f = TemporalFact(
            content="Old fact",
            valid_from=time.time() - 86400 * 10,
            valid_until=time.time() - 86400 * 5,
        )
        assert f.is_current is False

    def test_is_current_future(self):
        f = TemporalFact(
            content="Future fact",
            valid_from=time.time() + 86400,
            valid_until=time.time() + 86400 * 2,
        )
        assert f.is_current is False


class TestTemporalDiff:
    def test_creation(self):
        d = TemporalDiff(
            added=["New memory"],
            removed=["Old memory"],
            changed=[{"content": "Changed memory"}],
        )
        assert len(d.added) == 1
        assert len(d.removed) == 1
        assert len(d.changed) == 1


class TestTemporalReasoner:
    def test_creation(self):
        reasoner = TemporalReasoner()
        assert reasoner._reasoning_count == 0

    def test_at_time_no_manager(self):
        reasoner = TemporalReasoner()
        facts = reasoner.at_time("test query", timestamp=time.time())
        assert facts == []

    def test_diff_no_manager(self):
        reasoner = TemporalReasoner()
        diff = reasoner.diff("test query", start=time.time() - 86400, end=time.time())
        assert isinstance(diff, TemporalDiff)

    def test_is_valid_no_manager(self):
        reasoner = TemporalReasoner()
        result = reasoner.is_valid("The API uses OAuth2")
        assert result["valid"] is None

    def test_get_timeline_no_manager(self):
        reasoner = TemporalReasoner()
        timeline = reasoner.get_timeline("test query")
        assert timeline == []

    def test_predict_changes_no_manager(self):
        reasoner = TemporalReasoner()
        predictions = reasoner.predict_changes("test query")
        assert predictions == []

    def test_stats(self):
        reasoner = TemporalReasoner()
        reasoner.at_time("test", timestamp=time.time())
        stats = reasoner.stats()
        assert stats["reasoning_count"] == 1


# ── Lifecycle Manager Tests ──

class TestLifecycleAction:
    def test_creation(self):
        a = LifecycleAction(
            memory_id="mem_1",
            action="promote",
            reason="High access count",
        )
        assert a.memory_id == "mem_1"
        assert a.action == "promote"

    def test_to_dict(self):
        a = LifecycleAction(memory_id="1", action="decay", reason="Old")
        d = a.to_dict()
        assert d["memory_id"] == "1"
        assert d["action"] == "decay"


class TestLifecycleReport:
    def test_creation(self):
        r = LifecycleReport()
        assert r.promoted == 0
        assert r.decayed == 0
        assert r.total_processed == 0

    def test_to_dict(self):
        r = LifecycleReport(promoted=5, decayed=3)
        d = r.to_dict()
        assert d["promoted"] == 5
        assert d["decayed"] == 3


class TestLifecycleManager:
    def test_creation(self):
        mgr = LifecycleManager()
        assert mgr._total_actions == 0

    def test_promote_candidates_no_manager(self):
        mgr = LifecycleManager()
        report = mgr.promote_candidates()
        assert isinstance(report, LifecycleReport)
        assert report.promoted == 0

    def test_decay_unused_no_manager(self):
        mgr = LifecycleManager()
        report = mgr.decay_unused()
        assert isinstance(report, LifecycleReport)
        assert report.decayed == 0

    def test_archive_old_no_manager(self):
        mgr = LifecycleManager()
        report = mgr.archive_old()
        assert isinstance(report, LifecycleReport)
        assert report.archived == 0

    def test_delete_useless_no_manager(self):
        mgr = LifecycleManager()
        report = mgr.delete_useless()
        assert isinstance(report, LifecycleReport)
        assert report.deleted == 0

    def test_consolidate_related_no_manager(self):
        mgr = LifecycleManager()
        report = mgr.consolidate_related()
        assert isinstance(report, LifecycleReport)
        assert report.consolidated == 0

    def test_run_full_lifecycle_no_manager(self):
        mgr = LifecycleManager()
        report = mgr.run_full_lifecycle()
        assert isinstance(report, LifecycleReport)
        assert report.total_processed == 0

    def test_stats(self):
        mgr = LifecycleManager()
        stats = mgr.stats()
        assert "total_actions" in stats
        assert "promote_threshold" in stats


# ── Memory Summarizer Tests ──

class TestMemorySummary:
    def test_creation(self):
        s = MemorySummary(
            topic="API Authentication",
            summary="The API uses JWT tokens",
            key_points=["JWT tokens", "Refresh flow"],
            memory_count=5,
        )
        assert s.topic == "API Authentication"
        assert s.memory_count == 5

    def test_to_dict(self):
        s = MemorySummary(topic="Test", summary="Summary")
        d = s.to_dict()
        assert d["topic"] == "Test"
        assert d["summary"] == "Summary"


class TestMemorySummarizer:
    def test_creation(self):
        summarizer = MemorySummarizer()
        assert summarizer._summary_count == 0

    def test_summarize_topic_no_manager(self):
        summarizer = MemorySummarizer()
        summary = summarizer.summarize_topic("API auth")
        assert isinstance(summary, MemorySummary)
        assert summary.topic == "API auth"

    def test_summarize_time_range_no_manager(self):
        summarizer = MemorySummarizer()
        summary = summarizer.summarize_time_range(
            start=time.time() - 86400,
            end=time.time(),
        )
        assert isinstance(summary, MemorySummary)

    def test_summarize_agent_no_manager(self):
        summarizer = MemorySummarizer()
        summary = summarizer.summarize_agent("agent_1")
        assert isinstance(summary, MemorySummary)

    def test_summarize_project_no_manager(self):
        summarizer = MemorySummarizer()
        summary = summarizer.summarize_project("proj_1")
        assert isinstance(summary, MemorySummary)

    def test_executive_summary_no_manager(self):
        summarizer = MemorySummarizer()
        summary = summarizer.executive_summary()
        assert isinstance(summary, MemorySummary)
        assert summary.topic == "Executive Summary"

    def test_extractive_summary(self):
        summarizer = MemorySummarizer()
        contents = [
            "The API uses JWT tokens for authentication. This is critical.",
            "Users must refresh tokens every 24 hours.",
        ]
        summary = summarizer._extractive_summary(contents, max_sentences=2)
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_extract_key_points(self):
        summarizer = MemorySummarizer()
        contents = [
            "Important: The API requires authentication.",
            "Critical: Use HTTPS for all requests.",
        ]
        points = summarizer._extract_key_points(contents, max_points=5)
        assert isinstance(points, list)

    def test_stats(self):
        summarizer = MemorySummarizer()
        summarizer.summarize_topic("test")
        stats = summarizer.stats()
        assert stats["summary_count"] == 1


# ── Memory Clustering Tests ──

class TestMemoryCluster:
    def test_creation(self):
        c = MemoryCluster(
            cluster_id="cluster_1",
            label="API Auth",
            memory_ids=["mem_1", "mem_2"],
        )
        assert c.cluster_id == "cluster_1"
        assert c.size == 2

    def test_to_dict(self):
        c = MemoryCluster(cluster_id="c1", label="Test", memory_ids=["1", "2"])
        d = c.to_dict()
        assert d["cluster_id"] == "c1"
        assert d["size"] == 2


class TestMemoryClustering:
    def test_creation(self):
        clustering = MemoryClustering()
        assert clustering._cluster_count == 0

    def test_cluster_by_topic_no_manager(self):
        clustering = MemoryClustering()
        clusters = clustering.cluster_by_topic()
        assert isinstance(clusters, list)

    def test_cluster_by_time_no_manager(self):
        clustering = MemoryClustering()
        clusters = clustering.cluster_by_time()
        assert isinstance(clusters, list)

    def test_cluster_by_tags_no_manager(self):
        clustering = MemoryClustering()
        clusters = clustering.cluster_by_tags()
        assert isinstance(clusters, list)

    def test_cluster_by_agent_no_manager(self):
        clustering = MemoryClustering()
        clusters = clustering.cluster_by_agent()
        assert isinstance(clusters, list)

    def test_stats(self):
        clustering = MemoryClustering()
        clustering.cluster_by_topic()
        stats = clustering.stats()
        assert stats["cluster_count"] == 1


# ── Memory Recommender Tests ──

class TestMemoryRecommendation:
    def test_creation(self):
        r = MemoryRecommendation(
            memory_id="mem_1",
            content="The API uses JWT",
            reason="Context match",
            relevance_score=0.85,
            source="context",
        )
        assert r.memory_id == "mem_1"
        assert r.relevance_score == 0.85

    def test_to_dict(self):
        r = MemoryRecommendation(
            memory_id="1",
            content="Test",
            reason="Test reason",
            relevance_score=0.5,
            source="context",
        )
        d = r.to_dict()
        assert d["memory_id"] == "1"
        assert d["relevance_score"] == 0.5


class TestMemoryRecommender:
    def test_creation(self):
        recommender = MemoryRecommender()
        assert recommender._recommendation_count == 0

    def test_recommend_no_context(self):
        recommender = MemoryRecommender()
        recs = recommender.recommend("")
        assert recs == []

    def test_recommend_no_manager(self):
        recommender = MemoryRecommender()
        recs = recommender.recommend("API authentication")
        assert isinstance(recs, list)

    def test_recommend_for_task_no_manager(self):
        recommender = MemoryRecommender()
        recs = recommender.recommend_for_task("Deploy to production")
        assert isinstance(recs, list)

    def test_recommend_for_agent_no_manager(self):
        recommender = MemoryRecommender()
        recs = recommender.recommend_for_agent("security-auditor")
        assert isinstance(recs, list)

    def test_recommend_temporal_no_manager(self):
        recommender = MemoryRecommender()
        recs = recommender.recommend_temporal()
        assert isinstance(recs, list)

    def test_find_gaps_no_manager(self):
        recommender = MemoryRecommender()
        gaps = recommender.find_gaps("API authentication with JWT tokens")
        assert isinstance(gaps, list)

    def test_stats(self):
        recommender = MemoryRecommender()
        recommender.recommend("test context")
        stats = recommender.stats()
        assert stats["recommendation_count"] == 1
