"""
GlobalConnector — connects MOON to external services, agents, MCP servers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.config.settings import get_settings

logger = logging.getLogger("moontm.connector")


@dataclass
class ConnectionRecord:
    name: str
    kind: str  # "agent" | "service" | "mcp" | "webhook" | "loopback"
    url: str = ""
    model: str = ""
    scope: str = "local"
    permissions: list[str] = field(default_factory=list)
    credential_ref: str = ""
    enabled: bool = True
    metadata: dict = field(default_factory=dict)


class GlobalConnector:
    """Manages connections to external services and other agents."""

    def __init__(self, settings: Optional = None) -> None:
        self._settings = settings or get_settings()
        self._connections: dict[str, ConnectionRecord] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        # loopback peer
        self._connections["moon_local"] = ConnectionRecord(
            name="moon_local",
            kind="loopback",
            url="http://127.0.0.1:8777",
            scope="local",
            permissions=["read", "write", "execute"],
            enabled=True,
            metadata={"description": "local MOON terminal peer"},
        )

    def register(self, conn: ConnectionRecord) -> None:
        self._connections[conn.name] = conn
        logger.info("GlobalConnector: registered '%s' (%s)", conn.name, conn.kind)

    def get(self, name: str) -> Optional[ConnectionRecord]:
        return self._connections.get(name)

    def all(self) -> list[ConnectionRecord]:
        return list(self._connections.values())

    def enabled(self) -> list[ConnectionRecord]:
        return [c for c in self._connections.values() if c.enabled]

    def connect(self, name: str) -> Optional[ConnectionRecord]:
        """Best-effort connection (stub — returns record if exists)."""
        return self._connections.get(name)

    def to_dict(self) -> list[dict]:
        return [c.__dict__ for c in self._connections.values()]

    def __len__(self) -> int:
        return len(self._connections)
