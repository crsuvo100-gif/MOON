"""Pipeline -- sequential stage runner for a task."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class Pipeline:
    def __init__(self) -> None:
        self._stages: list[Callable[..., Awaitable[Any]]] = []

    def add(self, stage: Callable[..., Awaitable[Any]]) -> None:
        self._stages.append(stage)

    async def run(self, initial: Any) -> Any:
        value = initial
        for stage in self._stages:
            value = await stage(value)
        return value
