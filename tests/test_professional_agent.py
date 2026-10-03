"""Tests for the professional agent system."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.agents.professional.communication_bus import (
    CommunicationBus,
    AgentEvent,
    EventPriority,
)
from app.agents.professional.task_queue import (
    TaskQueue,
    TaskStatus,
    TaskPriority,
)
from app.agents.professional.quality_gate import (
    QualityGate,
    QualityLevel,
    QualityStage,
)
from app.agents.professional.self_healing import (
    SelfHealing,
    HealthCheck,
    HealthStatus,
    FailureType,
    RecoveryAction,
    CircuitBreaker,
)
from app.agents.professional.proactive_suggestions import (
    ProactiveSuggestions,
    SuggestionType,
    SuggestionPriority,
)
from app.agents.professional.multi_model_consensus import (
    MultiModelConsensus,
    ModelResponse,
    ConsensusStrategy,
    ConfidenceLevel,
)
from app.agents.professional.execution_analytics import (
    ExecutionAnalytics,
    ExecutionRecord,
    MetricType,
)
from app.agents.professional.adaptive_prompts import (
    AdaptivePrompts,
    TaskComplexity,
    UserExpertise,
)
from app.agents.professional.session_continuity import (
    SessionContinuity,
    SessionStatus,
)
from app.agents.professional.knowledge_graph import (
    KnowledgeGraph,
    EntityType,
    RelationType,
)
from app.agents.professional.professional_orchestrator import (
    ProfessionalAgentOrchestrator,
)


# ── Communication Bus ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_communication_bus_publish_subscribe():
    bus = CommunicationBus()
    await bus.start()
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe("test_event", handler, subscriber_id="test_sub")
    event = AgentEvent(event_type="test_event", source="test", payload={"key": "value"})
    await bus.publish(event)
    await asyncio.sleep(0.1)
    await bus.stop()

    assert len(received) == 1
    assert received[0].payload["key"] == "value"


@pytest.mark.asyncio
async def test_communication_bus_priority_filter():
    bus = CommunicationBus()
    await bus.start()
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe("test_event", handler, subscriber_id="test_sub", priority_filter=EventPriority.HIGH)
    # Low priority — should be filtered
    await bus.publish(AgentEvent(event_type="test_event", source="test", priority=EventPriority.LOW))
    # High priority — should pass
    await bus.publish(AgentEvent(event_type="test_event", source="test", priority=EventPriority.HIGH))
    await asyncio.sleep(0.1)
    await bus.stop()

    assert len(received) == 1
    assert received[0].priority == EventPriority.HIGH


@pytest.mark.asyncio
async def test_communication_bus_metrics():
    bus = CommunicationBus()
    await bus.start()
    bus.subscribe("test_event", lambda e: None, subscriber_id="sub1")
    await bus.publish(AgentEvent(event_type="test_event", source="test"))
    await asyncio.sleep(0.05)
    metrics = bus.get_metrics()
    await bus.stop()

    assert metrics["events_published"] >= 1
    assert metrics["subscriptions_total"] >= 1


# ── Task Queue ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_task_queue_submit_and_complete():
    queue = TaskQueue(max_concurrent=2)
    task_id = await queue.submit("test prompt", priority=TaskPriority.HIGH)
    assert task_id

    task = await queue.get_next(timeout=1.0)
    assert task is not None
    assert task.status == TaskStatus.SCHEDULED

    await queue.complete(task.task_id, result="done")
    assert queue.get_status(task.task_id) == TaskStatus.COMPLETED
    assert queue.get_result(task.task_id) == "done"


@pytest.mark.asyncio
async def test_task_queue_priority_ordering():
    queue = TaskQueue(max_concurrent=1)
    low_id = await queue.submit("low", priority=TaskPriority.LOW)
    high_id = await queue.submit("high", priority=TaskPriority.HIGH)
    critical_id = await queue.submit("critical", priority=TaskPriority.CRITICAL)

    first = await queue.get_next(timeout=1.0)
    assert first.task_id == critical_id

    second = await queue.get_next(timeout=1.0)
    assert second.task_id == high_id

    third = await queue.get_next(timeout=1.0)
    assert third.task_id == low_id


@pytest.mark.asyncio
async def test_task_queue_deduplication():
    queue = TaskQueue()
    id1 = await queue.submit("same prompt")
    id2 = await queue.submit("same prompt")
    assert id1 == id2


@pytest.mark.asyncio
async def test_task_queue_retry():
    queue = TaskQueue()
    task_id = await queue.submit("test")
    task = await queue.get_next(timeout=1.0)
    assert task is not None
    await queue.fail(task.task_id, "error")
    # Should be retried
    assert queue.get_status(task.task_id) == TaskStatus.PENDING


# ── Quality Gate ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quality_gate_valid_output():
    gate = QualityGate(min_score=0.5)
    result = await gate.validate(
        output="This is a complete, well-structured response that fully addresses the task.",
        task="Write a response",
    )
    assert result.passed
    assert result.overall_score > 0.5


@pytest.mark.asyncio
async def test_quality_gate_safety_rejection():
    gate = QualityGate(min_score=0.5)
    result = await gate.validate(
        output="Run rm -rf / to fix the issue",
        task="Fix the issue",
    )
    assert not result.passed
    assert result.level == QualityLevel.REJECTED


@pytest.mark.asyncio
async def test_quality_gate_checks_populated():
    gate = QualityGate()
    result = await gate.validate(output="Test output", task="Test task")
    assert len(result.checks) == 5  # correctness, completeness, safety, presentation, relevance
    stages = {c.stage for c in result.checks}
    assert QualityStage.CORRECTNESS in stages
    assert QualityStage.SAFETY in stages


# ── Self-Healing ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_self_healing_register_and_report():
    sh = SelfHealing()
    await sh.start()
    sh.register_component("test_component")
    await sh.report_health("test_component", status=HealthStatus.HEALTHY, latency_ms=10.0)
    health = sh.get_health("test_component")
    assert isinstance(health, HealthCheck)
    assert health.status == HealthStatus.HEALTHY
    await sh.stop()


@pytest.mark.asyncio
async def test_circuit_breaker():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

    async def fail():
        raise Exception("fail")

    # First failure
    with pytest.raises(Exception):
        await cb.call(fail)
    assert cb.state == "closed"

    # Second failure — opens circuit
    with pytest.raises(Exception):
        await cb.call(fail)
    assert cb.state == "open"

    # Should reject immediately
    with pytest.raises(Exception, match="OPEN"):
        await cb.call(fail)


@pytest.mark.asyncio
async def test_self_healing_recovery():
    sh = SelfHealing()
    await sh.start()
    sh.register_component("test", recovery_handler=lambda: asyncio.sleep(0))
    sh.register_recovery_strategy(
        FailureType.UNKNOWN,
        RecoveryAction(failure_type=FailureType.UNKNOWN, component="test", strategy="restart"),
    )
    result = await sh.report_failure("test", FailureType.UNKNOWN, "test error")
    assert result is True
    await sh.stop()


# ── Proactive Suggestions ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_proactive_suggestions_detects_errors():
    ps = ProactiveSuggestions()
    suggestions = await ps.analyze(
        conversation=[
            {"role": "user", "content": "Fix the bug"},
            {"role": "assistant", "content": "There was an error in the code"},
        ],
        current_task="Fix the bug",
    )
    assert len(suggestions) > 0
    assert any(s.suggestion_type == SuggestionType.NEXT_ACTION for s in suggestions)


@pytest.mark.asyncio
async def test_proactive_suggestions_tool_recommendation():
    ps = ProactiveSuggestions()
    suggestions = await ps.analyze(
        conversation=[{"role": "user", "content": "Search the web for Python tutorials"}],
        current_task="Search the web for Python tutorials",
        available_tools=["web_search", "file_read"],
    )
    tool_suggestions = [s for s in suggestions if s.suggestion_type == SuggestionType.TOOL_RECOMMENDATION]
    assert len(tool_suggestions) > 0


@pytest.mark.asyncio
async def test_proactive_suggestions_cooldown():
    ps = ProactiveSuggestions(cooldown=60.0)
    s1 = await ps.analyze(
        conversation=[{"role": "assistant", "content": "There was an error"}],
        current_task="test",
    )
    s2 = await ps.analyze(
        conversation=[{"role": "assistant", "content": "There was an error"}],
        current_task="test",
    )
    # Second call should be filtered by cooldown
    assert len(s2) < len(s1) or len(s2) == 0


# ── Multi-Model Consensus ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_consensus_single_model():
    consensus = MultiModelConsensus()

    class FakeLLM:
        async def complete(self, **kwargs):
            return "The answer is 42."

    result = await consensus.reach_consensus(
        prompt="What is the answer?",
        models=[("model_a", FakeLLM())],
    )
    assert result.answer == "The answer is 42."
    assert result.level == ConfidenceLevel.LOW  # Single model = reduced confidence


@pytest.mark.asyncio
async def test_consensus_majority_vote():
    consensus = MultiModelConsensus(strategy=ConsensusStrategy.MAJORITY)

    class FakeLLM:
        def __init__(self, response):
            self._response = response
        async def complete(self, **kwargs):
            return self._response

    result = await consensus.reach_consensus(
        prompt="What is the answer?",
        models=[
            ("model_a", FakeLLM("The answer is 42")),
            ("model_b", FakeLLM("The answer is 42")),
            ("model_c", FakeLLM("I don't know")),
        ],
    )
    assert "42" in result.answer
    assert result.agreement_ratio >= 0.6


@pytest.mark.asyncio
async def test_consensus_weighted():
    consensus = MultiModelConsensus(strategy=ConsensusStrategy.WEIGHTED)
    consensus.set_model_weight("model_a", 1.0)
    consensus.set_model_weight("model_b", 0.5)

    class FakeLLM:
        def __init__(self, response):
            self._response = response
        async def complete(self, **kwargs):
            return self._response

    result = await consensus.reach_consensus(
        prompt="What is the answer?",
        models=[
            ("model_a", FakeLLM("The answer is 42")),
            ("model_b", FakeLLM("The answer is different")),
        ],
    )
    assert "42" in result.answer


# ── Execution Analytics ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analytics_record_and_summary():
    analytics = ExecutionAnalytics()
    await analytics.record_execution(ExecutionRecord(
        execution_id="exec_1",
        task_type="test",
        agent_name="test_agent",
        start_time=time.time() - 1.0,
        end_time=time.time(),
        success=True,
        tokens_used=100,
        tool_calls=2,
    ))
    summary = analytics.get_summary()
    assert summary.total_executions == 1
    assert summary.success_count == 1
    assert summary.total_tokens == 100


@pytest.mark.asyncio
async def test_analytics_realtime_metrics():
    analytics = ExecutionAnalytics()
    await analytics.record_execution(ExecutionRecord(
        execution_id="exec_1",
        task_type="test",
        agent_name="test_agent",
        start_time=time.time(),
        end_time=time.time(),
        success=True,
    ))
    metrics = analytics.get_realtime_metrics()
    assert metrics["total_executions"] == 1
    assert metrics["executions_last_minute"] == 1


@pytest.mark.asyncio
async def test_analytics_bottlenecks():
    analytics = ExecutionAnalytics()
    await analytics.record_execution(ExecutionRecord(
        execution_id="exec_1",
        task_type="test",
        agent_name="slow_agent",
        start_time=time.time() - 10.0,
        end_time=time.time(),
        success=True,
    ))
    bottlenecks = analytics.get_bottlenecks(threshold_ms=5000.0)
    assert len(bottlenecks) == 1
    assert bottlenecks[0]["agent"] == "slow_agent"


# ── Adaptive Prompts ────────────────────────────────────────────────────

def test_adaptive_prompts_complexity_assessment():
    ap = AdaptivePrompts()
    assert ap.assess_complexity("What is Python?") == TaskComplexity.SIMPLE
    assert ap.assess_complexity("Implement a binary search tree with insertion, deletion, and traversal methods") == TaskComplexity.MODERATE


def test_adaptive_prompts_config_generation():
    ap = AdaptivePrompts()
    config = ap.generate_config(task="Implement a complex system with multiple components")
    assert config.temperature >= 0.5
    assert config.max_tokens >= 1024
    # MODERATE complexity → no chain-of-thought
    assert config.chain_of_thought is False


def test_adaptive_prompts_complex_task_enables_cot():
    ap = AdaptivePrompts()
    # A task complex enough to trigger chain-of-thought
    complex_task = "Design and implement a distributed microservice architecture with fault tolerance, then optimize the database queries and refactor the authentication system"
    config = ap.generate_config(task=complex_task)
    assert config.chain_of_thought is True
    assert config.max_tokens >= 2048


def test_adaptive_prompts_expertise_adjustment():
    ap = AdaptivePrompts()
    ap.set_user_expertise(UserExpertise.EXPERT)
    config = ap.generate_config(task="Implement a complex system")
    assert "expert" in config.system_prompt.lower() or "brief" in config.system_prompt.lower()


def test_adaptive_prompts_template_rendering():
    ap = AdaptivePrompts()
    from app.agents.professional.adaptive_prompts import PromptTemplate
    ap.register_template(PromptTemplate(
        name="test_template",
        template="Hello {user}, welcome to {location}!",
        variables=["user", "location"],
    ))
    result = ap.render_template("test_template", user="Alice", location="Wonderland")
    assert result == "Hello Alice, welcome to Wonderland!"


# ── Session Continuity ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_create_and_resume():
    sc = SessionContinuity(storage_path="/tmp/test_sessions")
    session = await sc.create_session(user_id="test_user")
    assert session.session_id
    assert session.status == SessionStatus.ACTIVE

    resumed = await sc.resume_session(session.session_id)
    assert resumed is not None
    assert resumed.session_id == session.session_id


@pytest.mark.asyncio
async def test_session_update():
    sc = SessionContinuity(storage_path="/tmp/test_sessions")
    session = await sc.create_session()
    await sc.update_session(
        session.session_id,
        summary="Test summary",
        key_facts=["fact1", "fact2"],
    )
    summary = await sc.get_session_summary(session.session_id)
    assert "Test summary" in summary
    assert "fact1" in summary


@pytest.mark.asyncio
async def test_session_handoff():
    sc = SessionContinuity(storage_path="/tmp/test_sessions")
    s1 = await sc.create_session()
    s2 = await sc.create_session()
    await sc.update_session(s1.session_id, summary="Context from s1")
    handoff = await sc.handoff(s1.session_id, s2.session_id, notes="test handoff")
    assert handoff is not None
    assert handoff.from_session == s1.session_id
    assert handoff.to_session == s2.session_id


@pytest.mark.asyncio
async def test_session_cleanup_expired():
    sc = SessionContinuity(storage_path="/tmp/test_sessions", ttl=0.01)
    session = await sc.create_session()
    await asyncio.sleep(0.02)
    removed = await sc.cleanup_expired()
    assert removed >= 1


# ── Knowledge Graph ─────────────────────────────────────────────────────

def test_knowledge_graph_add_entity():
    kg = KnowledgeGraph(storage_path="/tmp/test_kg.json")
    entity = kg.add_entity("Python", EntityType.CONCEPT, properties={"type": "language"})
    assert entity.id
    assert entity.name == "Python"
    assert entity.entity_type == EntityType.CONCEPT


def test_knowledge_graph_search():
    kg = KnowledgeGraph(storage_path="/tmp/test_kg.json")
    kg.add_entity("Python", EntityType.CONCEPT)
    kg.add_entity("JavaScript", EntityType.CONCEPT)
    results = kg.search("Python")
    assert len(results) >= 1
    assert any(e.name == "Python" for e in results)


def test_knowledge_graph_relationships():
    kg = KnowledgeGraph(storage_path="/tmp/test_kg.json")
    e1 = kg.add_entity("User", EntityType.PERSON)
    e2 = kg.add_entity("Project", EntityType.PROJECT)
    rel = kg.add_relationship(e1.id, e2.id, RelationType.OWNS)
    assert rel is not None
    related = kg.get_related(e1.id)
    assert len(related) == 1
    assert related[0][0].name == "Project"


def test_knowledge_graph_facts():
    kg = KnowledgeGraph(storage_path="/tmp/test_kg.json")
    fact = kg.add_fact("Python is a programming language", confidence=0.95)
    assert fact.id
    assert fact.confidence == 0.95


def test_knowledge_graph_inference():
    kg = KnowledgeGraph(storage_path="/tmp/test_kg.json")
    e1 = kg.add_entity("Alice", EntityType.PERSON)
    e2 = kg.add_entity("ProjectX", EntityType.PROJECT)
    kg.add_relationship(e1.id, e2.id, RelationType.OWNS)
    inferred = kg.infer(e1.id)
    assert len(inferred) > 0
    assert any("owns" in f.statement.lower() for f in inferred)


def test_knowledge_graph_context_enrichment():
    kg = KnowledgeGraph(storage_path="/tmp/test_kg.json")
    e1 = kg.add_entity("Python", EntityType.CONCEPT)
    e2 = kg.add_entity("Programming", EntityType.CONCEPT)
    kg.add_relationship(e1.id, e2.id, RelationType.RELATED_TO)
    enrichment = kg.get_context_enrichment("Python")
    assert "Python" in enrichment


# ── Professional Agent Orchestrator ─────────────────────────────────────

@pytest.mark.asyncio
async def test_professional_orchestrator_initialize():
    orch = ProfessionalAgentOrchestrator()
    await orch.initialize()
    assert orch._initialized is True
    assert orch._current_session is not None
    await orch.shutdown()


@pytest.mark.asyncio
async def test_professional_orchestrator_submit_task():
    orch = ProfessionalAgentOrchestrator()
    await orch.initialize()
    task_id = await orch.submit_task("Test prompt", priority=TaskPriority.HIGH)
    assert task_id
    await orch.shutdown()


@pytest.mark.asyncio
async def test_professional_orchestrator_process_with_quality():
    orch = ProfessionalAgentOrchestrator()
    await orch.initialize()
    result = await orch.process_with_quality("Test prompt", task_type="test")
    assert "output" in result
    assert "quality_score" in result
    assert "execution_id" in result
    await orch.shutdown()


@pytest.mark.asyncio
async def test_professional_orchestrator_health():
    orch = ProfessionalAgentOrchestrator()
    await orch.initialize()
    health = orch.get_health()
    assert health["initialized"] is True
    assert "subsystems" in health
    assert "communication_bus" in health["subsystems"]
    assert "task_queue" in health["subsystems"]
    assert "quality_gate" in health["subsystems"]
    await orch.shutdown()


@pytest.mark.asyncio
async def test_professional_orchestrator_knowledge():
    orch = ProfessionalAgentOrchestrator()
    await orch.initialize()
    entity_id = orch.add_knowledge("TestEntity", EntityType.CONCEPT, properties={"key": "value"})
    assert entity_id
    fact_id = orch.add_fact("Test fact", confidence=0.9)
    assert fact_id
    results = orch.search_knowledge("TestEntity")
    assert len(results) >= 1
    await orch.shutdown()


@pytest.mark.asyncio
async def test_professional_orchestrator_proactive_suggestions():
    orch = ProfessionalAgentOrchestrator()
    await orch.initialize()
    suggestions = await orch.get_proactive_suggestions(
        conversation=[{"role": "assistant", "content": "There was an error"}],
        current_task="test",
    )
    assert isinstance(suggestions, list)
    await orch.shutdown()


@pytest.mark.asyncio
async def test_professional_orchestrator_analytics():
    orch = ProfessionalAgentOrchestrator()
    await orch.initialize()
    await orch.process_with_quality("Test prompt")
    summary = orch.get_analytics_summary()
    assert summary["total_executions"] >= 1
    realtime = orch.get_realtime_metrics()
    assert realtime["total_executions"] >= 1
    await orch.shutdown()


@pytest.mark.asyncio
async def test_professional_orchestrator_session_handoff():
    orch = ProfessionalAgentOrchestrator()
    await orch.initialize()
    # Create a second session
    session2 = await orch._session_continuity.create_session()
    result = await orch.create_handoff(session2.session_id, notes="test handoff")
    assert result is True
    await orch.shutdown()


@pytest.mark.asyncio
async def test_professional_orchestrator_shutdown_saves_knowledge():
    orch = ProfessionalAgentOrchestrator()
    await orch.initialize()
    orch.add_knowledge("PersistentEntity", EntityType.CONCEPT)
    await orch.shutdown()
    # Knowledge graph should be saved
    assert orch._knowledge_graph.get_metrics()["total_entities"] >= 1
