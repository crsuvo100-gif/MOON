"""Memory lifecycle manager -- promotion, decay, archival, and deletion.

Professional AI assistants manage memory lifecycle actively:

1. Promotion: Important short-term memories get promoted to long-term
2. Decay: Unused memories lose importance over time (Ebbinghaus curve)
3. Archival: Old but potentially useful memories get archived
4. Deletion: Useless or harmful memories get purged
5. Consolidation: Related memories get merged into coherent chunks

The lifecycle manager runs periodically to keep the memory store healthy.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger
from app.memory.record import Importance, Scope

logger = get_logger(__name__)


@dataclass
class LifecycleAction:
    """A single lifecycle action taken on a memory."""
    memory_id: str
    action: str  # "promote", "decay", "archive", "delete", "consolidate"
    reason: str
    old_state: str = ""
    new_state: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "action": self.action,
            "reason": self.reason,
            "old_state": self.old_state,
            "new_state": self.new_state,
            "timestamp": self.timestamp,
        }


@dataclass
class LifecycleReport:
    """A report of lifecycle actions taken."""
    actions: list[LifecycleAction] = field(default_factory=list)
    promoted: int = 0
    decayed: int = 0
    archived: int = 0
    deleted: int = 0
    consolidated: int = 0
    total_processed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [a.to_dict() for a in self.actions],
            "promoted": self.promoted,
            "decayed": self.decayed,
            "archived": self.archived,
            "deleted": self.deleted,
            "consolidated": self.consolidated,
            "total_processed": self.total_processed,
        }


class LifecycleManager:
    """Manages the lifecycle of memories.

    Usage:
        mgr = LifecycleManager(memory_manager)
        report = mgr.run_full_lifecycle()
        report = mgr.promote_candidates()
        report = mgr.decay_unused(max_age_days=30)
    """

    # Configuration
    PROMOTE_ACCESS_THRESHOLD = 5       # Access count to promote
    PROMOTE_CONFIDENCE_THRESHOLD = 0.7  # Confidence to promote
    DECAY_HALF_LIFE_DAYS = 7.0          # Days for importance to halve
    ARCHIVE_AGE_DAYS = 90.0             # Days before archival
    DELETE_AGE_DAYS = 365.0             # Days before deletion
    DELETE_MIN_IMPORTANCE = 0.1         # Don't delete above this importance

    def __init__(self, memory_manager=None) -> None:
        self._mm = memory_manager
        self._total_actions = 0

    def run_full_lifecycle(self) -> LifecycleReport:
        """Run all lifecycle stages in order."""
        report = LifecycleReport()

        # Stage 1: Promote candidates
        promote_report = self.promote_candidates()
        report.actions.extend(promote_report.actions)
        report.promoted = promote_report.promoted

        # Stage 2: Decay unused memories
        decay_report = self.decay_unused()
        report.actions.extend(decay_report.actions)
        report.decayed = decay_report.decayed

        # Stage 3: Archive old memories
        archive_report = self.archive_old()
        report.actions.extend(archive_report.actions)
        report.archived = archive_report.archived

        # Stage 4: Delete useless memories
        delete_report = self.delete_useless()
        report.actions.extend(delete_report.actions)
        report.deleted = delete_report.deleted

        # Stage 5: Consolidate related memories
        consolidate_report = self.consolidate_related()
        report.actions.extend(consolidate_report.actions)
        report.consolidated = consolidate_report.consolidated

        report.total_processed = len(report.actions)
        self._total_actions += report.total_processed
        return report

    def promote_candidates(self) -> LifecycleReport:
        """Promote short-term memories to long-term based on access and confidence."""
        report = LifecycleReport()
        if self._mm is None:
            return report

        try:
            # Get all short-term memories
            results = self._mm.search("", top_k=200)
        except Exception as exc:
            logger.debug("Promotion retrieval failed: %s", exc)
            return report

        for r in results:
            mem_id = self._get_id(r)
            rec = self._get_record(mem_id)
            if rec is None:
                continue

            # Check promotion criteria
            access_count = getattr(rec, "access_count", 0)
            confidence = getattr(rec, "confidence", 0.0)
            importance = getattr(rec, "importance", Importance.MEDIUM)

            if (access_count >= self.PROMOTE_ACCESS_THRESHOLD
                    and confidence >= self.PROMOTE_CONFIDENCE_THRESHOLD
                    and importance in (Importance.LOW, Importance.MEDIUM)):
                # Promote to higher importance
                new_importance = Importance.HIGH if importance is Importance.MEDIUM else Importance.MEDIUM
                try:
                    self._mm._store.update(mem_id, importance=new_importance)
                    action = LifecycleAction(
                        memory_id=mem_id,
                        action="promote",
                        reason=f"access_count={access_count}, confidence={confidence:.2f}",
                        old_state=str(importance),
                        new_state=str(new_importance),
                    )
                    report.actions.append(action)
                    report.promoted += 1
                except Exception as exc:
                    logger.debug("Failed to promote %s: %s", mem_id, exc)

        return report

    def decay_unused(self, max_age_days: float = 30.0) -> LifecycleReport:
        """Decay importance of unused memories over time."""
        report = LifecycleReport()
        if self._mm is None:
            return report

        try:
            results = self._mm.search("", top_k=200)
        except Exception as exc:
            logger.debug("Decay retrieval failed: %s", exc)
            return report

        now = time.time()
        for r in results:
            mem_id = self._get_id(r)
            rec = self._get_record(mem_id)
            if rec is None:
                continue

            updated = getattr(rec, "updated_at", 0.0)
            age_days = (now - updated) / 86400.0 if updated else 0.0

            if age_days > max_age_days:
                # Apply decay
                decay_factor = 0.5 ** (age_days / (max_age_days * 2))
                old_confidence = getattr(rec, "confidence", 0.5)
                new_confidence = old_confidence * decay_factor

                try:
                    self._mm._store.update(mem_id, confidence=new_confidence)
                    action = LifecycleAction(
                        memory_id=mem_id,
                        action="decay",
                        reason=f"age={age_days:.1f} days, decay_factor={decay_factor:.3f}",
                        old_state=f"confidence={old_confidence:.3f}",
                        new_state=f"confidence={new_confidence:.3f}",
                    )
                    report.actions.append(action)
                    report.decayed += 1
                except Exception as exc:
                    logger.debug("Failed to decay %s: %s", mem_id, exc)

        return report

    def archive_old(self) -> LifecycleReport:
        """Archive memories that are old but still potentially useful."""
        report = LifecycleReport()
        if self._mm is None:
            return report

        try:
            results = self._mm.search("", top_k=200)
        except Exception as exc:
            logger.debug("Archive retrieval failed: %s", exc)
            return report

        now = time.time()
        for r in results:
            mem_id = self._get_id(r)
            rec = self._get_record(mem_id)
            if rec is None:
                continue

            created = getattr(rec, "created_at", 0.0)
            age_days = (now - created) / 86400.0 if created else 0.0
            importance = getattr(rec, "importance", Importance.MEDIUM)

            if age_days > self.ARCHIVE_AGE_DAYS and importance in (Importance.LOW, Importance.MEDIUM):
                # Add archive tag
                tags = list(getattr(rec, "tags", []))
                if "archived" not in tags:
                    tags.append("archived")
                    try:
                        self._mm._store.update(mem_id, tags=tags)
                        action = LifecycleAction(
                            memory_id=mem_id,
                            action="archive",
                            reason=f"age={age_days:.1f} days",
                            old_state="active",
                            new_state="archived",
                        )
                        report.actions.append(action)
                        report.archived += 1
                    except Exception as exc:
                        logger.debug("Failed to archive %s: %s", mem_id, exc)

        return report

    def delete_useless(self) -> LifecycleReport:
        """Delete memories that are old, unimportant, and unused."""
        report = LifecycleReport()
        if self._mm is None:
            return report

        try:
            results = self._mm.search("", top_k=200)
        except Exception as exc:
            logger.debug("Delete retrieval failed: %s", exc)
            return report

        now = time.time()
        for r in results:
            mem_id = self._get_id(r)
            rec = self._get_record(mem_id)
            if rec is None:
                continue

            created = getattr(rec, "created_at", 0.0)
            age_days = (now - created) / 86400.0 if created else 0.0
            importance = getattr(rec, "importance", Importance.MEDIUM)
            access_count = getattr(rec, "access_count", 0)

            # Only delete if old, unimportant, and unused
            if (age_days > self.DELETE_AGE_DAYS
                    and importance is Importance.LOW
                    and access_count == 0):
                try:
                    self._mm._store.delete(mem_id)
                    action = LifecycleAction(
                        memory_id=mem_id,
                        action="delete",
                        reason=f"age={age_days:.1f} days, importance=LOW, access_count=0",
                        old_state="active",
                        new_state="deleted",
                    )
                    report.actions.append(action)
                    report.deleted += 1
                except Exception as exc:
                    logger.debug("Failed to delete %s: %s", mem_id, exc)

        return report

    def consolidate_related(self) -> LifecycleReport:
        """Consolidate related memories into coherent chunks."""
        report = LifecycleReport()
        if self._mm is None:
            return report

        try:
            results = self._mm.search("", top_k=100)
        except Exception as exc:
            logger.debug("Consolidation retrieval failed: %s", exc)
            return report

        # Group memories by tag overlap
        groups: dict[str, list[str]] = {}
        for r in results:
            mem_id = self._get_id(r)
            rec = self._get_record(mem_id)
            if rec is None:
                continue
            tags = getattr(rec, "tags", [])
            for tag in tags:
                if tag not in groups:
                    groups[tag] = []
                groups[tag].append(mem_id)

        # Consolidate groups with 3+ memories
        for tag, mem_ids in groups.items():
            if len(mem_ids) >= 3:
                # Mark as consolidated
                for mem_id in mem_ids:
                    rec = self._get_record(mem_id)
                    if rec:
                        tags = list(getattr(rec, "tags", []))
                        if "consolidated" not in tags:
                            tags.append("consolidated")
                            try:
                                self._mm._store.update(mem_id, tags=tags)
                                action = LifecycleAction(
                                    memory_id=mem_id,
                                    action="consolidate",
                                    reason=f"part of group '{tag}' ({len(mem_ids)} memories)",
                                    old_state="independent",
                                    new_state=f"consolidated:{tag}",
                                )
                                report.actions.append(action)
                                report.consolidated += 1
                            except Exception as exc:
                                logger.debug("Failed to consolidate %s: %s", mem_id, exc)

        return report

    def _get_record(self, memory_id: str) -> Any:
        """Get a memory record by ID."""
        if self._mm is None:
            return None
        try:
            return self._mm._store.get(memory_id)
        except Exception:
            return None

    @staticmethod
    def _get_id(mem: Any) -> str:
        if hasattr(mem, "memory_id"):
            return str(mem.memory_id)
        if hasattr(mem, "record"):
            return str(mem.record.memory_id)
        return str(id(mem))

    def stats(self) -> dict[str, Any]:
        """Return lifecycle manager statistics."""
        return {
            "total_actions": self._total_actions,
            "promote_threshold": self.PROMOTE_ACCESS_THRESHOLD,
            "decay_half_life_days": self.DECAY_HALF_LIFE_DAYS,
            "archive_age_days": self.ARCHIVE_AGE_DAYS,
            "delete_age_days": self.DELETE_AGE_DAYS,
        }
