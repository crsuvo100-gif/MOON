"""Metacognitive monitoring and control for agent cognition.

Tracks the agent's own cognitive state: confidence, uncertainty, cognitive load,
and strategy effectiveness. Provides feedback for strategy adjustment.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class Strategy(str, Enum):
    DIRECT = "direct"
    REACT = "react"
    PLAN_THEN_EXECUTE = "plan_then_execute"
    DECOMPOSE = "decompose"
    ASK_USER = "ask_user"


class CognitiveLoad(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    OVERLOADED = "overloaded"


@dataclass
class MetaState:
    """Current metacognitive state."""
    confidence: float = 0.5          # 0..1
    uncertainty: float = 0.5         # 0..1
    cognitive_load: CognitiveLoad = CognitiveLoad.LOW
    current_strategy: Strategy = Strategy.DIRECT
    strategy_effectiveness: dict[str, float] = field(default_factory=dict)
    iteration_count: int = 0
    error_count: int = 0
    success_count: int = 0
    avg_latency: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.error_count
        if total == 0:
            return 0.5
        return self.success_count / total

    @property
    def needs_adjustment(self) -> bool:
        """Check if the current strategy needs adjustment."""
        return self.uncertainty > 0.7 or self.confidence < 0.3


class Metacognition:
    """Metacognitive monitor that tracks and adjusts agent strategy.

    Monitors confidence, uncertainty, and cognitive load during task execution.
    Recommends strategy adjustments when performance degrades.
    """

    def __init__(self) -> None:
        self._state = MetaState()
        self._history: list[MetaState] = []
        self._lock = asyncio.Lock()

    async def update(
        self,
        *,
        confidence: float | None = None,
        uncertainty: float | None = None,
        latency: float | None = None,
        error: bool = False,
        success: bool = False,
    ) -> MetaState:
        """Update metacognitive state with new observations."""
        async with self._lock:
            if confidence is not None:
                self._state.confidence = max(0.0, min(1.0, confidence))
            if uncertainty is not None:
                self._state.uncertainty = max(0.0, min(1.0, uncertainty))
            if latency is not None:
                # Exponential moving average
                alpha = 0.3
                self._state.avg_latency = (
                    alpha * latency + (1 - alpha) * self._state.avg_latency
                )
            if error:
                self._state.error_count += 1
            if success:
                self._state.success_count += 1
            self._state.iteration_count += 1
            self._state.cognitive_load = self._compute_load()
            self._state.timestamp = time.time()
            return self._state

    async def record_strategy_result(self, strategy: Strategy, success: bool, latency: float) -> None:
        """Record the outcome of using a strategy."""
        async with self._lock:
            key = strategy.value
            prev = self._state.strategy_effectiveness.get(key, 0.5)
            alpha = 0.2
            new_val = prev * (1 - alpha) + (1.0 if success else 0.0) * alpha
            self._state.strategy_effectiveness[key] = new_val

    async def recommend_strategy(self) -> Strategy:
        """Recommend the best strategy based on effectiveness history."""
        async with self._lock:
            if not self._state.strategy_effectiveness:
                return Strategy.DIRECT
            best = max(
                self._state.strategy_effectiveness,
                key=lambda k: self._state.strategy_effectiveness[k],
            )
            return Strategy(best)

    async def should_escalate(self) -> bool:
        """Check if the task should be escalated to the user."""
        async with self._lock:
            return (
                self._state.uncertainty > 0.8
                or self._state.confidence < 0.2
                or self._state.cognitive_load == CognitiveLoad.OVERLOADED
            )

    async def get_state(self) -> MetaState:
        """Get current metacognitive state."""
        async with self._lock:
            return self._state

    async def reset(self) -> None:
        """Reset metacognitive state for a new task."""
        async with self._lock:
            self._history.append(self._state)
            self._state = MetaState()

    def _compute_load(self) -> CognitiveLoad:
        """Compute cognitive load from current state."""
        if self._state.iteration_count == 0:
            return CognitiveLoad.LOW
        error_rate = self._state.error_count / self._state.iteration_count
        if error_rate > 0.5 or self._state.iteration_count > 20:
            return CognitiveLoad.OVERLOADED
        if error_rate > 0.3 or self._state.iteration_count > 10:
            return CognitiveLoad.HIGH
        if error_rate > 0.1 or self._state.iteration_count > 5:
            return CognitiveLoad.MEDIUM
        return CognitiveLoad.LOW

    def get_summary(self) -> str:
        """Get a human-readable summary of metacognitive state."""
        s = self._state
        return (
            f"Strategy: {s.current_strategy.value}, "
            f"Confidence: {s.confidence:.2f}, "
            f"Uncertainty: {s.uncertainty:.2f}, "
            f"Load: {s.cognitive_load.value}, "
            f"Success rate: {s.success_rate:.2f}, "
            f"Iterations: {s.iteration_count}"
        )
