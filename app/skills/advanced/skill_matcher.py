"""Intelligent skill matching with multi-signal scoring.

Matches user tasks to the most relevant skills using keyword overlap,
semantic similarity, tag matching, and historical performance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillMatch:
    """Result of matching a skill to a task."""
    skill_name: str
    score: float  # 0.0 - 1.0
    matched_keywords: list[str] = field(default_factory=list)
    matched_tags: list[str] = field(default_factory=list)
    reason: str = ""


class SkillMatcher:
    """Multi-signal skill matcher.

    Combines keyword overlap, tag matching, and historical performance
    to rank skills for a given task.
    """

    def __init__(self, skills: dict[str, dict[str, Any]] | None = None):
        self._skills = skills or {}
        self._usage_counts: dict[str, int] = {}
        self._success_counts: dict[str, int] = {}

    def register_skill(self, name: str, metadata: dict[str, Any]) -> None:
        """Register a skill with its metadata for matching."""
        self._skills[name] = metadata

    def record_usage(self, name: str, success: bool = True) -> None:
        """Record skill usage for performance-based ranking."""
        self._usage_counts[name] = self._usage_counts.get(name, 0) + 1
        if success:
            self._success_counts[name] = self._success_counts.get(name, 0) + 1

    def match(self, task: str, top_k: int = 5) -> list[SkillMatch]:
        """Find the top-k most relevant skills for a task.

        Scoring:
        - Keyword overlap (40%): how many skill keywords appear in the task
        - Tag match (30%): how many skill tags match task intent
        - Performance bonus (20%): historical success rate
        - Recency bonus (10%): recently used skills get a small boost
        """
        if not self._skills:
            return []

        task_lower = task.lower()
        task_tokens = set(re.findall(r"[a-z0-9_]+", task_lower))

        matches: list[SkillMatch] = []
        for name, meta in self._skills.items():
            keywords = [k.lower() for k in meta.get("keywords", [])]
            tags = [t.lower() for t in meta.get("tags", [])]
            description = meta.get("description", "").lower()

            # Keyword overlap
            matched_kw = [kw for kw in keywords if kw in task_lower]
            kw_score = len(matched_kw) / max(len(keywords), 1) if keywords else 0.0

            # Tag match
            matched_tags = [t for t in tags if t in task_lower]
            tag_score = len(matched_tags) / max(len(tags), 1) if tags else 0.0

            # Description overlap
            desc_tokens = set(re.findall(r"[a-z0-9_]+", description))
            desc_overlap = len(task_tokens & desc_tokens) / max(len(desc_tokens), 1) if desc_tokens else 0.0

            # Performance bonus
            usage = self._usage_counts.get(name, 0)
            success = self._success_counts.get(name, 0)
            perf_score = (success / usage) if usage > 0 else 0.5

            # Combined score
            score = (
                0.40 * kw_score
                + 0.30 * tag_score
                + 0.20 * desc_overlap
                + 0.10 * perf_score
            )

            if score > 0.05:  # minimum threshold
                reason = f"kw={len(matched_kw)} tag={len(matched_tags)} perf={perf_score:.2f}"
                matches.append(SkillMatch(
                    skill_name=name,
                    score=round(score, 4),
                    matched_keywords=matched_kw,
                    matched_tags=matched_tags,
                    reason=reason,
                ))

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:top_k]

    def get_best_match(self, task: str) -> SkillMatch | None:
        """Get the single best matching skill for a task."""
        matches = self.match(task, top_k=1)
        return matches[0] if matches else None

    def get_skill_names(self) -> list[str]:
        """Get all registered skill names."""
        return list(self._skills.keys())
