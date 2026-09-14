"""
BaseTool ABC + ToolResult + ToolRegistry.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    name: str
    output: Any = ""
    success: bool = True
    error: Optional[str] = None
    metadata: dict = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "output": str(self.output) if self.output is not None else "",
            "success": self.success,
            "error": self.error or "",
        }


class BaseTool(ABC):
    """Every tool must implement name, description, async execute, and spec."""

    name: str = "base"
    description: str = ""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Return a string or dict result."""
        ...

    def spec(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}},
        }


class ToolRegistry:
    """Simple name → tool mapping."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
