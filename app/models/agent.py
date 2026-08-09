"""Agent card / registry models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentCard:
    name: str
    description: str
    allowed_tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
