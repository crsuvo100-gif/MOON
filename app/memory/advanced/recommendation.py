"""Memory recommendation engine -- proactive memory suggestions.

Professional AI assistants don't just retrieve memories -- they
proactively suggest relevant memories. This module provides:

1. Context-aware recommendations: Suggest memories relevant to current context
2. Task-based recommendations: Suggest memories for the current task
3. Agent-based recommendations: Suggest memories for the current agent
4. Temporal recommendations: Suggest memories based on time patterns
5. Gap recommendations: Suggest what information might be missing

The recommendation engine uses multiple signals to rank suggestions.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryRecommendation:
    """A recommended memory with context."""
    memory_id: str
    content: str
    reason: str
    relevance_score: float  # 0.0 - 1.0
    source: str  # "context", "task", "agent", "temporal", "gap"
    tags: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "content": self.content[:200],
            "reason": self.reason,
            "relevance_score": round(self.relevance_score, 4),
            "source": self.source,
            "tags": self.tags,
            "timestamp": self.timestamp,
        }


class MemoryRecommender:
    """Recommends memories proactively.

    Usage:
        recommender = MemoryRecommender(memory_manager)
        recs = recommender.recommend(context="Working on API auth")
        recs = recommender.recommend_for_task("Deploy to production")
        recs = recommender.recommend_for_agent("security-auditor")
        recs = recommender.find_gaps(context="API authentication")
    """

    def __init__(self, memory_manager=None) -> None:
        self._mm = memory_manager
        self._recommendation_count = 0

    def recommend(
        self,
        context: str,
        top_k: int = 10,
        min_score: float = 0.3,
    ) -> list[MemoryRecommendation]:
        """Recommend memories relevant to a context.

        Args:
            context: The current context (e.g., current conversation topic).
            top_k: Maximum recommendations.
            min_score: Minimum relevance score.

        Returns:
            List of MemoryRecommendation sorted by relevance.
        """
        self._recommendation_count += 1

        if not context or not context.strip():
            return []

        if self._mm is None:
            return []

        try:
            results = self._mm.search(context, top_k=top_k * 2)
        except Exception as exc:
            logger.debug("Recommendation retrieval failed: %s", exc)
            return []

        context_lower = context.lower()
        context_words = set(re.findall(r"[a-z_]{3,}", context_lower))

        recommendations: list[MemoryRecommendation] = []
        for r in results:
            content = self._get_content(r)
            content_lower = content.lower()
            content_words = set(re.findall(r"[a-z_]{3,}", content_lower))

            # Calculate relevance
            if context_words and content_words:
                overlap = len(context_words & content_words) / len(context_words)
            else:
                overlap = 0.0

            # Boost for high-confidence memories
            confidence = self._get_confidence(r)
            score = overlap * 0.7 + confidence * 0.3

            if score >= min_score:
                mem_id = self._get_id(r)
                tags = self._get_tags(r)
                recommendations.append(MemoryRecommendation(
                    memory_id=mem_id,
                    content=content,
                    reason=f"Context match: {overlap:.0%} keyword overlap",
                    relevance_score=score,
                    source="context",
                    tags=tags,
                ))

        recommendations.sort(key=lambda r: r.relevance_score, reverse=True)
        return recommendations[:top_k]

    def recommend_for_task(
        self,
        task_description: str,
        top_k: int = 10,
    ) -> list[MemoryRecommendation]:
        """Recommend memories relevant to a task.

        Args:
            task_description: Description of the task.
            top_k: Maximum recommendations.

        Returns:
            List of MemoryRecommendation.
        """
        self._recommendation_count += 1

        if not task_description or not task_description.strip():
            return []

        if self._mm is None:
            return []

        try:
            results = self._mm.search(task_description, top_k=top_k * 2)
        except Exception as exc:
            logger.debug("Task recommendation retrieval failed: %s", exc)
            return []

        task_lower = task_description.lower()
        task_words = set(re.findall(r"[a-z_]{3,}", task_lower))

        recommendations: list[MemoryRecommendation] = []
        for r in results:
            content = self._get_content(r)
            content_lower = content.lower()
            content_words = set(re.findall(r"[a-z_]{3,}", content_lower))

            if task_words and content_words:
                overlap = len(task_words & content_words) / len(task_words)
            else:
                overlap = 0.0

            # Boost for task-related tags
            tags = self._get_tags(r)
            tag_boost = 0.0
            if any(t in tags for t in ["task", "todo", "action", "deploy", "fix"]):
                tag_boost = 0.2

            score = min(1.0, overlap * 0.6 + tag_boost + self._get_confidence(r) * 0.2)

            if score >= 0.3:
                mem_id = self._get_id(r)
                recommendations.append(MemoryRecommendation(
                    memory_id=mem_id,
                    content=content,
                    reason=f"Task relevance: {overlap:.0%} match, tags: {tags[:3]}",
                    relevance_score=score,
                    source="task",
                    tags=tags,
                ))

        recommendations.sort(key=lambda r: r.relevance_score, reverse=True)
        return recommendations[:top_k]

    def recommend_for_agent(
        self,
        agent_id: str,
        top_k: int = 10,
    ) -> list[MemoryRecommendation]:
        """Recommend memories for a specific agent.

        Args:
            agent_id: The agent ID.
            top_k: Maximum recommendations.

        Returns:
            List of MemoryRecommendation.
        """
        self._recommendation_count += 1

        if not agent_id or not agent_id.strip():
            return []

        if self._mm is None:
            return []

        try:
            results = self._mm.search(f"agent:{agent_id}", top_k=top_k * 2)
        except Exception as exc:
            logger.debug("Agent recommendation retrieval failed: %s", exc)
            return []

        recommendations: list[MemoryRecommendation] = []
        for r in results:
            content = self._get_content(r)
            agent = self._get_agent(r)

            # Score by agent match and confidence
            agent_match = 1.0 if agent == agent_id else 0.3
            confidence = self._get_confidence(r)
            score = agent_match * 0.6 + confidence * 0.4

            if score >= 0.3:
                mem_id = self._get_id(r)
                tags = self._get_tags(r)
                recommendations.append(MemoryRecommendation(
                    memory_id=mem_id,
                    content=content,
                    reason=f"Agent match: {agent_match:.0%}, confidence: {confidence:.0%}",
                    relevance_score=score,
                    source="agent",
                    tags=tags,
                ))

        recommendations.sort(key=lambda r: r.relevance_score, reverse=True)
        return recommendations[:top_k]

    def recommend_temporal(
        self,
        top_k: int = 10,
    ) -> list[MemoryRecommendation]:
        """Recommend memories based on temporal patterns.

        Suggests memories that:
        - Were recently updated (might need attention)
        - Haven't been accessed in a while (might be forgotten)
        - Are related to current time (e.g., same day of week)

        Returns:
            List of MemoryRecommendation.
        """
        self._recommendation_count += 1

        if self._mm is None:
            return []

        try:
            results = self._mm.search("", top_k=top_k * 3)
        except Exception as exc:
            logger.debug("Temporal recommendation retrieval failed: %s", exc)
            return []

        now = time.time()
        recommendations: list[MemoryRecommendation] = []

        for r in results:
            content = self._get_content(r)
            updated = self._get_updated(r)
            access_count = self._get_access_count(r)

            # Recently updated (within 24 hours)
            if updated and (now - updated) < 86400:
                score = 0.7
                reason = "Recently updated"
            # Not accessed in 30+ days
            elif access_count == 0 and updated and (now - updated) > 30 * 86400:
                score = 0.5
                reason = "Not accessed in 30+ days"
            else:
                continue

            mem_id = self._get_id(r)
            tags = self._get_tags(r)
            recommendations.append(MemoryRecommendation(
                memory_id=mem_id,
                content=content,
                reason=reason,
                relevance_score=score,
                source="temporal",
                tags=tags,
            ))

        recommendations.sort(key=lambda r: r.relevance_score, reverse=True)
        return recommendations[:top_k]

    def find_gaps(
        self,
        context: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Find information gaps in memory for a context.

        Identifies topics that are mentioned but have no stored memories.

        Args:
            context: The context to check for gaps.
            top_k: Maximum gaps to report.

        Returns:
            List of gap descriptions.
        """
        self._recommendation_count += 1

        if not context or not context.strip():
            return []

        if self._mm is None:
            return []

        # Extract key topics from context
        context_lower = context.lower()
        context_words = set(re.findall(r"[a-z_]{4,}", context_lower))

        # Remove common words
        common_words = {
            "this", "that", "with", "from", "have", "been", "will", "would",
            "could", "should", "about", "into", "than", "then", "when",
            "where", "which", "while", "what", "their", "there", "these",
            "those", "being", "other", "some", "such", "only", "also",
        }
        topics = context_words - common_words

        # Check which topics have no memories
        gaps: list[dict[str, Any]] = []
        for topic in sorted(topics):
            try:
                results = self._mm.search(topic, top_k=1)
                if not results:
                    gaps.append({
                        "topic": topic,
                        "reason": f"No memories found about '{topic}'",
                        "suggestion": f"Consider researching and storing information about '{topic}'",
                    })
            except Exception:
                continue

        return gaps[:top_k]

    @staticmethod
    def _get_id(mem: Any) -> str:
        if hasattr(mem, "memory_id"):
            return str(mem.memory_id)
        if hasattr(mem, "record"):
            return str(mem.record.memory_id)
        return str(id(mem))

    @staticmethod
    def _get_content(mem: Any) -> str:
        if hasattr(mem, "content"):
            return str(mem.content)
        if hasattr(mem, "record"):
            return str(mem.record.content)
        return str(mem)

    @staticmethod
    def _get_confidence(mem: Any) -> float:
        if hasattr(mem, "confidence"):
            return float(mem.confidence)
        if hasattr(mem, "record"):
            return float(mem.record.confidence)
        return 0.5

    @staticmethod
    def _get_tags(mem: Any) -> list[str]:
        if hasattr(mem, "tags"):
            return list(mem.tags)
        if hasattr(mem, "record"):
            return list(mem.record.tags)
        return []

    @staticmethod
    def _get_agent(mem: Any) -> str:
        if hasattr(mem, "agent_id"):
            return str(mem.agent_id)
        if hasattr(mem, "record"):
            return str(mem.record.agent_id)
        return "unknown"

    @staticmethod
    def _get_updated(mem: Any) -> float:
        if hasattr(mem, "updated_at"):
            return float(mem.updated_at)
        if hasattr(mem, "record"):
            return float(mem.record.updated_at)
        return 0.0

    @staticmethod
    def _get_access_count(mem: Any) -> int:
        if hasattr(mem, "access_count"):
            return int(mem.access_count)
        if hasattr(mem, "record"):
            return int(mem.record.access_count)
        return 0

    def stats(self) -> dict[str, Any]:
        """Return recommender statistics."""
        return {
            "recommendation_count": self._recommendation_count,
        }
