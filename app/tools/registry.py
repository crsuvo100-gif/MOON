"""Tool registry -- name -> tool instance."""

from __future__ import annotations

import logging
from typing import Any

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        logger.debug("registered tool %s", tool.name)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools)
