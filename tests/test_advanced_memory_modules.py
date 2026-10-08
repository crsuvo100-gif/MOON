"""Tests for advanced memory modules — reasoning, conflict resolution,
importance scoring, temporal reasoning, lifecycle, summarization,
clustering, recommendations, forgetting curves, association engine,
query planning, memory export, validation, and deduplication."""

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
from app.memory.advanced.forgetting_curve import (
    ForgettingCurveManager,
    ForgettingCurve,
    ReviewSchedule,
)
from app.memory.advanced.association_engine import (
    AssociationEngine,
    Association,
    AssociationPath,
)
from app.memory.advanced.query_planner import (
    QueryPlanner,
    QueryPlan,
    SubQuery,
    PlannedResult,
)
from app.memory.advanced.memory_exporter import (
    MemoryExporter,
    ExportResult,
)
from app.memory.advanced.memory_validator import (
    MemoryValidator,
    ValidationIssue,
    ValidationReport,
)
from app.memory.advanced.deduplication import (
    MemoryDeduplicator,
    DuplicateGroup,
    DeduplicationReport,
    MergeResult,
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


# ---------------------------------------------------------------------------
# Forgetting Curve Tests
# ---------------------------------------------------------------------------


class TestForgettingCurve:
    def test_creation(self):
        curve = ForgettingCurve(memory_id="mem_1")
        assert curve.memory_id == "mem_1"
        assert curve.stability > 0
        assert curve.review_count == 0

    def test_retention_decays_over_time(self):
        now = time.time()
        curve = ForgettingCurve(memory_id="mem_1", stability=100.0, last_access=now - 200.0)
        r = curve.retention(at_time=now)
        assert 0.0 < r < 1.0

    def test_retention_fresh_memory(self):
        now = time.time()
        curve = ForgettingCurve(memory_id="mem_1", stability=100.0, last_access=now)
        r = curve.retention(at_time=now)
        assert r == pytest.approx(1.0, abs=0.01)

    def test_review_increases_stability(self):
        curve = ForgettingCurve(memory_id="mem_1", stability=100.0)
        old_stability = curve.stability
        curve.review()
        assert curve.stability > old_stability
        assert curve.review_count == 1

    def test_is_at_risk(self):
        now = time.time()
        curve = ForgettingCurve(memory_id="mem_1", stability=1.0, last_access=now - 10000.0)
        assert curve.is_at_risk(threshold=0.5)

    def test_time_to_threshold(self):
        curve = ForgettingCurve(memory_id="mem_1", stability=100.0)
        t = curve.time_to_threshold(threshold=0.5)
        assert t > 0

    def test_to_dict(self):
        curve = ForgettingCurve(memory_id="mem_1")
        d = curve.to_dict()
        assert d["memory_id"] == "mem_1"
        assert "current_retention" in d
        assert "at_risk" in d


class TestForgettingCurveManager:
    def test_creation(self):
        mgr = ForgettingCurveManager()
        assert mgr._curves == {}

    def test_register_memory(self):
        mgr = ForgettingCurveManager()
        curve = mgr.register_memory("mem_1")
        assert curve.memory_id == "mem_1"
        assert "mem_1" in mgr._curves

    def test_get_retention(self):
        mgr = ForgettingCurveManager()
        mgr.register_memory("mem_1")
        r = mgr.get_retention("mem_1")
        assert 0.0 <= r <= 1.0

    def test_get_at_risk_empty(self):
        mgr = ForgettingCurveManager()
        assert mgr.get_at_risk_memories() == []

    def test_get_review_schedule(self):
        mgr = ForgettingCurveManager()
        mgr.register_memory("mem_1")
        schedule = mgr.get_review_schedule("mem_1")
        assert schedule is not None
        assert schedule.memory_id == "mem_1"
        assert len(schedule.intervals) > 0

    def test_get_due_reviews_empty(self):
        mgr = ForgettingCurveManager()
        assert mgr.get_due_reviews() == []

    def test_adjust_importance(self):
        mgr = ForgettingCurveManager()
        mgr.register_memory("mem_1")
        adjusted = mgr.adjust_importance("mem_1", 0.5)
        assert 0.0 <= adjusted <= 1.0

    def test_stats(self):
        mgr = ForgettingCurveManager()
        mgr.register_memory("mem_1")
        stats = mgr.stats()
        assert stats["total_memories"] == 1
        assert "at_risk" in stats
        assert "avg_retention" in stats


# ---------------------------------------------------------------------------
# Association Engine Tests
# ---------------------------------------------------------------------------


class TestAssociationEngine:
    def test_creation(self):
        engine = AssociationEngine()
        assert engine._associations == {}
        assert not engine._built

    def test_compute_association_identical(self):
        engine = AssociationEngine()
        strength, assoc_type, shared = engine._compute_association(
            "hello world", ["tag1"], time.time(),
            "hello world", ["tag1"], time.time(),
        )
        assert strength > 0.5
        assert len(shared) > 0

    def test_compute_association_different(self):
        engine = AssociationEngine()
        strength, assoc_type, shared = engine._compute_association(
            "apple banana", ["fruit"], time.time(),
            "car engine", ["vehicle"], time.time(),
        )
        assert strength < 0.5

    def test_get_related_empty(self):
        import asyncio
        engine = AssociationEngine()
        related = asyncio.run(engine.get_related("nonexistent"))
        assert related == []

    def test_find_paths_empty(self):
        import asyncio
        engine = AssociationEngine()
        paths = asyncio.run(engine.find_paths("a", "b"))
        assert paths == []

    def test_suggest_new_associations_empty(self):
        import asyncio
        engine = AssociationEngine()
        suggestions = asyncio.run(engine.suggest_new_associations())
        assert suggestions == []

    def test_stats(self):
        engine = AssociationEngine()
        stats = engine.stats()
        assert stats["total_associations"] == 0
        assert "by_type" in stats


# ---------------------------------------------------------------------------
# Query Planner Tests
# ---------------------------------------------------------------------------


class TestQueryPlanner:
    def test_creation(self):
        planner = QueryPlanner()
        assert planner._plan_count == 0

    def test_plan_simple_query(self):
        planner = QueryPlanner()
        plan = planner.plan("What is API authentication?")
        assert plan.original_query == "What is API authentication?"
        assert len(plan.sub_queries) >= 1
        assert plan.execution_strategy in ("parallel", "sequential", "mixed")

    def test_plan_complex_query(self):
        planner = QueryPlanner()
        plan = planner.plan("What did we learn about API auth and how does it relate to security?")
        assert len(plan.sub_queries) >= 1

    def test_decompose_single(self):
        planner = QueryPlanner()
        parts = planner._decompose_query("simple query")
        assert len(parts) == 1

    def test_infer_sources_default(self):
        planner = QueryPlanner()
        sources = planner._infer_sources("random text")
        assert isinstance(sources, list)
        assert len(sources) > 0

    def test_infer_sources_ltm(self):
        planner = QueryPlanner()
        sources = planner._infer_sources("what did we learn about security")
        assert "ltm" in sources

    def test_infer_sources_episodic(self):
        planner = QueryPlanner()
        sources = planner._infer_sources("what did we do yesterday")
        assert "episodic" in sources

    def test_extract_keywords(self):
        planner = QueryPlanner()
        keywords = planner._extract_keywords("API authentication with JWT tokens")
        assert "api" in keywords
        assert "authentication" in keywords
        assert "jwt" in keywords
        assert "tokens" in keywords

    def test_extract_time_range_last_week(self):
        planner = QueryPlanner()
        tr = planner._extract_time_range("what happened last week")
        assert tr is not None
        assert tr[1] > tr[0]

    def test_extract_time_range_none(self):
        planner = QueryPlanner()
        tr = planner._extract_time_range("what is authentication")
        assert tr is None

    def test_determine_strategy_single(self):
        planner = QueryPlanner()
        sq = SubQuery(query_text="test", target_sources=["ltm"])
        strategy = planner._determine_strategy([sq])
        assert strategy == "sequential"

    def test_stats(self):
        planner = QueryPlanner()
        planner.plan("test query")
        stats = planner.stats()
        assert stats["plan_count"] == 1


# ---------------------------------------------------------------------------
# Memory Exporter Tests
# ---------------------------------------------------------------------------


class TestMemoryExporter:
    def test_creation(self):
        exporter = MemoryExporter()
        assert exporter._mm is None

    def test_to_json_no_manager(self):
        import asyncio
        exporter = MemoryExporter()
        result = asyncio.run(exporter.to_json())
        assert result.format == "json"
        assert result.memory_count == 0

    def test_to_markdown_no_manager(self):
        import asyncio
        exporter = MemoryExporter()
        result = asyncio.run(exporter.to_markdown())
        assert result.format == "markdown"
        assert result.memory_count == 0

    def test_to_csv_no_manager(self):
        import asyncio
        exporter = MemoryExporter()
        result = asyncio.run(exporter.to_csv())
        assert result.format == "csv"
        assert result.memory_count == 0

    def test_to_text_no_manager(self):
        import asyncio
        exporter = MemoryExporter()
        result = asyncio.run(exporter.to_text())
        assert result.format == "text"
        assert result.memory_count == 0

    def test_export_to_file_invalid_format(self, tmp_path):
        import asyncio
        exporter = MemoryExporter()
        with pytest.raises(ValueError, match="Unsupported format"):
            asyncio.run(exporter.export_to_file(str(tmp_path / "test.xyz"), format="xyz"))

    def test_stats(self):
        exporter = MemoryExporter()
        stats = exporter.stats()
        assert "json" in stats["supported_formats"]
        assert "markdown" in stats["supported_formats"]
        assert "csv" in stats["supported_formats"]
        assert "text" in stats["supported_formats"]


# ---------------------------------------------------------------------------
# Memory Validator Tests
# ---------------------------------------------------------------------------


class TestMemoryValidator:
    def test_creation(self):
        validator = MemoryValidator()
        assert validator._mm is None

    def test_validate_all_no_manager(self):
        import asyncio
        validator = MemoryValidator()
        report = asyncio.run(validator.validate_all())
        assert report.total_memories == 0
        assert report.health_score == 1.0

    def test_check_contradictions(self):
        validator = MemoryValidator()
        memories = [
            {"id": "1", "content": "the sky is blue", "tags": [], "created_at": time.time()},
            {"id": "2", "content": "the sky is not blue", "tags": [], "created_at": time.time()},
        ]
        issues = validator._check_contradictions(memories)
        assert len(issues) > 0
        assert issues[0].issue_type == "contradiction"

    def test_check_low_quality_short(self):
        validator = MemoryValidator(min_content_length=10)
        memories = [
            {"id": "1", "content": "hi", "tags": [], "created_at": time.time()},
        ]
        issues = validator._check_low_quality(memories)
        assert any(i.issue_type == "low_quality" for i in issues)

    def test_check_low_quality_vague(self):
        validator = MemoryValidator()
        memories = [
            {"id": "1", "content": "something stuff maybe perhaps", "tags": [], "created_at": time.time()},
        ]
        issues = validator._check_low_quality(memories)
        assert any(i.issue_type == "low_quality" for i in issues)

    def test_check_temporal_consistency(self):
        validator = MemoryValidator()
        future = time.time() + 999999
        memories = [
            {"id": "1", "content": "test", "tags": [], "created_at": future},
        ]
        issues = validator._check_temporal_consistency(memories)
        assert len(issues) > 0
        assert issues[0].issue_type == "temporal"

    def test_check_completeness_no_tags(self):
        validator = MemoryValidator()
        memories = [
            {"id": "1", "content": "test memory content", "tags": [], "created_at": time.time()},
        ]
        issues = validator._check_completeness(memories)
        assert any(i.issue_type == "incomplete" for i in issues)

    def test_check_duplicates(self):
        validator = MemoryValidator()
        memories = [
            {"id": "1", "content": "the quick brown fox jumps", "tags": [], "created_at": time.time()},
            {"id": "2", "content": "the quick brown fox jumps", "tags": [], "created_at": time.time()},
        ]
        issues = validator._check_duplicates(memories)
        assert len(issues) > 0
        assert issues[0].issue_type == "duplicate"

    def test_health_score_perfect(self):
        report = ValidationReport(total_memories=10, issues=[])
        assert report.health_score == 1.0

    def test_health_score_with_issues(self):
        issues = [
            ValidationIssue("contradiction", "high", "1", "test"),
            ValidationIssue("low_quality", "medium", "2", "test"),
        ]
        report = ValidationReport(total_memories=10, issues=issues)
        assert report.health_score < 1.0

    def test_stats(self):
        validator = MemoryValidator()
        stats = validator.stats()
        assert "min_content_length" in stats
        assert "max_duplicate_similarity" in stats


# ---------------------------------------------------------------------------
# Deduplication Tests
# ---------------------------------------------------------------------------


class TestMemoryDeduplicator:
    def test_creation(self):
        dedup = MemoryDeduplicator()
        assert dedup._mm is None

    def test_find_duplicates_no_manager(self):
        import asyncio
        dedup = MemoryDeduplicator()
        report = asyncio.run(dedup.find_duplicates())
        assert report.total_memories == 0
        assert report.total_duplicates == 0

    def test_compute_similarity_identical(self):
        dedup = MemoryDeduplicator()
        sim = dedup._compute_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_compute_similarity_different(self):
        dedup = MemoryDeduplicator()
        sim = dedup._compute_similarity("apple banana", "car engine")
        assert sim == 0.0

    def test_compute_similarity_partial(self):
        dedup = MemoryDeduplicator()
        sim = dedup._compute_similarity("the quick brown fox", "the quick red fox")
        assert 0.0 < sim < 1.0

    def test_merge_duplicates_empty(self):
        import asyncio
        dedup = MemoryDeduplicator()
        results = asyncio.run(dedup.merge_duplicates([]))
        assert results == []

    def test_duplicate_rate_zero(self):
        report = DeduplicationReport(total_memories=10, total_duplicates=0)
        assert report.duplicate_rate == 0.0

    def test_duplicate_rate_nonzero(self):
        report = DeduplicationReport(total_memories=10, total_duplicates=5)
        assert report.duplicate_rate == 0.5

    def test_stats(self):
        dedup = MemoryDeduplicator()
        stats = dedup.stats()
        assert "near_duplicate_threshold" in stats
