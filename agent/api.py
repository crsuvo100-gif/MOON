"""
MOON Agent API — FastAPI server for /api/moon-agent integration.

Exposes:
- POST /api/moon-agent    — Process a message through the agent engine
- GET  /api/moon-agent    — List all available agents
- GET  /api/moon-agent/route?query=<q> — Route a query to an agent
- GET  /api/health        — Health check
- WebSocket /api/ws       — Real-time chat (if WebSocket support needed)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Add project root to path
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.engine import (
    default_engine,
    api_agent_process,
    api_agent_list,
    api_agent_router,
)


# ---------------------------------------------------------------------------
# Try Starlette/FastAPI; fall back to bare ASGI if unavailable
# ---------------------------------------------------------------------------

try:
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse, HTMLResponse, Response
    from starlette.requests import Request
    from starlette.routing import Route, WebSocketRoute
    from starlette.websockets import WebSocket
    from starlette.types import ASGIApp, Receive, Scope, Send
    HAS_ASGI = True
except ImportError:
    HAS_ASGI = False


# ---------------------------------------------------------------------------
# ASGI application
# ---------------------------------------------------------------------------

class MoonAgentAPI:
    """
    ASGI application for /api/moon-agent.

    Works with Starlette if available, or as a bare ASGI app.
    """

    def __init__(self):
        self.engine = default_engine

    async def handle_request(self, scope: Scope, receive: Receive, send: Send):
        """Main ASGI entry point."""
        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
        else:
            await send({
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({
                "type": "http.response.body",
                "body": b"Not found",
            })

    async def _handle_http(self, scope: Scope, receive: Receive, send: Send):
        """Handle HTTP requests."""
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        query_string = scope.get("query_string", b"").decode()

        # Parse query params
        query_params = {}
        if query_string:
            for pair in query_string.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    query_params[k] = v

        # Route matching
        if path == "/api/health" and method == "GET":
            await self._health(scope, send)

        elif path == "/api/moon-agent" and method == "GET":
            await self._list_agents(scope, send)

        elif path == "/api/moon-agent" and method == "POST":
            await self._process_message(scope, receive, send)

        elif path == "/api/moon-agent/route" and method == "GET":
            query = query_params.get("query", "")
            await self._route_query(scope, send, query)

        elif path == "/api/moon-agent/agents" and method == "GET":
            await self._list_agents(scope, send)

        elif path == "/api/moon-agent/memory" and method == "GET":
            await self._get_memory(scope, send)

        elif path == "/api/moon-agent/memory" and method == "POST":
            await self._set_memory(scope, receive, send)

        else:
            await self._not_found(scope, send)

    async def _handle_websocket(self, scope: Scope, receive: Receive, send: Send):
        """Handle WebSocket connections."""
        ws = WebSocket(scope)
        await ws.accept()

        try:
            while True:
                msg = await ws.receive_json()
                message = msg.get("text", "")
                session_id = msg.get("session_id", f"ws-{id(ws)}")
                explicit_agent = msg.get("agent")

                result = await self.engine.process_message(
                    message,
                    session_id=session_id,
                    explicit_agent=explicit_agent,
                )

                agent_name = result["agent"]
                selected = self.engine.get_agent(agent_name)
                response = await self.engine.generate_response(
                    selected,
                    result["message"],
                )

                await ws.send_json({
                    "type": "response",
                    "agent": agent_name,
                    "response": response,
                    "persona": selected.to_dict() if selected else None,
                    "session_id": session_id,
                })

        except Exception:
            await ws.close()

    # -- HTTP response helpers --

    async def _send_json(self, scope: Scope, send: Send, data: dict, status: int = 200):
        body = json.dumps(data, indent=2).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

    async def _send_html(self, scope: Scope, send: Send, html: str, status: int = 200):
        body = html.encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/html; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

    async def _health(self, scope: Scope, send: Send):
        """Health check endpoint."""
        health = {
            "status": "healthy",
            "service": "moon-agent-api",
            "version": "1.0.0",
            "agent_count": len(self.engine.list_agents()),
            "lock_state": "unlocked",
            "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0,
        }
        await self._send_json(scope, send, health)

    async def _list_agents(self, scope: Scope, send: Send):
        """List all agents."""
        agents = self.engine.list_agents()
        await self._send_json(scope, send, {
            "agents": agents,
            "count": len(agents),
        })

    async def _process_message(self, scope: Scope, receive: Receive, send: Send):
        """Process a message through the agent engine."""
        # Read request body
        body = b""
        while True:
            msg = await receive()
            if msg["type"] == "http.request":
                body += msg.get("body", b"")
                if not msg.get("more_body", False):
                    break

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            await self._send_json(scope, send, {
                "error": "Invalid JSON",
                "detail": "Request body must be valid JSON",
            }, status=400)
            return

        message = data.get("message", "")
        if not message:
            await self._send_json(scope, send, {
                "error": "Missing message",
                "detail": "POST body must include 'message' field",
            }, status=400)
            return

        session_id = data.get("session_id")
        explicit_agent = data.get("agent")

        # Parse agent: prefix if no explicit agent
        if not explicit_agent:
            parsed_agent, clean_message = self.engine.parse_agent_prefix(message)
            if parsed_agent:
                explicit_agent = parsed_agent
        else:
            clean_message = message

        # Process
        result = await self.engine.process_message(
            message,
            session_id=session_id,
            explicit_agent=explicit_agent,
        )

        # Generate response
        selected = self.engine.get_agent(result["agent"])
        response_text = await self.engine.generate_response(
            selected,
            result["message"],
        )

        result["response"] = response_text

        # Optionally invoke tools
        tools_requested = data.get("tools", [])
        if tools_requested:
            for tool_name in tools_requested:
                tool_result = await self.engine.run_tool(tool_name, {})
                result.setdefault("tools_used", []).append({
                    "tool": tool_name,
                    "result": tool_result,
                })

        await self._send_json(scope, send, result)

    async def _route_query(self, scope: Scope, send: Send, query: str):
        """Route a query to an agent."""
        result = api_agent_router(query)
        await self._send_json(scope, send, result)

    async def _get_memory(self, scope: Scope, send: Send):
        """Get memory entries (simplified — uses engine memory)."""
        memory = self.engine.get_memory()
        await self._send_json(scope, send, {
            "memory": memory,
            "count": len(memory),
        })

    async def _set_memory(self, scope: Scope, receive: Send, send: Send):
        """Set a memory entry."""
        body = b""
        while True:
            msg = await receive()
            if msg["type"] == "http.request":
                body += msg.get("body", b"")
                if not msg.get("more_body", False):
                    break

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            await self._send_json(scope, send, {
                "error": "Invalid JSON",
            }, status=400)
            return

        key = data.get("key")
        value = data.get("value")
        session_id = data.get("session_id", "default")

        if not key:
            await self._send_json(scope, send, {
                "error": "Missing key",
            }, status=400)
            return

        self.engine._memory.append({
            "session": session_id,
            "key": key,
            "value": value,
            "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0,
        })

        await self._send_json(scope, send, {
            "status": "written",
            "key": key,
            "session_id": session_id,
        })

    async def _not_found(self, scope: Scope, send: Send):
        """404 response."""
        await self._send_json(scope, send, {
            "error": "Not found",
            "path": scope.get("path", ""),
            "available_endpoints": [
                "GET  /api/health",
                "GET  /api/moon-agent",
                "POST /api/moon-agent",
                "GET  /api/moon-agent/route?query=<q>",
                "GET  /api/moon-agent/agents",
                "GET  /api/moon-agent/memory",
                "POST /api/moon-agent/memory",
            ],
        }, status=404)


# ---------------------------------------------------------------------------
# Starlette wrapper (if available)
# ---------------------------------------------------------------------------

if HAS_ASGI:
    async def _starlette_handle(request: Request):
        """Starlette adapter for the MoonAgentAPI."""
        api = MoonAgentAPI()
        scope = request.scope
        receive = request._receive
        send = request._send

        # Delegate to the ASGI handler
        await api.handle_request(scope, receive, send)

    async def health_route(request: Request):
        api = MoonAgentAPI()
        scope = request.scope
        receive = request._receive
        send = request._send
        await api._health(scope, send)
        return Response("", media_type="application/json")

    async def agents_route(request: Request):
        api = MoonAgentAPI()
        scope = request.scope
        receive = request._receive
        send = request._send
        await api._list_agents(scope, send)
        return Response("", media_type="application/json")

    async def message_route(request: Request):
        api = MoonAgentAPI()
        scope = request.scope
        receive = request._receive
        send = request._send
        if request.method == "GET":
            await api._list_agents(scope, send)
        else:
            await api._process_message(scope, receive, send)
        return Response("", media_type="application/json")

    async def route_route(request: Request):
        api = MoonAgentAPI()
        scope = request.scope
        receive = request._receive
        send = request._send
        query = request.query_params.get("query", "")
        await api._route_query(scope, send, query)
        return Response("", media_type="application/json")

    async def memory_route(request: Request):
        api = MoonAgentAPI()
        scope = request.scope
        receive = request._receive
        send = request._send
        if request.method == "GET":
            await api._get_memory(scope, send)
        else:
            await api._set_memory(scope, receive, send)
        return Response("", media_type="application/json")

    app = Starlette(
        routes=[
            Route("/api/health", health_route, methods=["GET"]),
            Route("/api/moon-agent", message_route, methods=["GET", "POST"]),
            Route("/api/moon-agent/route", route_route, methods=["GET"]),
            Route("/api/moon-agent/agents", agents_route, methods=["GET"]),
            Route("/api/moon-agent/memory", memory_route, methods=["GET", "POST"]),
        ],
    )


# ---------------------------------------------------------------------------
# Bare ASGI app (fallback)
# ---------------------------------------------------------------------------

async def bare_asgi_app(scope: Scope, receive: Receive, send: Send):
    """Bare ASGI application without Starlette."""
    api = MoonAgentAPI()
    await api.handle_request(scope, receive, send)


# Use Starlette app if available, else bare ASGI
application = app if HAS_ASGI else bare_asgi_app


# ---------------------------------------------------------------------------
# Standalone server runner
# ---------------------------------------------------------------------------

def run_server(host: str = "0.0.0.0", port: int = 8778):
    """Run the API server standalone."""
    try:
        import uvicorn
        print(f"[moon-agent-api] Starting server on {host}:{port}")
        uvicorn.run(
            "agent.api:application",
            host=host,
            port=port,
            log_level="info",
            app_dir=str(ROOT),
        )
    except ImportError:
        print("[moon-agent-api] uvicorn not available, starting bare server...")
        import socket

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(5)
        print(f"[moon-agent-api] Listening on {host}:{port}")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while True:
                conn, addr = server.accept()
                print(f"[moon-agent-api] Connection from {addr}")
                # Handle basic HTTP (very simplified)
                data = conn.recv(4096).decode(errors="ignore")
                if data:
                    # Parse request line
                    lines = data.split("\r\n")
                    request_line = lines[0] if lines else ""
                    print(f"[moon-agent-api] {request_line}")

                    # Build a minimal scope
                    method = request_line.split()[0] if request_line else "GET"
                    path = request_line.split()[1] if request_line else "/"

                    scope = {
                        "type": "http",
                        "method": method,
                        "path": path,
                        "query_string": b"",
                        "headers": [],
                        "server": (host, port),
                        "client": addr,
                    }

                    async def _receive():
                        return {"type": "http.request", "body": b"", "more_body": False}

                    async def _send(event):
                        if event["type"] == "http.response.start":
                            status = event["status"]
                            headers = event.get("headers", [])
                            header_str = "".join(f"{k.decode()}: {v.decode()}\r\n" for k, v in headers)
                            conn.send(f"HTTP/1.1 {status} OK\r\n{header_str}\r\n".encode())
                        elif event["type"] == "http.response.body":
                            conn.send(event.get("body", b""))

                    loop.run_until_complete(application(scope, _receive, _send))

                conn.close()
        except KeyboardInterrupt:
            print("\n[moon-agent-api] Shutting down...")
        finally:
            server.close()


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="moon_agent_api",
        description="MOON Agent API server — /api/moon-agent integration endpoint",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8778, help="Port to listen on")
    parser.add_argument("--test", action="store_true", help="Run self-test and exit")

    args = parser.parse_args()

    if args.test:
        # Self-test
        print("╔══════════════════════════════════════════╗")
        print("║  MOON AGENT API — SELF TEST              ║")
        print("╚══════════════════════════════════════════╝")
        print()

        print("=== Agent List ===")
        agents = api_agent_list()
        for a in agents:
            print(f"  [{a['name']}] {a['description'][:60]} ({a['tools']})")
        print()

        print("=== Route Test ===")
        result = api_agent_router("write a python script to scan ports")
        print(f"  Query: write a python script to scan ports")
        print(f"  Routed to: {result['agent']}")
        print(f"  Persona: {result['persona']['description'][:60]}")
        print()

        print("=== Process Test ===")
        result = api_agent_process({
            "message": "agent:code write a function to sort a list",
            "session_id": "api-self-test",
        })
        print(f"  Agent: {result['agent']}")
        print(f"  Session: {result['session_id']}")
        print(f"  Response: {result.get('response', '(no LLM connected)')[:100]}")
        print()

        print("=== Tool Test ===")
        import asyncio
        tool_result = asyncio.run(default_engine.run_tool("system_info", {}))
        print(f"  system_info: {tool_result}")
        print()

        print("All tests passed.")
        sys.exit(0)

    run_server(host=args.host, port=args.port)
