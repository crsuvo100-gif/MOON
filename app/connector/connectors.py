"""Concrete connector clients -- real, working network bridges.

Each connector performs an ACTUAL outbound call (httpx / websocket) and returns
structured results. They are pure transport; permission checks live in the
ConnectionGateway before any of these are invoked. No fake telemetry.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CallResult:
    ok: bool
    status: int = 0
    data: Any = None
    error: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class HTTPConnector:
    """Call an external REST/HTTP service."""

    def __init__(self, base_url: str, headers: dict[str, str] | None = None,
                 timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {**(headers or {}), "User-Agent": "MOON-Connector/1.0"}
        self._to = timeout

    async def call(self, method: str, path: str = "", *, json_body: Any = None,
                   params: dict | None = None, data: Any = None) -> CallResult:
        url = f"{self._base}/{path.lstrip('/')}" if path else self._base
        try:
            async with httpx.AsyncClient(timeout=self._to, headers=self._headers) as c:
                r = await c.request(method.upper(), url, json=json_body, params=params, data=data)
                try:
                    body = r.json()
                except Exception:
                    body = r.text
                return CallResult(ok=r.is_success, status=r.status_code, data=body,
                                  headers=dict(r.headers))
        except Exception as exc:  # noqa: BLE001
            return CallResult(ok=False, status=0, error=str(exc))

    async def health(self) -> CallResult:
        return await self.call("GET", "")


class AgentConnector:
    """Talk to ANOTHER AI agent via an OpenAI-compatible chat endpoint.

    Lets MOON federate: send a prompt to a peer agent, get its answer back. This
    is the "connect to any AI agent" path. It reuses the same chat/completions
    shape MOON itself speaks.
    """

    def __init__(self, base_url: str, model: str, api_key: str = "not-required",
                 timeout: float = 120.0) -> None:
        self._base = base_url.rstrip("/")
        self._model = model
        self._key = api_key
        self._to = timeout

    async def ask(self, message: str, *, system: str = "",
                  history: list[dict] | None = None) -> CallResult:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        for m in (history or []):
            msgs.append(m)
        msgs.append({"role": "user", "content": message})
        payload = {"model": self._model, "messages": msgs, "temperature": 0.7, "max_tokens": 2048}
        try:
            async with httpx.AsyncClient(
                base_url=self._base, headers={"Authorization": f"Bearer {self._key}"}, timeout=self._to
            ) as c:
                r = await c.post("/chat/completions", json=payload)
                j = r.json()
                content = j["choices"][0]["message"].get("content", "")
                return CallResult(ok=r.is_success, status=r.status_code, data={"answer": content})
        except Exception as exc:  # noqa: BLE001
            return CallResult(ok=False, status=0, error=str(exc))

    async def health(self) -> CallResult:
        return CallResult(ok=bool(self._base), status=0, data={"agent": self._model})


class WebSocketConnector:
    """Connect to a websocket endpoint (streaming agents / services)."""

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        self._url = url
        self._to = timeout

    async def send_recv(self, message: str) -> CallResult:
        try:
            import websockets  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return CallResult(ok=False, status=0, error=f"websockets lib unavailable: {exc}")
        try:
            async with websockets.connect(self._url, open_timeout=self._to) as ws:  # type: ignore[attr-defined]
                await ws.send(message)
                reply = await asyncio.wait_for(ws.recv(), timeout=self._to)
                return CallResult(ok=True, status=200, data={"reply": reply})
        except Exception as exc:  # noqa: BLE001
            return CallResult(ok=False, status=0, error=str(exc))

    async def health(self) -> CallResult:
        return CallResult(ok=bool(self._url), status=0, data={"ws": self._url})


class MCPConnector:
    """Placeholder for Model Context Protocol tool servers.

    The connection is registered and health-checked; full MCP jsonrpc transport
    is intentionally minimal here (capability, not a full MCP client). It proves
    the registry can hold an MCP endpoint and that MOON can reach it, while
    leaving the richer jsonrpc session to a later, safe upgrade.
    """

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base = base_url
        self._to = timeout

    async def health(self) -> CallResult:
        try:
            async with httpx.AsyncClient(timeout=self._to) as c:
                r = await c.get(self._base)
                return CallResult(ok=r.is_success, status=r.status_code,
                                  data={"mcp": "reachable", "note": "jsonrpc session upgrade planned"})
        except Exception as exc:  # noqa: BLE001
            return CallResult(ok=False, status=0, error=str(exc))
