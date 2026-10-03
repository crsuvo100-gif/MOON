"""Self-Healing System — proactive fault detection and recovery.

Monitors agent health, detects failures, and automatically applies
recovery strategies. Supports circuit breakers, graceful degradation,
and automatic restart of failed components.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from app.config.logging import get_logger

logger = get_logger(__name__)


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    RECOVERING = "recovering"


class FailureType(Enum):
    LLM_TIMEOUT = "llm_timeout"
    LLM_ERROR = "llm_error"
    TOOL_ERROR = "tool_error"
    MEMORY_ERROR = "memory_error"
    CONTEXT_OVERFLOW = "context_overflow"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Result of a health check."""
    component: str
    status: HealthStatus
    latency_ms: float
    last_check: float
    error_count: int = 0
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryAction:
    """A recovery action to take."""
    failure_type: FailureType
    component: str
    strategy: str
    max_attempts: int = 3
    backoff_base: float = 1.0
    timeout: float = 30.0


class CircuitBreaker:
    """Circuit breaker pattern for fault tolerance."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 2,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._failures = 0
        self._last_failure_time: float | None = None
        self._state = "closed"  # closed, open, half-open
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        return self._state

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function through the circuit breaker."""
        async with self._lock:
            if self._state == "open":
                if self._last_failure_time and (time.time() - self._last_failure_time) > self._recovery_timeout:
                    self._state = "half-open"
                    self._half_open_calls = 0
                    logger.info("Circuit breaker entering half-open state")
                else:
                    raise Exception("Circuit breaker is OPEN")

            if self._state == "half-open" and self._half_open_calls >= self._half_open_max_calls:
                raise Exception("Circuit breaker is HALF-OPEN (max calls reached)")

            if self._state == "half-open":
                self._half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                if self._state == "half-open":
                    self._state = "closed"
                    self._failures = 0
                    logger.info("Circuit breaker closed (recovered)")
                else:
                    self._failures = max(0, self._failures - 1)
            return result
        except Exception as exc:
            async with self._lock:
                self._failures += 1
                self._last_failure_time = time.time()
                if self._failures >= self._failure_threshold:
                    self._state = "open"
                    logger.warning("Circuit breaker OPENED after %d failures", self._failures)
            raise


class SelfHealing:
    """Self-healing system for proactive fault detection and recovery."""

    def __init__(self, *, check_interval: float = 30.0) -> None:
        self._health_checks: dict[str, HealthCheck] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._recovery_strategies: dict[FailureType, list[RecoveryAction]] = {}
        self._check_interval = check_interval
        self._running = False
        self._check_task: asyncio.Task | None = None
        self._metrics: dict[str, int] = defaultdict(int)
        self._recovery_handlers: dict[str, Callable] = {}

    async def start(self) -> None:
        """Start the health monitoring loop."""
        if self._running:
            return
        self._running = True
        self._check_task = asyncio.create_task(self._health_loop())
        logger.info("Self-healing system started")

    async def stop(self) -> None:
        """Stop the health monitoring loop."""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        logger.info("Self-healing system stopped")

    def register_component(
        self,
        name: str,
        *,
        health_check: Callable | None = None,
        recovery_handler: Callable | None = None,
        circuit_breaker: bool = True,
    ) -> None:
        """Register a component for health monitoring."""
        self._health_checks[name] = HealthCheck(
            component=name,
            status=HealthStatus.HEALTHY,
            latency_ms=0.0,
            last_check=time.time(),
        )
        if circuit_breaker:
            self._circuit_breakers[name] = CircuitBreaker()
        if recovery_handler:
            self._recovery_handlers[name] = recovery_handler
        logger.debug("Registered component for self-healing: %s", name)

    def register_recovery_strategy(
        self,
        failure_type: FailureType,
        action: RecoveryAction,
    ) -> None:
        """Register a recovery strategy for a failure type."""
        if failure_type not in self._recovery_strategies:
            self._recovery_strategies[failure_type] = []
        self._recovery_strategies[failure_type].append(action)

    async def report_health(
        self,
        component: str,
        *,
        status: HealthStatus,
        latency_ms: float = 0.0,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Report health status for a component."""
        check = self._health_checks.get(component)
        if check:
            check.status = status
            check.latency_ms = latency_ms
            check.last_check = time.time()
            if error:
                check.error_count += 1
                check.last_error = error
            if metadata:
                check.metadata.update(metadata)

    async def report_failure(
        self,
        component: str,
        failure_type: FailureType,
        error: str,
    ) -> bool:
        """Report a failure and attempt recovery.

        Returns:
            True if recovery was successful.
        """
        self._metrics["failures"] += 1
        await self.report_health(
            component,
            status=HealthStatus.UNHEALTHY,
            error=error,
        )

        # Attempt recovery
        strategies = self._recovery_strategies.get(failure_type, [])
        for strategy in strategies:
            if strategy.component == component:
                return await self._execute_recovery(strategy, error)

        # Default recovery: try component-specific handler
        handler = self._recovery_handlers.get(component)
        if handler:
            try:
                await handler()
                await self.report_health(component, status=HealthStatus.HEALTHY)
                self._metrics["recoveries"] += 1
                return True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Recovery failed for %s: %s", component, exc)

        return False

    async def _execute_recovery(self, action: RecoveryAction, error: str) -> bool:
        """Execute a recovery action."""
        logger.info("Attempting recovery: %s for %s (%s)", action.strategy, action.component, action.failure_type.value)
        self._metrics["recovery_attempts"] += 1

        for attempt in range(1, action.max_attempts + 1):
            try:
                await asyncio.sleep(action.backoff_base * (2 ** (attempt - 1)))
                handler = self._recovery_handlers.get(action.component)
                if handler:
                    await asyncio.wait_for(handler(), timeout=action.timeout)
                    await self.report_health(action.component, status=HealthStatus.HEALTHY)
                    self._metrics["recoveries"] += 1
                    logger.info("Recovery successful for %s (attempt %d)", action.component, attempt)
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Recovery attempt %d failed for %s: %s", attempt, action.component, exc)

        return False

    async def _health_loop(self) -> None:
        """Periodic health check loop."""
        while self._running:
            try:
                for name, check in self._health_checks.items():
                    # Check for stale health reports
                    if time.time() - check.last_check > self._check_interval * 3:
                        if check.status == HealthStatus.HEALTHY:
                            check.status = HealthStatus.DEGRADED
                            logger.warning("Component %s marked DEGRADED (stale health)", name)

                    # Check error rate
                    if check.error_count > 10:
                        check.status = HealthStatus.UNHEALTHY
                        logger.warning("Component %s marked UNHEALTHY (%d errors)", name, check.error_count)

                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Health loop error: %s", exc)
                await asyncio.sleep(1.0)

    def get_health(self, component: str | None = None) -> HealthCheck | dict[str, HealthCheck]:
        """Get health status for a component or all components."""
        if component:
            return self._health_checks.get(component, HealthCheck(
                component=component, status=HealthStatus.UNHEALTHY, latency_ms=0, last_check=time.time()
            ))
        return dict(self._health_checks)

    def get_circuit_breaker(self, component: str) -> CircuitBreaker | None:
        return self._circuit_breakers.get(component)

    def get_metrics(self) -> dict[str, Any]:
        return {
            **self._metrics,
            "components_monitored": len(self._health_checks),
            "circuit_breakers": len(self._circuit_breakers),
            "recovery_strategies": sum(len(v) for v in self._recovery_strategies.values()),
        }
