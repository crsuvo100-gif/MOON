"""Database query tool (sqlite by default)."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class DatabaseTool(BaseTool):
    name = "database"
    description = "Run a read-only SQL query against the local sqlite DB."

    async def execute(self, query: str = "", db: str = ":memory:", **kwargs: Any) -> str:
        if not query:
            return "[no query]"
        if not query.strip().lower().startswith(("select", "pragma")):
            return "[only read queries allowed]"
        try:
            conn = sqlite3.connect(db)
            cur = conn.execute(query)
            rows = cur.fetchmany(50)
            conn.close()
            return str(rows)
        except Exception as exc:  # noqa: BLE001
            return f"[db error: {exc}]"
