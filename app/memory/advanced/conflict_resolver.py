"""Memory conflict resolver -- detect and resolve contradictions.

Professional AI assistants encounter conflicting information over time.
This module detects contradictions between memories and resolves them
using configurable strategies:

1. Keep newest: The most recent memory wins (default)
2. Keep highest confidence: The most confident memory wins
3. Keep both: Flag as conflicting, keep both with conflict metadata
4. Merge: Combine both memories into a single merged memory
5. Ask user: Flag for human review

Conflicts are detected by:
- Contradictory statements about the same entity
- Mutually exclusive facts (X is true vs X is false)
- Temporal contradictions (X was true then X became false)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Conflict:
    """A detected conflict between two memories."""
    memory_id_a: str
    memory_id_b: str
    content_a: str
    content_b: str
    conflict_type: str  # "contradiction", "temporal", "mutual_exclusive"
    severity: float     # 0.0 - 1.0
    description: str = ""
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id_a": self.memory_id_a,
            "memory_id_b": self.memory_id_b,
            "content_a": self.content_a[:200],
            "content_b": self.content_b[:200],
            "conflict_type": self.conflict_type,
            "severity": round(self.severity, 4),
            "description": self.description,
            "detected_at": self.detected_at,
        }


@dataclass
class Resolution:
    """A conflict resolution result."""
    conflict: Conflict
    strategy: str
    winner_id: str | None
    loser_id: str | None
    merged_content: str | None = None
    resolved_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict": self.conflict.to_dict(),
            "strategy": self.strategy,
            "winner_id": self.winner_id,
            "loser_id": self.loser_id,
            "merged_content": self.merged_content[:200] if self.merged_content else None,
            "resolved_at": self.resolved_at,
        }


class ConflictResolver:
    """Detects and resolves conflicts between memories.

    Usage:
        resolver = ConflictResolver(memory_manager)
        conflicts = resolver.detect_conflicts(query="API endpoint")
        resolutions = resolver.resolve_conflicts(conflicts, strategy="newest")
    """

    # Words that indicate negation/contradiction
    _NEGATION_WORDS = {"not", "no", "never", "cannot", "can't", "won't", "doesn't", "isn't", "aren't", "wasn't", "weren't"}

    # Words that indicate mutual exclusivity
    _EXCLUSIVE_WORDS = {"either", "or", "but", "however", "although", "though", "whereas", "while"}

    def __init__(self, memory_manager=None) -> None:
        self._mm = memory_manager
        self._conflict_count = 0
        self._resolution_count = 0

    def detect_conflicts(
        self,
        query: str = "",
        top_k: int = 50,
        min_severity: float = 0.3,
    ) -> list[Conflict]:
        """Detect conflicts among memories relevant to a query.

        Args:
            query: Optional query to scope the search.
            top_k: Maximum memories to check.
            min_severity: Minimum severity to report.

        Returns:
            List of detected conflicts.
        """
        memories = self._retrieve_memories(query, top_k)
        if len(memories) < 2:
            return []

        conflicts: list[Conflict] = []
        for i, mem_a in enumerate(memories):
            for mem_b in memories[i + 1:]:
                conflict = self._check_pair(mem_a, mem_b)
                if conflict and conflict.severity >= min_severity:
                    conflicts.append(conflict)

        conflicts.sort(key=lambda c: c.severity, reverse=True)
        self._conflict_count += len(conflicts)
        return conflicts

    def resolve_conflicts(
        self,
        conflicts: list[Conflict],
        strategy: str = "newest",
    ) -> list[Resolution]:
        """Resolve conflicts using the specified strategy.

        Args:
            conflicts: List of conflicts to resolve.
            strategy: One of "newest", "confidence", "keep_both", "merge", "ask_user".

        Returns:
            List of resolutions.
        """
        resolutions: list[Resolution] = []
        for conflict in conflicts:
            resolution = self._resolve_single(conflict, strategy)
            if resolution:
                resolutions.append(resolution)
                self._resolution_count += 1
        return resolutions

    def auto_resolve(
        self,
        query: str = "",
        strategy: str = "newest",
        min_severity: float = 0.5,
    ) -> list[Resolution]:
        """Detect and resolve conflicts in one step."""
        conflicts = self.detect_conflicts(query, min_severity=min_severity)
        return self.resolve_conflicts(conflicts, strategy)

    def _retrieve_memories(self, query: str, top_k: int) -> list[Any]:
        """Retrieve memories from the memory manager."""
        if self._mm is None:
            return []
        try:
            if query:
                return self._mm.search(query, top_k=top_k)
            # Get all memories if no query
            return self._mm.search("", top_k=top_k)
        except Exception as exc:
            logger.debug("Conflict retrieval failed: %s", exc)
            return []

    def _check_pair(self, mem_a: Any, mem_b: Any) -> Conflict | None:
        """Check if two memories conflict."""
        content_a = self._get_content(mem_a)
        content_b = self._get_content(mem_b)
        id_a = self._get_id(mem_a)
        id_b = self._get_id(mem_b)

        # Check for direct contradiction
        contradiction = self._check_contradiction(content_a, content_b)
        if contradiction:
            return Conflict(
                memory_id_a=id_a,
                memory_id_b=id_b,
                content_a=content_a,
                content_b=content_b,
                conflict_type="contradiction",
                severity=contradiction["severity"],
                description=contradiction["description"],
            )

        # Check for temporal conflict
        temporal = self._check_temporal_conflict(mem_a, mem_b)
        if temporal:
            return Conflict(
                memory_id_a=id_a,
                memory_id_b=id_b,
                content_a=content_a,
                content_b=content_b,
                conflict_type="temporal",
                severity=temporal["severity"],
                description=temporal["description"],
            )

        # Check for mutual exclusivity
        exclusive = self._check_mutual_exclusive(content_a, content_b)
        if exclusive:
            return Conflict(
                memory_id_a=id_a,
                memory_id_b=id_b,
                content_a=content_a,
                content_b=content_b,
                conflict_type="mutual_exclusive",
                severity=exclusive["severity"],
                description=exclusive["description"],
            )

        return None

    def _check_contradiction(self, a: str, b: str) -> dict[str, Any] | None:
        """Check if two statements contradict each other."""
        a_lower = a.lower()
        b_lower = b.lower()

        # Check for negation patterns
        a_has_neg = any(w in a_lower for w in self._NEGATION_WORDS)
        b_has_neg = any(w in b_lower for w in self._NEGATION_WORDS)

        if a_has_neg != b_has_neg:
            # One has negation, the other doesn't - potential contradiction
            # Check if they're about the same topic
            a_words = set(re.findall(r"[a-z_]{3,}", a_lower))
            b_words = set(re.findall(r"[a-z_]{3,}", b_lower))
            if a_words and b_words:
                overlap = len(a_words & b_words) / min(len(a_words), len(b_words))
                if overlap >= 0.5:
                    return {
                        "severity": 0.5 + 0.3 * overlap,
                        "description": f"Potential contradiction: one statement negates the other "
                                       f"(overlap: {overlap:.0%})",
                    }

        return None

    def _check_temporal_conflict(self, mem_a: Any, mem_b: Any) -> dict[str, Any] | None:
        """Check if two memories have a temporal conflict."""
        ts_a = self._get_timestamp(mem_a)
        ts_b = self._get_timestamp(mem_b)

        if not ts_a or not ts_b:
            return None

        content_a = self._get_content(mem_a).lower()
        content_b = self._get_content(mem_b).lower()

        # Check for "was X" vs "is now Y" patterns
        if ("was" in content_a and "now" in content_b) or ("was" in content_b and "now" in content_a):
            a_words = set(re.findall(r"[a-z_]{3,}", content_a))
            b_words = set(re.findall(r"[a-z_]{3,}", content_b))
            if a_words and b_words:
                overlap = len(a_words & b_words) / min(len(a_words), len(b_words))
                if overlap >= 0.4:
                    return {
                        "severity": 0.4 + 0.2 * overlap,
                        "description": "Temporal conflict: state changed over time",
                    }

        return None

    def _check_mutual_exclusive(self, a: str, b: str) -> dict[str, Any] | None:
        """Check if two statements are mutually exclusive."""
        a_lower = a.lower()
        b_lower = b.lower()

        # Check for exclusive language
        a_has_excl = any(w in a_lower for w in self._EXCLUSIVE_WORDS)
        b_has_excl = any(w in b_lower for w in self._EXCLUSIVE_WORDS)

        if a_has_excl or b_has_excl:
            a_words = set(re.findall(r"[a-z_]{3,}", a_lower))
            b_words = set(re.findall(r"[a-z_]{3,}", b_lower))
            if a_words and b_words:
                overlap = len(a_words & b_words) / min(len(a_words), len(b_words))
                if overlap >= 0.6:
                    return {
                        "severity": 0.5 + 0.2 * overlap,
                        "description": "Mutually exclusive statements detected",
                    }

        return None

    def _resolve_single(self, conflict: Conflict, strategy: str) -> Resolution | None:
        """Resolve a single conflict."""
        if strategy == "newest":
            return self._resolve_newest(conflict)
        elif strategy == "confidence":
            return self._resolve_confidence(conflict)
        elif strategy == "keep_both":
            return self._resolve_keep_both(conflict)
        elif strategy == "merge":
            return self._resolve_merge(conflict)
        elif strategy == "ask_user":
            return self._resolve_ask_user(conflict)
        return None

    def _resolve_newest(self, conflict: Conflict) -> Resolution:
        """Keep the newest memory."""
        # Get timestamps from memory manager
        ts_a = self._get_memory_timestamp(conflict.memory_id_a)
        ts_b = self._get_memory_timestamp(conflict.memory_id_b)

        if ts_a >= ts_b:
            winner, loser = conflict.memory_id_a, conflict.memory_id_b
        else:
            winner, loser = conflict.memory_id_b, conflict.memory_id_a

        return Resolution(
            conflict=conflict,
            strategy="newest",
            winner_id=winner,
            loser_id=loser,
        )

    def _resolve_confidence(self, conflict: Conflict) -> Resolution:
        """Keep the highest-confidence memory."""
        conf_a = self._get_memory_confidence(conflict.memory_id_a)
        conf_b = self._get_memory_confidence(conflict.memory_id_b)

        if conf_a >= conf_b:
            winner, loser = conflict.memory_id_a, conflict.memory_id_b
        else:
            winner, loser = conflict.memory_id_b, conflict.memory_id_a

        return Resolution(
            conflict=conflict,
            strategy="confidence",
            winner_id=winner,
            loser_id=loser,
        )

    def _resolve_keep_both(self, conflict: Conflict) -> Resolution:
        """Keep both memories with conflict metadata."""
        return Resolution(
            conflict=conflict,
            strategy="keep_both",
            winner_id=None,
            loser_id=None,
        )

    def _resolve_merge(self, conflict: Conflict) -> Resolution:
        """Merge both memories into one."""
        merged = f"[merged] {conflict.content_a[:150]} | {conflict.content_b[:150]}"
        return Resolution(
            conflict=conflict,
            strategy="merge",
            winner_id=conflict.memory_id_a,
            loser_id=conflict.memory_id_b,
            merged_content=merged,
        )

    def _resolve_ask_user(self, conflict: Conflict) -> Resolution:
        """Flag for human review."""
        return Resolution(
            conflict=conflict,
            strategy="ask_user",
            winner_id=None,
            loser_id=None,
        )

    def _get_memory_timestamp(self, memory_id: str) -> float:
        """Get the timestamp of a memory."""
        if self._mm is None:
            return 0.0
        try:
            rec = self._mm._store.get(memory_id)
            return rec.updated_at if rec else 0.0
        except Exception:
            return 0.0

    def _get_memory_confidence(self, memory_id: str) -> float:
        """Get the confidence of a memory."""
        if self._mm is None:
            return 0.0
        try:
            rec = self._mm._store.get(memory_id)
            return rec.confidence if rec else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _get_content(mem: Any) -> str:
        if hasattr(mem, "content"):
            return str(mem.content)
        if hasattr(mem, "record"):
            return str(mem.record.content)
        return str(mem)

    @staticmethod
    def _get_id(mem: Any) -> str:
        if hasattr(mem, "memory_id"):
            return str(mem.memory_id)
        if hasattr(mem, "record"):
            return str(mem.record.memory_id)
        return str(id(mem))

    @staticmethod
    def _get_timestamp(mem: Any) -> float:
        if hasattr(mem, "updated_at"):
            return float(mem.updated_at)
        if hasattr(mem, "record"):
            return float(mem.record.updated_at)
        return 0.0

    def stats(self) -> dict[str, Any]:
        """Return conflict resolver statistics."""
        return {
            "conflicts_detected": self._conflict_count,
            "conflicts_resolved": self._resolution_count,
        }
