"""ContextLifecycle — manages the lifecycle of context items.

Every professional AI assistant needs to manage context through its lifecycle:
creation, activation, refresh, staleness detection, and eventual removal.
This module provides that lifecycle management.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class ContextPhase(Enum):
    """Lifecycle phase of a context item."""
    CREATED = "created"         # Just added to context
    ACTIVE = "active"           # Recently used, fresh
    STALE = "stale"             # Not used for a while
    ARCHIVED = "archived"       # Kept for reference but not active
    EXPIRED = "expired"         # Should be removed


@dataclass
class LifecycleEvent:
    """A lifecycle event for a context item."""
    item_id: str
    from_phase: ContextPhase
    to_phase: ContextPhase
    timestamp: float = field(default_factory=time.time)
    reason: str = ""


class ContextLifecycle:
    """Manages the lifecycle of context items.

    Tracks items through their lifecycle phases and provides:
    - Automatic phase transitions based on age and usage
    - Staleness detection
    - Expiration policies
    - Lifecycle event history
    """

    def __init__(
        self,
        *,
        stale_after_seconds: float = 300.0,      # 5 minutes
        expire_after_seconds: float = 3600.0,     # 1 hour
        archive_after_seconds: float = 1800.0,    # 30 minutes
        max_items: int = 100,
    ) -> None:
        self._stale_after = stale_after_seconds
        self._expire_after = expire_after_seconds
        self._archive_after = archive_after_seconds
        self._max_items = max_items
        self._events: list[LifecycleEvent] = []
        self._phase_map: dict[str, ContextPhase] = {}

    def register(self, item_id: str) -> None:
        """Register a new context item in the lifecycle."""
        self._phase_map[item_id] = ContextPhase.CREATED
        self._emit_event(item_id, ContextPhase.CREATED, ContextPhase.CREATED, "registered")

    def activate(self, item_id: str) -> None:
        """Mark an item as active (just used)."""
        old_phase = self._phase_map.get(item_id, ContextPhase.CREATED)
        self._phase_map[item_id] = ContextPhase.ACTIVE
        self._emit_event(item_id, old_phase, ContextPhase.ACTIVE, "activated")

    def get_phase(self, item_id: str) -> ContextPhase:
        """Get the current lifecycle phase of an item."""
        return self._phase_map.get(item_id, ContextPhase.CREATED)

    def update(self, *, current_time: float | None = None, item_ages: dict[str, float] | None = None) -> list[LifecycleEvent]:
        """Update lifecycle phases based on age and usage.

        Args:
            current_time: Current timestamp (defaults to time.time()).
            item_ages: Dict mapping item_id to age in seconds.

        Returns:
            List of lifecycle events that occurred during this update.
        """
        now = current_time or time.time()
        ages = item_ages or {}
        events: list[LifecycleEvent] = []

        for item_id, phase in list(self._phase_map.items()):
            age = ages.get(item_id, 0.0)

            if phase == ContextPhase.CREATED:
                # New items become active immediately
                self._phase_map[item_id] = ContextPhase.ACTIVE
                events.append(LifecycleEvent(item_id, ContextPhase.CREATED, ContextPhase.ACTIVE, reason="activated"))

            elif phase == ContextPhase.ACTIVE:
                if age > self._stale_after:
                    self._phase_map[item_id] = ContextPhase.STALE
                    events.append(LifecycleEvent(item_id, ContextPhase.ACTIVE, ContextPhase.STALE, reason="stale"))

            elif phase == ContextPhase.STALE:
                if age > self._archive_after:
                    self._phase_map[item_id] = ContextPhase.ARCHIVED
                    events.append(LifecycleEvent(item_id, ContextPhase.STALE, ContextPhase.ARCHIVED, reason="archived"))
                elif age < self._stale_after / 2:
                    # Item was refreshed
                    self._phase_map[item_id] = ContextPhase.ACTIVE
                    events.append(LifecycleEvent(item_id, ContextPhase.STALE, ContextPhase.ACTIVE, reason="refreshed"))

            elif phase == ContextPhase.ARCHIVED:
                if age > self._expire_after:
                    self._phase_map[item_id] = ContextPhase.EXPIRED
                    events.append(LifecycleEvent(item_id, ContextPhase.ARCHIVED, ContextPhase.EXPIRED, reason="expired"))

        self._events.extend(events)
        return events

    def get_expired(self) -> list[str]:
        """Get IDs of items that have expired."""
        return [item_id for item_id, phase in self._phase_map.items() if phase == ContextPhase.EXPIRED]

    def get_stale(self) -> list[str]:
        """Get IDs of items that are stale."""
        return [item_id for item_id, phase in self._phase_map.items() if phase == ContextPhase.STALE]

    def get_active(self) -> list[str]:
        """Get IDs of items that are active."""
        return [item_id for item_id, phase in self._phase_map.items() if phase == ContextPhase.ACTIVE]

    def remove(self, item_id: str) -> bool:
        """Remove an item from lifecycle tracking."""
        if item_id in self._phase_map:
            del self._phase_map[item_id]
            return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get lifecycle statistics."""
        stats: dict[str, int] = {phase.value: 0 for phase in ContextPhase}
        for phase in self._phase_map.values():
            stats[phase.value] = stats.get(phase.value, 0) + 1
        return {
            "total_items": len(self._phase_map),
            "by_phase": stats,
            "total_events": len(self._events),
            "recent_events": len([e for e in self._events if now() - e.timestamp < 60]),
        }

    def _emit_event(self, item_id: str, from_phase: ContextPhase, to_phase: ContextPhase, reason: str) -> None:
        """Record a lifecycle event."""
        event = LifecycleEvent(item_id, from_phase, to_phase, reason=reason)
        self._events.append(event)
        if len(self._events) > 1000:
            self._events = self._events[-500:]


def now() -> float:
    """Get current time."""
    return time.time()
