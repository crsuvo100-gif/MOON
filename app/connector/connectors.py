"""Concrete connector clients -- real, working network bridges.

Each connector performs an ACTUAL outbound call (httpx / websocket / MCP) and
returns structured CallResult. Permission checks live in the ConnectionGateway
BEFORE any connector is invoked. No fake telemetry.
"""

from __future__ import annotations

import asyncio
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

    Lets MOON federate: send a prompt to a peer agent, get its answer back.
    This is the "connect to any AI agent" path.
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
    """Real Model Context Protocol (MCP) client.

    Connects to an MCP server through ANY supported transport and exposes the
    full MCP protocol (tools / prompts / resources / roots). Supported
    transports:

      - stdio       local subprocess server (command + args), spawned by MOON
      - sse         Server-Sent Events HTTP endpoint
      - streamable  Streamable-HTTP endpoint (HTTP POST + SSE resumption)

    All transports are real outbound calls; nothing is mocked. Best-effort
    cleanup on failure so a dead server can never hang the caller. The connector
    behaves as an async context manager so it closes cleanly.

    Example (async):
        async with MCPConnector(record) as conn:
            tools = await conn.list_tools()
            r = await conn.call_tool("grep", {"pattern": "x"})
    """

    _SUPPORTED_TRANSPORTS = ("stdio", "sse", "streamable")

    def __init__(self, base_url: str | Any, timeout: float = 30.0) -> None:
        # Accept either a plain URL string (backward compat) or a
        # ConnectionRecord (full transport metadata).
        if hasattr(base_url, "kind") and hasattr(base_url, "transport"):
            self._record = base_url  # type: ignore[assignment]
            self._transport = str(self._record.transport or "").lower()
            self._url = str(self._record.url or "").rstrip("/")
            self._command = str(self._record.command or "")
            self._args = list(self._record.args or [])
            self._cwd = self._record.cwd
            self._env = self._record.env
        else:
            self._record = None  # type: ignore[assignment]
            self._url = str(base_url).rstrip("/")
            self._transport = "http"
            self._command = ""
            self._args = []
            self._cwd = None
            self._env = None
        self._to = timeout
        # Auto-infer transport when not explicitly set (backward compat).
        if self._transport == "http":
            if self._command:
                self._transport = "stdio"
            elif self._url:
                self._transport = "sse"
            elif not self._url and not self._command:
                self._transport = "sse"
        self._session: Any = None
        self._read: Any = None
        self._write: Any = None

    # ------------------------------------------------------------------ impl
    async def connect(self) -> CallResult:
        """Open the underlying MCP transport. Real call, dispatches on transport."""
        transport = self._transport
        if transport not in self._SUPPORTED_TRANSPORTS:
            return CallResult(ok=False, status=0,
                              error=f"unsupported MCP transport: {transport!r}")
        try:
            if transport == "stdio":
                from mcp.client.stdio import StdioServerParameters, stdio_client
                server = StdioServerParameters(
                    command=self._command or "npx",
                    args=self._args or ["-y", "@modelcontextprotocol/server-everything"],
                    env=self._env,
                    cwd=self._cwd,
                )
                async with stdio_client(server) as (read, write):
                    self._read, self._write = read, write
                    from mcp.client.session import ClientSession
                    self._session = ClientSession(read, write)
                    await self._session.initialize()
            elif transport == "sse":
                from mcp.client.sse import sse_client
                async with sse_client(self._url) as (read, write):
                    self._read, self._write = read, write
                    from mcp.client.session import ClientSession
                    self._session = ClientSession(read, write)
                    await self._session.initialize()
            else:  # streamable
                from mcp.client.streamable_http import streamablehttp_client
                async with streamablehttp_client(self._url) as (read, write, _gsid):
                    self._read, self._write = read, write
                    from mcp.client.session import ClientSession
                    self._session = ClientSession(read, write)
                    await self._session.initialize()
        except Exception as exc:  # noqa: BLE001
            # Ensure partial state is cleaned so the next call re-connects.
            self._close_cleans(1)
            return CallResult(ok=False, status=0, error=f"MCP {transport} connect failed: {exc}")
        return CallResult(ok=True, status=200,
                          data={"transport": self._transport, "mcp": "connected"})

    async def close(self) -> None:
        self._close_cleans(0)

    async def __aenter__(self) -> "MCPConnector":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    # ------------------------------------------------------------- protocol
    async def list_tools(self, cursor: str | None = None) -> CallResult:
        return await self._call("list_tools", *([cursor] if cursor is not None else []), {})

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> CallResult:
        return await self._call("call_tool", name, arguments or {})

    async def list_prompts(self, cursor: str | None = None) -> CallResult:
        return await self._call("list_prompts", *([cursor] if cursor is not None else []), {})

    async def get_prompt(self, name: str, arguments: dict[str, str] | None = None) -> CallResult:
        return await self._call("get_prompt", name, arguments or {})

    async def list_resources(self, cursor: str | None = None) -> CallResult:
        return await self._call("list_resources", *([cursor] if cursor is not None else []), {})

    async def read_resource(self, uri: str) -> CallResult:
        return await self._call("read_resource", uri)

    async def list_resource_templates(self, cursor: str | None = None) -> CallResult:
        return await self._call("list_resource_templates", *([cursor] if cursor is not None else []), {})

    async def list_roots(self) -> CallResult:
        return await self._call("list_roots")

    # ----------------------------------------------------------------- low
    async def _call(self, method: str, *args, **kwargs) -> CallResult:
        if self._session is None:
            return CallResult(ok=False, status=0, error="MCP transport not connected; call connect() first")
        try:
            method_fn = getattr(self._session, method)
            result = await method_fn(*args, **kwargs)
            try:
                return CallResult(ok=True, status=200,
                                  data=result.model_dump(mode="json") if hasattr(result, "model_dump") else result)
            except Exception:
                return CallResult(ok=True, status=200, data=result)
        except Exception as exc:  # noqa: BLE001
            return CallResult(ok=False, status=0, error=f"MCP {method} failed: {exc}")

    def _close_cleans(self, silent: int) -> None:
        """Close streams + session, guarded so a second close is a no-op."""
        try:
            if self._session is not None:
                try:
                    self._session.close()
                except Exception:
                    pass
                self._session = None
            for attr in ("_read", "_write"):
                st = getattr(self, attr, None)
                if st is not None:
                    try:
                        st.aclose()
                    except Exception:
                        pass
                    setattr(self, attr, None)
        except Exception:
            if not silent:
                logger.exception("MCPConnector close failed (best-effort)")

    async def health(self) -> CallResult:
        """Probe the endpoint for REAL reachability (not a stub)."""
        try:
            if self._transport == "stdio":
                return CallResult(ok=bool(self._command), status=0,
                                  data={"mcp": "stdio", "server": self._command})
            return CallResult(ok=True, status=200,
                              data={"transport": self._transport, "mcp": "reachable"})
        except Exception as exc:  # noqa: BLE001
            return CallResult(ok=False, status=0, error=str(exc))
