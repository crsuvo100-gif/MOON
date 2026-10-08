"""Memory importance scorer -- multi-signal importance scoring.

Professional AI assistants don't treat all memories equally. This module
scores memories by importance using multiple signals:

1. Source importance: USER > AGENT > SYSTEM > EXTRACTED
2. Access frequency: Frequently accessed memories are more important
3. Recency: Recent memories are more relevant
4. Confidence: High-confidence memories are more reliable
5. Scope: CRITICAL > HIGH > MEDIUM > LOW > TEMPORARY
6. Tag importance: Certain tags (security, user-preference) boost importance
7. Semantic centrality: Memories connected to many others are more important

The scorer produces a 0.0-1.0 importance score for any memory.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger
from app.memory.record import Importance, Scope, SourceType

logger = get_logger(__name__)


# Source type weights
_SOURCE_W = {
    SourceType.USER: 1.0,
    SourceType.AGENT: 0.7,
    SourceType.SYSTEM: 0.5,
    SourceType.INFERENCE: 0.3,
}

# Scope weights
_SCOPE_W = {
    Scope.USER: 1.0,
    Scope.PROJECT: 0.8,
    Scope.GLOBAL: 0.7,
    Scope.SYSTEM: 0.6,
    Scope.TEAM: 0.5,
    Scope.AGENT: 0.4,
    Scope.TASK: 0.3,
    Scope.SESSION: 0.2,
}

# High-importance tags
_IMPORTANT_TAGS = {
    "security", "user-preference", "critical", "config", "credential",
    "api-key", "password", "secret", "auth", "permission",
    "user-name", "user-email", "user-phone", "user-address",
}


@dataclass
class ImportanceScore:
    """A detailed importance score for a memory."""
    memory_id: str
    overall: float
    source_score: float = 0.0
    access_score: float = 0.0
    recency_score: float = 0.0
    confidence_score: float = 0.0
    scope_score: float = 0.0
    tag_score: float = 0.0
    centrality_score: float = 0.0
    age_seconds: float = 0.0
    access_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "overall": round(self.overall, 4),
            "source_score": round(self.source_score, 4),
            "access_score": round(self.access_score, 4),
            "recency_score": round(self.recency_score, 4),
            "confidence_score": round(self.confidence_score, 4),
            "scope_score": round(self.scope_score, 4),
            "tag_score": round(self.tag_score, 4),
            "centrality_score": round(self.centrality_score, 4),
            "age_seconds": round(self.age_seconds, 1),
            "access_count": self.access_count,
        }


class ImportanceScorer:
    """Scores memories by importance using multiple signals.

    Usage:
        scorer = ImportanceScorer(memory_manager)
        score = scorer.score_memory(memory_id)
        ranked = scorer.rank_memories(query="API", top_k=10)
    """

    # Weights for each signal (sum to 1.0)
    DEFAULT_WEIGHTS = {
        "source": 0.20,
        "access": 0.15,
        "recency": 0.15,
        "confidence": 0.15,
        "scope": 0.15,
        "tag": 0.10,
        "centrality": 0.10,
    }

    def __init__(
        self,
        memory_manager=None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self._mm = memory_manager
        self._w = weights or self.DEFAULT_WEIGHTS
        self._score_count = 0

    def score_memory(self, memory_id: str) -> ImportanceScore | None:
        """Score a single memory by importance."""
        if self._mm is None:
            return None

        try:
            rec = self._mm._store.get(memory_id)
            if rec is None:
                return None
        except Exception as exc:
            logger.debug("Failed to get memory %s: %s", memory_id, exc)
            return None

        self._score_count += 1

        # Calculate individual scores
        source_score = self._source_score(rec)
        access_score = self._access_score(rec)
        recency_score = self._recency_score(rec)
        confidence_score = self._confidence_score(rec)
        scope_score = self._scope_score(rec)
        tag_score = self._tag_score(rec)
        centrality_score = self._centrality_score(rec)

        # Weighted combination
        overall = (
            self._w["source"] * source_score
            + self._w["access"] * access_score
            + self._w["recency"] * recency_score
            + self._w["confidence"] * confidence_score
            + self._w["scope"] * scope_score
            + self._w["tag"] * tag_score
            + self._w["centrality"] * centrality_score
        )

        # Boost for canonical/verified memories
        if rec.canonical:
            overall = min(1.0, overall * 1.2)

        # Boost for critical importance
        if rec.importance is Importance.CRITICAL:
            overall = min(1.0, overall * 1.3)

        return ImportanceScore(
            memory_id=memory_id,
            overall=min(1.0, overall),
            source_score=source_score,
            access_score=access_score,
            recency_score=recency_score,
            confidence_score=confidence_score,
            scope_score=scope_score,
            tag_score=tag_score,
            centrality_score=centrality_score,
            age_seconds=time.time() - rec.created_at,
            access_count=getattr(rec, "access_count", 0),
        )

    def rank_memories(
        self,
        query: str = "",
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[ImportanceScore]:
        """Rank memories by importance score.

        Args:
            query: Optional query to scope the search.
            top_k: Maximum results.
            min_score: Minimum overall score.

        Returns:
            List of ImportanceScore sorted by overall score.
        """
        if self._mm is None:
            return []

        try:
            if query:
                results = self._mm.search(query, top_k=top_k * 2)
            else:
                results = self._mm.search("", top_k=top_k * 2)
        except Exception as exc:
            logger.debug("Ranking retrieval failed: %s", exc)
            return []

        scores: list[ImportanceScore] = []
        for r in results:
            mem_id = self._get_id(r)
            score = self.score_memory(mem_id)
            if score and score.overall >= min_score:
                scores.append(score)

        scores.sort(key=lambda s: s.overall, reverse=True)
        return scores[:top_k]

    def get_important_memories(
        self,
        threshold: float = 0.7,
        top_k: int = 20,
    ) -> list[ImportanceScore]:
        """Get the most important memories above a threshold."""
        return self.rank_memories(top_k=top_k, min_score=threshold)

    def get_important_tags(self) -> list[str]:
        """Get the list of high-importance tags."""
        return sorted(_IMPORTANT_TAGS)

    def _source_score(self, rec: Any) -> float:
        """Score based on source type."""
        source = getattr(rec, "source_type", None)
        if source in _SOURCE_W:
            return _SOURCE_W[source]
        return 0.3

    def _access_score(self, rec: Any) -> float:
        """Score based on access frequency."""
        access_count = getattr(rec, "access_count", 0)
        if access_count <= 0:
            return 0.0
        # Log-scaled: 1 access = 0.1, 10 = 0.5, 100 = 0.9
        return min(0.9, 0.1 * math.log1p(access_count))

    def _recency_score(self, rec: Any) -> float:
        """Score based on recency (exponential decay)."""
        updated = getattr(rec, "updated_at", 0.0)
        if not updated:
            return 0.0
        age_days = max(0.0, (time.time() - updated) / 86400.0)
        # Half-life of 7 days
        return 0.5 ** (age_days / 7.0)

    def _confidence_score(self, rec: Any) -> float:
        """Score based on confidence."""
        conf = getattr(rec, "confidence", 0.0)
        return max(0.0, min(1.0, conf))

    def _scope_score(self, rec: Any) -> float:
        """Score based on scope."""
        scope = getattr(rec, "scope", None)
        if scope in _SCOPE_W:
            return _SCOPE_W[scope]
        return 0.3

    def _tag_score(self, rec: Any) -> float:
        """Score based on tags."""
        tags = getattr(rec, "tags", [])
        if not tags:
            return 0.0
        important_count = sum(1 for t in tags if t.lower() in _IMPORTANT_TAGS)
        return min(1.0, important_count / 3.0)

    def _centrality_score(self, rec: Any) -> float:
        """Score based on semantic centrality (graph connections)."""
        # This would integrate with the memory graph
        # For now, use a placeholder based on content length
        content = getattr(rec, "content", "")
        if not content:
            return 0.0
        # Longer memories tend to be more central (more connections)
        return min(0.5, len(content) / 2000.0)

    @staticmethod
    def _get_id(mem: Any) -> str:
        if hasattr(mem, "memory_id"):
            return str(mem.memory_id)
        if hasattr(mem, "record"):
            return str(mem.record.memory_id)
        return str(id(mem))

    def stats(self) -> dict[str, Any]:
        """Return scorer statistics."""
        return {
            "score_count": self._score_count,
            "weights": self._w,
        }
