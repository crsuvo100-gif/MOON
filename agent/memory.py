"""
MOON Memory — SQLite-backed session memory store for Moon_Twin.

Replicates Hermes state.py pattern: persistent session storage with
conversation history, agent selection logs, and memory consolidation.
"""

from __future__ import annotations

import sqlite3
import json
import os
import time
from pathlib import Path
from typing import Any, Optional
from contextlib import contextmanager


class MoonMemory:
    """
    Persistent memory store for Moon_Twin agent sessions.

    Stores:
    - Conversation messages (per session)
    - Agent selection events
    - Tool execution logs
    - Memory entries (user/wiki-style notes)
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or f"moon_memory_{os.getpid()}.db")
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    agent TEXT,
                    created_at REAL,
                    message_count INTEGER DEFAULT 0,
                    last_active REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    agent TEXT,
                    created_at REAL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    agent_name TEXT,
                    query TEXT,
                    intent_route TEXT,
                    created_at REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    key TEXT,
                    value TEXT,
                    created_at REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_events_session
                ON agent_events(session_id)
            """)

    @contextmanager
    def _connect(self):
        """Context manager for DB connections."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- Sessions --

    def create_session(self, session_id: str, agent: str = "general") -> dict:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, agent, created_at, last_active) VALUES (?, ?, ?, ?)",
                (session_id, agent, time.time(), time.time()),
            )
            return self.get_session(session_id)

    def get_session(self, session_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_session(self, session_id: str, agent: str | None = None) -> None:
        with self._connect() as conn:
            now = time.time()
            if agent:
                conn.execute(
                    "UPDATE sessions SET agent = ?, last_active = ? WHERE id = ?",
                    (agent, now, session_id),
                )
            else:
                conn.execute(
                    "UPDATE sessions SET last_active = ? WHERE id = ?",
                    (now, session_id),
                )

    def increment_message_count(self, session_id: str) -> int:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET message_count = message_count + 1, last_active = ? WHERE id = ?",
                (time.time(), session_id),
            )
            row = conn.execute(
                "SELECT message_count FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return row["message_count"] if row else 0

    # -- Messages --

    def add_message(self, session_id: str, role: str, content: str, agent: str = "general") -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO messages (session_id, role, content, agent, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, agent, time.time()),
            )
            return cur.lastrowid

    def get_messages(self, session_id: str, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    def clear_messages(self, session_id: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM messages WHERE session_id = ?", (session_id,)
            )
            return cur.rowcount

    # -- Agent events --

    def log_agent_event(
        self,
        session_id: str,
        agent_name: str,
        query: str,
        intent_route: str | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO agent_events (session_id, agent_name, query, intent_route, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, agent_name, query, intent_route, time.time()),
            )
            return cur.lastrowid

    def get_agent_events(self, session_id: str, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_events WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    # -- Memory entries (wiki-style notes) --

    def set_memory(self, session_id: str, key: str, value: Any) -> int:
        value_json = json.dumps(value) if not isinstance(value, str) else value
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO memory_entries (session_id, key, value, created_at) VALUES (?, ?, ?, ?)",
                (session_id, key, value_json, time.time()),
            )
            return cur.lastrowid

    def get_memory(self, session_id: str, key: str) -> Optional[Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM memory_entries WHERE session_id = ? AND key = ?",
                (session_id, key),
            ).fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except json.JSONDecodeError:
                    return row["value"]
            return None

    def get_all_memory(self, session_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value FROM memory_entries WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            result = {}
            for r in rows:
                try:
                    result[r["key"]] = json.loads(r["value"])
                except json.JSONDecodeError:
                    result[r["key"]] = r["value"]
            return result

    def delete_memory(self, session_id: str, key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM memory_entries WHERE session_id = ? AND key = ?",
                (session_id, key),
            )
            return cur.rowcount > 0

    def clear_all_memory(self, session_id: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM memory_entries WHERE session_id = ?", (session_id,)
            )
            return cur.rowcount

    # -- Cleanup --

    def prune_old_sessions(self, max_age_hours: float = 24) -> int:
        """Remove sessions older than max_age_hours."""
        cutoff = time.time() - (max_age_hours * 3600)
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM sessions WHERE last_active < ?", (cutoff,)
            )
            return cur.rowcount

    def close(self):
        """Close the database (no-op for SQLite, but here for API consistency)."""
        pass


# ---------------------------------------------------------------------------
# Default instance
# ---------------------------------------------------------------------------

default_memory = MoonMemory()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    mem = MoonMemory(db_path=f"/tmp/moon_memory_test_{os.getpid()}.db")

    sid = "test-session"
    mem.create_session(sid, agent="general")
    print("Created session:", mem.get_session(sid))

    mem.add_message(sid, "user", "hello moon")
    mem.add_message(sid, "agent", "hello user")
    print("Messages:", mem.get_messages(sid))

    mem.log_agent_event(sid, "code", "write a function", intent_route="code")
    print("Agent events:", mem.get_agent_events(sid))

    mem.set_memory(sid, "user_name", "Moon_Twin")
    print("Memory:", mem.get_all_memory(sid))

    print("All OK")
