"""Conversation history (rolling transcript for a session).

Enhanced with token tracking, session persistence, search/filter,
context window management, and import/export capabilities.
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config.logging import get_logger
from app.models.message import Message

logger = get_logger(__name__)


@dataclass
class ConversationTurn:
    """A single conversation turn with metadata."""
    message: Message
    timestamp: float = field(default_factory=time.time)
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict, is_dataclass
        msg = self.message
        msg_dict = asdict(msg) if is_dataclass(msg) else str(msg)
        return {
            "message": msg_dict,
            "timestamp": self.timestamp,
            "token_count": self.token_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConversationTurn":
        msg = d["message"]
        if isinstance(msg, dict):
            msg = Message(**msg)
        return cls(
            message=msg,
            timestamp=d.get("timestamp", time.time()),
            token_count=d.get("token_count", 0),
            metadata=d.get("metadata", {}),
        )


class ConversationHistory:
    """Rolling conversation transcript with enhanced features.

    Features:
    - Token counting and budget enforcement
    - Session persistence (save/load to JSON)
    - Search and filter by role, keyword, time range
    - Context window management (trim to fit token budget)
    - Import/export in multiple formats
    - Per-session isolation
    """

    def __init__(
        self,
        session_id: str = "main",
        max_turns: int = 40,
        max_tokens: int = 8000,
        persist_path: str | Path | None = None,
    ) -> None:
        self.session_id = session_id
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self._buf: deque[ConversationTurn] = deque(maxlen=max_turns * 2)
        self._persist_path = Path(persist_path) if persist_path else None
        self._total_tokens = 0
        self._created_at = time.time()
        self._last_activity = time.time()

        # Auto-load if persist path exists
        if self._persist_path and self._persist_path.exists():
            self.load()

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------
    def append(self, message: Message, **metadata: Any) -> None:
        """Add a message to the conversation history."""
        token_count = self._estimate_tokens(message.content if hasattr(message, "content") else str(message))
        turn = ConversationTurn(
            message=message,
            token_count=token_count,
            metadata=metadata,
        )
        self._buf.append(turn)
        self._total_tokens += token_count
        self._last_activity = time.time()

        # Enforce token budget
        self._enforce_token_budget()

        # Auto-persist
        if self._persist_path:
            self.save()

    def clear(self) -> None:
        """Clear all conversation history."""
        self._buf.clear()
        self._total_tokens = 0
        self._last_activity = time.time()

    def messages(self) -> list[Message]:
        """Get all messages as a list."""
        return [t.message for t in self._buf]

    def turns(self) -> list[ConversationTurn]:
        """Get all turns with metadata."""
        return list(self._buf)

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------
    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count (rough: ~4 chars per token for English)."""
        return max(1, len(text) // 4)

    @property
    def total_tokens(self) -> int:
        """Total estimated tokens in conversation."""
        return sum(t.token_count for t in self._buf)

    @property
    def turn_count(self) -> int:
        """Number of turns in conversation."""
        return len(self._buf)

    def _enforce_token_budget(self) -> None:
        """Trim oldest turns if token budget exceeded."""
        while self._buf and self.total_tokens > self.max_tokens:
            removed = self._buf.popleft()
            logger.debug("Trimmed oldest turn to enforce token budget (freed ~%d tokens)", removed.token_count)

    def trim_to_budget(self, budget_tokens: int) -> int:
        """Trim conversation to fit within token budget. Returns tokens freed."""
        freed = 0
        while self._buf and self.total_tokens > budget_tokens:
            removed = self._buf.popleft()
            freed += removed.token_count
        return freed

    # ------------------------------------------------------------------
    # Search and filter
    # ------------------------------------------------------------------
    def search(self, keyword: str, *, case_sensitive: bool = False) -> list[ConversationTurn]:
        """Search conversation for messages containing keyword."""
        results = []
        for turn in self._buf:
            content = turn.message.content if hasattr(turn.message, "content") else str(turn.message)
            if not case_sensitive:
                if keyword.lower() in content.lower():
                    results.append(turn)
            else:
                if keyword in content:
                    results.append(turn)
        return results

    def filter_by_role(self, role: str) -> list[ConversationTurn]:
        """Filter turns by message role."""
        return [t for t in self._buf if hasattr(t.message, "role") and t.message.role == role]

    def filter_since(self, timestamp: float) -> list[ConversationTurn]:
        """Get turns since a given timestamp."""
        return [t for t in self._buf if t.timestamp >= timestamp]

    def get_last_n(self, n: int) -> list[Message]:
        """Get the last N messages."""
        return [t.message for t in list(self._buf)[-n:]]

    # ------------------------------------------------------------------
    # Context window management
    # ------------------------------------------------------------------
    def get_context_window(self, max_tokens: int | None = None) -> list[Message]:
        """Get messages fitting within token budget (most recent first)."""
        budget = max_tokens or self.max_tokens
        result = []
        total = 0
        for turn in reversed(self._buf):
            if total + turn.token_count > budget:
                break
            result.append(turn.message)
            total += turn.token_count
        return list(reversed(result))

    def get_summary(self) -> dict[str, Any]:
        """Get conversation summary statistics."""
        roles: dict[str, int] = {}
        for turn in self._buf:
            role = getattr(turn.message, "role", "unknown")
            roles[role] = roles.get(role, 0) + 1

        return {
            "session_id": self.session_id,
            "turn_count": self.turn_count,
            "total_tokens": self.total_tokens,
            "roles": roles,
            "created_at": self._created_at,
            "last_activity": self._last_activity,
            "duration_seconds": self._last_activity - self._created_at,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self, path: str | Path | None = None) -> Path:
        """Save conversation history to JSON file."""
        target = Path(path) if path else self._persist_path
        if not target:
            raise ValueError("No persist path specified")

        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": self.session_id,
            "max_turns": self.max_turns,
            "max_tokens": self.max_tokens,
            "created_at": self._created_at,
            "last_activity": self._last_activity,
            "turns": [t.to_dict() for t in self._buf],
        }
        target.write_text(json.dumps(data, indent=2, default=str))
        logger.debug("Saved conversation history (%d turns) to %s", self.turn_count, target)
        return target

    def load(self, path: str | Path | None = None) -> None:
        """Load conversation history from JSON file."""
        source = Path(path) if path else self._persist_path
        if not source or not source.exists():
            return

        data = json.loads(source.read_text())
        self.session_id = data.get("session_id", self.session_id)
        self.max_turns = data.get("max_turns", self.max_turns)
        self.max_tokens = data.get("max_tokens", self.max_tokens)
        self._created_at = data.get("created_at", time.time())
        self._last_activity = data.get("last_activity", time.time())

        self._buf.clear()
        for turn_data in data.get("turns", []):
            turn = ConversationTurn.from_dict(turn_data)
            self._buf.append(turn)

        logger.debug("Loaded conversation history (%d turns) from %s", self.turn_count, source)

    # ------------------------------------------------------------------
    # Import/Export
    # ------------------------------------------------------------------
    def export_text(self, path: str | Path) -> Path:
        """Export conversation as readable text file."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for turn in self._buf:
            role = getattr(turn.message, "role", "unknown")
            content = turn.message.content if hasattr(turn.message, "content") else str(turn.message)
            lines.append(f"[{role}]: {content}")
        target.write_text("\n\n".join(lines))
        return target

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "turn_count": self.turn_count,
            "total_tokens": self.total_tokens,
            "summary": self.get_summary(),
            "turns": [t.to_dict() for t in self._buf],
        }

    def __len__(self) -> int:
        return len(self._buf)

    def __repr__(self) -> str:
        return f"ConversationHistory(session={self.session_id!r}, turns={self.turn_count}, tokens={self.total_tokens})"
