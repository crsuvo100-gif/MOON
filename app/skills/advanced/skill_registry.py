"""Advanced skill registry.

Central registry for all skills with metadata, state management,
and fast lookup capabilities.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.skills.advanced.skill_lifecycle import SkillLifecycle, SkillState


@dataclass
class SkillMetadata:
    """Complete metadata for a registered skill."""
    name: str
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    instructions: str = ""
    examples: list[Any] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    output_format: str = ""
    source: str = ""
    format: str = "markdown"
    state: SkillState = SkillState.DISCOVERED
    created_at: float = 0.0
    updated_at: float = 0.0
    use_count: int = 0
    success_count: int = 0
    avg_execution_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class AdvancedSkillRegistry:
    """Central registry for all skills.

    Provides fast lookup, metadata management, and lifecycle
    tracking for all skills in the system.
    """

    def __init__(self):
        self._skills: dict[str, SkillMetadata] = {}
        self._lifecycle = SkillLifecycle()
        self._keyword_index: dict[str, set[str]] = {}
        self._tag_index: dict[str, set[str]] = {}

    def register(self, metadata: SkillMetadata) -> None:
        """Register a skill with full metadata."""
        now = time.time()
        if metadata.created_at == 0.0:
            metadata.created_at = now
        metadata.updated_at = now
        self._skills[metadata.name] = metadata
        self._lifecycle.register(metadata.name, metadata.__dict__)
        self._rebuild_index()

    def unregister(self, name: str) -> bool:
        """Remove a skill from the registry."""
        if name in self._skills:
            del self._skills[name]
            self._rebuild_index()
            return True
        return False

    def get(self, name: str) -> SkillMetadata | None:
        """Get skill metadata by name."""
        return self._skills.get(name)

    def get_all(self) -> dict[str, SkillMetadata]:
        """Get all registered skills."""
        return dict(self._skills)

    def list_names(self) -> list[str]:
        """List all registered skill names."""
        return list(self._skills.keys())

    def find_by_keyword(self, keyword: str) -> list[SkillMetadata]:
        """Find skills by keyword."""
        keyword_lower = keyword.lower()
        names = self._keyword_index.get(keyword_lower, set())
        return [self._skills[n] for n in names if n in self._skills]

    def find_by_tag(self, tag: str) -> list[SkillMetadata]:
        """Find skills by tag."""
        tag_lower = tag.lower()
        names = self._tag_index.get(tag_lower, set())
        return [self._skills[n] for n in names if n in self._skills]

    def search(self, query: str) -> list[SkillMetadata]:
        """Search skills by query string."""
        query_lower = query.lower()
        results: list[SkillMetadata] = []
        for name, meta in self._skills.items():
            if query_lower in name.lower():
                results.append(meta)
                continue
            if query_lower in meta.description.lower():
                results.append(meta)
                continue
            if any(query_lower in k.lower() for k in meta.keywords):
                results.append(meta)
                continue
            if any(query_lower in t.lower() for t in meta.tags):
                results.append(meta)
        return results

    def record_usage(self, name: str, success: bool, execution_time: float) -> None:
        """Record skill usage for analytics."""
        meta = self._skills.get(name)
        if meta:
            meta.use_count += 1
            if success:
                meta.success_count += 1
            # Running average
            meta.avg_execution_time = (
                (meta.avg_execution_time * (meta.use_count - 1) + execution_time)
                / meta.use_count
            )
            meta.updated_at = time.time()

    def get_active_skills(self) -> list[SkillMetadata]:
        """Get all active skills."""
        return [m for m in self._skills.values() if m.state == SkillState.ACTIVE]

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        total = len(self._skills)
        active = sum(1 for m in self._skills.values() if m.state == SkillState.ACTIVE)
        deprecated = sum(1 for m in self._skills.values() if m.state == SkillState.DEPRECATED)
        disabled = sum(1 for m in self._skills.values() if m.state == SkillState.DISABLED)
        total_uses = sum(m.use_count for m in self._skills.values())
        total_success = sum(m.success_count for m in self._skills.values())
        return {
            "total_skills": total,
            "active": active,
            "deprecated": deprecated,
            "disabled": disabled,
            "total_uses": total_uses,
            "overall_success_rate": total_success / total_uses if total_uses > 0 else 0.0,
        }

    def _rebuild_index(self) -> None:
        """Rebuild keyword and tag indexes."""
        self._keyword_index.clear()
        self._tag_index.clear()
        for name, meta in self._skills.items():
            for kw in meta.keywords:
                kw_lower = kw.lower()
                if kw_lower not in self._keyword_index:
                    self._keyword_index[kw_lower] = set()
                self._keyword_index[kw_lower].add(name)
            for tag in meta.tags:
                tag_lower = tag.lower()
                if tag_lower not in self._tag_index:
                    self._tag_index[tag_lower] = set()
                self._tag_index[tag_lower].add(name)
