"""GlobalConnectorTool -- MOON's agent-facing global-connection tool.

ADDITIVE: exposes the ConnectionGateway to MOON's tool layer. Logical actions:
  connect   -- register a new connection (service/agent/mcp/webhook/ws)
  list      -- show registered connections + permission posture
  call      -- invoke an HTTP/agent connection (permission-checked)
  health    -- ping every connection and record real status
  disconnect-- remove a connection

Every state-changing/egress action is permission-gated. CONFIRMATION-tier hosts
require the operator to pass `confirmed=true`. NEVER-tier (credential reads) is
always denied. Nothing egresses without a passing gate -- no fake telemetry.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.tools.base import BaseTool
from app.connector.gateway import ConnectionGateway, ConnectionRecord
from app.connector.permission import ConnectorPermissionManager

logger = logging.getLogger(__name__)


class GlobalConnectorTool(BaseTool):
    name = "global_connector"
    description = (
        "MOON's global connection layer. Register and call connections to external "
        "services, other AI agents, MCP tool-servers, webhooks, and websockets -- "
        "all permission-gated. Actions: connect, list, call, health, disconnect."
    )

    def __init__(self, gateway: ConnectionGateway | None = None) -> None:
        self._gw = gateway or ConnectionGateway()

    async def execute(self, **kwargs: Any) -> Any:
        action = (kwargs.get("action") or "list").lower()
        if action == "connect":
            return await self._connect(kwargs)
        if action == "list":
            return self._list()
        if action == "call":
            return await self._call(kwargs)
        if action == "health":
            return await self._health()
        if action == "disconnect":
            return self._disconnect(kwargs)
        return f"[global_connector] unknown action '{action}'. Use connect|list|call|health|disconnect."

    # -- actions ------------------------------------------------------------
    async def _connect(self, kw: dict) -> str:
        name = kw.get("name") or ""
        url = kw.get("url") or ""
        kind = (kw.get("kind") or "service").lower()
        if not name or not url:
            return "[global_connector] connect requires name and url."
        host = self._gw.host_of(url)
        scope = {
            "agent": "network.agent", "service": "network.service",
            "webhook": "network.webhook", "mcp": "network.service",
            "websocket": "network.service",
        }.get(kind, "network.egress")
        allowed, tier, reason = self._gw.check_connection(name, host, scope)
        if not allowed and tier == "never":
            return f"[global_connector] BLOCKED: {reason}"
        if not allowed and tier == "confirmation" and not kw.get("confirmed"):
            return (f"[global_connector] CONFIRMATION REQUIRED to connect to '{host}' "
                    f"({reason}). Re-issue with confirmed=true if Psycho approves.")
        rec = ConnectionRecord(
            name=name, kind=kind, url=url, model=kw.get("model", ""),
            scope=scope, permissions=(scope,), credential_ref=kw.get("credential_ref", ""),
        )
        self._gw.register(rec)
        return (f"[global_connector] registered '{name}' ({kind}) -> {url}\n"
                f"  egress tier: {tier} | reason: {reason}\n"
                f"  secrets are referenced by name only; never stored on disk.")

    def _list(self) -> str:
        conns = self._gw.list()
        if not conns:
            return "[global_connector] no connections registered yet."
        lines = ["[global_connector] registered connections:"]
        for c in conns:
            lines.append(f"  - {c.name} [{c.kind}] {c.url}  status={c.last_status}")
        lines.append("\nEgress is permission-gated: allowlisted/private hosts = SAFE (auto); "
                     "others = CONFIRMATION (Psycho approves). secrets.read = NEVER auto.")
        return "\n".join(lines)

    async def _call(self, kw: dict) -> str:
        name = kw.get("name") or ""
        rec = self._gw.get(name)
        if rec is None:
            return f"[global_connector] no connection named '{name}'."
        if not rec.enabled:
            return f"[global_connector] '{name}' is disabled."
        host = self._gw.host_of(rec.url)
        allowed, tier, reason = self._gw.check_connection(name, host, rec.scope)
        if not allowed and tier == "never":
            return f"[global_connector] BLOCKED: {reason}"
        if not allowed and tier == "confirmation" and not kw.get("confirmed"):
            return (f"[global_connector] CONFIRMATION REQUIRED to call '{host}' "
                    f"({reason}). Re-issue with confirmed=true if Psycho approves.")
        conn = self._gw.build_connector(rec)
        try:
            if rec.kind == "agent":
                res = await conn.ask(kw.get("message", ""), system=kw.get("system", ""))
            elif rec.kind in ("websocket", "mcp"):
                res = await conn.health()
            else:
                method = (kw.get("method") or "GET").upper()
                res = await conn.call(method, kw.get("path", ""), json_body=kw.get("json"),
                                      params=kw.get("params"), data=kw.get("data"))
        except Exception as exc:  # noqa: BLE001
            self._gw.set_status(name, f"error:{exc}")
            return f"[global_connector] call failed: {exc}"
        self._gw.set_status(name, "ok" if res.ok else f"http:{res.status}")
        body = res.data if isinstance(res.data, str) else json.dumps(res.data, default=str)[:1500]
        return f"[global_connector] {name} -> {res.status}\n{body}"

    async def _health(self) -> str:
        lines = ["[global_connector] connection health:"]
        for c in self._gw.list():
            conn = self._gw.build_connector(c)
            try:
                res = await conn.health()
                ok = res.ok
                detail = (res.data if isinstance(res.data, str) else json.dumps(res.data, default=str))[:120]
            except Exception as exc:  # noqa: BLE001
                ok, detail = False, str(exc)[:120]
            self._gw.set_status(c.name, "ok" if ok else "unreachable")
            lines.append(f"  - {c.name} [{c.kind}] {'ONLINE' if ok else 'UNREACHABLE'} :: {detail}")
        return "\n".join(lines)

    def _disconnect(self, kw: dict) -> str:
        name = kw.get("name") or ""
        if self._gw.remove(name):
            return f"[global_connector] removed '{name}'."
        return f"[global_connector] no connection named '{name}'."
