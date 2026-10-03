"""lifecycle.py — agent lifecycle management with state machine.

Professional AI agents have well-defined lifecycle states (idle, planning,
executing, waiting, learning, terminated) with valid transitions. This
module provides a lifecycle manager that tracks agent state, enforces
valid transitions, and provides hooks for state change events.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    CREATED = "created"
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING = "waiting"
    LEARNING = "learning"
    REVIEWING = "reviewing"
    TERMINATED = "terminated"
    ERROR = "error"


# Valid state transitions
_VALID_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.CREATED: {AgentState.IDLE, AgentState.TERMINATED},
    AgentState.IDLE: {AgentState.PLANNING, AgentState.EXECUTING, AgentState.LEARNING, AgentState.TERMINATED},
    AgentState.PLANNING: {AgentState.EXECUTING, AgentState.WAITING, AgentState.IDLE, AgentState.ERROR},
    AgentState.EXECUTING: {AgentState.WAITING, AgentState.REVIEWING, AgentState.IDLE, AgentState.ERROR, AgentState.TERMINATED},
    AgentState.WAITING: {AgentState.EXECUTING, AgentState.IDLE, AgentState.ERROR},
    AgentState.LEARNING: {AgentState.IDLE, AgentState.REVIEWING, AgentState.ERROR},
    AgentState.REVIEWING: {AgentState.IDLE, AgentState.EXECUTING, AgentState.LEARNING, AgentState.ERROR},
    AgentState.ERROR: {AgentState.IDLE, AgentState.PLANNING, AgentState.TERMINATED},
    AgentState.TERMINATED: set(),
}


@dataclass
class StateTransition:
    from_state: AgentState
    to_state: AgentState
    timestamp: float
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LifecycleEvent:
    event_type: str  # "state_change", "error", "timeout", "retry"
    agent_id: str
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)


class AgentLifecycle:
    """Manages agent lifecycle with state machine enforcement.

    Tracks current state, enforces valid transitions, records history,
    and provides hooks for state change events. Supports timeouts per
    state and automatic error recovery.
    """

    def __init__(
        self,
        agent_id: str,
        *,
        state_timeout: float = 300.0,
        max_retries: int = 3,
        on_state_change: Callable[[StateTransition], None] | None = None,
        on_event: Callable[[LifecycleEvent], None] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self._state = AgentState.CREATED
        self._state_timeout = state_timeout
        self._max_retries = max_retries
        self._on_state_change = on_state_change
        self._on_event = on_event
        self._history: list[StateTransition] = []
        self._events: list[LifecycleEvent] = []
        self._state_start_time = time.time()
        self._retry_count = 0
        self._lock = asyncio.Lock()
        self._state_data: dict[str, Any] = {}

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def state_duration(self) -> float:
        return time.time() - self._state_start_time

    @property
    def is_active(self) -> bool:
        return self._state not in (AgentState.TERMINATED, AgentState.ERROR)

    @property
    def can_transition(self) -> bool:
        return self._state in _VALID_TRANSITIONS

    async def transition(
        self,
        new_state: AgentState,
        *,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
        force: bool = False,
    ) -> bool:
        async with self._lock:
            if not force and not self._is_valid_transition(new_state):
                logger.warning(
                    "Invalid transition %s -> %s for agent %s",
                    self._state, new_state, self.agent_id,
                )
                return False

            old_state = self._state
            now = time.time()
            transition = StateTransition(
                from_state=old_state,
                to_state=new_state,
                timestamp=now,
                reason=reason,
                metadata=metadata or {},
            )
            self._history.append(transition)
            self._state = new_state
            self._state_start_time = now
            self._state_data = metadata or {}

            if new_state == AgentState.ERROR:
                self._retry_count += 1
            elif new_state == AgentState.IDLE:
                self._retry_count = 0

            if self._on_state_change:
                try:
                    if asyncio.iscoroutinefunction(self._on_state_change):
                        asyncio.create_task(self._on_state_change(transition))
                    else:
                        self._on_state_change(transition)
                except Exception as exc:
                    logger.warning("State change callback error: %s", exc)

            logger.info(
                "Agent %s: %s -> %s (%s)",
                self.agent_id, old_state.value, new_state.value, reason,
            )
            return True

    def _is_valid_transition(self, new_state: AgentState) -> bool:
        return new_state in _VALID_TRANSITIONS.get(self._state, set())

    async def check_timeout(self) -> bool:
        """Check if current state has exceeded timeout. Returns True if timed out."""
        if self._state in (AgentState.TERMINATED, AgentState.IDLE, AgentState.CREATED):
            return False
        if self.state_duration > self._state_timeout:
            await self._emit_event("timeout", {
                "state": self._state.value,
                "duration": self.state_duration,
                "timeout": self._state_timeout,
            })
            return True
        return False

    async def _emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        event = LifecycleEvent(
            event_type=event_type,
            agent_id=self.agent_id,
            timestamp=time.time(),
            data=data,
        )
        self._events.append(event)
        if self._on_event:
            try:
                if asyncio.iscoroutinefunction(self._on_event):
                    asyncio.create_task(self._on_event(event))
                else:
                    self._on_event(event)
            except Exception as exc:
                logger.warning("Event callback error: %s", exc)

    async def record_error(self, error: str, *, recoverable: bool = True) -> None:
        await self._emit_event("error", {
            "error": error,
            "recoverable": recoverable,
            "state": self._state.value,
        })
        if recoverable and self._retry_count < self._max_retries:
            await self.transition(AgentState.ERROR, reason=error)
        else:
            await self.transition(AgentState.TERMINATED, reason=f"unrecoverable: {error}")

    async def record_retry(self) -> None:
        await self._emit_event("retry", {
            "retry_count": self._retry_count,
            "max_retries": self._max_retries,
        })

    def get_history(self) -> list[StateTransition]:
        return list(self._history)

    def get_events(self, *, limit: int = 100) -> list[LifecycleEvent]:
        return self._events[-limit:]

    def stats(self) -> dict[str, Any]:
        state_counts: dict[str, int] = {}
        for t in self._history:
            state_counts[t.to_state.value] = state_counts.get(t.to_state.value, 0) + 1
        return {
            "agent_id": self.agent_id,
            "current_state": self._state.value,
            "state_duration": self.state_duration,
            "total_transitions": len(self._history),
            "total_events": len(self._events),
            "retry_count": self._retry_count,
            "is_active": self.is_active,
            "state_counts": state_counts,
        }
