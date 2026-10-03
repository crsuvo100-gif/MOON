"""Unified brain orchestrator — ties all advanced brain modules together.

Coordinates ReAct reasoning, DAG planning, working memory, metacognition,
context compression, tool composition, uncertainty estimation, deep reflection,
and goal tracking into a cohesive cognitive pipeline.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger
from app.brain.advanced.react import ReActLoop, ReActResult
from app.brain.advanced.dag_planner import DAGPlanner, DAGPlan
from app.brain.advanced.working_memory import WorkingMemory
from app.brain.advanced.metacognition import Metacognition, Strategy
from app.brain.advanced.context_compressor import ContextCompressor
from app.brain.advanced.tool_composer import ToolComposer, ToolChain
from app.brain.advanced.uncertainty import UncertaintyEstimator
from app.brain.advanced.reflection import DeepReflection, ReflectionLevel
from app.brain.advanced.goal_tracker import GoalTracker, GoalStatus

logger = get_logger(__name__)


@dataclass
class BrainResult:
    """Result of a full brain orchestration."""
    answer: str
    success: bool
    strategy_used: str
    iterations: int
    tool_calls: int
    confidence: float
    uncertainty: float
    execution_time: float
    react_result: ReActResult | None = None
    dag_plan: DAGPlan | None = None
    reflection: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BrainOrchestrator:
    """Unified brain orchestrator coordinating all advanced cognition modules.

    Provides a single entry point for professional-grade agent cognition:
    plan → reason → act → observe → reflect → learn.
    """

    def __init__(
        self,
        *,
        llm: Any = None,
        tool_executor: Any = None,
        max_iterations: int = 10,
        max_tool_calls: int = 5,
        enable_reflection: bool = True,
        enable_uncertainty: bool = True,
        enable_goal_tracking: bool = True,
    ) -> None:
        self._llm = llm
        self._tool_executor = tool_executor
        self._enable_reflection = enable_reflection
        self._enable_uncertainty = enable_uncertainty
        self._enable_goal_tracking = enable_goal_tracking

        # Initialize all subsystems
        self._react = ReActLoop(
            max_iterations=max_iterations,
            max_tool_calls=max_tool_calls,
            tool_executor=tool_executor,
            llm=llm,
        )
        self._planner = DAGPlanner()
        self._memory = WorkingMemory(capacity=20)
        self._meta = Metacognition()
        self._compressor = ContextCompressor(llm=llm)
        self._composer = ToolComposer(tool_executor=tool_executor)
        self._uncertainty = UncertaintyEstimator()
        self._reflection = DeepReflection(llm=llm)
        self._goals = GoalTracker()

    async def think(
        self,
        *,
        task: str,
        context: str | None = None,
        available_tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> BrainResult:
        """Execute the full cognitive pipeline for a task.

        Args:
            task: The user task.
            context: Optional additional context.
            available_tools: Available tool specs.
            system_prompt: Optional system prompt.

        Returns:
            BrainResult with the answer and full execution metadata.
        """
        start_time = time.time()
        await self._meta.reset()

        # Step 1: Create goal if tracking enabled
        goal_id = None
        if self._enable_goal_tracking:
            goal = await self._goals.create_goal(
                goal_id=f"goal_{int(start_time)}",
                description=task[:200],
            )
            goal_id = goal.id

        # Step 2: Add task to working memory
        await self._memory.add(task, importance=0.9, metadata={"type": "task"})

        # Step 3: Choose strategy based on metacognition
        strategy = await self._meta.recommend_strategy()
        await self._meta.update(confidence=0.5, uncertainty=0.5)

        # Step 4: Execute ReAct loop
        react_result = await self._react.run(
            task=task,
            system_prompt=system_prompt,
            context=context,
            available_tools=available_tools,
        )

        # Step 5: Update working memory with results
        if react_result.answer:
            await self._memory.add(
                react_result.answer[:500],
                importance=0.7,
                metadata={"type": "result"},
            )

        # Step 6: Estimate uncertainty
        uncertainty_result = None
        if self._enable_uncertainty:
            uncertainty_result = await self._uncertainty.estimate(
                model_confidence=0.7 if react_result.success else 0.3,
                task_complexity=0.5,
                task_type="general",
            )
            await self._meta.update(
                confidence=uncertainty_result.confidence,
                uncertainty=uncertainty_result.uncertainty,
            )

        # Step 7: Reflect on the process
        reflection_data = None
        if self._enable_reflection:
            reflection_result = await self._reflection.reflect(
                task=task,
                approach=f"ReAct with strategy {strategy.value}",
                outcome=react_result.answer,
                success=react_result.success,
                iterations=react_result.iterations,
                errors=[],
                level=ReflectionLevel.TASK,
            )
            reflection_data = {
                "critique": reflection_result.critique,
                "lessons": reflection_result.lessons_learned,
                "improvements": reflection_result.improvements,
            }

        # Step 8: Update goal progress
        if goal_id:
            await self._goals.update_progress(
                goal_id,
                progress=1.0 if react_result.success else 0.3,
                status=GoalStatus.COMPLETED if react_result.success else GoalStatus.ACTIVE,
            )

        # Step 9: Update metacognition
        execution_time = time.time() - start_time
        await self._meta.update(
            latency=execution_time,
            error=not react_result.success,
            success=react_result.success,
        )
        await self._meta.record_strategy_result(
            strategy, react_result.success, execution_time
        )

        return BrainResult(
            answer=react_result.answer,
            success=react_result.success,
            strategy_used=strategy.value,
            iterations=react_result.iterations,
            tool_calls=react_result.metadata.get("tool_calls", 0),
            confidence=uncertainty_result.confidence if uncertainty_result else 0.5,
            uncertainty=uncertainty_result.uncertainty if uncertainty_result else 0.5,
            execution_time=execution_time,
            react_result=react_result,
            reflection=reflection_data,
            metadata={
                "goal_id": goal_id,
                "metacognition": self._meta.get_summary(),
            },
        )

    async def plan_and_execute(
        self,
        *,
        task: str,
        subtasks: list[dict[str, Any]],
        context: str | None = None,
    ) -> BrainResult:
        """Plan a task as a DAG and execute it.

        Args:
            task: The main task.
            subtasks: List of subtask specs with id, description, dependencies.
            context: Optional context.

        Returns:
            BrainResult with the combined answer.
        """
        start_time = time.time()

        # Build DAG plan
        plan = self._planner.plan(subtasks)

        # Execute each node
        async def _execute_node(node: Any) -> str:
            result = await self.think(
                task=node.description,
                context=context,
            )
            return result.answer

        plan = await self._planner.execute(plan, executor=_execute_node)

        # Combine results
        answers = [
            f"[{nid}]: {plan.nodes[nid].result}"
            for nid in plan.nodes
            if plan.nodes[nid].result
        ]
        combined = "\n\n".join(answers)

        execution_time = time.time() - start_time

        return BrainResult(
            answer=combined,
            success=plan.failed_nodes == 0,
            strategy_used="dag_plan",
            iterations=len(plan.nodes),
            tool_calls=0,
            confidence=0.8 if plan.failed_nodes == 0 else 0.4,
            uncertainty=0.2 if plan.failed_nodes == 0 else 0.6,
            execution_time=execution_time,
            dag_plan=plan,
            metadata={"stages": len(plan.stages)},
        )

    async def get_memory_context(self) -> str:
        """Get working memory as a context string."""
        return self._memory.to_context_string()

    async def get_goal_summary(self) -> dict[str, Any]:
        """Get goal tracking summary."""
        return await self._goals.get_progress_summary()

    async def get_metacognition_state(self) -> str:
        """Get metacognition summary."""
        return self._meta.get_summary()

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        await self._memory.clear()
