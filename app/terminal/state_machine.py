"""Execution state machine for MOON terminal.

States:
    IDLE → PLANNING → WAITING_PERMISSION → STARTING → RUNNING → VERIFYING → COMPLETED
                                                        ↓           ↓
                                                    RECOVERING → FAILED
                                                        ↓
                                                    CANCELLED
                                                        ↓
                                                    TIMED_OUT
                                                        ↓
                                                    DENIED

Every transition is validated. The UI subscribes to state-change events.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


class ExecutionState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    WAITING_PERMISSION = "waiting_permission"
    STARTING = "starting"
    RUNNING = "running"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    DENIED = "denied"


# Valid transitions: current_state → {allowed_next_states}
_VALID_TRANSITIONS: Dict[ExecutionState, Set[ExecutionState]] = {
    ExecutionState.IDLE: {
        ExecutionState.PLANNING,
        ExecutionState.STARTING,
        ExecutionState.RUNNING,
    },
    ExecutionState.PLANNING: {
        ExecutionState.WAITING_PERMISSION,
        ExecutionState.STARTING,
        ExecutionState.RUNNING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.WAITING_PERMISSION: {
        ExecutionState.STARTING,
        ExecutionState.DENIED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.STARTING: {
        ExecutionState.RUNNING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.RUNNING: {
        ExecutionState.VERIFYING,
        ExecutionState.RECOVERING,
        ExecutionState.COMPLETED,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
        ExecutionState.TIMED_OUT,
    },
    ExecutionState.VERIFYING: {
        ExecutionState.COMPLETED,
        ExecutionState.RECOVERING,
        ExecutionState.FAILED,
    },
    ExecutionState.RECOVERING: {
        ExecutionState.RUNNING,
        ExecutionState.VERIFYING,
        ExecutionState.COMPLETED,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.COMPLETED: set(),  # terminal
    ExecutionState.FAILED: set(),  # terminal
    ExecutionState.CANCELLED: set(),  # terminal
    ExecutionState.TIMED_OUT: set(),  # terminal
    ExecutionState.DENIED: set(),  # terminal
}


class StateMachine:
    """Tracks execution state and validates transitions."""

    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        self._state = ExecutionState.IDLE
        self._history: List[Dict[str, Any]] = []
        self._listeners: List[Callable[[ExecutionState, ExecutionState], None]] = []
        self._record(ExecutionState.IDLE, "initialized")

    @property
    def state(self) -> ExecutionState:
        return self._state

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def _record(self, new_state: ExecutionState, reason: str = ""):
        entry = {
            "timestamp": time.time(),
            "state": new_state.value,
            "reason": reason,
        }
        self._history.append(entry)

    def add_listener(self, callback: Callable[[ExecutionState, ExecutionState], None]):
        """Register a listener called with (old_state, new_state) on each transition."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[ExecutionState, ExecutionState], None]):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def transition_to(self, new_state: ExecutionState, reason: str = "") -> bool:
        """Attempt a transition. Returns True if valid, False if rejected."""
        if new_state == self._state:
            return True  # idempotent
        allowed = _VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            return False
        old_state = self._state
        self._state = new_state
        self._record(new_state, reason)
        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception:
                pass  # never crash on listener error
        return True

    def can_transition_to(self, new_state: ExecutionState) -> bool:
        return new_state in _VALID_TRANSITIONS.get(self._state, set())

    def is_terminal(self) -> bool:
        return self._state in {
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.TIMED_OUT,
            ExecutionState.DENIED,
        }

    def __repr__(self) -> str:
        return f"StateMachine({self.execution_id}, state={self._state.value})"
