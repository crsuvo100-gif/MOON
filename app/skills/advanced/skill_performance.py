"""Skill performance tracking and analytics.

Tracks how often skills are used, success rates, execution times,
and provides analytics for skill optimization.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillUsageRecord:
    """Record of a single skill usage."""
    skill_name: str
    task: str
    success: bool
    execution_time: float
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillStats:
    """Aggregated statistics for a skill."""
    skill_name: str
    total_uses: int = 0
    successful_uses: int = 0
    failed_uses: int = 0
    total_execution_time: float = 0.0
    avg_execution_time: float = 0.0
    success_rate: float = 0.0
    last_used: float = 0.0
    avg_score: float = 0.0


class SkillPerformance:
    """Tracks and analyzes skill performance.

    Maintains usage records and computes aggregated statistics
    for each skill, enabling data-driven skill optimization.
    """

    def __init__(self, max_records: int = 1000):
        self._records: list[SkillUsageRecord] = []
        self._max_records = max_records
        self._stats: dict[str, SkillStats] = {}

    def record(self, record: SkillUsageRecord) -> None:
        """Record a skill usage."""
        if record.timestamp == 0.0:
            record.timestamp = time.time()
        self._records.append(record)
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]
        self._update_stats(record)

    def _update_stats(self, record: SkillUsageRecord) -> None:
        """Update aggregated stats for a skill."""
        name = record.skill_name
        if name not in self._stats:
            self._stats[name] = SkillStats(skill_name=name)
        stats = self._stats[name]
        stats.total_uses += 1
        if record.success:
            stats.successful_uses += 1
        else:
            stats.failed_uses += 1
        stats.total_execution_time += record.execution_time
        stats.avg_execution_time = stats.total_execution_time / stats.total_uses
        stats.success_rate = stats.successful_uses / stats.total_uses
        stats.last_used = record.timestamp

    def get_stats(self, skill_name: str) -> SkillStats | None:
        """Get stats for a specific skill."""
        return self._stats.get(skill_name)

    def get_all_stats(self) -> dict[str, SkillStats]:
        """Get all skill stats."""
        return dict(self._stats)

    def get_top_skills(self, n: int = 5) -> list[SkillStats]:
        """Get top N skills by usage count."""
        sorted_stats = sorted(self._stats.values(), key=lambda s: s.total_uses, reverse=True)
        return sorted_stats[:n]

    def get_most_reliable(self, n: int = 5) -> list[SkillStats]:
        """Get top N skills by success rate (min 3 uses)."""
        eligible = [s for s in self._stats.values() if s.total_uses >= 3]
        sorted_stats = sorted(eligible, key=lambda s: s.success_rate, reverse=True)
        return sorted_stats[:n]

    def get_slowest(self, n: int = 5) -> list[SkillStats]:
        """Get top N slowest skills by avg execution time."""
        sorted_stats = sorted(self._stats.values(), key=lambda s: s.avg_execution_time, reverse=True)
        return sorted_stats[:n]

    def get_recent_records(self, n: int = 10) -> list[SkillUsageRecord]:
        """Get the most recent N usage records."""
        return self._records[-n:]

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all skill performance."""
        total_uses = sum(s.total_uses for s in self._stats.values())
        total_success = sum(s.successful_uses for s in self._stats.values())
        avg_time = (
            sum(s.avg_execution_time for s in self._stats.values()) / len(self._stats)
            if self._stats else 0.0
        )
        return {
            "total_skills": len(self._stats),
            "total_uses": total_uses,
            "overall_success_rate": total_success / total_uses if total_uses > 0 else 0.0,
            "avg_execution_time": round(avg_time, 3),
            "top_skills": [
                {"name": s.skill_name, "uses": s.total_uses, "success_rate": round(s.success_rate, 3)}
                for s in self.get_top_skills(5)
            ],
            "most_reliable": [
                {"name": s.skill_name, "success_rate": round(s.success_rate, 3)}
                for s in self.get_most_reliable(5)
            ],
        }
