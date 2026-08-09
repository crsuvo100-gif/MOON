"""Pipeline -- sequential stage runner for a task."""

from __future__ import annotations

from typing import Any, Callable, Awaitable


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
