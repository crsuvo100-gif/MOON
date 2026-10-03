"""orchestrator.py — advanced agent system orchestrator.

Ties together all advanced agent modules (pipeline, blackboard, lifecycle,
performance, learning, coordination, context sharing, error recovery,
tool optimizer, state manager) into a unified system that the main
Orchestrator can use.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.agents.advanced.pipeline import AgentPipeline, PipelineResult
from app.agents.advanced.blackboard import Blackboard
from app.agents.advanced.lifecycle import AgentLifecycle, AgentState, StateTransition
from app.agents.advanced.performance import PerformanceTracker, TaskExecution
from app.agents.advanced.learning import AgentLearning, LearningRecord
from app.agents.advanced.coordination import CoordinationProtocol, CoordinationMode
from app.agents.advanced.context_sharing import ContextSharing
from app.agents.advanced.error_recovery import ErrorRecovery, ErrorCategory, ErrorSeverity
from app.agents.advanced.tool_optimizer import ToolOptimizer
from app.agents.advanced.state_manager import AgentStateManager, AgentState as PersistedState

logger = logging.getLogger(__name__)


class AdvancedAgentOrchestrator:
    """Unified facade for the advanced agent system.

    Provides a single entry point to all advanced agent capabilities:
    - Pipeline execution with multi-stage processing
    - Blackboard-based multi-agent coordination
    - Agent lifecycle management
    - Performance tracking and analytics
    - Self-learning from outcomes
    - Inter-agent context sharing
    - Error detection and recovery
    - Tool usage optimization
    - State persistence and recovery
    """

    def __init__(self) -> None:
        self._pipeline = AgentPipeline("main")
        self._blackboard = Blackboard("main")
        self._lifecycle: AgentLifecycle | None = None
        self._performance = PerformanceTracker()
        self._learning = AgentLearning()
        self._coordination = CoordinationProtocol(mode=CoordinationMode.HIERARCHICAL)
        self._context_sharing = ContextSharing()
        self._error_recovery = ErrorRecovery()
        self._tool_optimizer = ToolOptimizer()
        self._state_manager = AgentStateManager()
        self._initialized = False

    async def initialize(self, agent_id: str = "orchestrator") -> None:
        """Initialize the advanced agent system."""
        self._lifecycle = AgentLifecycle(
            agent_id=agent_id,
            on_state_change=self._on_state_change,
            on_event=self._on_lifecycle_event,
        )
        self._initialized = True
        logger.info("Advanced agent system initialized")

    def _on_state_change(self, transition: StateTransition) -> None:
        logger.debug("State change: %s -> %s", transition.from_state, transition.to_state)

    def _on_lifecycle_event(self, event) -> None:
        logger.debug("Lifecycle event: %s", event.event_type)

    async def execute_pipeline(
        self,
        context: dict[str, Any],
        *,
        agent_id: str = "pipeline",
    ) -> PipelineResult:
        """Execute the multi-stage pipeline."""
        if not self._initialized:
            await self.initialize()

        # Record performance
        start = time.monotonic()
        execution = TaskExecution(
            task_id=f"pipeline_{int(start * 1000)}",
            agent_id=agent_id,
            start_time=start,
        )

        try:
            result = await self._pipeline.execute(context)
            execution.end_time = time.monotonic()
            execution.success = result.success
            execution.quality_score = 1.0 if result.success else 0.0
            self._performance.record(execution)

            # Learn from outcome
            await self._learning.record_outcome(
                agent_id=agent_id,
                task_prompt=str(context.get("task", "")),
                outcome=result.final_output[:500],
                success=result.success,
                lesson="; ".join(result.errors) if result.errors else "",
            )

            return result
        except Exception as exc:
            execution.end_time = time.monotonic()
            execution.success = False
            execution.error = str(exc)
            self._performance.record(execution)

            # Handle error
            await self._error_recovery.handle_error(
                agent_id=agent_id,
                message=str(exc),
                category=ErrorCategory.UNKNOWN,
                severity=ErrorSeverity.HIGH,
            )
            raise

    async def coordinate_task(
        self,
        description: str,
        requirements: list[str],
        *,
        priority: int = 5,
    ) -> str:
        """Announce a task for multi-agent coordination."""
        if not self._initialized:
            await self.initialize()
        return await self._coordination.announce_task(
            description, requirements, priority=priority,
        )

    async def share_context(
        self,
        task_id: str,
        agent_id: str,
        content: str,
        *,
        context_type: str = "finding",
    ) -> str:
        """Share context between agents."""
        if not self._initialized:
            await self.initialize()
        return await self._context_sharing.publish(
            task_id, agent_id, content, context_type=context_type,
        )

    async def get_shared_context(
        self,
        task_id: str,
        agent_id: str,
        *,
        query: str = "",
    ) -> list:
        """Get relevant shared context for an agent."""
        if not self._initialized:
            await self.initialize()
        return await self._context_sharing.get_relevant_contexts(
            task_id, agent_id, query=query,
        )

    async def save_agent_state(self, state: PersistedState) -> None:
        """Persist agent state."""
        if not self._initialized:
            await self.initialize()
        await self._state_manager.save_state(state)

    async def load_agent_state(self, agent_id: str, task_id: str) -> PersistedState | None:
        """Load persisted agent state."""
        if not self._initialized:
            await self.initialize()
        return await self._state_manager.load_state(agent_id, task_id)

    async def record_tool_usage(
        self,
        tool_name: str,
        agent_id: str,
        task_id: str,
        *,
        success: bool = True,
        duration: float = 0.0,
    ) -> None:
        """Record tool usage for optimization."""
        if not self._initialized:
            await self.initialize()
        await self._tool_optimizer.record_usage(
            tool_name, agent_id, task_id,
            success=success, duration=duration,
        )

    async def handle_error(
        self,
        agent_id: str,
        message: str,
        *,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    ):
        """Handle an agent error with recovery."""
        if not self._initialized:
            await self.initialize()
        return await self._error_recovery.handle_error(
            agent_id, message, category=category, severity=severity,
        )

    async def get_performance_report(self) -> dict[str, Any]:
        """Get comprehensive performance report."""
        if not self._initialized:
            await self.initialize()
        return {
            "performance": self._performance.get_summary(),
            "bottlenecks": self._performance.get_bottlenecks(),
            "recommendations": self._performance.get_recommendations(),
            "learning": self._learning.stats(),
            "coordination": self._coordination.stats(),
            "context_sharing": self._context_sharing.stats(),
            "error_recovery": await self._error_recovery.get_error_stats(),
            "tool_optimization": self._tool_optimizer.stats(),
            "state_management": self._state_manager.stats(),
        }

    async def get_learning_summary(self, agent_id: str | None = None) -> dict[str, Any]:
        """Get learning summary for an agent or all agents."""
        if not self._initialized:
            await self.initialize()
        if agent_id:
            return await self._learning.get_agent_summary(agent_id)
        return self._learning.stats()

    async def suggest_improvements(self, agent_id: str) -> list[str]:
        """Get improvement suggestions for an agent."""
        if not self._initialized:
            await self.initialize()
        return await self._learning.suggest_improvements(agent_id)

    async def shutdown(self) -> None:
        """Gracefully shutdown the advanced agent system."""
        if self._lifecycle:
            await self._lifecycle.transition(
                AgentState.TERMINATED, reason="shutdown", force=True,
            )
        self._initialized = False
        logger.info("Advanced agent system shutdown")

    @property
    def pipeline(self) -> AgentPipeline:
        return self._pipeline

    @property
    def blackboard(self) -> Blackboard:
        return self._blackboard

    @property
    def lifecycle(self) -> AgentLifecycle | None:
        return self._lifecycle

    @property
    def performance(self) -> PerformanceTracker:
        return self._performance

    @property
    def learning(self) -> AgentLearning:
        return self._learning

    @property
    def coordination(self) -> CoordinationProtocol:
        return self._coordination

    @property
    def context_sharing(self) -> ContextSharing:
        return self._context_sharing

    @property
    def error_recovery(self) -> ErrorRecovery:
        return self._error_recovery

    @property
    def tool_optimizer(self) -> ToolOptimizer:
        return self._tool_optimizer

    @property
    def state_manager(self) -> AgentStateManager:
        return self._state_manager
