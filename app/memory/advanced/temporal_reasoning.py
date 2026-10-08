"""Temporal reasoning -- reason about memory over time.

Professional AI assistants understand that knowledge changes over time.
This module provides temporal reasoning capabilities:

1. "What did I know at time X?" -- historical state reconstruction
2. "When did I learn this?" -- temporal provenance tracking
3. "What changed between X and Y?" -- temporal diff
4. "Is this still valid?" -- temporal validity checking
5. "What will likely change next?" -- temporal prediction

The module operates on the existing memory store and uses timestamps
to reason about knowledge evolution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TemporalFact:
    """A fact with temporal information."""
    content: str
    valid_from: float
    valid_until: float | None = None
    confidence: float = 0.5
    source: str = ""

    @property
    def is_current(self) -> bool:
        now = time.time()
        if self.valid_until and now > self.valid_until:
            return False
        return now >= self.valid_from

    @property
    def age_days(self) -> float:
        return (time.time() - self.valid_from) / 86400.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "is_current": self.is_current,
            "confidence": self.confidence,
            "source": self.source,
            "age_days": round(self.age_days, 2),
        }


@dataclass
class TemporalDiff:
    """A diff between two temporal states."""
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[dict[str, str]] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": self.added,
            "removed": self.removed,
            "changed": self.changed,
            "unchanged": self.unchanged,
        }


class TemporalReasoner:
    """Reasons about memory over time.

    Usage:
        reasoner = TemporalReasoner(memory_manager)
        facts = reasoner.at_time("What did I know about the API?", timestamp=1695000000)
        diff = reasoner.diff("API config", start=1695000000, end=1696000000)
        valid = reasoner.is_valid("The API uses OAuth2")
    """

    def __init__(self, memory_manager=None) -> None:
        self._mm = memory_manager
        self._reasoning_count = 0

    def at_time(
        self,
        query: str,
        timestamp: float,
        top_k: int = 10,
    ) -> list[TemporalFact]:
        """Reconstruct what was known at a specific point in time.

        Args:
            query: The topic to query.
            timestamp: The point in time to reconstruct.
            top_k: Maximum facts to return.

        Returns:
            List of TemporalFact valid at that time.
        """
        self._reasoning_count += 1

        if self._mm is None:
            return []

        try:
            results = self._mm.search(query, top_k=top_k * 2)
        except Exception as exc:
            logger.debug("Temporal retrieval failed: %s", exc)
            return []

        facts: list[TemporalFact] = []
        for r in results:
            content = self._get_content(r)
            created = self._get_created(r)
            updated = self._get_updated(r)

            # A fact was "known" at timestamp T if it was created before T
            # and not yet updated after T (i.e., the version at T is what we see now
            # if created <= T <= updated, or the latest version if created <= T)
            if created <= timestamp:
                # Check if there's a more recent version
                if updated <= timestamp:
                    # This version was current at T
                    facts.append(TemporalFact(
                        content=content,
                        valid_from=created,
                        valid_until=None,
                        confidence=self._get_confidence(r),
                        source=self._get_source(r),
                    ))
                else:
                    # This was updated after T, so it was different at T
                    # We can't reconstruct the old version, but we know it existed
                    facts.append(TemporalFact(
                        content=f"[updated since] {content[:200]}",
                        valid_from=created,
                        valid_until=updated,
                        confidence=self._get_confidence(r) * 0.7,
                        source=self._get_source(r),
                    ))

        facts.sort(key=lambda f: f.valid_from, reverse=True)
        return facts[:top_k]

    def diff(
        self,
        query: str,
        start: float,
        end: float,
        top_k: int = 20,
    ) -> TemporalDiff:
        """Compute what changed about a topic between two points in time.

        Args:
            query: The topic to diff.
            start: Start timestamp.
            end: End timestamp.
            top_k: Maximum items to consider.

        Returns:
            TemporalDiff with added, removed, changed, and unchanged items.
        """
        self._reasoning_count += 1

        facts_start = self.at_time(query, start, top_k)
        facts_end = self.at_time(query, end, top_k)

        start_contents = {f.content for f in facts_start}
        end_contents = {f.content for f in facts_end}

        added = [c for c in end_contents if c not in start_contents]
        removed = [c for c in start_contents if c not in end_contents]
        unchanged = [c for c in start_contents if c in end_contents]

        # Detect changes (similar but not identical)
        changed: list[dict[str, str]] = []
        for c_start in start_contents & end_contents:
            # Check if confidence changed significantly
            conf_start = next((f.confidence for f in facts_start if f.content == c_start), 0.5)
            conf_end = next((f.confidence for f in facts_end if f.content == c_start), 0.5)
            if abs(conf_start - conf_end) > 0.2:
                changed.append({
                    "content": c_start[:100],
                    "confidence_change": f"{conf_start:.2f} -> {conf_end:.2f}",
                })

        return TemporalDiff(
            added=added[:top_k],
            removed=removed[:top_k],
            changed=changed[:top_k],
            unchanged=unchanged[:top_k],
        )

    def is_valid(self, statement: str, query: str = "") -> dict[str, Any]:
        """Check if a statement is still valid based on memory.

        Args:
            statement: The statement to check.
            query: Optional context query.

        Returns:
            Dict with validity info.
        """
        self._reasoning_count += 1

        if self._mm is None:
            return {"valid": None, "reason": "no memory manager"}

        try:
            results = self._mm.search(query or statement, top_k=5)
        except Exception as exc:
            logger.debug("Validity check failed: %s", exc)
            return {"valid": None, "reason": str(exc)}

        if not results:
            return {"valid": None, "reason": "no relevant memories found"}

        # Check if any memory contradicts the statement
        statement_lower = statement.lower()
        for r in results:
            content = self._get_content(r).lower()
            # Simple contradiction check
            if self._is_contradiction(statement_lower, content):
                return {
                    "valid": False,
                    "reason": "contradicted by stored memory",
                    "contradicting_memory": content[:200],
                }

        # Check if any memory supports the statement
        for r in results:
            content = self._get_content(r).lower()
            if self._is_support(statement_lower, content):
                return {
                    "valid": True,
                    "reason": "supported by stored memory",
                    "supporting_memory": content[:200],
                    "confidence": self._get_confidence(r),
                }

        return {"valid": None, "reason": "no supporting or contradicting evidence"}

    def get_timeline(
        self,
        query: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Get a timeline of memories about a topic.

        Returns:
            List of dicts with content and timestamp, sorted chronologically.
        """
        self._reasoning_count += 1

        if self._mm is None:
            return []

        try:
            results = self._mm.search(query, top_k=top_k)
        except Exception as exc:
            logger.debug("Timeline retrieval failed: %s", exc)
            return []

        timeline: list[dict[str, Any]] = []
        for r in results:
            timeline.append({
                "content": self._get_content(r)[:200],
                "timestamp": self._get_created(r),
                "updated_at": self._get_updated(r),
                "confidence": self._get_confidence(r),
                "source": self._get_source(r),
            })

        timeline.sort(key=lambda x: x["timestamp"])
        return timeline

    def predict_changes(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Predict what might change next based on temporal patterns.

        Uses simple heuristics:
        - Topics with frequent updates are likely to change again
        - Topics with declining confidence may need updating
        - Topics with recent conflicts are unstable

        Returns:
            List of predictions with confidence scores.
        """
        self._reasoning_count += 1

        timeline = self.get_timeline(query, top_k * 4)
        if len(timeline) < 2:
            return []

        predictions: list[dict[str, Any]] = []

        # Calculate update frequency
        timestamps = [t["timestamp"] for t in timeline]
        if len(timestamps) >= 2:
            intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
            avg_interval = sum(intervals) / len(intervals)
            last_update = timestamps[-1]
            time_since_last = time.time() - last_update

            if time_since_last > avg_interval * 1.5:
                predictions.append({
                    "prediction": f"Topic '{query[:50]}' is overdue for an update",
                    "confidence": min(0.8, 0.3 + 0.1 * len(timeline)),
                    "reason": f"Last update was {time_since_last/86400:.1f} days ago, "
                              f"average interval is {avg_interval/86400:.1f} days",
                })

        # Check for declining confidence
        confidences = [t["confidence"] for t in timeline if t["confidence"] > 0]
        if len(confidences) >= 2:
            if confidences[-1] < confidences[0] * 0.7:
                predictions.append({
                    "prediction": f"Confidence in '{query[:50]}' is declining",
                    "confidence": 0.6,
                    "reason": f"Confidence dropped from {confidences[0]:.2f} to {confidences[-1]:.2f}",
                })

        return predictions

    @staticmethod
    def _is_contradiction(statement: str, memory: str) -> bool:
        """Check if a memory contradicts a statement."""
        # Simple negation detection
        negation_words = {"not", "no", "never", "cannot", "won't", "doesn't"}
        stmt_has_neg = any(w in statement for w in negation_words)
        mem_has_neg = any(w in memory for w in negation_words)

        if stmt_has_neg != mem_has_neg:
            # Check topic overlap
            stmt_words = set(statement.split())
            mem_words = set(memory.split())
            if stmt_words and mem_words:
                overlap = len(stmt_words & mem_words) / min(len(stmt_words), len(mem_words))
                if overlap >= 0.4:
                    return True
        return False

    @staticmethod
    def _is_support(statement: str, memory: str) -> bool:
        """Check if a memory supports a statement."""
        stmt_words = set(statement.split())
        mem_words = set(memory.split())
        if not stmt_words:
            return False
        overlap = len(stmt_words & mem_words) / len(stmt_words)
        return overlap >= 0.5

    @staticmethod
    def _get_content(mem: Any) -> str:
        if hasattr(mem, "content"):
            return str(mem.content)
        if hasattr(mem, "record"):
            return str(mem.record.content)
        return str(mem)

    @staticmethod
    def _get_created(mem: Any) -> float:
        if hasattr(mem, "created_at"):
            return float(mem.created_at)
        if hasattr(mem, "record"):
            return float(mem.record.created_at)
        return 0.0

    @staticmethod
    def _get_updated(mem: Any) -> float:
        if hasattr(mem, "updated_at"):
            return float(mem.updated_at)
        if hasattr(mem, "record"):
            return float(mem.record.updated_at)
        return 0.0

    @staticmethod
    def _get_confidence(mem: Any) -> float:
        if hasattr(mem, "confidence"):
            return float(mem.confidence)
        if hasattr(mem, "record"):
            return float(mem.record.confidence)
        return 0.5

    @staticmethod
    def _get_source(mem: Any) -> str:
        if hasattr(mem, "source_type"):
            return str(mem.source_type)
        if hasattr(mem, "record"):
            return str(mem.record.source_type)
        return "unknown"

    def stats(self) -> dict[str, Any]:
        """Return temporal reasoner statistics."""
        return {
            "reasoning_count": self._reasoning_count,
        }
