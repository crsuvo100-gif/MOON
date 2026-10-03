"""learning.py — agent self-learning from outcomes.

Professional AI assistants learn from their successes and failures.
This module provides a learning system that extracts patterns from
task outcomes, builds a knowledge base of what works, and adjusts
agent behavior based on accumulated experience.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LearningRecord:
    record_id: str
    agent_id: str
    task_prompt: str
    outcome: str
    success: bool
    lesson: str
    timestamp: float = field(default_factory=time.time)
    category: str = ""  # "success", "failure", "improvement", "pattern"
    confidence: float = 0.5
    applied: bool = False


@dataclass
class LearnedPattern:
    pattern_id: str
    description: str
    condition: str  # when this pattern applies
    action: str  # what to do
    confidence: float = 0.5
    success_count: int = 0
    failure_count: int = 0
    last_used: float = 0.0

    @property
    def total_uses(self) -> int:
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        return self.success_count / max(1, self.total_uses)


class AgentLearning:
    """Self-learning system that extracts lessons from task outcomes.

    Records every task outcome, extracts patterns, and builds a
    knowledge base of what works. Patterns are reinforced on success
    and weakened on failure. The system can suggest behavioral
    adjustments based on accumulated experience.
    """

    def __init__(self, *, max_records: int = 5000) -> None:
        self._max_records = max_records
        self._records: list[LearningRecord] = []
        self._patterns: dict[str, LearnedPattern] = {}
        self._agent_records: dict[str, list[LearningRecord]] = {}
        self._lock = asyncio.Lock()

    async def record_outcome(
        self,
        agent_id: str,
        task_prompt: str,
        outcome: str,
        success: bool,
        lesson: str = "",
        *,
        category: str = "",
        confidence: float = 0.5,
    ) -> LearningRecord:
        import uuid
        record = LearningRecord(
            record_id=uuid.uuid4().hex[:12],
            agent_id=agent_id,
            task_prompt=task_prompt[:500],
            outcome=outcome[:1000],
            success=success,
            lesson=lesson,
            category=category or ("success" if success else "failure"),
            confidence=confidence,
        )
        async with self._lock:
            self._records.append(record)
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]

            if agent_id not in self._agent_records:
                self._agent_records[agent_id] = []
            self._agent_records[agent_id].append(record)
            if len(self._agent_records[agent_id]) > self._max_records:
                self._agent_records[agent_id] = self._agent_records[agent_id][-self._max_records:]

        # Extract patterns from this outcome
        await self._extract_patterns(record)
        return record

    async def _extract_patterns(self, record: LearningRecord) -> None:
        """Extract reusable patterns from a learning record."""
        if not record.lesson:
            return

        # Simple pattern extraction: group by lesson keywords
        words = set(record.lesson.lower().split())
        for other in self._records[-50:]:
            if other.record_id == record.record_id:
                continue
            other_words = set(other.lesson.lower().split())
            overlap = words & other_words
            if len(overlap) >= 3:
                # Found a pattern
                pattern_key = "_".join(sorted(overlap)[:3])
                if pattern_key in self._patterns:
                    pattern = self._patterns[pattern_key]
                    if record.success:
                        pattern.success_count += 1
                    else:
                        pattern.failure_count += 1
                    pattern.last_used = time.time()
                else:
                    self._patterns[pattern_key] = LearnedPattern(
                        pattern_id=pattern_key,
                        description=f"Pattern from: {record.lesson[:100]}",
                        condition=record.task_prompt[:200],
                        action=record.lesson[:200],
                        confidence=record.confidence,
                        success_count=1 if record.success else 0,
                        failure_count=0 if record.success else 1,
                        last_used=time.time(),
                    )

    async def get_lessons(
        self,
        agent_id: str | None = None,
        *,
        success_only: bool = False,
        limit: int = 20,
    ) -> list[LearningRecord]:
        async with self._lock:
            records = self._agent_records.get(agent_id, []) if agent_id else self._records
            if success_only:
                records = [r for r in records if r.success]
            return records[-limit:]

    async def get_patterns(
        self,
        *,
        min_confidence: float = 0.3,
        limit: int = 20,
    ) -> list[LearnedPattern]:
        async with self._lock:
            patterns = [
                p for p in self._patterns.values()
                if p.confidence >= min_confidence
            ]
            patterns.sort(key=lambda p: p.success_rate, reverse=True)
            return patterns[:limit]

    async def get_agent_summary(self, agent_id: str) -> dict[str, Any]:
        async with self._lock:
            records = self._agent_records.get(agent_id, [])
            if not records:
                return {"agent_id": agent_id, "total_records": 0}

            successes = [r for r in records if r.success]
            failures = [r for r in records if not r.success]
            lessons = [r.lesson for r in records if r.lesson]

            return {
                "agent_id": agent_id,
                "total_records": len(records),
                "successes": len(successes),
                "failures": len(failures),
                "success_rate": round(len(successes) / len(records), 3),
                "recent_lessons": lessons[-10:],
                "categories": list(set(r.category for r in records)),
            }

    async def suggest_improvements(self, agent_id: str) -> list[str]:
        """Suggest behavioral improvements based on learning history."""
        async with self._lock:
            records = self._agent_records.get(agent_id, [])
            if len(records) < 5:
                return []

            suggestions = []
            failures = [r for r in records if not r.success]
            successes = [r for r in records if r.success]

            if len(failures) > len(successes):
                suggestions.append(
                    f"Agent '{agent_id}' has more failures than successes. "
                    f"Consider reviewing its tool scope or prompt."
                )

            # Check for repeated failure patterns
            failure_lessons = [r.lesson for r in failures if r.lesson]
            if failure_lessons:
                from collections import Counter
                common = Counter(failure_lessons).most_common(3)
                for lesson, count in common:
                    if count >= 2:
                        suggestions.append(
                            f"Recurring failure ({count}x): {lesson[:100]}"
                        )

            # Check for success patterns to reinforce
            success_lessons = [r.lesson for r in successes if r.lesson]
            if success_lessons:
                from collections import Counter
                common_success = Counter(success_lessons).most_common(2)
                for lesson, count in common_success:
                    if count >= 3:
                        suggestions.append(
                            f"Reinforce successful pattern ({count}x): {lesson[:100]}"
                        )

            return suggestions

    async def apply_pattern(self, pattern_id: str) -> bool:
        """Mark a pattern as applied (used to adjust behavior)."""
        async with self._lock:
            if pattern_id in self._patterns:
                self._patterns[pattern_id].last_used = time.time()
                return True
            return False

    def stats(self) -> dict[str, Any]:
        total = len(self._records)
        successes = sum(1 for r in self._records if r.success)
        return {
            "total_records": total,
            "successes": successes,
            "failures": total - successes,
            "success_rate": round(successes / max(1, total), 3),
            "total_patterns": len(self._patterns),
            "agents_tracked": len(self._agent_records),
        }
