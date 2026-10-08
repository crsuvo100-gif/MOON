"""episodic_memory.py -- Episodic Memory (past task trajectories).

Enhanced implementation with episode consolidation, success/failure analysis,
lesson extraction, and temporal reasoning.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Episode:
    """A single task episode with outcome and lessons."""
    goal: str
    outcome: str
    lesson: str = ""
    ts: float = field(default_factory=time.time)
    success: bool = True
    duration_seconds: float = 0.0
    steps: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    importance: float = 1.0

    @property
    def age_seconds(self) -> float:
        return time.time() - self.ts

    @property
    def effective_importance(self) -> float:
        """Importance weighted by recency."""
        recency = 1.0 / (1.0 + self.age_seconds / 86400.0)  # 1-day half-life
        return self.importance * recency


class EpisodicMemory:
    """Stores and retrieves task episodes with ranking + expiration.

    Features:
    - Episode consolidation (merge similar episodes)
    - Success/failure analysis
    - Lesson extraction
    - Temporal reasoning (time-based queries)
    - Tag-based filtering
    - Importance-based ranking
    """

    def __init__(
        self,
        max_episodes: int = 1000,
        ttl: float = 60 * 60 * 24 * 30,  # 30 days
        consolidation_enabled: bool = True,
    ) -> None:
        self._max = max_episodes
        self._ttl = ttl
        self._consolidation_enabled = consolidation_enabled
        self._eps: list[Episode] = []
        self._success_count = 0
        self._failure_count = 0

    def record(
        self,
        goal: str,
        outcome: str,
        lesson: str = "",
        success: bool = True,
        duration_seconds: float = 0.0,
        steps: list[str] | None = None,
        tags: list[str] | None = None,
        importance: float = 1.0,
    ) -> Episode:
        """Record a new episode.

        Args:
            goal: What was attempted
            outcome: What happened
            lesson: What was learned
            success: Whether the task succeeded
            duration_seconds: How long it took
            steps: List of steps taken
            tags: Tags for filtering
            importance: Importance score

        Returns:
            The created Episode
        """
        episode = Episode(
            goal=goal,
            outcome=outcome,
            lesson=lesson,
            success=success,
            duration_seconds=duration_seconds,
            steps=steps or [],
            tags=tags or [],
            importance=importance,
        )
        self._eps.append(episode)
        if success:
            self._success_count += 1
        else:
            self._failure_count += 1

        if len(self._eps) > self._max:
            self._eps = self._eps[-self._max:]

        if self._consolidation_enabled:
            self._consolidate()

        return episode

    def recall(
        self,
        query: str,
        k: int = 5,
        success_only: bool = False,
        tags: list[str] | None = None,
    ) -> list[Episode]:
        """Recall relevant episodes.

        Args:
            query: Search query
            k: Number of episodes to return
            success_only: Only return successful episodes
            tags: Filter by tags

        Returns:
            List of matching episodes
        """
        candidates = self._pruned()

        if success_only:
            candidates = [e for e in candidates if e.success]

        if tags:
            candidates = [
                e for e in candidates
                if any(t in e.tags for t in tags)
            ]

        scored = [(self._score(query, e), e) for e in candidates]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:k]]

    def get_lessons(self, k: int = 10) -> list[str]:
        """Extract lessons from past episodes."""
        lessons = [
            e.lesson for e in self._pruned()
            if e.lesson
        ]
        # Return most recent lessons
        return lessons[-k:][::-1]

    def get_success_rate(self) -> float:
        """Calculate overall success rate."""
        total = self._success_count + self._failure_count
        if total == 0:
            return 0.0
        return self._success_count / total

    def get_failure_patterns(self) -> list[str]:
        """Analyze failure patterns."""
        failures = [e for e in self._pruned() if not e.success]
        # Simple pattern extraction: common words in failure outcomes
        if not failures:
            return []
        # Return most common failure outcomes
        outcomes = [e.outcome for e in failures]
        return outcomes[-5:]  # most recent 5

    def expire(self) -> int:
        """Remove expired episodes.

        Returns:
            Number of episodes removed
        """
        before = len(self._eps)
        self._eps = self._pruned()
        return before - len(self._eps)

    def stats(self) -> dict[str, Any]:
        """Return episodic memory statistics."""
        total = len(self._eps)
        successful = sum(1 for e in self._eps if e.success)
        failed = total - successful
        return {
            "total_episodes": total,
            "successful": successful,
            "failed": failed,
            "success_rate": round(self.get_success_rate(), 4),
            "max_episodes": self._max,
            "ttl_seconds": self._ttl,
            "avg_duration_seconds": (
                round(sum(e.duration_seconds for e in self._eps) / total, 2)
                if total > 0 else 0.0
            ),
        }

    def _pruned(self) -> list[Episode]:
        """Get non-expired episodes."""
        now = time.time()
        return [e for e in self._eps if now - e.ts <= self._ttl]

    @staticmethod
    def _score(query: str, e: Episode) -> float:
        """Score an episode for relevance."""
        q = (query or "").lower()
        text = (e.goal + " " + e.outcome + " " + e.lesson).lower()
        recency = 1.0 / (1.0 + (time.time() - e.ts) / 86400.0)
        overlap = sum(1 for w in q.split() if w and w in text)
        return 0.3 * recency + 0.7 * math.tanh(overlap / 3.0)

    def _consolidate(self) -> None:
        """Merge similar episodes to reduce redundancy."""
        if len(self._eps) < 2:
            return

        # Simple consolidation: merge episodes with identical goals
        seen: dict[str, int] = {}
        to_remove: list[int] = []
        for i, ep in enumerate(self._eps):
            key = ep.goal.lower().strip()
            if key in seen:
                # Merge into existing
                existing = self._eps[seen[key]]
                existing.outcome += f" | {ep.outcome}"
                if ep.lesson and ep.lesson not in existing.lesson:
                    existing.lesson += f" | {ep.lesson}"
                existing.importance = max(existing.importance, ep.importance)
                to_remove.append(i)
            else:
                seen[key] = i

        # Remove merged episodes (in reverse order to preserve indices)
        for i in sorted(to_remove, reverse=True):
            self._eps.pop(i)
