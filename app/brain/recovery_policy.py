"""Failure recovery decision policy (spec 36).

When Agent A fails, the Main Brain must CHOOSE what to do rather than blindly
retry (spec 36) and must never retry forever (spec 51). This module owns that
decision so it is explicit, testable, and bounded.

    RETRY_SAME_AGENT | CHANGE_BRAIN | CHANGE_AGENT | SPLIT_TASK | ASK_USER

It is deliberately pure: given the failure context it returns a decision plus a
reason. The orchestrator executes the decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RecoveryAction(str, Enum):
    RETRY_SAME_AGENT = "RETRY_SAME_AGENT"
    CHANGE_BRAIN = "CHANGE_BRAIN"
    CHANGE_AGENT = "CHANGE_AGENT"
    SPLIT_TASK = "SPLIT_TASK"
    ASK_USER = "ASK_USER"
    ABORT = "ABORT"


# Error signatures that tell us WHICH action is appropriate.
_BRAIN_ERRORS = (
    "connecterror", "connection", "timeout", "timed out", "readtimeout",
    "remoteprotocolerror", "server disconnected", "model not found",
    "no such model", "ollama", "econnrefused", "unavailable",
)
_TASK_ERRORS = (
    "validation", "invalid output", "empty response", "could not form",
    "tool", "permission", "unauthor",
)
_SPLITTABLE = (
    "too long", "context length", "context window", "exceeds", "complex",
    "decompose",
)


@dataclass
class FailureContext:
    """Everything the policy needs to decide (spec 36)."""

    agent: str
    task: str
    error: str = ""
    attempt: int = 0                     # attempts already made
    max_attempts: int = 3
    brain_healthy: bool = True
    other_agents: list[str] = field(default_factory=list)
    task_is_composite: bool = False
    high_risk: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"agent": self.agent, "error": self.error, "attempt": self.attempt,
                "max_attempts": self.max_attempts, "brain_healthy": self.brain_healthy,
                "task_is_composite": self.task_is_composite, "high_risk": self.high_risk}


@dataclass
class RecoveryDecision:
    action: RecoveryAction
    reason: str
    target_agent: str = ""
    target_brain: str = ""
    retry_attempt: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action.value, "reason": self.reason,
                "target_agent": self.target_agent, "target_brain": self.target_brain,
                "retry_attempt": self.retry_attempt}


class RecoveryPolicy:
    """Bounded failure-recovery decisions (spec 36 / 51)."""

    def __init__(self, *, max_attempts: int = 3) -> None:
        self._max = max_attempts

    def decide(self, ctx: FailureContext) -> RecoveryDecision:
        err = (ctx.error or "").lower()
        attempts = ctx.attempt
        cap = min(ctx.max_attempts or self._max, self._max)

        # 1. Budget exhausted -> never loop (spec 51). Escalate.
        if attempts >= cap:
            return RecoveryDecision(
                RecoveryAction.ASK_USER,
                f"attempt budget exhausted ({attempts}/{cap}); escalating instead of retrying forever",
            )

        # 2. High-risk work never auto-retries or auto-substitutes (spec 51/35).
        if ctx.high_risk:
            return RecoveryDecision(
                RecoveryAction.ASK_USER,
                "high-risk task failed; explicit operator decision required",
            )

        # 3. Brain-level failure -> change brain, not agent (spec 37).
        if any(sig in err for sig in _BRAIN_ERRORS) or not ctx.brain_healthy:
            return RecoveryDecision(
                RecoveryAction.CHANGE_BRAIN,
                f"brain-level failure ('{ctx.error[:60]}') -> switch brain, keep agent",
                target_agent=ctx.agent, target_brain="strong",
                retry_attempt=attempts + 1,
            )

        # 4. Context/scope failure -> split the task (spec 36).
        if ctx.task_is_composite or any(sig in err for sig in _SPLITTABLE):
            return RecoveryDecision(
                RecoveryAction.SPLIT_TASK,
                "task too large/composite for one pass -> decompose and delegate",
                retry_attempt=attempts + 1,
            )

        # 5. First failure on a task-level error -> retry the same agent once.
        if attempts == 0:
            return RecoveryDecision(
                RecoveryAction.RETRY_SAME_AGENT,
                f"first failure ('{ctx.error[:60]}'); retrying same agent",
                target_agent=ctx.agent, retry_attempt=1,
            )

        # 6. Repeated task-level failure -> change agent (spec 36).
        others = [a for a in ctx.other_agents if a and a != ctx.agent]
        if others:
            return RecoveryDecision(
                RecoveryAction.CHANGE_AGENT,
                f"repeated failure; reassigning to '{others[0]}'",
                target_agent=others[0], retry_attempt=attempts + 1,
            )

        # 7. Nothing left to try.
        return RecoveryDecision(
            RecoveryAction.ASK_USER,
            "no alternative agent available; operator input required",
        )


__all__ = ["RecoveryAction", "FailureContext", "RecoveryDecision", "RecoveryPolicy"]
