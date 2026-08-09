"""Task model -- the unit of work MOON executes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class Task:
    prompt: str
    agent_name: str = "auto"
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    status: str = "pending"
    result: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0

    @classmethod
    def create(cls, prompt: str, agent_name: str = "auto") -> "Task":
        return cls(prompt=prompt, agent_name=agent_name)

    def mark_running(self) -> None:
        self.status = "running"

    def complete(self, result: str, *, data: dict[str, Any] | None = None, tokens_used: int = 0) -> None:
        self.status = "completed"
        self.result = result
        if data is not None:
            self.data.update(data)
        self.tokens_used = tokens_used

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.result = error
