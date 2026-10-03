"""ContextAnalytics — analytics and insights for context usage.

Every professional AI assistant needs to understand its context usage
patterns: what sources are most used, what gets evicted, how often
compression happens, and what the overall context health looks like.
This module provides that analytics capability.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ContextAnalytics:
    """Analytics snapshot for context usage."""
    total_additions: int = 0
    total_evictions: int = 0
    total_compressions: int = 0
    total_injections: int = 0
    source_distribution: dict[str, int] = field(default_factory=dict)
    avg_utilization: float = 0.0
    peak_utilization: float = 0.0
    compression_events: list[dict[str, Any]] = field(default_factory=list)
    eviction_events: list[dict[str, Any]] = field(default_factory=list)
    utilization_history: list[float] = field(default_factory=list)
    session_start: float = field(default_factory=time.time)

    @property
    def session_duration(self) -> float:
        return time.time() - self.session_start

    @property
    def eviction_rate(self) -> float:
        if self.total_additions == 0:
            return 0.0
        return self.total_evictions / self.total_additions

    @property
    def compression_rate(self) -> float:
        if self.total_additions == 0:
            return 0.0
        return self.total_compressions / self.total_additions

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_additions": self.total_additions,
            "total_evictions": self.total_evictions,
            "total_compressions": self.total_compressions,
            "total_injections": self.total_injections,
            "source_distribution": self.source_distribution,
            "avg_utilization": self.avg_utilization,
            "peak_utilization": self.peak_utilization,
            "eviction_rate": round(self.eviction_rate, 3),
            "compression_rate": round(self.compression_rate, 3),
            "session_duration": round(self.session_duration, 1),
            "utilization_history": self.utilization_history[-20:],
        }


class ContextAnalyticsTracker:
    """Tracks context usage analytics over time.

    Can be used standalone or as part of the ContextOrchestrator.
    """

    def __init__(self, *, max_history: int = 100) -> None:
        self._analytics = ContextAnalytics()
        self._max_history = max_history

    @property
    def analytics(self) -> ContextAnalytics:
        return self._analytics

    def record_addition(self, *, source: str) -> None:
        """Record a context addition."""
        self._analytics.total_additions += 1
        self._analytics.source_distribution[source] = self._analytics.source_distribution.get(source, 0) + 1

    def record_eviction(self, *, source: str, reason: str = "") -> None:
        """Record a context eviction."""
        self._analytics.total_evictions += 1
        self._analytics.eviction_events.append({
            "source": source,
            "reason": reason,
            "timestamp": time.time(),
        })
        if len(self._analytics.eviction_events) > self._max_history:
            self._analytics.eviction_events = self._analytics.eviction_events[-self._max_history:]

    def record_compression(self, *, strategy: str, original_tokens: int, compressed_tokens: int) -> None:
        """Record a context compression."""
        self._analytics.total_compressions += 1
        self._analytics.compression_events.append({
            "strategy": strategy,
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "ratio": round(compressed_tokens / original_tokens, 3) if original_tokens > 0 else 0,
            "timestamp": time.time(),
        })
        if len(self._analytics.compression_events) > self._max_history:
            self._analytics.compression_events = self._analytics.compression_events[-self._max_history:]

    def record_injection(self, *, tokens: int, items: int) -> None:
        """Record a context injection."""
        self._analytics.total_injections += 1

    def record_utilization(self, utilization: float) -> None:
        """Record current utilization."""
        self._analytics.utilization_history.append(round(utilization, 3))
        if len(self._analytics.utilization_history) > self._max_history:
            self._analytics.utilization_history = self._analytics.utilization_history[-self._max_history:]

        # Update average and peak
        history = self._analytics.utilization_history
        self._analytics.avg_utilization = sum(history) / len(history) if history else 0.0
        self._analytics.peak_utilization = max(history) if history else 0.0

    def get_summary(self) -> dict[str, Any]:
        """Get analytics summary."""
        return self._analytics.to_dict()

    def get_source_breakdown(self) -> dict[str, Any]:
        """Get breakdown by source."""
        total = self._analytics.total_additions
        if total == 0:
            return {}
        return {
            source: {
                "count": count,
                "percentage": round(count / total * 100, 1),
            }
            for source, count in self._analytics.source_distribution.items()
        }

    def get_health_score(self) -> float:
        """Calculate overall context health score (0-1)."""
        score = 1.0

        # Penalize high eviction rate
        if self._analytics.eviction_rate > 0.3:
            score -= 0.2
        if self._analytics.eviction_rate > 0.5:
            score -= 0.2

        # Penalize high compression rate
        if self._analytics.compression_rate > 0.2:
            score -= 0.1
        if self._analytics.compression_rate > 0.4:
            score -= 0.1

        # Penalize high peak utilization
        if self._analytics.peak_utilization > 0.95:
            score -= 0.1
        if self._analytics.peak_utilization > 0.99:
            score -= 0.1

        return max(0.0, score)
