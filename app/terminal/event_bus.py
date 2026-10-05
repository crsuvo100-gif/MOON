"""Typed Event Bus for the terminal UI.

Provides:
- ``Event`` enum with all event names used across the system.
- ``publish(event, payload=None)`` – publish a typed event.
- ``subscribe(event, callback)`` – register a callback for a typed event.
- ``get_bus()`` – backward‑compatible accessor returning the internal singleton.
"""

from __future__ import annotations

import sys
from enum import Enum
from typing import Any, Callable, Dict, List

# Re‑use the same event names as the runtime event system.
class Event(Enum):
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

    # UI‑specific events
    UI_IDLE = "UI_IDLE"
    UI_EXECUTING = "UI_EXECUTING"
    UI_PERMISSION = "UI_PERMISSION"
    UI_VERIFICATION = "UI_VERIFICATION"
    UI_ERROR = "UI_ERROR"
    UI_SUCCESS = "UI_SUCCESS"

# Simple in‑process bus implementation.
class _EventBus:
    def __init__(self) -> None:
        # Store subscribers keyed by Event enum members; also support legacy string events.
        self._subscribers: Dict[Event, List[Callable[[Any], None]]] = {}
        self._legacy_subscribers: Dict[str, List[Callable[[Any], None]]] = {}

    def _resolve_event(self, ev: Event | str) -> Event | str:
        """Return an Event enum if possible, otherwise keep the original string.

        Allows existing code that passes raw string event names to continue working.
        """
        if isinstance(ev, Event):
            return ev
        try:
            return Event(ev)
        except Exception:
            return ev

    def subscribe(self, event: Event | str, callback: Callable[[Any], None]) -> None:
        ev = self._resolve_event(event)
        if isinstance(ev, Event):
            self._subscribers.setdefault(ev, []).append(callback)
        else:
            self._legacy_subscribers.setdefault(ev, []).append(callback)

    def publish(self, event: Event | str, payload: Any = None) -> None:
        ev = self._resolve_event(event)
        # Notify new‑style subscribers
        for cb in self._subscribers.get(ev if isinstance(ev, Event) else None, []):
            try:
                cb(payload)
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(f"EventBus subscriber error for {ev}: {exc}\n")
        # Notify legacy string‑based subscribers
        if not isinstance(ev, Event):
            for cb in self._legacy_subscribers.get(ev, []):
                try:
                    cb(payload)
                except Exception as exc:  # noqa: BLE001
                    sys.stderr.write(f"EventBus subscriber error for {ev}: {exc}\n")

    # Back‑compat alias used by older code
    def emit(self, topic: str, payload: Any = None) -> None:
        """Legacy emit method – forwards to :meth:`publish`.

        Older components call ``bus.emit(event_name, data)`` with a plain string.
        """
        self.publish(topic, payload)

# Singleton instance used by the rest of the code.
_event_bus = _EventBus()

def subscribe(event: Event, callback: Callable[[Any], None]) -> None:
    """Register ``callback`` for ``event``.

    ``callback`` receives the optional ``payload`` passed to :func:`publish`.
    """
    _event_bus.subscribe(event, callback)


def publish(event: Event, payload: Any = None) -> None:
    """Publish ``event`` with optional ``payload``.

    The function forwards to the internal singleton.
    """
    _event_bus.publish(event, payload)


def get_bus() -> _EventBus:
    """Legacy accessor returning the internal bus instance.

    Existing code imports ``get_bus`` from ``app.terminal.event_bus``; this keeps that API
    functional while encouraging the newer typed ``publish``/``subscribe`` helpers.
    """
    return _event_bus
