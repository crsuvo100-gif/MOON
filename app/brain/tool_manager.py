"""ToolManager -- registry-backed tool dispatch with safety gating."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ToolResult:
    name: str
    output: Any
    success: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "output": self.output,
            "success": self.success,
            "error": self.error,
        }


class ToolManager:
    def __init__(self, registry, *, enabled_tools: set[str] | None = None, allow_dangerous: bool = False) -> None:
        self._registry = registry
        self._enabled = enabled_tools or {t.name for t in registry.all()}
        self._allow_dangerous = allow_dangerous

    def available_specs(self) -> list[dict[str, Any]]:
        specs = []
        for t in self._registry.all():
            if t.name in self._enabled:
                try:
                    specs.append(t.spec())
                except Exception:  # noqa: BLE001
                    specs.append({"name": t.name, "description": "", "parameters": {}})
        return specs

    async def run(self, name: str, args: dict[str, Any], *, agent=None) -> ToolResult:
        tool = self._registry.get(name)
        if tool is None or name not in self._enabled:
            return ToolResult(name=name, output=None, success=False, error="tool not available")
        try:
            result = await tool.execute(**(args or {}))
            return ToolResult(name=name, output=result, success=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tool %s failed: %s", name, exc)
            return ToolResult(name=name, output=None, success=False, error=str(exc))
