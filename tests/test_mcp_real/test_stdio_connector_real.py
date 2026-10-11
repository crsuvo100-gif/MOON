"""Real stdio MCP server -> MCPConnector outbound call. PROves real stdio transport.

A local minios JSONRPC-over-stdin/stdout MCP server is spawned as a subprocess;
MCPConnector's stdio_client connects to it over real stdin/stdout and performs a
full round trip: initialize -> tools/list -> tools/call.
"""
import asyncio
import sys
from pathlib import Path

import pytest

from app.connector.connectors import MCPConnector  # noqa: E402


@pytest.mark.asyncio
async def test_stdio_connector_real():
    server_script = Path(__file__).resolve().parent / "stdio_server.py"

    async def run_connector():
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(server_script),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            class R:
                kind = "mcp"
                transport = "stdio"
                url = ""
                command = sys.executable
                args = [str(server_script)]
                cwd = None
                env = None

            conn = MCPConnector(R())
            res = await conn.connect()
            assert res.ok, f"stdio connect failed: {res.error}"
            assert res.status == 200, f"expected 200, got {res.status}"

            t = await conn.list_tools()
            assert t.ok, f"list_tools failed: {t.error}"
            names = [(x.get("name") if isinstance(x, dict) else x) for x in (t.data or {}).get("tools", [])]
            assert "echo" in names, f"expected 'echo' tool, got {names}"

            c = await conn.call_tool("echo", {"msg": "MOON接続は実動作!"})
            assert c.ok, f"call_tool failed: {c.error}"
            content = (c.data or {}).get("content", [{}])[0].get("text", "")
            assert "MOON接続は実動作!" in content, f"unexpected content: {content}"
        finally:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                pass

    await asyncio.wait_for(run_connector(), timeout=30.0)
