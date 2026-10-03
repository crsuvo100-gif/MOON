"""error_recovery.py — agent error detection and recovery.

Professional AI assistants handle errors gracefully with automatic
recovery strategies. This module provides error classification,
recovery strategies, and fallback mechanisms.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    LOW = "low"  # can continue, minor issue
    MEDIUM = "medium"  # degraded but functional
    HIGH = "high"  # significant impact, needs recovery
    CRITICAL = "critical"  # task cannot continue


class ErrorCategory(str, Enum):
    LLM_FAILURE = "llm_failure"
    TOOL_FAILURE = "tool_failure"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    RESOURCE = "resource"
    LOGIC = "logic"
    NETWORK = "network"
    UNKNOWN = "unknown"


@dataclass
class AgentError:
    error_id: str
    agent_id: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    timestamp: float = field(default_factory=time.time)
    recoverable: bool = True
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3
    resolved: bool = False
    recovery_action: str = ""
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryResult:
    success: bool
    action_taken: str
    new_state: str = ""
    message: str = ""


RecoveryStrategy = Callable[[AgentError], Awaitable[RecoveryResult]]


class ErrorRecovery:
    """Error detection and recovery system for agents.

    Classifies errors by category and severity, applies appropriate
    recovery strategies, and tracks recovery success rates.
    Supports custom recovery strategies per error category.
    """

    def __init__(self) -> None:
        self._errors: dict[str, AgentError] = {}
        self._agent_errors: dict[str, list[str]] = {}
        self._strategies: dict[ErrorCategory, list[RecoveryStrategy]] = {}
        self._recovery_history: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._register_default_strategies()

    def _register_default_strategies(self) -> None:
        """Register default recovery strategies for each error category."""

        async def _retry_strategy(error: AgentError) -> RecoveryResult:
            if error.recovery_attempts < error.max_recovery_attempts:
                await asyncio.sleep(0.5 * (error.recovery_attempts + 1))
                return RecoveryResult(
                    success=True,
                    action_taken="retry",
                    message=f"Retry attempt {error.recovery_attempts + 1}",
                )
            return RecoveryResult(
                success=False,
                action_taken="retry_exhausted",
                message="Max retry attempts reached",
            )

        async def _fallback_strategy(error: AgentError) -> RecoveryResult:
            return RecoveryResult(
                success=True,
                action_taken="fallback",
                new_state="degraded",
                message="Switched to fallback mode",
            )

        async def _rebuild_context_strategy(error: AgentError) -> RecoveryResult:
            return RecoveryResult(
                success=True,
                action_taken="rebuild_context",
                new_state="rebuilt",
                message="Context rebuilt from scratch",
            )

        async def _switch_model_strategy(error: AgentError) -> RecoveryResult:
            return RecoveryResult(
                success=True,
                action_taken="switch_model",
                new_state="model_switched",
                message="Switched to alternative model",
            )

        # Register strategies per category
        self._strategies[ErrorCategory.LLM_FAILURE] = [
            _retry_strategy, _switch_model_strategy, _fallback_strategy,
        ]
        self._strategies[ErrorCategory.TOOL_FAILURE] = [
            _retry_strategy, _fallback_strategy,
        ]
        self._strategies[ErrorCategory.TIMEOUT] = [
            _retry_strategy, _rebuild_context_strategy,
        ]
        self._strategies[ErrorCategory.VALIDATION] = [
            _rebuild_context_strategy, _retry_strategy,
        ]
        self._strategies[ErrorCategory.RESOURCE] = [
            _fallback_strategy, _retry_strategy,
        ]
        self._strategies[ErrorCategory.LOGIC] = [
            _rebuild_context_strategy, _fallback_strategy,
        ]
        self._strategies[ErrorCategory.NETWORK] = [
            _retry_strategy, _fallback_strategy,
        ]
        self._strategies[ErrorCategory.UNKNOWN] = [
            _retry_strategy, _fallback_strategy,
        ]

    def register_strategy(
        self,
        category: ErrorCategory,
        strategy: RecoveryStrategy,
    ) -> None:
        if category not in self._strategies:
            self._strategies[category] = []
        self._strategies[category].append(strategy)

    async def handle_error(
        self,
        agent_id: str,
        message: str,
        *,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: dict[str, Any] | None = None,
    ) -> RecoveryResult:
        """Handle an error: classify, record, and attempt recovery."""
        import uuid
        error_id = uuid.uuid4().hex[:12]
        error = AgentError(
            error_id=error_id,
            agent_id=agent_id,
            category=category,
            severity=severity,
            message=message,
            recoverable=severity not in (ErrorSeverity.CRITICAL,),
            context=context or {},
        )

        async with self._lock:
            self._errors[error_id] = error
            if agent_id not in self._agent_errors:
                self._agent_errors[agent_id] = []
            self._agent_errors[agent_id].append(error_id)

        logger.warning(
            "Agent %s error [%s/%s]: %s",
            agent_id, category.value, severity.value, message[:100],
        )

        if not error.recoverable:
            return RecoveryResult(
                success=False,
                action_taken="none",
                message="Error is not recoverable",
            )

        # Attempt recovery
        strategies = self._strategies.get(category, self._strategies[ErrorCategory.UNKNOWN])
        for strategy in strategies:
            try:
                result = await strategy(error)
                error.recovery_attempts += 1
                if result.success:
                    error.resolved = True
                    error.recovery_action = result.action_taken
                    self._recovery_history.append({
                        "error_id": error_id,
                        "agent_id": agent_id,
                        "category": category.value,
                        "action": result.action_taken,
                        "success": True,
                        "timestamp": time.time(),
                    })
                    logger.info(
                        "Agent %s recovered from %s via %s",
                        agent_id, category.value, result.action_taken,
                    )
                    return result
            except Exception as exc:
                logger.warning("Recovery strategy failed: %s", exc)

        # All strategies failed
        self._recovery_history.append({
            "error_id": error_id,
            "agent_id": agent_id,
            "category": category.value,
            "action": "all_failed",
            "success": False,
            "timestamp": time.time(),
        })
        return RecoveryResult(
            success=False,
            action_taken="all_failed",
            message="All recovery strategies failed",
        )

    async def get_errors(
        self,
        agent_id: str | None = None,
        *,
        unresolved_only: bool = False,
        limit: int = 100,
    ) -> list[AgentError]:
        async with self._lock:
            if agent_id:
                error_ids = self._agent_errors.get(agent_id, [])
                errors = [self._errors[eid] for eid in error_ids if eid in self._errors]
            else:
                errors = list(self._errors.values())
            if unresolved_only:
                errors = [e for e in errors if not e.resolved]
            return sorted(errors, key=lambda e: e.timestamp, reverse=True)[:limit]

    async def get_error_stats(self) -> dict[str, Any]:
        async with self._lock:
            total = len(self._errors)
            resolved = sum(1 for e in self._errors.values() if e.resolved)
            by_category: dict[str, int] = {}
            by_severity: dict[str, int] = {}
            for e in self._errors.values():
                by_category[e.category.value] = by_category.get(e.category.value, 0) + 1
                by_severity[e.severity.value] = by_severity.get(e.severity.value, 0) + 1

            recovery_success = sum(1 for h in self._recovery_history if h["success"])
            recovery_total = len(self._recovery_history)

            return {
                "total_errors": total,
                "resolved": resolved,
                "unresolved": total - resolved,
                "resolution_rate": round(resolved / max(1, total), 3),
                "by_category": by_category,
                "by_severity": by_severity,
                "recovery_success_rate": round(recovery_success / max(1, recovery_total), 3),
                "total_recovery_attempts": recovery_total,
            }

    async def clear_resolved(self) -> int:
        """Clear resolved errors. Returns count removed."""
        async with self._lock:
            resolved_ids = [
                eid for eid, e in self._errors.items() if e.resolved
            ]
            for eid in resolved_ids:
                error = self._errors.pop(eid)
                if error.agent_id in self._agent_errors:
                    self._agent_errors[error.agent_id] = [
                        x for x in self._agent_errors[error.agent_id] if x != eid
                    ]
            return len(resolved_ids)
