"""ConnectionGateway -- MOON's persistent, permission-gated connection registry.

Lets MOON remember and reuse connections to external services, other AI agents,
MCP servers, and webhooks. Each connection is stored under connections/registry.json
(survives restarts, like the capability registry) and every OPEN/CALL is
permission-checked via ConnectorPermissionManager + the active-op auth gate.
"""

from __future__ import annotations

import json
import logging
import socket
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.connector.permission import ConnectorPermissionManager

logger = logging.getLogger(__name__)


@dataclass
class ConnectionRecord:
    name: str
    kind: str                       # service | agent | mcp | webhook | websocket
    url: str
    model: str = ""
    scope: str = "network.egress"
    permissions: tuple[str, ...] = field(default_factory=tuple)
    credential_ref: str = ""        # logical name; value NEVER stored on disk
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_status: str = "unknown"
    last_checked: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["permissions"] = list(self.permissions)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConnectionRecord":
        d = dict(d)
        d["permissions"] = tuple(d.get("permissions", []))
        return cls(**d)


class ConnectionGateway:
    """Persists connections and enforces egress permissions before opening them."""

    def __init__(self, root: Path | None = None,
                 perms: ConnectorPermissionManager | None = None) -> None:
        self._root = root or (Path(__file__).resolve().parent.parent.parent / "connections")
        self._root.mkdir(parents=True, exist_ok=True)
        self._file = self._root / "registry.json"
        self._perms = perms or ConnectorPermissionManager()
        self._conns: dict[str, ConnectionRecord] = {}
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                for row in json.loads(self._file.read_text(encoding="utf-8")):
                    rec = ConnectionRecord.from_dict(row)
                    self._conns[rec.name] = rec
            except Exception as exc:  # noqa: BLE001
                logger.warning("connection registry load failed: %s", exc)

    def _save(self) -> None:
        self._file.write_text(
            json.dumps([c.to_dict() for c in self._conns.values()], indent=2),
            encoding="utf-8",
        )

    # -- permission gate ----------------------------------------------------
    def check_connection(self, name: str, host: str, scope: str) -> tuple[bool, str, str]:
        """Returns (allowed, tier, reason). CONFIRMATION -> caller must confirm."""
        d = self._perms.egress_decision(host, scope)
        return d.allowed, d.tier.value, d.reason

    # -- CRUD ---------------------------------------------------------------
    def register(self, rec: ConnectionRecord) -> str:
        self._conns[rec.name] = rec
        self._save()
        return rec.name

    def get(self, name: str) -> ConnectionRecord | None:
        return self._conns.get(name)

    def list(self) -> list[ConnectionRecord]:
        return list(self._conns.values())

    def remove(self, name: str) -> bool:
        if name in self._conns:
            del self._conns[name]
            self._save()
            return True
        return False

    def set_status(self, name: str, status: str) -> None:
        rec = self._conns.get(name)
        if rec:
            rec.last_status = status
            rec.last_checked = time.time()
            self._save()

    @staticmethod
    def host_of(url: str) -> str:
        try:
            return urlparse(url).hostname or url
        except Exception:
            return url

    def build_connector(self, rec: ConnectionRecord):
        """Instantiate the concrete connector client for a record (no call yet)."""
        from app.connector.connectors import (
            HTTPConnector, AgentConnector, WebSocketConnector, MCPConnector,
        )
        if rec.kind == "agent":
            return AgentConnector(rec.url, rec.model or "gpt-4o-mini", timeout=120.0)
        if rec.kind == "websocket":
            return WebSocketConnector(rec.url)
        if rec.kind == "mcp":
            return MCPConnector(rec.url)
        return HTTPConnector(rec.url, timeout=30.0)

    # -- federation ---------------------------------------------------------
    async def call_agent(self, name: str, message: str, *,
                         system: str = "", history: list[dict] | None = None) -> dict[str, Any]:
        """Delegate a prompt to a registered peer AI agent and return its answer.

        This is MOON's two-way federation: she not only reaches OUT to the world
        but can also ask another AI agent to do a subtask and fold the answer back
        into her own reasoning. Permission-gated by the connection's scope.
        Returns {"ok": bool, "answer": str, ...}.
        """
        from app.connector.connectors import CallResult  # noqa: F401
        rec = self._conns.get(name)
        if rec is None:
            return {"ok": False, "error": f"no connection named '{name}'"}
        if rec.kind != "agent":
            return {"ok": False, "error": f"connection '{name}' is kind '{rec.kind}', not 'agent'"}
        if not rec.enabled:
            return {"ok": False, "error": f"connection '{name}' is disabled"}
        from app.connector.connectors import AgentConnector
        conn: AgentConnector = self.build_connector(rec)  # type: ignore[assignment]
        res = await conn.ask(message, system=system, history=history)
        self.set_status(name, "ok" if res.ok else f"error: {res.error}")
        if res.ok:
            return {"ok": True, "answer": (res.data or {}).get("answer", ""), "agent": rec.model}
        return {"ok": False, "error": res.error}
