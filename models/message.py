"""Conversation message model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Role = str  # "system" | "user" | "assistant" | "tool"


@dataclass
class Message:
    role: str
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def system(cls, text: str) -> Message:
        return cls(role="system", content=text)

    @classmethod
    def user(cls, text: str) -> Message:
        return cls(role="user", content=text)

    @classmethod
    def assistant(cls, text: str) -> Message:
        return cls(role="assistant", content=text)

    @classmethod
    def tool_result(cls, text: str, tool: str | None = None) -> Message:
        return cls(role="tool", content=text, name=tool)
