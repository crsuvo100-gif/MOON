"""Working memory -- transient scratch space per agent brain."""

from __future__ import annotations

from typing import Any


class WorkingMemory:
    def __init__(self) -> None:
        self._state: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def items(self) -> dict[str, Any]:
        return dict(self._state)

    def clear(self) -> None:
        self._state.clear()
