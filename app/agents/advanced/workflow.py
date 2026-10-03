"""Professional agent workflow — integrates all advanced agent modules into a
cohesive multi-stage execution pipeline.

This workflow enhances the basic pipeline with:
- Blackboard-based coordination
- Lifecycle state management
- Performance tracking
- Self-learning from outcomes
- Context sharing between agents
- Error detection and recovery
- Tool usage optimization
- State persistence and recovery
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger
from app.agents.advanced.blackboard import Blackboard
from app.agents.advanced.lifecycle import AgentLifecycle, AgentState
from app.agents.advanced.performance import PerformanceTracker, TaskExecution
from app.agents.advanced.learning import AgentLearning
from app.agents.advanced.coordination import CoordinationProtocol, CoordinationMode
from app.agents.advanced.context_sharing import ContextSharing
from app.agents.advanced.error_recovery import ErrorRecovery, ErrorCategory, ErrorSeverity
from app.agents.advanced.tool_optimizer import ToolOptimizer
from app.agents.advanced.state_manager import AgentStateManager

logger = get_logger(__name__)


@dataclass
class WorkflowResult:
    """Result of a professional agent workflow execution."""
    success: bool
    output: str
    stages_completed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    performance: dict[str, Any] = field(default_factory=dict)
    learning: dict[str, Any] = field(default_factory=dict)
    coordination: dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ProfessionalAgentWorkflow:
    """Professional agent workflow integrating all advanced agent modules.

    This workflow provides a structured execution pipeline:
    1. Initialize lifecycle and blackboard
    2. Announce task for coordination
    3. Execute with performance tracking
    4. Share context between agents
    5. Handle errors with recovery
    6. Learn from outcomes
    7. Persist state for recovery
    """

    def __init__(
        self,
        *,
        agent_id: str = "orchestrator",
        coordination_mode: CoordinationMode = CoordinationMode.HIERARCHICAL,
        enable_learning: bool = True,
        enable_error_recovery: bool = True,
        enable_tool_optimization: bool = True,
        enable_state_persistence: bool = True,
    ) -> None:
        self._agent_id = agent_id
        self._enable_learning = enable_learning
        self._enable_error_recovery = enable_error_recovery
        self._enable_tool_optimization = enable_tool_optimization
        self._enable_state_persistence = enable_state_persistence

        # Subsystems
        self._blackboard = Blackboard(agent_id)
        self._lifecycle: AgentLifecycle | None = None
        self._performance = PerformanceTracker()
        self._learning = AgentLearning()
        self._coordination = CoordinationProtocol(mode=coordination_mode)
        self._context_sharing = ContextSharing()
        self._error_recovery = ErrorRecovery()
        self._tool_optimizer = ToolOptimizer()
        self._state_manager = AgentStateManager()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the workflow."""
        self._lifecycle = AgentLifecycle(
            agent_id=self._agent_id,
            on_state_change=self._on_state_change,
            on_event=self._on_lifecycle_event,
        )
        self._initialized = True
        logger.info("Professional agent workflow initialized for %s", self._agent_id)

    def _on_state_change(self, transition) -> None:
        logger.debug("State change: %s -> %s", transition.from_state, transition.to_state)

    def _on_lifecycle_event(self, event) -> None:
        logger.debug("Lifecycle event: %s", event.event_type)

    async def execute(
        self,
        *,
        task: str,
        context: dict[str, Any] | None = None,
        requirements: list[str] | None = None,
        priority: int = 5,
    ) -> WorkflowResult:
        """Execute the professional agent workflow.

        Args:
            task: The task to execute.
            context: Additional context.
            requirements: Task requirements.
            priority: Task priority (1-10).

        Returns:
            WorkflowResult with the output and full execution metadata.
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.monotonic()
        stages_completed: list[str] = []
        errors: list[str] = []

        # Stage 1: Lifecycle - transition to idle first, then planning
        if self._lifecycle is not None:
            try:
                await self._lifecycle.transition(AgentState.IDLE, reason="task_received")
                await self._lifecycle.transition(AgentState.PLANNING, reason="task_received")
                stages_completed.append("lifecycle_planning")
            except Exception as exc:
                errors.append(f"lifecycle_planning: {exc}")

        # Stage 2: Coordination - announce task
        try:
            task_id = await self._coordination.announce_task(
                task, requirements or [], priority=priority,
            )
            stages_completed.append("coordination")
        except Exception as exc:
            errors.append(f"coordination: {exc}")
            task_id = f"task_{int(start_time * 1000)}"

        # Stage 3: Blackboard - post task
        try:
            await self._blackboard.post(
                agent_id=self._agent_id,
                content=task,
                content_type="task",
                task_id=task_id,
            )
            stages_completed.append("blackboard")
        except Exception as exc:
            errors.append(f"blackboard: {exc}")

        # Stage 4: Lifecycle - transition to executing
        try:
            await self._lifecycle.transition(AgentState.EXECUTING, reason="task_accepted")
            stages_completed.append("lifecycle_executing")
        except Exception as exc:
            errors.append(f"lifecycle_executing: {exc}")

        # Stage 5: Performance tracking - start
        execution = TaskExecution(
            task_id=task_id,
            agent_id=self._agent_id,
            start_time=start_time,
        )

        # Stage 6: Execute the task (placeholder - actual execution is done by the caller)
        output = ""
        success = False
        try:
            # The actual task execution is done by the Orchestrator's cognition loop
            # This workflow wraps it with professional agent infrastructure
            output = context.get("output", "") if context else ""
            success = bool(output)
            stages_completed.append("execution")
        except Exception as exc:
            errors.append(f"execution: {exc}")
            if self._enable_error_recovery:
                try:
                    await self._error_recovery.handle_error(
                        agent_id=self._agent_id,
                        message=str(exc),
                        category=ErrorCategory.UNKNOWN,
                        severity=ErrorSeverity.HIGH,
                    )
                    stages_completed.append("error_recovery")
                except Exception as recovery_exc:
                    errors.append(f"error_recovery: {recovery_exc}")

        # Stage 7: Performance tracking - end
        execution.end_time = time.monotonic()
        execution.success = success
        execution.quality_score = 1.0 if success else 0.0
        self._performance.record(execution)
        stages_completed.append("performance")

        # Stage 8: Context sharing - publish result
        try:
            await self._context_sharing.publish(
                task_id=task_id,
                agent_id=self._agent_id,
                content=output[:500] if output else "",
                context_type="result",
            )
            stages_completed.append("context_sharing")
        except Exception as exc:
            errors.append(f"context_sharing: {exc}")

        # Stage 9: Learning - record outcome
        if self._enable_learning:
            try:
                await self._learning.record_outcome(
                    agent_id=self._agent_id,
                    task_prompt=task,
                    outcome=output[:500] if output else "",
                    success=success,
                    lesson="; ".join(errors) if errors else "",
                )
                stages_completed.append("learning")
            except Exception as exc:
                errors.append(f"learning: {exc}")

        # Stage 10: Tool optimization - record usage
        if self._enable_tool_optimization and context and "tool_calls" in context:
            try:
                for tool_call in context.get("tool_calls", []):
                    await self._tool_optimizer.record_usage(
                        tool_name=tool_call.get("name", "unknown"),
                        agent_id=self._agent_id,
                        task_id=task_id,
                        success=tool_call.get("success", True),
                        duration=tool_call.get("duration", 0.0),
                    )
                stages_completed.append("tool_optimization")
            except Exception as exc:
                errors.append(f"tool_optimization: {exc}")

        # Stage 11: State persistence
        if self._enable_state_persistence:
            try:
                await self._state_manager.save_state(
                    agent_id=self._agent_id,
                    task_id=task_id,
                    state={
                        "task": task,
                        "output": output[:1000],
                        "success": success,
                        "stages": stages_completed,
                        "errors": errors,
                    },
                )
                stages_completed.append("state_persistence")
            except Exception as exc:
                errors.append(f"state_persistence: {exc}")

        # Stage 12: Lifecycle - transition to completed
        try:
            await self._lifecycle.transition(
                AgentState.IDLE if success else AgentState.TERMINATED,
                reason="task_completed" if success else "task_failed",
            )
            stages_completed.append("lifecycle_completed")
        except Exception as exc:
            errors.append(f"lifecycle_completed: {exc}")

        execution_time = time.monotonic() - start_time

        return WorkflowResult(
            success=success,
            output=output,
            stages_completed=stages_completed,
            errors=errors,
            performance=self._performance.get_summary(),
            learning=self._learning.stats(),
            coordination=self._coordination.stats(),
            execution_time=execution_time,
            metadata={
                "task_id": task_id,
                "stages_completed": len(stages_completed),
                "errors_count": len(errors),
            },
        )

    async def get_performance_report(self) -> dict[str, Any]:
        """Get comprehensive performance report."""
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

    async def shutdown(self) -> None:
        """Gracefully shutdown the workflow."""
        if self._lifecycle:
            await self._lifecycle.transition(
                AgentState.TERMINATED, reason="shutdown", force=True,
            )
        self._initialized = False
        logger.info("Professional agent workflow shutdown")
