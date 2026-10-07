"""Execution history manager for MOON terminal.

Stores execution history with search, filtering, and pagination.
Never stores secrets — commands are sanitized before storage.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .security import sanitize_command


class HistoryEntry(BaseModel):
    execution_id: str
    timestamp: float
    command: str
    cwd: str
    backend: str
    status: str
    exit_code: Optional[int] = None
    duration: float = 0.0
    session_id: Optional[str] = None


class HistoryManager:
    """Manages execution history with persistence and search."""

    def __init__(self, persist: bool = True, max_entries: int = 1000):
        self._entries: List[HistoryEntry] = []
        self.persist = persist
        self.max_entries = max_entries
        self._history_file = Path(".moon_terminal_history.json")
        if self.persist and self._history_file.exists():
            self._load()

    def _load(self):
        """Load history from disk."""
        try:
            data = json.loads(self._history_file.read_text())
            for item in data:
                try:
                    self._entries.append(HistoryEntry(**item))
                except Exception:
                    pass
        except Exception:
            pass

    def _save(self):
        """Save history to disk."""
        if not self.persist:
            return
        try:
            data = [entry.dict() for entry in self._entries]
            self._history_file.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def add_entry(
        self,
        command: str,
        cwd: str,
        backend: str,
        status: str,
        exit_code: Optional[int] = None,
        duration: float = 0.0,
        session_id: Optional[str] = None,
    ) -> HistoryEntry:
        """Add a history entry. Command is sanitized before storage."""
        entry = HistoryEntry(
            execution_id=str(uuid.uuid4()),
            timestamp=time.time(),
            command=sanitize_command(command),
            cwd=cwd,
            backend=backend,
            status=status,
            exit_code=exit_code,
            duration=duration,
            session_id=session_id,
        )
        self._entries.append(entry)
        # Trim to max entries
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]
        self._save()
        return entry

    def get_recent(self, count: int = 20) -> List[HistoryEntry]:
        """Get the most recent entries."""
        return list(reversed(self._entries[-count:]))

    def get_all(self) -> List[HistoryEntry]:
        """Get all entries."""
        return list(self._entries)

    def search(self, query: str) -> List[HistoryEntry]:
        """Search history by command text."""
        query_lower = query.lower()
        return [
            e for e in self._entries
            if query_lower in e.command.lower()
        ]

    def get_by_status(self, status: str) -> List[HistoryEntry]:
        """Get entries filtered by status."""
        return [e for e in self._entries if e.status == status]

    def get_by_session(self, session_id: str) -> List[HistoryEntry]:
        """Get entries for a specific session."""
        return [e for e in self._entries if e.session_id == session_id]

    def get_successful(self) -> List[HistoryEntry]:
        """Get successful executions."""
        return [e for e in self._entries if e.status == "success"]

    def get_failed(self) -> List[HistoryEntry]:
        """Get failed executions."""
        return [e for e in self._entries if e.status == "failed"]

    def clear(self):
        """Clear all history."""
        self._entries.clear()
        self._save()

    def __len__(self) -> int:
        return len(self._entries)


# Module-level singleton
history_manager = HistoryManager()
