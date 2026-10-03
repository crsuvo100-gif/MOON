"""performance.py — agent performance tracking and scoring.

Professional AI assistants track agent performance across multiple
dimensions: success rate, latency, token efficiency, tool usage, and
output quality. This module provides a performance tracker that
aggregates metrics, computes trends, and identifies bottlenecks.
"""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TaskExecution:
    task_id: str
    agent_id: str
    start_time: float
    end_time: float = 0.0
    success: bool = False
    tokens_used: int = 0
    tool_calls: int = 0
    error: str = ""
    quality_score: float = 0.0  # 0-1, from validation/reflection

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time if self.end_time else 0.0


@dataclass
class AgentMetrics:
    agent_id: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    total_tokens: int = 0
    total_tool_calls: int = 0
    total_duration: float = 0.0
    avg_quality: float = 0.0
    avg_latency: float = 0.0
    success_rate: float = 0.0
    token_efficiency: float = 0.0  # tokens per task
    tool_efficiency: float = 0.0  # tool calls per task
    p50_latency: float = 0.0
    p95_latency: float = 0.0
    trend: str = "stable"  # improving, degrading, stable


class PerformanceTracker:
    """Tracks and analyzes agent performance across tasks.

    Records every task execution, computes aggregate metrics per agent,
    identifies performance trends, and provides actionable insights.
    """

    def __init__(self, *, max_history: int = 1000) -> None:
        self._max_history = max_history
        self._executions: list[TaskExecution] = []
        self._agent_executions: dict[str, list[TaskExecution]] = {}

    def record(self, execution: TaskExecution) -> None:
        self._executions.append(execution)
        if len(self._executions) > self._max_history:
            self._executions = self._executions[-self._max_history:]

        agent = execution.agent_id
        if agent not in self._agent_executions:
            self._agent_executions[agent] = []
        self._agent_executions[agent].append(execution)
        if len(self._agent_executions[agent]) > self._max_history:
            self._agent_executions[agent] = self._agent_executions[agent][-self._max_history:]

    def get_agent_metrics(self, agent_id: str) -> AgentMetrics:
        executions = self._agent_executions.get(agent_id, [])
        if not executions:
            return AgentMetrics(agent_id=agent_id)

        total = len(executions)
        successful = sum(1 for e in executions if e.success)
        failed = total - successful
        total_tokens = sum(e.tokens_used for e in executions)
        total_tools = sum(e.tool_calls for e in executions)
        total_duration = sum(e.duration for e in executions)
        qualities = [e.quality_score for e in executions if e.quality_score > 0]
        durations = [e.duration for e in executions if e.duration > 0]

        avg_quality = statistics.mean(qualities) if qualities else 0.0
        avg_latency = statistics.mean(durations) if durations else 0.0
        p50 = statistics.median(durations) if durations else 0.0
        p95 = sorted(durations)[int(len(durations) * 0.95)] if len(durations) > 1 else p50

        # Trend: compare recent 20% vs older 20%
        trend = "stable"
        if len(executions) >= 10:
            recent = executions[-max(1, len(executions) // 5):]
            older = executions[:max(1, len(executions) // 5)]
            recent_success = sum(1 for e in recent if e.success) / len(recent)
            older_success = sum(1 for e in older if e.success) / len(older)
            if recent_success > older_success + 0.1:
                trend = "improving"
            elif recent_success < older_success - 0.1:
                trend = "degrading"

        return AgentMetrics(
            agent_id=agent_id,
            total_tasks=total,
            successful_tasks=successful,
            failed_tasks=failed,
            total_tokens=total_tokens,
            total_tool_calls=total_tools,
            total_duration=total_duration,
            avg_quality=round(avg_quality, 3),
            avg_latency=round(avg_latency, 3),
            success_rate=round(successful / total, 3),
            token_efficiency=round(total_tokens / max(1, total), 1),
            tool_efficiency=round(total_tools / max(1, total), 2),
            p50_latency=round(p50, 3),
            p95_latency=round(p95, 3),
            trend=trend,
        )

    def get_all_metrics(self) -> dict[str, AgentMetrics]:
        return {
            agent_id: self.get_agent_metrics(agent_id)
            for agent_id in self._agent_executions
        }

    def get_summary(self) -> dict[str, Any]:
        all_metrics = self.get_all_metrics()
        if not all_metrics:
            return {"total_agents": 0, "total_tasks": 0}

        total_tasks = sum(m.total_tasks for m in all_metrics.values())
        total_success = sum(m.successful_tasks for m in all_metrics.values())
        total_tokens = sum(m.total_tokens for m in all_metrics.values())
        total_tools = sum(m.total_tool_calls for m in all_metrics.values())
        all_durations = [
            e.duration for e in self._executions if e.duration > 0
        ]

        return {
            "total_agents": len(all_metrics),
            "total_tasks": total_tasks,
            "overall_success_rate": round(total_success / max(1, total_tasks), 3),
            "total_tokens": total_tokens,
            "total_tool_calls": total_tools,
            "avg_latency": round(statistics.mean(all_durations), 3) if all_durations else 0,
            "p95_latency": round(
                sorted(all_durations)[int(len(all_durations) * 0.95)], 3
            ) if len(all_durations) > 1 else 0,
            "agents": {
                aid: {
                    "success_rate": m.success_rate,
                    "avg_latency": m.avg_latency,
                    "avg_quality": m.avg_quality,
                    "trend": m.trend,
                    "total_tasks": m.total_tasks,
                }
                for aid, m in all_metrics.items()
            },
        }

    def get_bottlenecks(self, *, threshold_ms: float = 5000) -> list[dict[str, Any]]:
        """Identify agents with latency above threshold."""
        bottlenecks = []
        for agent_id, metrics in self.get_all_metrics().items():
            if metrics.p95_latency * 1000 > threshold_ms:
                bottlenecks.append({
                    "agent_id": agent_id,
                    "p95_latency_ms": round(metrics.p95_latency * 1000, 1),
                    "avg_latency_ms": round(metrics.avg_latency * 1000, 1),
                    "success_rate": metrics.success_rate,
                    "trend": metrics.trend,
                })
        return sorted(bottlenecks, key=lambda x: x["p95_latency_ms"], reverse=True)

    def get_recommendations(self) -> list[str]:
        """Generate actionable recommendations based on performance data."""
        recs = []
        for agent_id, metrics in self.get_all_metrics().items():
            if metrics.success_rate < 0.5 and metrics.total_tasks > 5:
                recs.append(
                    f"Agent '{agent_id}' has low success rate ({metrics.success_rate:.0%}). "
                    f"Consider reviewing its tool scope or prompt."
                )
            if metrics.trend == "degrading" and metrics.total_tasks > 10:
                recs.append(
                    f"Agent '{agent_id}' performance is degrading. "
                    f"Consider retraining or adjusting its configuration."
                )
            if metrics.p95_latency > 30 and metrics.total_tasks > 5:
                recs.append(
                    f"Agent '{agent_id}' has high p95 latency ({metrics.p95_latency:.1f}s). "
                    f"Consider optimizing its tool calls or using a faster model."
                )
            if metrics.token_efficiency > 5000 and metrics.total_tasks > 5:
                recs.append(
                    f"Agent '{agent_id}' uses many tokens per task ({metrics.token_efficiency:.0f}). "
                    f"Consider tightening its system prompt or reducing context."
                )
        return recs
