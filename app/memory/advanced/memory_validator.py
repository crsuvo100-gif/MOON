"""Memory validator -- validate memory consistency and quality.

Professional AI assistants need to ensure their memories are consistent,
high-quality, and free of contradictions. This module:

1. Detects contradictions between memories (A says X, B says not-X).
2. Identifies low-quality memories (too short, too vague, duplicates).
3. Checks temporal consistency (memories with impossible time ordering).
4. Validates memory completeness (missing tags, missing metadata).
5. Scores overall memory health.

Usage:
    validator = MemoryValidator(memory_manager)
    report = await validator.validate_all()
    issues = report.issues
    score = report.health_score
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationIssue:
    """A single validation issue found in memory."""
    issue_type: str       # "contradiction", "low_quality", "temporal", "incomplete", "duplicate"
    severity: str         # "low", "medium", "high", "critical"
    memory_id: str
    description: str
    related_memory_id: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "memory_id": self.memory_id,
            "description": self.description,
            "related_memory_id": self.related_memory_id,
            "suggestion": self.suggestion,
        }


@dataclass
class ValidationReport:
    """Complete validation report."""
    issues: list[ValidationIssue] = field(default_factory=list)
    total_memories: int = 0
    checked_at: float = field(default_factory=time.time)

    @property
    def health_score(self) -> float:
        """Calculate health score (0.0-1.0, higher is better)."""
        if self.total_memories == 0:
            return 1.0
        # Weight issues by severity
        weights = {"low": 0.05, "medium": 0.1, "high": 0.2, "critical": 0.3}
        total_penalty = sum(weights.get(i.severity, 0.1) for i in self.issues)
        return max(0.0, 1.0 - total_penalty / self.total_memories)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def issues_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.issue_type] = counts.get(issue.issue_type, 0) + 1
        return counts

    @property
    def issues_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.severity] = counts.get(issue.severity, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "health_score": round(self.health_score, 4),
            "issue_count": self.issue_count,
            "total_memories": self.total_memories,
            "issues_by_type": self.issues_by_type,
            "issues_by_severity": self.issues_by_severity,
            "issues": [i.to_dict() for i in self.issues],
            "checked_at": self.checked_at,
        }


class MemoryValidator:
    """Validates memory consistency and quality.

    Usage:
        validator = MemoryValidator(memory_manager)
        report = await validator.validate_all()
        if report.health_score < 0.8:
            print("Memory health is poor!")
    """

    # Words that indicate negation/contradiction
    NEGATION_WORDS = {"not", "no", "never", "none", "cannot", "can't", "won't", "don't", "doesn't", "isn't", "aren't", "wasn't", "weren't"}

    # Vague words that indicate low-quality content
    VAGUE_WORDS = {"thing", "stuff", "something", "anything", "everything", "nothing", "somehow", "somewhat", "maybe", "perhaps", "probably"}

    def __init__(
        self,
        memory_manager=None,
        min_content_length: int = 10,
        max_duplicate_similarity: float = 0.9,
    ) -> None:
        self._mm = memory_manager
        self._min_content_length = min_content_length
        self._max_duplicate_similarity = max_duplicate_similarity

    async def validate_all(self) -> ValidationReport:
        """Run all validation checks and return a comprehensive report."""
        report = ValidationReport()

        # Gather all memories
        memories = await self._gather_memories()
        report.total_memories = len(memories)

        if not memories:
            return report

        # Run validation checks
        report.issues.extend(self._check_contradictions(memories))
        report.issues.extend(self._check_low_quality(memories))
        report.issues.extend(self._check_temporal_consistency(memories))
        report.issues.extend(self._check_completeness(memories))
        report.issues.extend(self._check_duplicates(memories))

        logger.info(
            "Memory validation: %d issues found (health: %.2f)",
            report.issue_count,
            report.health_score,
        )
        return report

    async def _gather_memories(self) -> list[dict[str, Any]]:
        """Gather all memories with their content and metadata."""
        memories: list[dict[str, Any]] = []
        if self._mm is None:
            return memories

        try:
            if hasattr(self._mm, '_ltm'):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    entries = loop.run_until_complete(self._mm._ltm.all())
                except RuntimeError:
                    entries = []
                for entry in entries:
                    inner = getattr(entry, 'entry', entry)
                    memories.append({
                        "id": entry.id,
                        "content": entry.content,
                        "tags": getattr(inner, 'tags', []),
                        "created_at": getattr(inner, 'created_at', 0),
                        "importance": getattr(entry, 'importance', 0.5),
                        "source": "ltm",
                    })
        except Exception as exc:
            logger.debug("Gather memories failed: %s", exc)

        return memories

    def _check_contradictions(self, memories: list[dict[str, Any]]) -> list[ValidationIssue]:
        """Detect potential contradictions between memories.

        Looks for pairs where one contains a negation word and the other
        doesn't, but they share significant keyword overlap.
        """
        issues: list[ValidationIssue] = []
        for i, mem_a in enumerate(memories):
            words_a = set(mem_a["content"].lower().split())
            has_neg_a = bool(words_a & self.NEGATION_WORDS)

            for mem_b in memories[i+1:]:
                words_b = set(mem_b["content"].lower().split())
                has_neg_b = bool(words_b & self.NEGATION_WORDS)

                # If one has negation and the other doesn't, check keyword overlap
                if has_neg_a != has_neg_b:
                    overlap = words_a & words_b
                    union = words_a | words_b
                    similarity = len(overlap) / max(len(union), 1)
                    if similarity > 0.5:
                        issues.append(ValidationIssue(
                            issue_type="contradiction",
                            severity="high",
                            memory_id=mem_a["id"],
                            description=f"Potential contradiction: '{mem_a['content'][:60]}' vs '{mem_b['content'][:60]}'",
                            related_memory_id=mem_b["id"],
                            suggestion="Review both memories and resolve the contradiction",
                        ))
        return issues

    def _check_low_quality(self, memories: list[dict[str, Any]]) -> list[ValidationIssue]:
        """Identify low-quality memories (too short, too vague)."""
        issues: list[ValidationIssue] = []
        for mem in memories:
            content = mem["content"]
            words = content.lower().split()

            # Too short
            if len(content) < self._min_content_length:
                issues.append(ValidationIssue(
                    issue_type="low_quality",
                    severity="medium",
                    memory_id=mem["id"],
                    description=f"Memory too short ({len(content)} chars): '{content[:50]}'",
                    suggestion="Expand with more context or detail",
                ))

            # Too vague
            vague_count = sum(1 for w in words if w in self.VAGUE_WORDS)
            if vague_count >= 2:
                issues.append(ValidationIssue(
                    issue_type="low_quality",
                    severity="low",
                    memory_id=mem["id"],
                    description=f"Memory contains vague language: '{content[:50]}'",
                    suggestion="Replace vague terms with specific details",
                ))

        return issues

    def _check_temporal_consistency(self, memories: list[dict[str, Any]]) -> list[ValidationIssue]:
        """Check for temporally impossible memory orderings."""
        issues: list[ValidationIssue] = []
        now = time.time()

        for mem in memories:
            created = mem.get("created_at", 0)
            if created > now + 60:  # Allow 1 minute clock skew
                issues.append(ValidationIssue(
                    issue_type="temporal",
                    severity="medium",
                    memory_id=mem["id"],
                    description=f"Memory has future timestamp: {created}",
                    suggestion="Check system clock or memory creation logic",
                ))

        return issues

    def _check_completeness(self, memories: list[dict[str, Any]]) -> list[ValidationIssue]:
        """Check for missing tags, metadata, or other completeness issues."""
        issues: list[ValidationIssue] = []
        for mem in memories:
            if not mem.get("tags"):
                issues.append(ValidationIssue(
                    issue_type="incomplete",
                    severity="low",
                    memory_id=mem["id"],
                    description=f"Memory has no tags: '{mem['content'][:50]}'",
                    suggestion="Add relevant tags for better organization",
                ))

        return issues

    def _check_duplicates(self, memories: list[dict[str, Any]]) -> list[ValidationIssue]:
        """Find duplicate or near-duplicate memories."""
        issues: list[ValidationIssue] = []
        for i, mem_a in enumerate(memories):
            words_a = set(mem_a["content"].lower().split())
            for mem_b in memories[i+1:]:
                words_b = set(mem_b["content"].lower().split())
                overlap = words_a & words_b
                union = words_a | words_b
                similarity = len(overlap) / max(len(union), 1)
                if similarity >= self._max_duplicate_similarity:
                    issues.append(ValidationIssue(
                        issue_type="duplicate",
                        severity="medium",
                        memory_id=mem_a["id"],
                        description=f"Near-duplicate of {mem_b['id']}: '{mem_a['content'][:50]}'",
                        related_memory_id=mem_b["id"],
                        suggestion="Merge or remove duplicate memory",
                    ))
        return issues

    def stats(self) -> dict[str, Any]:
        """Return validator statistics."""
        return {
            "min_content_length": self._min_content_length,
            "max_duplicate_similarity": self._max_duplicate_similarity,
        }
