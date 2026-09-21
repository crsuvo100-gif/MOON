"""
ErrorRecovery — retry wrapper.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, TypeVar

logger = logging.getLogger("moontm.recovery")

T = TypeVar("T")


class ErrorRecovery:
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0) -> None:
        self._max_retries = max_retries
        self._base_delay = base_delay

    async def run(self, fn: Callable[[], T]) -> T:
        last: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                return await fn()
            except Exception as exc:
                last = exc
                logger.warning("Retry %d/%d failed: %s", attempt + 1, self._max_retries, exc)
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(self._base_delay * (2 ** attempt))
        if last:
            raise last
        raise RuntimeError("ErrorRecovery: no exception but also no result")
