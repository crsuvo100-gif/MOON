"""Base tool interface + result type."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    output: Any = None
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    name: str = ""
    description: str = ""

    def is_dangerous(self) -> bool:
        """Return True if this tool can modify the host or exfiltrate data.
        Override in subclasses that run shell commands, write files, or make
        outbound connections. The ToolManager checks this before execution."""
        return False

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        ...

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}},
        }
