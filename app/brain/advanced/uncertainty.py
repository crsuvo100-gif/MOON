"""Uncertainty estimation and confidence calibration for agent cognition.

Estimates uncertainty in agent outputs using multiple signals: model confidence,
consistency across samples, task complexity, and historical accuracy.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class UncertaintyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class UncertaintyResult:
    """Result of uncertainty estimation."""
    uncertainty: float  # 0..1
    level: UncertaintyLevel
    confidence: float  # 1 - uncertainty
    factors: dict[str, float] = field(default_factory=dict)
    recommendation: str = ""

    @property
    def should_verify(self) -> bool:
        return self.uncertainty > 0.5

    @property
    def should_ask_user(self) -> bool:
        return self.uncertainty > 0.8


class UncertaintyEstimator:
    """Estimates uncertainty using multiple signals.

    Combines model confidence, sampling consistency, task complexity,
    and historical accuracy into a unified uncertainty score.
    """

    def __init__(self) -> None:
        self._task_history: dict[str, list[bool]] = {}

    async def estimate(
        self,
        *,
        model_confidence: float | None = None,
        sample_outputs: list[str] | None = None,
        task_complexity: float = 0.5,
        task_type: str = "general",
        historical_accuracy: float | None = None,
    ) -> UncertaintyResult:
        """Estimate uncertainty from multiple signals.

        Args:
            model_confidence: Confidence reported by the model (0..1).
            sample_outputs: Multiple sampled outputs for consistency check.
            task_complexity: Estimated task complexity (0..1).
            task_type: Type of task for historical lookup.
            historical_accuracy: Historical accuracy for this task type (0..1).

        Returns:
            UncertaintyResult with unified uncertainty score.
        """
        factors: dict[str, float] = {}

        # Factor 1: Model confidence (inverted)
        if model_confidence is not None:
            factors["model_confidence"] = 1.0 - max(0.0, min(1.0, model_confidence))
        else:
            factors["model_confidence"] = 0.5  # unknown

        # Factor 2: Sampling consistency
        if sample_outputs and len(sample_outputs) > 1:
            consistency = self._compute_consistency(sample_outputs)
            factors["sampling_consistency"] = 1.0 - consistency
        else:
            factors["sampling_consistency"] = 0.3  # no samples to compare

        # Factor 3: Task complexity
        factors["task_complexity"] = max(0.0, min(1.0, task_complexity))

        # Factor 4: Historical accuracy
        if historical_accuracy is not None:
            factors["historical_accuracy"] = 1.0 - max(0.0, min(1.0, historical_accuracy))
        else:
            # Look up from history
            hist = self._task_history.get(task_type, [])
            if hist:
                acc = sum(hist) / len(hist)
                factors["historical_accuracy"] = 1.0 - acc
            else:
                factors["historical_accuracy"] = 0.5  # no history

        # Weighted combination
        weights = {
            "model_confidence": 0.3,
            "sampling_consistency": 0.25,
            "task_complexity": 0.2,
            "historical_accuracy": 0.25,
        }
        uncertainty = sum(
            factors[k] * weights[k] for k in factors
        ) / sum(weights[k] for k in factors if k in factors)

        uncertainty = max(0.0, min(1.0, uncertainty))
        level = self._classify(uncertainty)
        recommendation = self._recommend(uncertainty, level)

        return UncertaintyResult(
            uncertainty=uncertainty,
            level=level,
            confidence=1.0 - uncertainty,
            factors=factors,
            recommendation=recommendation,
        )

    async def record_outcome(self, task_type: str, success: bool) -> None:
        """Record task outcome for historical accuracy tracking."""
        if task_type not in self._task_history:
            self._task_history[task_type] = []
        self._task_history[task_type].append(success)
        # Keep last 50 outcomes
        self._task_history[task_type] = self._task_history[task_type][-50:]

    def _compute_consistency(self, outputs: list[str]) -> float:
        """Compute consistency score across multiple outputs."""
        if len(outputs) < 2:
            return 1.0
        # Simple pairwise similarity
        similarities = []
        for i in range(len(outputs)):
            for j in range(i + 1, len(outputs)):
                sim = self._text_similarity(outputs[i], outputs[j])
                similarities.append(sim)
        return sum(similarities) / len(similarities) if similarities else 0.5

    def _text_similarity(self, a: str, b: str) -> float:
        """Simple text similarity using token overlap."""
        tokens_a = set(a.lower().split())
        tokens_b = set(b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return len(intersection) / len(union)

    def _classify(self, uncertainty: float) -> UncertaintyLevel:
        if uncertainty < 0.3:
            return UncertaintyLevel.LOW
        if uncertainty < 0.5:
            return UncertaintyLevel.MEDIUM
        if uncertainty < 0.8:
            return UncertaintyLevel.HIGH
        return UncertaintyLevel.CRITICAL

    def _recommend(self, uncertainty: float, level: UncertaintyLevel) -> str:
        if level == UncertaintyLevel.LOW:
            return "Proceed with confidence"
        if level == UncertaintyLevel.MEDIUM:
            return "Consider verification for critical decisions"
        if level == UncertaintyLevel.HIGH:
            return "Verify output before proceeding; consider alternative approaches"
        return "Stop and ask the user for guidance"
