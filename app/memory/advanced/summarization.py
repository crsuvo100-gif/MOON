"""Memory summarization -- generate concise summaries of memory content.

Professional AI assistants need to summarize large amounts of memory
into concise, actionable summaries. This module provides:

1. Topic summaries: Summarize all memories about a topic
2. Temporal summaries: Summarize what happened in a time period
3. Agent summaries: Summarize what an agent knows
4. Project summaries: Summarize project-related memories
5. Executive summaries: High-level overview of all memory

Summaries are generated using extractive techniques (selecting the most
important sentences) and can be cached for performance.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemorySummary:
    """A summary of memory content."""
    topic: str
    summary: str
    key_points: list[str] = field(default_factory=list)
    memory_count: int = 0
    time_range: tuple[float, float] | None = None
    confidence: float = 0.5
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "summary": self.summary,
            "key_points": self.key_points,
            "memory_count": self.memory_count,
            "time_range": self.time_range,
            "confidence": self.confidence,
            "generated_at": self.generated_at,
        }


class MemorySummarizer:
    """Generates summaries of memory content.

    Usage:
        summarizer = MemorySummarizer(memory_manager)
        summary = summarizer.summarize_topic("API authentication")
        summary = summarizer.summarizer.summarize_time_range(
            start=time.time() - 86400, end=time.time()
        )
        summary = summarizer.executive_summary()
    """

    # Configuration
    MAX_SUMMARY_SENTENCES = 5
    MAX_KEY_POINTS = 10
    MIN_SENTENCE_LENGTH = 10
    MAX_SENTENCE_LENGTH = 300

    def __init__(self, memory_manager=None) -> None:
        self._mm = memory_manager
        self._summary_count = 0
        self._cache: dict[str, tuple[float, MemorySummary]] = {}

    def summarize_topic(
        self,
        topic: str,
        top_k: int = 50,
        max_sentences: int | None = None,
    ) -> MemorySummary:
        """Summarize all memories about a topic.

        Args:
            topic: The topic to summarize.
            top_k: Maximum memories to consider.
            max_sentences: Override default max sentences.

        Returns:
            MemorySummary with the generated summary.
        """
        self._summary_count += 1
        max_sent = max_sentences or self.MAX_SUMMARY_SENTENCES

        if self._mm is None:
            return MemorySummary(topic=topic, summary="No memory manager available")

        try:
            results = self._mm.search(topic, top_k=top_k)
        except Exception as exc:
            logger.debug("Topic summary retrieval failed: %s", exc)
            return MemorySummary(topic=topic, summary=f"Error: {exc}")

        if not results:
            return MemorySummary(topic=topic, summary="No memories found")

        # Extract content
        contents = [self._get_content(r) for r in results]
        timestamps = [self._get_timestamp(r) for r in results]

        # Generate extractive summary
        summary_text = self._extractive_summary(contents, max_sent)
        key_points = self._extract_key_points(contents, self.MAX_KEY_POINTS)

        # Calculate confidence based on memory count and quality
        confidence = min(0.9, 0.3 + 0.05 * len(results))

        time_range = None
        if timestamps:
            time_range = (min(timestamps), max(timestamps))

        return MemorySummary(
            topic=topic,
            summary=summary_text,
            key_points=key_points,
            memory_count=len(results),
            time_range=time_range,
            confidence=confidence,
        )

    def summarize_time_range(
        self,
        start: float,
        end: float,
        top_k: int = 100,
    ) -> MemorySummary:
        """Summarize what happened in a time range.

        Args:
            start: Start timestamp.
            end: End timestamp.
            top_k: Maximum memories to consider.

        Returns:
            MemorySummary for the time range.
        """
        self._summary_count += 1

        if self._mm is None:
            return MemorySummary(topic=f"Time range {start}-{end}", summary="No memory manager")

        try:
            # Get all memories and filter by time
            results = self._mm.search("", top_k=top_k)
        except Exception as exc:
            logger.debug("Time range retrieval failed: %s", exc)
            return MemorySummary(topic=f"Time range {start}-{end}", summary=f"Error: {exc}")

        # Filter by time range
        filtered = []
        for r in results:
            ts = self._get_timestamp(r)
            if start <= ts <= end:
                filtered.append(r)

        if not filtered:
            return MemorySummary(
                topic=f"Time range {start}-{end}",
                summary="No memories in this time range",
            )

        contents = [self._get_content(r) for r in filtered]
        summary_text = self._extractive_summary(contents, self.MAX_SUMMARY_SENTENCES)
        key_points = self._extract_key_points(contents, self.MAX_KEY_POINTS)

        return MemorySummary(
            topic=f"Time range {start}-{end}",
            summary=summary_text,
            key_points=key_points,
            memory_count=len(filtered),
            time_range=(start, end),
            confidence=min(0.9, 0.3 + 0.05 * len(filtered)),
        )

    def summarize_agent(self, agent_id: str, top_k: int = 50) -> MemorySummary:
        """Summarize what an agent knows.

        Args:
            agent_id: The agent ID to summarize.
            top_k: Maximum memories to consider.

        Returns:
            MemorySummary for the agent.
        """
        return self.summarize_topic(f"agent:{agent_id}", top_k=top_k)

    def summarize_project(self, project_id: str, top_k: int = 50) -> MemorySummary:
        """Summarize project-related memories.

        Args:
            project_id: The project ID to summarize.
            top_k: Maximum memories to consider.

        Returns:
            MemorySummary for the project.
        """
        return self.summarize_topic(f"project:{project_id}", top_k=top_k)

    def executive_summary(self, top_k: int = 100) -> MemorySummary:
        """Generate a high-level executive summary of all memory.

        Returns:
            MemorySummary with an overview of all memory.
        """
        self._summary_count += 1

        if self._mm is None:
            return MemorySummary(topic="Executive Summary", summary="No memory manager")

        try:
            results = self._mm.search("", top_k=top_k)
        except Exception as exc:
            logger.debug("Executive summary retrieval failed: %s", exc)
            return MemorySummary(topic="Executive Summary", summary=f"Error: {exc}")

        if not results:
            return MemorySummary(topic="Executive Summary", summary="No memories stored")

        # Group by scope
        scope_counts: dict[str, int] = {}
        importance_counts: dict[str, int] = {}
        tag_counts: dict[str, int] = {}

        for r in results:
            scope = self._get_scope(r)
            scope_counts[scope] = scope_counts.get(scope, 0) + 1

            importance = self._get_importance(r)
            importance_counts[importance] = importance_counts.get(importance, 0) + 1

            for tag in self._get_tags(r):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Generate summary
        total = len(results)
        top_scopes = sorted(scope_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        summary_parts = [
            f"Total memories: {total}",
            f"Top scopes: {', '.join(f'{s}({c})' for s, c in top_scopes)}",
            f"Top tags: {', '.join(f'{t}({c})' for t, c in top_tags)}",
        ]

        key_points = [
            f"Most common scope: {top_scopes[0][0] if top_scopes else 'N/A'}",
            f"Most common tag: {top_tags[0][0] if top_tags else 'N/A'}",
            f"High importance memories: {importance_counts.get('HIGH', 0) + importance_counts.get('CRITICAL', 0)}",
        ]

        return MemorySummary(
            topic="Executive Summary",
            summary=" | ".join(summary_parts),
            key_points=key_points,
            memory_count=total,
            confidence=min(0.95, 0.4 + 0.01 * total),
        )

    def _extractive_summary(self, contents: list[str], max_sentences: int) -> str:
        """Generate an extractive summary from memory contents.

        Selects the most important sentences based on:
        - Position (first sentences are more important)
        - Length (medium-length sentences are preferred)
        - Keyword density (sentences with more keywords)
        """
        # Split into sentences
        all_sentences: list[tuple[str, float]] = []
        for content in contents:
            sentences = re.split(r"[.!?]+", content)
            for i, sent in enumerate(sentences):
                sent = sent.strip()
                if len(sent) < self.MIN_SENTENCE_LENGTH:
                    continue
                if len(sent) > self.MAX_SENTENCE_LENGTH:
                    sent = sent[:self.MAX_SENTENCE_LENGTH] + "..."

                # Score: position + length + keyword density
                position_score = 1.0 / (i + 1)  # Earlier sentences score higher
                length_score = min(1.0, len(sent) / 100.0)
                word_count = len(sent.split())
                keyword_score = min(1.0, word_count / 20.0)

                score = 0.4 * position_score + 0.3 * length_score + 0.3 * keyword_score
                all_sentences.append((sent, score))

        # Sort by score and take top N
        all_sentences.sort(key=lambda x: x[1], reverse=True)
        selected = all_sentences[:max_sentences]

        # Reorder by original position for coherence
        selected.sort(key=lambda x: contents[0].find(x[0]) if x[0] in contents[0] else 0)

        return ". ".join(s for s, _ in selected) + "."

    def _extract_key_points(self, contents: list[str], max_points: int) -> list[str]:
        """Extract key points from memory contents."""
        key_points: list[tuple[str, float]] = []

        for content in contents:
            sentences = re.split(r"[.!?]+", content)
            for sent in sentences:
                sent = sent.strip()
                if len(sent) < self.MIN_SENTENCE_LENGTH:
                    continue
                if len(sent) > self.MAX_SENTENCE_LENGTH:
                    continue

                # Score by importance indicators
                score = 0.0
                lower = sent.lower()
                if any(w in lower for w in ["important", "critical", "key", "essential", "must"]):
                    score += 0.5
                if any(w in lower for w in ["user", "config", "security", "api", "error"]):
                    score += 0.3
                if len(sent.split()) >= 5:
                    score += 0.2

                if score > 0:
                    key_points.append((sent, score))

        key_points.sort(key=lambda x: x[1], reverse=True)
        return [kp for kp, _ in key_points[:max_points]]

    @staticmethod
    def _get_content(mem: Any) -> str:
        if hasattr(mem, "content"):
            return str(mem.content)
        if hasattr(mem, "record"):
            return str(mem.record.content)
        return str(mem)

    @staticmethod
    def _get_timestamp(mem: Any) -> float:
        if hasattr(mem, "created_at"):
            return float(mem.created_at)
        if hasattr(mem, "record"):
            return float(mem.record.created_at)
        return 0.0

    @staticmethod
    def _get_scope(mem: Any) -> str:
        if hasattr(mem, "scope"):
            return str(mem.scope)
        if hasattr(mem, "record"):
            return str(mem.record.scope)
        return "unknown"

    @staticmethod
    def _get_importance(mem: Any) -> str:
        if hasattr(mem, "importance"):
            return str(mem.importance)
        if hasattr(mem, "record"):
            return str(mem.record.importance)
        return "MEDIUM"

    @staticmethod
    def _get_tags(mem: Any) -> list[str]:
        if hasattr(mem, "tags"):
            return list(mem.tags)
        if hasattr(mem, "record"):
            return list(mem.record.tags)
        return []

    def stats(self) -> dict[str, Any]:
        """Return summarizer statistics."""
        return {
            "summary_count": self._summary_count,
            "cache_size": len(self._cache),
        }
