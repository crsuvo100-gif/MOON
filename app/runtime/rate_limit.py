"""Rate limiting (spec 51).

Spec 51 forbids "unlimited tool calls" and "uncontrolled agent spawning". The
iteration caps (``max_iterations``/``max_tool_calls``) bound a single task, but
nothing bounded the RATE of work across tasks. This adds a small token-bucket
limiter so a runaway caller cannot hammer tools/agents without limit.

Pure-Python, thread-safe, no dependencies.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RateLimitDecision:
    allowed: bool
    reason: str = ""
    retry_after: float = 0.0
    remaining: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason,
                "retry_after": round(self.retry_after, 3),
                "remaining": round(self.remaining, 2)}


class TokenBucket:
    """Classic token bucket: ``rate`` tokens/sec, burst up to ``capacity``."""

    def __init__(self, rate: float = 2.0, capacity: float = 10.0) -> None:
        self._rate = max(0.01, float(rate))
        self._capacity = max(1.0, float(capacity))
        self._tokens = self._capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last = now

    def take(self, n: float = 1.0) -> RateLimitDecision:
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return RateLimitDecision(True, "ok", 0.0, self._tokens)
            needed = n - self._tokens
            wait = needed / self._rate
            return RateLimitDecision(
                False, f"rate limit: need {n:g} token(s), {self._tokens:.2f} available",
                retry_after=wait, remaining=self._tokens)


@dataclass
class _Bucket:
    bucket: TokenBucket
    hits: int = 0
    denied: int = 0
    field_default: Any = field(default=None)


class RateLimiter:
    """Named token buckets for tools / agents / global task submission."""

    def __init__(self, *, tool_rate: float = 5.0, tool_burst: float = 20.0,
                 agent_rate: float = 2.0, agent_burst: float = 10.0,
                 task_rate: float = 1.0, task_burst: float = 5.0) -> None:
        self._defaults = {
            "tool": (tool_rate, tool_burst),
            "agent": (agent_rate, agent_burst),
            "task": (task_rate, task_burst),
        }
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def _get(self, name: str) -> TokenBucket:
        with self._lock:
            if name not in self._buckets:
                kind = name.split(":", 1)[0]
                rate, burst = self._defaults.get(kind, (2.0, 10.0))
                self._buckets[name] = _Bucket(TokenBucket(rate, burst))
            return self._buckets[name].bucket

    def check(self, name: str, n: float = 1.0) -> RateLimitDecision:
        """Consume a token for ``name`` (e.g. ``tool:terminal``, ``agent:coding``)."""
        b = self._get(name)
        d = b.take(n)
        with self._lock:
            rec = self._buckets.get(name)
            if rec is not None:
                if d.allowed:
                    rec.hits += 1
                else:
                    rec.denied += 1
        return d

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                name: {"hits": rec.hits, "denied": rec.denied,
                       "remaining": round(rec.bucket._tokens, 2)}
                for name, rec in self._buckets.items()
            }


_LIMITER: RateLimiter | None = None
_LOCK = threading.Lock()


def get_limiter() -> RateLimiter:
    """Process-wide limiter (spec 3: one internal safety mechanism)."""
    global _LIMITER
    with _LOCK:
        if _LIMITER is None:
            _LIMITER = RateLimiter()
        return _LIMITER


__all__ = ["RateLimitDecision", "TokenBucket", "RateLimiter", "get_limiter"]
