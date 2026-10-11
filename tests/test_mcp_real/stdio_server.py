"""Minimal MCP stdio server over JSONRPC-over-stdin lines."""
import asyncio
import json
import sys

async def _handle(msg):
    method = msg.get("method")
    if method == "initialize":
        resp = {"jsonrpc": "2.0", "id": msg.get("id"),
                "result": {"protocolVersion": "2024-11-05",
                           "capabilities": {},
                           "serverInfo": {"name": "minios", "version": "0.1.0"}}}
        print(json.dumps(resp)); sys.stdout.flush()
    if method == "tools/list":
        resp = {"jsonrpc": "2.0", "id": msg.get("id"),
                "result": {"tools": [{"name": "echo",
                                      "description": "echo args",
                                      "inputSchema": {"type": "object",
                                                      "properties": {"msg": {"type": "string"}}}}]}}
        print(json.dumps(resp)); sys.stdout.flush()
    if method == "tools/call":
        args = msg.get("params", {}).get("arguments", {})
        resp = {"jsonrpc": "2.0", "id": msg.get("id"),
                "result": {"content": [{"type": "text",
                                        "text": args.get("msg", "hello")}]}}
        print(json.dumps(resp)); sys.stdout.flush()
    return resp

async def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        try:
            resp = await _handle(msg)
            print(json.dumps(resp)); sys.stdout.flush()
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": str(e)}})); sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(main())
