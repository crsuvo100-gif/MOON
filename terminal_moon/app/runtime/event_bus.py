"""
EventBus — internal pub/sub. Bridges to terminal_interface's _EVENTS ring buffer.
"""
from __future__ import annotations

import asyncio
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("moontm.eventbus")


class EventType(Enum):
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    AGENT_SELECTED = "agent_selected"
    AGENT_STARTED = "agent_started"
    TOOL_SELECTED = "tool_selected"
    TOOL_COMPLETED = "tool_completed"
    AGENT_COMPLETED = "agent_completed"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_FAILED = "verification_failed"
    MEMORY_UPDATED = "memory_updated"
    SKILL_UPDATED = "skill_updated"
    AGENT_CREATED = "agent_created"
    AGENT_TEST_FAILED = "agent_test_failed"
    AGENT_APPROVED = "agent_approved"
    AGENT_REJECTED = "agent_rejected"
    ROLLBACK_STARTED = "rollback_started"
    ROLLBACK_COMPLETED = "rollback_completed"
    ERROR = "error"
    THINKING = "thinking"
    LOCK = "lock"
    TASK_COMPLETED = "task_completed"


@dataclass
class Event:
    type: EventType
    execution_id: str = ""
    agent_id: str = ""
    detail: str = ""
    payload: dict = field(default_factory=dict)


_BUS: Optional["EventBus"] = None
_BUS_LOCK = asyncio.Lock()  # noqa: F821  (defined below)


def bus() -> "EventBus":
    """Singleton accessor."""
    global _BUS
    if _BUS is None:
        _BUS = EventBus()
    return _BUS


class EventBus:
    """In-process pub/sub. Subscribers receive Event objects."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[Event], None]] = []

    def subscribe(self, fn: Callable[[Event], None]) -> None:
        if fn not in self._subscribers:
            self._subscribers.append(fn)

    def unsubscribe(self, fn: Callable[[Event], None]) -> None:
        if fn in self._subscribers:
            self._subscribers.remove(fn)

    def publish(
        self,
        etype: EventType,
        execution_id: str = "",
        agent_id: str = "",
        detail: str = "",
        payload: Optional[dict] = None,
    ) -> Event:
        ev = Event(type=etype, execution_id=execution_id,
                   agent_id=agent_id, detail=detail,
                   payload=payload or {})
        for fn in self._subscribers:
            try:
                fn(ev)
            except Exception as exc:
                logger.warning("EventBus subscriber error: %s", exc)
        return ev
