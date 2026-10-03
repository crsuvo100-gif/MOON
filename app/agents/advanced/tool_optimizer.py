"""tool_optimizer.py — agent tool usage optimization.

Professional AI assistants optimize which tools they use and how they
use them. This module tracks tool usage patterns, identifies redundancies,
suggests tool combinations, and learns optimal tool sequences.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolUsage:
    tool_name: str
    agent_id: str
    task_id: str
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    duration: float = 0.0
    input_size: int = 0
    output_size: int = 0
    error: str = ""


@dataclass
class ToolSequence:
    sequence_id: str
    tool_names: list[str]
    task_pattern: str
    success_count: int = 0
    failure_count: int = 0
    avg_duration: float = 0.0
    last_used: float = 0.0

    @property
    def total_uses(self) -> int:
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        return self.success_count / max(1, self.total_uses)


class ToolOptimizer:
    """Tracks and optimizes agent tool usage.

    Records every tool invocation, identifies patterns in tool sequences,
    suggests optimal tool combinations, and learns which tools work
    best for which task types.
    """

    def __init__(self, *, max_history: int = 5000) -> None:
        self._max_history = max_history
        self._usage: list[ToolUsage] = []
        self._sequences: dict[str, ToolSequence] = {}
        self._tool_stats: dict[str, dict[str, Any]] = {}
        self._agent_tool_stats: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def record_usage(
        self,
        tool_name: str,
        agent_id: str,
        task_id: str,
        *,
        success: bool = True,
        duration: float = 0.0,
        input_size: int = 0,
        output_size: int = 0,
        error: str = "",
    ) -> None:
        usage = ToolUsage(
            tool_name=tool_name,
            agent_id=agent_id,
            task_id=task_id,
            success=success,
            duration=duration,
            input_size=input_size,
            output_size=output_size,
            error=error,
        )
        async with self._lock:
            self._usage.append(usage)
            if len(self._usage) > self._max_history:
                self._usage = self._usage[-self._max_history:]

            # Update tool stats
            if tool_name not in self._tool_stats:
                self._tool_stats[tool_name] = {
                    "total_uses": 0, "successes": 0, "failures": 0,
                    "total_duration": 0.0, "total_input": 0, "total_output": 0,
                }
            stats = self._tool_stats[tool_name]
            stats["total_uses"] += 1
            if success:
                stats["successes"] += 1
            else:
                stats["failures"] += 1
            stats["total_duration"] += duration
            stats["total_input"] += input_size
            stats["total_output"] += output_size

            # Update agent-tool stats
            if agent_id not in self._agent_tool_stats:
                self._agent_tool_stats[agent_id] = {}
            if tool_name not in self._agent_tool_stats[agent_id]:
                self._agent_tool_stats[agent_id][tool_name] = {
                    "total_uses": 0, "successes": 0, "failures": 0,
                }
            at_stats = self._agent_tool_stats[agent_id][tool_name]
            at_stats["total_uses"] += 1
            if success:
                at_stats["successes"] += 1
            else:
                at_stats["failures"] += 1

    async def get_tool_stats(self, tool_name: str) -> dict[str, Any] | None:
        async with self._lock:
            stats = self._tool_stats.get(tool_name)
            if not stats:
                return None
            total = stats["total_uses"]
            return {
                "tool_name": tool_name,
                "total_uses": total,
                "success_rate": round(stats["successes"] / max(1, total), 3),
                "avg_duration": round(stats["total_duration"] / max(1, total), 3),
                "avg_input_size": round(stats["total_input"] / max(1, total), 1),
                "avg_output_size": round(stats["total_output"] / max(1, total), 1),
            }

    async def get_agent_tool_stats(self, agent_id: str) -> dict[str, Any]:
        async with self._lock:
            return dict(self._agent_tool_stats.get(agent_id, {}))

    async def get_most_used_tools(self, *, limit: int = 10) -> list[dict[str, Any]]:
        async with self._lock:
            sorted_tools = sorted(
                self._tool_stats.items(),
                key=lambda x: x[1]["total_uses"],
                reverse=True,
            )
            result = []
            for name, stats in sorted_tools[:limit]:
                total = stats["total_uses"]
                result.append({
                    "tool_name": name,
                    "total_uses": total,
                    "success_rate": round(stats["successes"] / max(1, total), 3),
                    "avg_duration": round(stats["total_duration"] / max(1, total), 3),
                })
            return result

    async def get_least_used_tools(self, *, limit: int = 10) -> list[dict[str, Any]]:
        async with self._lock:
            sorted_tools = sorted(
                self._tool_stats.items(),
                key=lambda x: x[1]["total_uses"],
            )
            result = []
            for name, stats in sorted_tools[:limit]:
                total = stats["total_uses"]
                result.append({
                    "tool_name": name,
                    "total_uses": total,
                    "success_rate": round(stats["successes"] / max(1, total), 3),
                })
            return result

    async def get_failing_tools(self, *, threshold: float = 0.5) -> list[dict[str, Any]]:
        """Get tools with success rate below threshold."""
        async with self._lock:
            failing = []
            for name, stats in self._tool_stats.items():
                total = stats["total_uses"]
                if total < 3:
                    continue
                success_rate = stats["successes"] / total
                if success_rate < threshold:
                    failing.append({
                        "tool_name": name,
                        "success_rate": round(success_rate, 3),
                        "total_uses": total,
                        "failures": stats["failures"],
                    })
            return sorted(failing, key=lambda x: x["success_rate"])

    async def suggest_optimizations(self) -> list[str]:
        """Suggest tool usage optimizations."""
        suggestions = []
        async with self._lock:
            # Check for failing tools
            failing = await self.get_failing_tools(threshold=0.5)
            for tool in failing:
                suggestions.append(
                    f"Tool '{tool['tool_name']}' has low success rate "
                    f"({tool['success_rate']:.0%}). Consider reviewing its implementation."
                )

            # Check for slow tools
            for name, stats in self._tool_stats.items():
                total = stats["total_uses"]
                if total < 3:
                    continue
                avg_duration = stats["total_duration"] / total
                if avg_duration > 10:
                    suggestions.append(
                        f"Tool '{name}' is slow (avg {avg_duration:.1f}s). "
                        f"Consider optimizing or caching."
                    )

            # Check for unused tools
            all_tools = set(self._tool_stats.keys())
            used_tools = set()
            for agent_tools in self._agent_tool_stats.values():
                used_tools.update(agent_tools.keys())
            unused = all_tools - used_tools
            if unused:
                suggestions.append(
                    f"Unused tools: {', '.join(sorted(unused))}. "
                    f"Consider removing or promoting them."
                )

        return suggestions

    async def learn_sequence(
        self,
        tool_names: list[str],
        task_pattern: str,
        success: bool,
        duration: float,
    ) -> None:
        """Learn a tool sequence pattern."""
        import uuid
        seq_key = "->".join(tool_names)
        async with self._lock:
            if seq_key in self._sequences:
                seq = self._sequences[seq_key]
                if success:
                    seq.success_count += 1
                else:
                    seq.failure_count += 1
                seq.avg_duration = (seq.avg_duration + duration) / 2
                seq.last_used = time.time()
            else:
                self._sequences[seq_key] = ToolSequence(
                    sequence_id=uuid.uuid4().hex[:12],
                    tool_names=list(tool_names),
                    task_pattern=task_pattern,
                    success_count=1 if success else 0,
                    failure_count=0 if success else 1,
                    avg_duration=duration,
                    last_used=time.time(),
                )

    async def get_sequences(
        self,
        *,
        min_uses: int = 2,
        limit: int = 20,
    ) -> list[ToolSequence]:
        async with self._lock:
            sequences = [
                s for s in self._sequences.values()
                if s.total_uses >= min_uses
            ]
            sequences.sort(key=lambda s: s.success_rate, reverse=True)
            return sequences[:limit]

    def stats(self) -> dict[str, Any]:
        total_uses = len(self._usage)
        successful = sum(1 for u in self._usage if u.success)
        return {
            "total_tool_uses": total_uses,
            "successful_uses": successful,
            "failed_uses": total_uses - successful,
            "success_rate": round(successful / max(1, total_uses), 3),
            "unique_tools": len(self._tool_stats),
            "unique_agents": len(self._agent_tool_stats),
            "learned_sequences": len(self._sequences),
        }
