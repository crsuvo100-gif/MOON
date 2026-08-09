"""Memory entry model for persistent stores."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

try:
    from app.config.constants import MemoryScope
except Exception:  # pragma: no cover
    MemoryScope = None  # type: ignore


@dataclass
class MemoryEntry:
    content: str
    scope: Any = "long_term"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: "mem_" + uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "scope": getattr(self.scope, "value", str(self.scope)),
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        return cls(
            content=data.get("content", ""),
            scope=data.get("scope", "long_term"),
            tags=list(data.get("tags", [])),
            metadata=data.get("metadata", {}),
            id=data.get("id", "mem_" + uuid.uuid4().hex[:12]),
            created_at=data.get("created_at", time.time()),
        )
