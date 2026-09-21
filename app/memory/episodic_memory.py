"""episodic_memory.py -- Episodic Memory (past task trajectories)."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Episode:
    goal: str
    outcome: str
    lesson: str = ""
    ts: float = field(default_factory=time.time)
    success: bool = True


class EpisodicMemory:
    """Stores and retrieves task episodes with ranking + expiration."""

    def __init__(self, max_episodes: int = 1000, ttl: float = 60 * 60 * 24 * 30) -> None:
        self._max = max_episodes
        self._ttl = ttl
        self._eps: list[Episode] = []

    def record(self, goal: str, outcome: str, lesson: str = "", success: bool = True) -> None:
        self._eps.append(Episode(goal, outcome, lesson, time.time(), success))
        if len(self._eps) > self._max:
            self._eps = self._eps[-self._max:]

    def recall(self, query: str, k: int = 5) -> list[Episode]:
        scored = [(self._score(query, e), e) for e in self._pruned()]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:k]]

    def _pruned(self) -> list[Episode]:
        now = time.time()
        return [e for e in self._eps if now - e.ts <= self._ttl]

    @staticmethod
    def _score(query: str, e: Episode) -> float:
        q = (query or "").lower()
        text = (e.goal + " " + e.outcome + " " + e.lesson).lower()
        recency = 1.0 / (1.0 + (time.time() - e.ts) / 86400.0)
        overlap = sum(1 for w in q.split() if w and w in text)
        return 0.3 * recency + 0.7 * math.tanh(overlap / 3.0)

    def expire(self) -> int:
        before = len(self._eps)
        self._eps = self._pruned()
        return before - len(self._eps)
