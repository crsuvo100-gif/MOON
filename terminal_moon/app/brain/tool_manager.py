"""
ToolManager — registry-backed dispatch with timeout + safety gating.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.tools.base import BaseTool, ToolResult, ToolRegistry

logger = logging.getLogger("moontm.tools")


class ToolManager:
    """Wraps a ToolRegistry with enable/disable gating and `tool_timeout`."""

    def __init__(
        self,
        registry: ToolRegistry,
        enabled_tools: Optional[list[str]] = None,
        allow_dangerous: bool = True,
        tool_timeout: float = 30.0,
    ) -> None:
        self._registry = registry
        self._enabled = set(enabled_tools or registry.tool_names)
        self._allow_dangerous = allow_dangerous
        self._tool_timeout = tool_timeout

    def available_specs(self) -> list[dict]:
        specs: list[dict] = []
        for name in self._registry.tool_names:
            if name not in self._enabled:
                continue
            tool = self._registry.get(name)
            if tool:
                specs.append(tool.spec())
        return specs

    async def run(
        self,
        name: str,
        args: dict,
        agent: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> ToolResult:
        tool = self._registry.get(name)
        if not tool:
            return ToolResult(name=name, output="", success=False,
                              error=f"Tool '{name}' not found")

        if name not in self._enabled:
            return ToolResult(name=name, output="", success=False,
                              error=f"Tool '{name}' is disabled")

        t = timeout if timeout is not None else self._tool_timeout
        try:
            result = await asyncio.wait_for(
                tool.execute(**args),
                timeout=t,
            )
            output = str(result) if result is not None else ""
            return ToolResult(name=name, output=output, success=True)
        except asyncio.TimeoutError:
            logger.warning("Tool %s timed out after %ss", name, t)
            return ToolResult(name=name, output="", success=False,
                              error=f"Tool '{name}' timed out after {t}s")
        except Exception as exc:
            logger.warning("Tool %s failed: %s", name, exc)
            return ToolResult(name=name, output="", success=False,
                              error=f"Tool '{name}' error: {exc}")
