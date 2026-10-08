"""Forgetting curve -- Ebbinghaus-based memory decay modeling.

Professional AI assistants model human memory decay to prioritize which
memories to keep, consolidate, or forget. This module implements the
Ebbinghaus forgetting curve:

    R(t) = e^(-t / S)

Where:
    R(t) = retention at time t
    t    = time since last access
    S    = stability of the memory (increases with each review)

Key features:
- Calculate retention probability for any memory
- Predict when a memory will fall below a retention threshold
- Schedule optimal review intervals (spaced repetition)
- Adjust memory importance based on forgetting curve
- Batch-process all memories to find "at-risk" ones
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ForgettingCurve:
    """Parameters for a single memory's forgetting curve."""
    memory_id: str
    stability: float = 1.0          # S parameter (higher = more stable)
    last_access: float = 0.0        # timestamp of last access
    review_count: int = 0           # number of times reviewed
    base_retention: float = 1.0     # initial retention (0.0-1.0)

    def __post_init__(self) -> None:
        if self.last_access == 0.0:
            self.last_access = time.time()

    def retention(self, at_time: float | None = None) -> float:
        """Calculate retention probability at given time (default: now).

        R(t) = base_retention * e^(-t / S)
        where t = at_time - last_access
        """
        t = (at_time or time.time()) - self.last_access
        if t < 0:
            t = 0
        if self.stability <= 0:
            return 0.0
        return self.base_retention * math.exp(-t / self.stability)

    def time_to_threshold(self, threshold: float = 0.3) -> float:
        """Predict seconds until retention falls below threshold.

        Solves: threshold = e^(-t / S) for t
        t = -S * ln(threshold)
        """
        if self.stability <= 0 or threshold <= 0 or threshold >= 1:
            return 0.0
        return -self.stability * math.log(threshold)

    def is_at_risk(self, threshold: float = 0.3) -> bool:
        """Check if memory retention is below threshold."""
        return self.retention() < threshold

    def review(self, at_time: float | None = None) -> None:
        """Record a review, increasing stability.

        Each review increases stability by a factor (spaced repetition).
        S_new = S_old * (1 + 0.5 * review_count)
        """
        now = at_time or time.time()
        self.last_access = now
        self.review_count += 1
        # Stability grows with each review (spaced repetition effect)
        self.stability *= (1.0 + 0.5 * min(self.review_count, 10))
        self.base_retention = 1.0  # Reset retention after review

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "stability": round(self.stability, 4),
            "last_access": self.last_access,
            "review_count": self.review_count,
            "base_retention": round(self.base_retention, 4),
            "current_retention": round(self.retention(), 4),
            "at_risk": self.is_at_risk(),
        }


@dataclass
class ReviewSchedule:
    """Optimal review schedule for a memory."""
    memory_id: str
    intervals: list[float] = field(default_factory=list)  # seconds between reviews
    next_review: float = 0.0  # timestamp of next recommended review

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "intervals": [round(i, 1) for i in self.intervals],
            "next_review": self.next_review,
        }


class ForgettingCurveManager:
    """Manages forgetting curves for all memories.

    Usage:
        fcm = ForgettingCurveManager(memory_manager)
        fcm.register_memory("mem_1")
        fcm.review("mem_1")
        at_risk = fcm.get_at_risk_memories()
        schedule = fcm.get_review_schedule("mem_1")
    """

    def __init__(
        self,
        memory_manager=None,
        default_stability: float = 86400.0,  # 1 day in seconds
        risk_threshold: float = 0.3,
    ) -> None:
        self._mm = memory_manager
        self._default_stability = default_stability
        self._risk_threshold = risk_threshold
        self._curves: dict[str, ForgettingCurve] = {}

    def register_memory(
        self,
        memory_id: str,
        stability: float | None = None,
        last_access: float | None = None,
    ) -> ForgettingCurve:
        """Register a memory for forgetting curve tracking."""
        curve = ForgettingCurve(
            memory_id=memory_id,
            stability=stability or self._default_stability,
            last_access=last_access or time.time(),
        )
        self._curves[memory_id] = curve
        return curve

    def get_curve(self, memory_id: str) -> ForgettingCurve | None:
        """Get the forgetting curve for a memory."""
        return self._curves.get(memory_id)

    def review(self, memory_id: str) -> None:
        """Record a review of a memory, increasing its stability."""
        if memory_id in self._curves:
            self._curves[memory_id].review()
        else:
            self.register_memory(memory_id)

    def get_retention(self, memory_id: str) -> float:
        """Get current retention probability for a memory."""
        curve = self._curves.get(memory_id)
        if curve is None:
            return 0.0
        return curve.retention()

    def get_at_risk_memories(self, threshold: float | None = None) -> list[ForgettingCurve]:
        """Get all memories with retention below threshold."""
        thresh = threshold or self._risk_threshold
        return [c for c in self._curves.values() if c.is_at_risk(thresh)]

    def get_review_schedule(self, memory_id: str) -> ReviewSchedule | None:
        """Generate optimal review schedule using spaced repetition.

        Intervals follow the classic spaced repetition pattern:
        1 day, 3 days, 7 days, 14 days, 30 days, 60 days, 120 days...
        """
        curve = self._curves.get(memory_id)
        if curve is None:
            return None

        base = self._default_stability
        intervals = [base * f for f in [1, 3, 7, 14, 30, 60, 120]]
        next_review = curve.last_access + intervals[min(curve.review_count, len(intervals) - 1)]

        return ReviewSchedule(
            memory_id=memory_id,
            intervals=intervals,
            next_review=next_review,
        )

    def get_due_reviews(self) -> list[str]:
        """Get memory IDs that are due for review."""
        now = time.time()
        due = []
        for memory_id, curve in self._curves.items():
            schedule = self.get_review_schedule(memory_id)
            if schedule and schedule.next_review <= now:
                due.append(memory_id)
        return due

    def adjust_importance(self, memory_id: str, current_importance: float) -> float:
        """Adjust memory importance based on forgetting curve retention.

        Memories with low retention get boosted importance (to trigger
        re-consolidation) or reduced importance (if truly forgotten).
        """
        retention = self.get_retention(memory_id)
        if retention < 0.1:
            # Nearly forgotten - reduce importance
            return current_importance * 0.5
        elif retention < 0.3:
            # At risk - boost importance to trigger review
            return min(1.0, current_importance * 1.2)
        return current_importance

    def batch_register_from_manager(self) -> int:
        """Register all memories from the memory manager."""
        if self._mm is None:
            return 0
        count = 0
        try:
            # Register LTM entries
            if hasattr(self._mm, '_ltm'):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    entries = loop.run_until_complete(self._mm._ltm.all())
                except RuntimeError:
                    entries = []
                for entry in entries:
                    if entry.id not in self._curves:
                        self.register_memory(
                            entry.id,
                            last_access=getattr(entry, 'created_at', time.time()),
                        )
                        count += 1
        except Exception as exc:
            logger.debug("Batch register from manager failed: %s", exc)
        return count

    def stats(self) -> dict[str, Any]:
        """Return forgetting curve statistics."""
        total = len(self._curves)
        at_risk = len(self.get_at_risk_memories())
        retentions = [c.retention() for c in self._curves.values()]
        avg_retention = sum(retentions) / len(retentions) if retentions else 0.0
        return {
            "total_memories": total,
            "at_risk": at_risk,
            "avg_retention": round(avg_retention, 4),
            "risk_threshold": self._risk_threshold,
            "default_stability": self._default_stability,
        }
