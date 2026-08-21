"""EventBus (spec sections 3, 41).

An internal event system for the runtime. Events are published to the existing
terminal_interface event ring buffer (via _emit_event) so the HUD EVENTS
timeline and /api/events already surface them -- no duplicate mechanism. The
bus also keeps a small in-process subscriber list for in-process listeners
(e.g. the future ws/events channel).

Event names follow spec 41 (TASK_CREATED, AGENT_SELECTED, VERIFICATION_PASSED,
AGENT_CREATED, ROLLBACK_COMPLETED, ...).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    AGENT_SELECTED = "AGENT_SELECTED"
    AGENT_STARTED = "AGENT_STARTED"
    TOOL_SELECTED = "TOOL_SELECTED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_PASSED = "VERIFICATION_PASSED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    MEMORY_UPDATED = "MEMORY_UPDATED"
    SKILL_UPDATED = "SKILL_UPDATED"
    AGENT_CREATED = "AGENT_CREATED"
    AGENT_TEST_FAILED = "AGENT_TEST_FAILED"
    AGENT_APPROVED = "AGENT_APPROVED"
    AGENT_REJECTED = "AGENT_REJECTED"
    ROLLBACK_STARTED = "ROLLBACK_STARTED"
    ROLLBACK_COMPLETED = "ROLLBACK_COMPLETED"
    ERROR = "ERROR"


@dataclass
class Event:
    type: str
    execution_id: str = ""
    agent_id: str = ""
    detail: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Callable[[Event], None]] = []

    def subscribe(self, fn: Callable[[Event], None]) -> None:
        self._subscribers.append(fn)

    def publish(self, etype: str | EventType, *, execution_id: str = "",
                agent_id: str = "", detail: str = "", payload: dict | None = None) -> Event:
        name = etype.value if isinstance(etype, EventType) else str(etype)
        ev = Event(type=name, execution_id=execution_id, agent_id=agent_id,
                   detail=detail, payload=payload or {})
        # Surface to the existing event ring buffer (HUD + /api/events).
        try:
            from app.terminal_interface import _emit_event
            _emit_event("event", f"{name}: {detail}")
        except Exception:  # noqa: BLE001
            pass
        # Notify in-process listeners.
        for fn in self._subscribers:
            try:
                fn(ev)
            except Exception:  # noqa: BLE001
                pass
        return ev


# Process-wide singleton (spec 3 "internal event system").
_BUS = EventBus()


def bus() -> EventBus:
    return _BUS
