"""Execution Analytics — real-time performance monitoring.

Tracks agent execution metrics, identifies bottlenecks, and provides
insights for optimization. Supports real-time dashboards and
historical trend analysis.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class MetricType(Enum):
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    TOKEN_USAGE = "token_usage"
    TOOL_USAGE = "tool_usage"
    SUCCESS_RATE = "success_rate"


@dataclass
class MetricPoint:
    """A single metric data point."""
    metric_type: MetricType
    value: float
    timestamp: float
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionRecord:
    """A single execution record."""
    execution_id: str
    task_type: str
    agent_name: str
    start_time: float
    end_time: float | None = None
    success: bool = False
    tokens_used: int = 0
    tool_calls: int = 0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float | None:
        if self.end_time:
            return self.end_time - self.start_time
        return None


@dataclass
class AnalyticsSummary:
    """Summary of execution analytics."""
    total_executions: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_latency: float = 0.0
    p50_latency: float = 0.0
    p95_latency: float = 0.0
    p99_latency: float = 0.0
    total_tokens: int = 0
    avg_tokens: float = 0.0
    total_tool_calls: int = 0
    avg_tool_calls: float = 0.0
    success_rate: float = 0.0
    error_rate: float = 0.0
    top_errors: list[tuple[str, int]] = field(default_factory=list)
    agent_breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)


class ExecutionAnalytics:
    """Real-time execution analytics and performance monitoring."""

    def __init__(self, *, max_history: int = 10000, window_size: int = 100) -> None:
        self._records: deque[ExecutionRecord] = deque(maxlen=max_history)
        self._metrics: dict[MetricType, deque[MetricPoint]] = {
            mt: deque(maxlen=window_size) for mt in MetricType
        }
        self._error_counts: dict[str, int] = defaultdict(int)
        self._agent_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "total": 0, "success": 0, "failure": 0, "total_tokens": 0, "total_tool_calls": 0,
        })
        self._start_time = time.time()
        self._lock = asyncio.Lock()

    async def record_execution(self, record: ExecutionRecord) -> None:
        """Record an execution."""
        async with self._lock:
            self._records.append(record)

            # Update agent stats
            stats = self._agent_stats[record.agent_name]
            stats["total"] += 1
            if record.success:
                stats["success"] += 1
            else:
                stats["failure"] += 1
            stats["total_tokens"] += record.tokens_used
            stats["total_tool_calls"] += record.tool_calls

            # Update error counts
            for error in record.errors:
                self._error_counts[error] += 1

            # Record metrics
            if record.duration:
                self._metrics[MetricType.LATENCY].append(MetricPoint(
                    metric_type=MetricType.LATENCY,
                    value=record.duration,
                    timestamp=record.end_time or time.time(),
                    labels={"agent": record.agent_name, "task_type": record.task_type},
                ))

            self._metrics[MetricType.TOKEN_USAGE].append(MetricPoint(
                metric_type=MetricType.TOKEN_USAGE,
                value=record.tokens_used,
                timestamp=record.end_time or time.time(),
                labels={"agent": record.agent_name},
            ))

            self._metrics[MetricType.TOOL_USAGE].append(MetricPoint(
                metric_type=MetricType.TOOL_USAGE,
                value=record.tool_calls,
                timestamp=record.end_time or time.time(),
                labels={"agent": record.agent_name},
            ))

    async def record_metric(
        self,
        metric_type: MetricType,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a custom metric."""
        async with self._lock:
            self._metrics[metric_type].append(MetricPoint(
                metric_type=metric_type,
                value=value,
                timestamp=time.time(),
                labels=labels or {},
            ))

    def get_summary(self, *, window_seconds: float | None = None) -> AnalyticsSummary:
        """Get analytics summary.

        Args:
            window_seconds: If set, only include records from this window.
        """
        records = list(self._records)
        if window_seconds:
            cutoff = time.time() - window_seconds
            records = [r for r in records if r.start_time >= cutoff]

        if not records:
            return AnalyticsSummary()

        durations = [r.duration for r in records if r.duration is not None]
        tokens = [r.tokens_used for r in records]
        tool_calls = [r.tool_calls for r in records]
        success_count = sum(1 for r in records if r.success)
        failure_count = len(records) - success_count

        # Calculate percentiles
        sorted_durations = sorted(durations) if durations else [0]
        p50 = sorted_durations[len(sorted_durations) // 2] if sorted_durations else 0
        p95 = sorted_durations[int(len(sorted_durations) * 0.95)] if sorted_durations else 0
        p99 = sorted_durations[int(len(sorted_durations) * 0.99)] if sorted_durations else 0

        # Top errors
        top_errors = sorted(self._error_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        # Agent breakdown
        agent_breakdown = {}
        for agent, stats in self._agent_stats.items():
            agent_records = [r for r in records if r.agent_name == agent]
            agent_durations = [r.duration for r in agent_records if r.duration is not None]
            agent_breakdown[agent] = {
                "total": stats["total"],
                "success": stats["success"],
                "failure": stats["failure"],
                "success_rate": stats["success"] / stats["total"] if stats["total"] > 0 else 0,
                "avg_latency": statistics.mean(agent_durations) if agent_durations else 0,
                "total_tokens": stats["total_tokens"],
                "total_tool_calls": stats["total_tool_calls"],
            }

        return AnalyticsSummary(
            total_executions=len(records),
            success_count=success_count,
            failure_count=failure_count,
            avg_latency=statistics.mean(durations) if durations else 0,
            p50_latency=p50,
            p95_latency=p95,
            p99_latency=p99,
            total_tokens=sum(tokens),
            avg_tokens=statistics.mean(tokens) if tokens else 0,
            total_tool_calls=sum(tool_calls),
            avg_tool_calls=statistics.mean(tool_calls) if tool_calls else 0,
            success_rate=success_count / len(records) if records else 0,
            error_rate=failure_count / len(records) if records else 0,
            top_errors=top_errors,
            agent_breakdown=agent_breakdown,
        )

    def get_metric_history(
        self,
        metric_type: MetricType,
        *,
        limit: int = 100,
    ) -> list[MetricPoint]:
        """Get history for a specific metric."""
        return list(self._metrics[metric_type])[-limit:]

    def get_bottlenecks(self, *, threshold_ms: float = 5000.0) -> list[dict[str, Any]]:
        """Identify performance bottlenecks."""
        bottlenecks = []
        for agent, stats in self._agent_stats.items():
            if stats["total"] == 0:
                continue
            agent_records = [r for r in self._records if r.agent_name == agent]
            slow_records = [r for r in agent_records if r.duration and r.duration * 1000 > threshold_ms]
            if slow_records:
                bottlenecks.append({
                    "agent": agent,
                    "slow_executions": len(slow_records),
                    "total_executions": stats["total"],
                    "slow_ratio": len(slow_records) / stats["total"],
                    "avg_slow_latency": statistics.mean([r.duration for r in slow_records if r.duration]) * 1000,
                })
        return bottlenecks

    def get_realtime_metrics(self) -> dict[str, Any]:
        """Get real-time metrics for dashboard."""
        now = time.time()
        recent = [r for r in self._records if r.start_time > now - 60]  # Last minute

        return {
            "uptime_seconds": now - self._start_time,
            "executions_last_minute": len(recent),
            "success_rate_last_minute": (
                sum(1 for r in recent if r.success) / len(recent) if recent else 0
            ),
            "avg_latency_last_minute": (
                statistics.mean([r.duration for r in recent if r.duration is not None])
                if any(r.duration is not None for r in recent) else 0
            ),
            "total_executions": len(self._records),
            "total_errors": sum(self._error_counts.values()),
            "active_agents": len(self._agent_stats),
        }

    def get_metrics(self) -> dict[str, Any]:
        return {
            "total_records": len(self._records),
            "uptime_seconds": time.time() - self._start_time,
            "error_types": len(self._error_counts),
            "agents_tracked": len(self._agent_stats),
        }
