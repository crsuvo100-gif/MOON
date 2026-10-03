"""ContextAwareness — self-monitoring and context state awareness.

Every professional AI assistant needs to be aware of its own context state:
what it knows, what it doesn't know, how much context it has used, and
when it needs to compress or retrieve more. This module provides that
self-awareness capability.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class ContextHealth(Enum):
    """Health status of the context window."""
    HEALTHY = "healthy"       # Plenty of room, good coverage
    WARNING = "warning"       # Getting full, consider compression
    CRITICAL = "critical"     # Nearly full, compression required
    OVERFLOW = "overflow"     # Over budget, eviction happening


@dataclass
class ContextAwarenessState:
    """Snapshot of context awareness state."""
    health: ContextHealth
    utilization: float
    total_items: int
    total_tokens: int
    available_tokens: int
    sources: dict[str, int]
    oldest_item_age: float
    newest_item_age: float
    avg_relevance: float
    avg_importance: float
    recommendations: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class ContextAwareness:
    """Self-monitoring context awareness system.

    Wraps a ContextWindow and provides:
    - Health monitoring (healthy/warning/critical/overflow)
    - Coverage analysis (what sources are represented)
    - Relevance tracking (are we holding relevant items?)
    - Recommendations (compress, retrieve more, evict, etc.)
    - Trend detection (is context growing or shrinking?)
    """

    def __init__(self, *, warning_threshold: float = 0.7, critical_threshold: float = 0.9) -> None:
        self._warning_threshold = warning_threshold
        self._critical_threshold = critical_threshold
        self._history: list[ContextAwarenessState] = []
        self._max_history = 50

    def assess(self, window) -> ContextAwarenessState:
        """Assess the current context window state and return awareness state."""
        utilization = window.utilization
        items = window.items

        # Determine health
        if utilization >= 1.0:
            health = ContextHealth.OVERFLOW
        elif utilization >= self._critical_threshold:
            health = ContextHealth.CRITICAL
        elif utilization >= self._warning_threshold:
            health = ContextHealth.WARNING
        else:
            health = ContextHealth.HEALTHY

        # Source coverage
        sources: dict[str, int] = {}
        for item in items:
            sources[item.source] = sources.get(item.source, 0) + 1

        # Age analysis
        now = time.time()
        ages = [now - item.timestamp for item in items] if items else [0.0]
        oldest_age = max(ages)
        newest_age = min(ages)

        # Relevance and importance
        avg_relevance = sum(i.relevance for i in items) / len(items) if items else 0.0
        avg_importance = sum(i.importance for i in items) / len(items) if items else 0.0

        # Generate recommendations
        recommendations = self._generate_recommendations(
            health=health,
            utilization=utilization,
            sources=sources,
            avg_relevance=avg_relevance,
            avg_importance=avg_importance,
            available_tokens=window.available_tokens,
        )

        state = ContextAwarenessState(
            health=health,
            utilization=utilization,
            total_items=len(items),
            total_tokens=window.used_tokens,
            available_tokens=window.available_tokens,
            sources=sources,
            oldest_item_age=oldest_age,
            newest_item_age=newest_age,
            avg_relevance=avg_relevance,
            avg_importance=avg_importance,
            recommendations=recommendations,
        )

        self._history.append(state)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return state

    def get_trend(self) -> dict[str, Any]:
        """Analyze context usage trend over recent assessments."""
        if len(self._history) < 2:
            return {"trend": "stable", "delta_utilization": 0.0, "delta_items": 0}

        recent = self._history[-5:]
        older = self._history[:5] if len(self._history) >= 5 else self._history[:1]

        avg_recent_util = sum(s.utilization for s in recent) / len(recent)
        avg_older_util = sum(s.utilization for s in older) / len(older)
        delta_util = avg_recent_util - avg_older_util

        avg_recent_items = sum(s.total_items for s in recent) / len(recent)
        avg_older_items = sum(s.total_items for s in older) / len(older)
        delta_items = avg_recent_items - avg_older_items

        if delta_util > 0.1:
            trend = "growing"
        elif delta_util < -0.1:
            trend = "shrinking"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "delta_utilization": round(delta_util, 3),
            "delta_items": round(delta_items, 1),
            "assessments_count": len(self._history),
        }

    def should_compress(self) -> bool:
        """Check if context compression is recommended."""
        if not self._history:
            return False
        latest = self._history[-1]
        return latest.health in (ContextHealth.WARNING, ContextHealth.CRITICAL, ContextHealth.OVERFLOW)

    def should_retrieve(self) -> bool:
        """Check if more context retrieval is recommended."""
        if not self._history:
            return False
        latest = self._history[-1]
        # Recommend retrieval if we have room and low relevance
        return latest.utilization < 0.5 and latest.avg_relevance < 0.6

    def _generate_recommendations(
        self,
        *,
        health: ContextHealth,
        utilization: float,
        sources: dict[str, int],
        avg_relevance: float,
        avg_importance: float,
        available_tokens: int,
    ) -> list[str]:
        """Generate actionable recommendations based on context state."""
        recs: list[str] = []

        if health == ContextHealth.OVERFLOW:
            recs.append("URGENT: Context overflow — compress immediately")
        elif health == ContextHealth.CRITICAL:
            recs.append("Context nearly full — compress or evict low-value items")
        elif health == ContextHealth.WARNING:
            recs.append("Context getting full — monitor usage")

        if avg_relevance < 0.4:
            recs.append("Low average relevance — consider evicting irrelevant items")
        if avg_importance < 0.3:
            recs.append("Low average importance — review what context is being kept")
        if "history" not in sources:
            recs.append("No conversation history in context — add recent messages")
        if "retrieval" not in sources:
            recs.append("No retrieved knowledge — consider semantic search")
        if available_tokens < 500:
            recs.append("Very few tokens available — prioritize essential context only")

        return recs
