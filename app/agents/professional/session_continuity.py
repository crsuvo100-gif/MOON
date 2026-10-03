"""Session Continuity — cross-session context management.

Maintains context across multiple conversation sessions, enabling
the agent to remember user preferences, ongoing tasks, and historical
decisions. Supports session resumption and context handoff.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class SessionStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    EXPIRED = "expired"


@dataclass
class SessionContext:
    """Context for a single session."""
    session_id: str
    user_id: str
    created_at: float
    last_active: float
    status: SessionStatus
    summary: str = ""
    key_facts: list[str] = field(default_factory=list)
    ongoing_tasks: list[dict[str, Any]] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionHandoff:
    """Handoff data between sessions."""
    from_session: str
    to_session: str
    timestamp: float
    context_summary: str
    active_tasks: list[dict[str, Any]]
    user_preferences: dict[str, Any]
    notes: str = ""


class SessionContinuity:
    """Cross-session context management.

    Maintains conversation context across sessions, enabling
    seamless resumption and context handoff.
    """

    def __init__(self, *, storage_path: str = ".moon/sessions", ttl: float = 86400.0) -> None:
        self._sessions: dict[str, SessionContext] = {}
        self._storage_path = Path(storage_path)
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl  # Session TTL in seconds
        self._handoff_history: list[SessionHandoff] = []
        self._metrics: dict[str, int] = defaultdict(int)

    async def create_session(
        self,
        *,
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> SessionContext:
        """Create a new session."""
        session_id = str(uuid.uuid4())[:8]
        now = time.time()

        session = SessionContext(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            last_active=now,
            status=SessionStatus.ACTIVE,
            metadata=metadata or {},
        )

        self._sessions[session_id] = session
        self._metrics["sessions_created"] += 1

        # Persist to disk
        await self._save_session(session)

        logger.info("Created session %s for user %s", session_id, user_id)
        return session

    async def resume_session(self, session_id: str) -> SessionContext | None:
        """Resume an existing session."""
        # Check memory first
        if session_id in self._sessions:
            session = self._sessions[session_id]
            if session.status == SessionStatus.ACTIVE:
                session.last_active = time.time()
                self._metrics["sessions_resumed"] += 1
                return session

        # Try loading from disk
        session = await self._load_session(session_id)
        if session:
            session.status = SessionStatus.ACTIVE
            session.last_active = time.time()
            self._sessions[session_id] = session
            self._metrics["sessions_resumed"] += 1
            logger.info("Resumed session %s", session_id)
            return session

        logger.warning("Session not found: %s", session_id)
        return None

    async def update_session(
        self,
        session_id: str,
        *,
        summary: str | None = None,
        key_facts: list[str] | None = None,
        ongoing_tasks: list[dict[str, Any]] | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> bool:
        """Update session context."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        if summary is not None:
            session.summary = summary
        if key_facts is not None:
            session.key_facts.extend(key_facts)
        if ongoing_tasks is not None:
            session.ongoing_tasks = ongoing_tasks
        if preferences is not None:
            session.preferences.update(preferences)

        session.last_active = time.time()
        await self._save_session(session)
        self._metrics["sessions_updated"] += 1
        return True

    async def handoff(
        self,
        from_session_id: str,
        to_session_id: str,
        *,
        notes: str = "",
    ) -> SessionHandoff | None:
        """Create a handoff between sessions."""
        from_session = self._sessions.get(from_session_id)
        to_session = self._sessions.get(to_session_id)

        if not from_session or not to_session:
            return None

        handoff = SessionHandoff(
            from_session=from_session_id,
            to_session=to_session_id,
            timestamp=time.time(),
            context_summary=from_session.summary,
            active_tasks=from_session.ongoing_tasks,
            user_preferences=from_session.preferences,
            notes=notes,
        )

        self._handoff_history.append(handoff)

        # Update target session with handoff context
        to_session.summary = from_session.summary
        to_session.key_facts = list(from_session.key_facts)
        to_session.ongoing_tasks = list(from_session.ongoing_tasks)
        to_session.preferences.update(from_session.preferences)
        to_session.last_active = time.time()

        await self._save_session(to_session)
        self._metrics["handoffs"] += 1

        logger.info("Handoff from %s to %s", from_session_id, to_session_id)
        return handoff

    async def get_session_summary(self, session_id: str) -> str:
        """Get a summary of the session."""
        session = self._sessions.get(session_id)
        if not session:
            return ""

        parts = []
        if session.summary:
            parts.append(f"Summary: {session.summary}")
        if session.key_facts:
            parts.append(f"Key facts: {', '.join(session.key_facts[:5])}")
        if session.ongoing_tasks:
            parts.append(f"Ongoing tasks: {len(session.ongoing_tasks)}")

        return "\n".join(parts)

    async def cleanup_expired(self) -> int:
        """Clean up expired sessions. Returns count removed."""
        now = time.time()
        expired = []

        for sid, session in self._sessions.items():
            if now - session.last_active > self._ttl:
                expired.append(sid)

        for sid in expired:
            del self._sessions[sid]
            self._metrics["sessions_expired"] += 1

        if expired:
            logger.info("Cleaned up %d expired sessions", len(expired))

        return len(expired)

    async def _save_session(self, session: SessionContext) -> None:
        """Persist session to disk."""
        path = self._storage_path / f"{session.session_id}.json"
        data = {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "created_at": session.created_at,
            "last_active": session.last_active,
            "status": session.status.value,
            "summary": session.summary,
            "key_facts": session.key_facts,
            "ongoing_tasks": session.ongoing_tasks,
            "preferences": session.preferences,
            "metadata": session.metadata,
        }
        try:
            path.write_text(json.dumps(data, indent=2, default=str))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to save session %s: %s", session.session_id, exc)

    async def _load_session(self, session_id: str) -> SessionContext | None:
        """Load session from disk."""
        path = self._storage_path / f"{session_id}.json"
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
            return SessionContext(
                session_id=data["session_id"],
                user_id=data["user_id"],
                created_at=data["created_at"],
                last_active=data["last_active"],
                status=SessionStatus(data.get("status", "active")),
                summary=data.get("summary", ""),
                key_facts=data.get("key_facts", []),
                ongoing_tasks=data.get("ongoing_tasks", []),
                preferences=data.get("preferences", {}),
                metadata=data.get("metadata", {}),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load session %s: %s", session_id, exc)
            return None

    def get_metrics(self) -> dict[str, Any]:
        return {
            **self._metrics,
            "active_sessions": len(self._sessions),
            "total_handoffs": len(self._handoff_history),
        }
