"""Deep reflection and self-critique for agent cognition.

Implements multi-level reflection: task-level (did I solve it?),
strategy-level (was my approach good?), and self-model-level (what did I learn about myself?).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class ReflectionLevel(str, Enum):
    TASK = "task"
    STRATEGY = "strategy"
    SELF_MODEL = "self_model"


@dataclass
class ReflectionResult:
    """Result of a deep reflection."""
    level: ReflectionLevel
    critique: str
    lessons_learned: list[str]
    improvements: list[str]
    confidence_delta: float  # how much confidence should change
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class DeepReflection:
    """Deep reflection and self-critique engine.

    After task execution, reflects on the process and outcomes to extract
    lessons, identify improvements, and update the agent's self-model.
    """

    def __init__(self, *, llm: Any = None) -> None:
        self._llm = llm
        self._lessons: list[dict[str, Any]] = []
        self._reflection_count = 0

    async def reflect(
        self,
        *,
        task: str,
        approach: str,
        outcome: str,
        success: bool,
        iterations: int,
        errors: list[str] | None = None,
        level: ReflectionLevel = ReflectionLevel.TASK,
    ) -> ReflectionResult:
        """Perform deep reflection on a completed task.

        Args:
            task: The original task.
            approach: Description of the approach taken.
            outcome: The outcome/result.
            success: Whether the task was successful.
            iterations: Number of iterations used.
            errors: List of errors encountered.
            level: Depth of reflection.

        Returns:
            ReflectionResult with critique and lessons.
        """
        self._reflection_count += 1
        errors = errors or []

        # Build reflection prompt
        critique = await self._generate_critique(
            task, approach, outcome, success, iterations, errors, level
        )
        lessons = self._extract_lessons(critique, success, errors)
        improvements = self._suggest_improvements(critique, approach, errors)
        confidence_delta = self._compute_confidence_delta(success, iterations, errors)

        result = ReflectionResult(
            level=level,
            critique=critique,
            lessons_learned=lessons,
            improvements=improvements,
            confidence_delta=confidence_delta,
            metadata={
                "task": task[:200],
                "success": success,
                "iterations": iterations,
                "error_count": len(errors),
            },
        )

        # Store lessons
        for lesson in lessons:
            self._lessons.append({
                "lesson": lesson,
                "task": task[:200],
                "success": success,
                "timestamp": time.time(),
            })

        return result

    async def reflect_on_strategy(
        self,
        *,
        strategy: str,
        task_type: str,
        outcomes: list[bool],
        latencies: list[float],
    ) -> ReflectionResult:
        """Reflect on the effectiveness of a strategy for a task type.

        Args:
            strategy: The strategy used.
            task_type: Type of task.
            outcomes: List of success/failure booleans.
            latencies: List of execution times.

        Returns:
            ReflectionResult focused on strategy effectiveness.
        """
        success_rate = sum(outcomes) / len(outcomes) if outcomes else 0.0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        critique = (
            f"Strategy '{strategy}' for task type '{task_type}':\n"
            f"  Success rate: {success_rate:.2f} ({sum(outcomes)}/{len(outcomes)})\n"
            f"  Average latency: {avg_latency:.2f}s\n"
        )
        if success_rate < 0.5:
            critique += "  This strategy is underperforming. Consider alternatives."
        elif success_rate > 0.8:
            critique += "  This strategy is effective. Keep using it for this task type."
        else:
            critique += "  This strategy is adequate but has room for improvement."

        lessons = []
        if success_rate < 0.5:
            lessons.append(f"Strategy '{strategy}' has low success rate for {task_type}")
        if avg_latency > 30.0:
            lessons.append(f"Strategy '{strategy}' is slow for {task_type} ({avg_latency:.1f}s avg)")

        return ReflectionResult(
            level=ReflectionLevel.STRATEGY,
            critique=critique,
            lessons_learned=lessons,
            improvements=[f"Consider alternative strategies for {task_type}"] if success_rate < 0.5 else [],
            confidence_delta=0.0,
            metadata={"strategy": strategy, "task_type": task_type, "success_rate": success_rate},
        )

    def get_lessons(self, *, task_type: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve learned lessons, optionally filtered by task type."""
        lessons = self._lessons
        if task_type:
            lessons = [l for l in lessons if task_type in l.get("task", "")]
        return lessons[-limit:]

    def clear_lessons(self) -> None:
        """Clear all stored lessons."""
        self._lessons.clear()

    async def _generate_critique(
        self,
        task: str,
        approach: str,
        outcome: str,
        success: bool,
        iterations: int,
        errors: list[str],
        level: ReflectionLevel,
    ) -> str:
        """Generate a critique using the LLM or heuristics."""
        if self._llm:
            try:
                from app.services.llm_service import ChatMessage
                prompt = (
                    f"Reflect on this task execution:\n"
                    f"Task: {task}\n"
                    f"Approach: {approach}\n"
                    f"Outcome: {outcome}\n"
                    f"Success: {success}\n"
                    f"Iterations: {iterations}\n"
                    f"Errors: {errors}\n"
                    f"Level: {level.value}\n\n"
                    "Provide a brief critique: what went well, what could be improved, "
                    "and what was learned."
                )
                resp = await self._llm.complete(
                    [ChatMessage(role="user", content=prompt)],
                    max_tokens=512,
                    temperature=0.3,
                )
                return (resp.content or "").strip()
            except Exception as exc:
                logger.warning("LLM critique failed: %s", exc)

        # Fallback heuristic critique
        parts = []
        if success:
            parts.append("Task completed successfully.")
        else:
            parts.append("Task did not complete successfully.")
        if iterations > 10:
            parts.append(f"High iteration count ({iterations}) suggests inefficiency.")
        if errors:
            parts.append(f"Encountered {len(errors)} errors: {errors[:3]}")
        return " ".join(parts)

    def _extract_lessons(self, critique: str, success: bool, errors: list[str]) -> list[str]:
        """Extract lessons from the critique."""
        lessons = []
        if not success:
            lessons.append("Task failed — analyze root cause before retrying")
        if errors:
            error_types = set()
            for e in errors:
                if "timeout" in e.lower():
                    error_types.add("timeout")
                elif "connection" in e.lower():
                    error_types.add("connection")
                elif "permission" in e.lower():
                    error_types.add("permission")
            for et in error_types:
                lessons.append(f"Encountered {et} errors — add resilience")
        if "inefficiency" in critique.lower():
            lessons.append("Process was inefficient — consider better planning")
        return lessons

    def _suggest_improvements(self, critique: str, approach: str, errors: list[str]) -> list[str]:
        """Suggest improvements based on critique."""
        improvements = []
        if "inefficiency" in critique.lower():
            improvements.append("Use DAG planning for complex tasks")
        if errors:
            improvements.append("Add error recovery and retry logic")
        if "planning" in approach.lower():
            improvements.append("Review planning quality and adjust decomposition")
        return improvements

    def _compute_confidence_delta(self, success: bool, iterations: int, errors: list[str]) -> float:
        """Compute how much confidence should change."""
        delta = 0.0
        if success:
            delta += 0.1
        else:
            delta -= 0.2
        if iterations > 10:
            delta -= 0.05
        if len(errors) > 3:
            delta -= 0.1
        return max(-0.5, min(0.5, delta))
