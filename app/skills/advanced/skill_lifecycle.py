"""Skill lifecycle state machine.

Manages the lifecycle of a skill from discovery through
activation, usage, deprecation, and removal.
"""

from __future__ import annotations

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Any


class SkillState(Enum):
    """Lifecycle states for a skill."""
    DISCOVERED = "discovered"
    VALIDATED = "validated"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
    REMOVED = "removed"


@dataclass
class SkillLifecycleEvent:
    """A lifecycle transition event."""
    skill_name: str
    from_state: SkillState
    to_state: SkillState
    timestamp: float = 0.0
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class SkillLifecycle:
    """Manages skill lifecycle transitions.

    Skills move through states:
    DISCOVERED -> VALIDATED -> ACTIVE -> DEPRECATED -> REMOVED
                                    -> DISABLED -> ACTIVE
    """

    # Valid transitions
    _valid_transitions: dict[SkillState, set[SkillState]] = {
        SkillState.DISCOVERED: {SkillState.VALIDATED, SkillState.REMOVED},
        SkillState.VALIDATED: {SkillState.ACTIVE, SkillState.DISABLED, SkillState.REMOVED},
        SkillState.ACTIVE: {SkillState.DEPRECATED, SkillState.DISABLED, SkillState.REMOVED},
        SkillState.DEPRECATED: {SkillState.ACTIVE, SkillState.DISABLED, SkillState.REMOVED},
        SkillState.DISABLED: {SkillState.ACTIVE, SkillState.REMOVED},
        SkillState.REMOVED: set(),
    }

    def __init__(self):
        self._states: dict[str, SkillState] = {}
        self._events: list[SkillLifecycleEvent] = []
        self._skill_metadata: dict[str, dict[str, Any]] = {}

    def register(self, skill_name: str, metadata: dict[str, Any] | None = None) -> None:
        """Register a new skill in DISCOVERED state."""
        if skill_name not in self._states:
            self._states[skill_name] = SkillState.DISCOVERED
            self._skill_metadata[skill_name] = metadata or {}

    def transition(
        self,
        skill_name: str,
        new_state: SkillState,
        reason: str = "",
    ) -> bool:
        """Transition a skill to a new state.

        Returns:
            True if the transition was valid and applied
        """
        if skill_name not in self._states:
            return False

        current = self._states[skill_name]
        if new_state not in self._valid_transitions.get(current, set()):
            return False

        self._states[skill_name] = new_state
        self._events.append(SkillLifecycleEvent(
            skill_name=skill_name,
            from_state=current,
            to_state=new_state,
            timestamp=time.time(),
            reason=reason,
        ))
        return True

    def get_state(self, skill_name: str) -> SkillState | None:
        """Get the current state of a skill."""
        return self._states.get(skill_name)

    def is_active(self, skill_name: str) -> bool:
        """Check if a skill is active."""
        return self._states.get(skill_name) == SkillState.ACTIVE

    def is_usable(self, skill_name: str) -> bool:
        """Check if a skill is usable (active or deprecated)."""
        state = self._states.get(skill_name)
        return state in (SkillState.ACTIVE, SkillState.DEPRECATED)

    def get_active_skills(self) -> list[str]:
        """Get all active skill names."""
        return [name for name, state in self._states.items() if state == SkillState.ACTIVE]

    def get_all_states(self) -> dict[str, SkillState]:
        """Get all skill states."""
        return dict(self._states)

    def get_events(self, skill_name: str | None = None) -> list[SkillLifecycleEvent]:
        """Get lifecycle events, optionally filtered by skill name."""
        if skill_name:
            return [e for e in self._events if e.skill_name == skill_name]
        return list(self._events)

    def get_metadata(self, skill_name: str) -> dict[str, Any]:
        """Get metadata for a skill."""
        return self._skill_metadata.get(skill_name, {})

    def set_metadata(self, skill_name: str, metadata: dict[str, Any]) -> None:
        """Set metadata for a skill."""
        self._skill_metadata[skill_name] = metadata

    def can_transition(self, skill_name: str, new_state: SkillState) -> bool:
        """Check if a transition is valid."""
        current = self._states.get(skill_name)
        if current is None:
            return False
        return new_state in self._valid_transitions.get(current, set())
