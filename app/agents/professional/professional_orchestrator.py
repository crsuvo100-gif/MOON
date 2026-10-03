"""Professional Agent Orchestrator — ties all professional systems together.

Coordinates communication, task scheduling, quality assurance,
self-healing, proactive suggestions, consensus, analytics,
adaptive prompting, session continuity, and knowledge graph
into a unified professional agent experience.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from typing import Any

from app.config.logging import get_logger
from app.agents.professional.communication_bus import CommunicationBus, AgentEvent, EventPriority
from app.agents.professional.task_queue import TaskQueue, TaskPriority, TaskStatus
from app.agents.professional.quality_gate import QualityGate, QualityLevel
from app.agents.professional.self_healing import SelfHealing, HealthStatus, FailureType
from app.agents.professional.proactive_suggestions import ProactiveSuggestions, Suggestion, SuggestionType
from app.agents.professional.multi_model_consensus import MultiModelConsensus, ConsensusStrategy
from app.agents.professional.execution_analytics import ExecutionAnalytics, ExecutionRecord, MetricType
from app.agents.professional.adaptive_prompts import AdaptivePrompts, TaskComplexity, UserExpertise
from app.agents.professional.session_continuity import SessionContinuity, SessionContext, SessionStatus
from app.agents.professional.knowledge_graph import KnowledgeGraph, EntityType, RelationType

logger = get_logger(__name__)


class ProfessionalAgentOrchestrator:
    """Unified orchestrator for all professional agent systems.

    Coordinates 10 advanced subsystems to deliver a professional
    AI assistant experience with enterprise-grade reliability.
    """

    def __init__(
        self,
        *,
        max_concurrent_tasks: int = 5,
        quality_threshold: float = 0.7,
        enable_consensus: bool = True,
        enable_self_healing: bool = True,
        enable_proactive: bool = True,
        session_ttl: float = 86400.0,
    ) -> None:
        self._communication = CommunicationBus()
        self._task_queue = TaskQueue(max_concurrent=max_concurrent_tasks)
        self._quality_gate = QualityGate(min_score=quality_threshold)
        self._self_healing = SelfHealing() if enable_self_healing else None
        self._proactive = ProactiveSuggestions() if enable_proactive else None
        self._consensus = MultiModelConsensus() if enable_consensus else None
        self._analytics = ExecutionAnalytics()
        self._adaptive_prompts = AdaptivePrompts()
        self._session_continuity = SessionContinuity(ttl=session_ttl)
        self._knowledge_graph = KnowledgeGraph()

        self._quality_threshold = quality_threshold
        self._initialized = False
        self._current_session: SessionContext | None = None
        self._metrics: dict[str, int] = defaultdict(int)

    async def initialize(self) -> None:
        """Initialize all professional subsystems."""
        if self._initialized:
            return

        # Start communication bus
        await self._communication.start()

        # Start self-healing
        if self._self_healing:
            await self._self_healing.start()
            # Register core components
            self._self_healing.register_component("communication_bus")
            self._self_healing.register_component("task_queue")
            self._self_healing.register_component("quality_gate")
            self._self_healing.register_component("analytics")

        # Load knowledge graph
        await self._knowledge_graph.load()

        # Create default session
        self._current_session = await self._session_continuity.create_session()

        self._initialized = True
        logger.info("Professional Agent Orchestrator initialized")

    async def shutdown(self) -> None:
        """Shutdown all professional subsystems."""
        # Save knowledge graph
        await self._knowledge_graph.save()

        # Stop self-healing
        if self._self_healing:
            await self._self_healing.stop()

        # Stop communication bus
        await self._communication.stop()

        # Clean up expired sessions
        await self._session_continuity.cleanup_expired()

        self._initialized = False
        logger.info("Professional Agent Orchestrator shutdown")

    async def submit_task(
        self,
        prompt: str,
        *,
        priority: TaskPriority = TaskPriority.NORMAL,
        agent_name: str = "planning",
        task_type: str = "general",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Submit a task to the professional queue.

        Returns:
            Task ID.
        """
        task_id = await self._task_queue.submit(
            prompt,
            priority=priority,
            agent_name=agent_name,
            metadata=metadata,
        )

        # Publish event
        await self._communication.publish(AgentEvent(
            event_type="task_submitted",
            source="professional_orchestrator",
            payload={"task_id": task_id, "task_type": task_type, "priority": priority.value},
            priority=EventPriority.NORMAL,
        ))

        self._metrics["tasks_submitted"] += 1
        return task_id

    async def process_with_quality(
        self,
        prompt: str,
        *,
        context: str = "",
        task_type: str = "general",
        use_consensus: bool = False,
        models: list[tuple[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Process a prompt with full quality pipeline.

        Args:
            prompt: The user prompt.
            context: Additional context.
            task_type: Type of task.
            use_consensus: Whether to use multi-model consensus.
            models: List of (name, llm_service) for consensus.

        Returns:
            Result dict with output, quality score, and metadata.
        """
        start_time = time.time()
        execution_id = str(uuid.uuid4())[:8]

        # Generate adaptive prompt config
        config = self._adaptive_prompts.generate_config(
            task=prompt,
            context=context,
            task_type=task_type,
        )

        # Get knowledge graph enrichment
        kg_context = self._knowledge_graph.get_context_enrichment(prompt)

        # Execute (with consensus if requested)
        if use_consensus and models and self._consensus:
            consensus_result = await self._consensus.reach_consensus(
                prompt=prompt,
                models=models,
                system_prompt=config.system_prompt,
                temperature=config.temperature,
            )
            output = consensus_result.answer
            confidence = consensus_result.confidence
        else:
            # Single-model execution would happen here
            # For now, return a placeholder
            output = ""
            confidence = 0.5

        # Quality gate
        quality_result = await self._quality_gate.validate(
            output=output,
            task=prompt,
            context=context,
        )

        # Record analytics
        execution_time = time.time() - start_time
        record = ExecutionRecord(
            execution_id=execution_id,
            task_type=task_type,
            agent_name="professional_orchestrator",
            start_time=start_time,
            end_time=time.time(),
            success=quality_result.passed,
            metadata={
                "quality_score": quality_result.overall_score,
                "confidence": confidence,
                "use_consensus": use_consensus,
            },
        )
        await self._analytics.record_execution(record)

        # Report health
        if self._self_healing:
            await self._self_healing.report_health(
                "professional_orchestrator",
                status=HealthStatus.HEALTHY if quality_result.passed else HealthStatus.DEGRADED,
                latency_ms=execution_time * 1000,
            )

        self._metrics["tasks_processed"] += 1

        return {
            "output": output,
            "quality_score": quality_result.overall_score,
            "quality_passed": quality_result.passed,
            "confidence": confidence,
            "execution_time": execution_time,
            "execution_id": execution_id,
            "knowledge_context": kg_context,
        }

    async def get_proactive_suggestions(
        self,
        *,
        conversation: list[dict[str, Any]],
        current_task: str = "",
        available_tools: list[str] | None = None,
    ) -> list[Suggestion]:
        """Get proactive suggestions for the current context."""
        if not self._proactive:
            return []
        return await self._proactive.analyze(
            conversation=conversation,
            current_task=current_task,
            available_tools=available_tools,
        )

    async def create_handoff(self, to_session_id: str, notes: str = "") -> bool:
        """Create a session handoff."""
        if not self._current_session:
            return False
        handoff = await self._session_continuity.handoff(
            self._current_session.session_id,
            to_session_id,
            notes=notes,
        )
        return handoff is not None

    def add_knowledge(
        self,
        name: str,
        entity_type: EntityType,
        *,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """Add an entity to the knowledge graph."""
        entity = self._knowledge_graph.add_entity(
            name, entity_type, properties=properties
        )
        return entity.id

    def add_fact(self, statement: str, *, confidence: float = 0.8) -> str:
        """Add a fact to the knowledge graph."""
        fact = self._knowledge_graph.add_fact(statement, confidence=confidence)
        return fact.id

    def search_knowledge(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Search the knowledge graph."""
        entities = self._knowledge_graph.search(query, limit=limit)
        return [
            {
                "id": e.id,
                "name": e.name,
                "type": e.entity_type.value,
                "confidence": e.confidence,
            }
            for e in entities
        ]

    def get_health(self) -> dict[str, Any]:
        """Get comprehensive health status."""
        health = {
            "initialized": self._initialized,
            "current_session": self._current_session.session_id if self._current_session else None,
            "subsystems": {
                "communication_bus": self._communication.get_metrics(),
                "task_queue": self._task_queue.get_metrics(),
                "quality_gate": self._quality_gate.get_metrics(),
                "analytics": self._analytics.get_metrics(),
                "adaptive_prompts": self._adaptive_prompts.get_metrics(),
                "session_continuity": self._session_continuity.get_metrics(),
                "knowledge_graph": self._knowledge_graph.get_metrics(),
            },
        }

        if self._self_healing:
            health["subsystems"]["self_healing"] = self._self_healing.get_metrics()
        if self._proactive:
            health["subsystems"]["proactive_suggestions"] = self._proactive.get_metrics()
        if self._consensus:
            health["subsystems"]["multi_model_consensus"] = self._consensus.get_metrics()

        return health

    def get_analytics_summary(self) -> dict[str, Any]:
        """Get analytics summary."""
        return self._analytics.get_summary().__dict__

    def get_realtime_metrics(self) -> dict[str, Any]:
        """Get real-time metrics."""
        return self._analytics.get_realtime_metrics()
