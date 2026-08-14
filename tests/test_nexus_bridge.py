"""Tests for the additive MOON NEXUS bridge (web/nexus + app/brain/nexus)."""

from __future__ import annotations

import asyncio

from app.brain.nexus.bridge import NexusBridge, evaluate_command


def test_command_gate_blocks_destructive():
    ok, _confirm, _reason = evaluate_command("rm -rf /")
    assert ok is False and "Blocked" in _reason


def test_command_gate_requires_confirmation_for_sudo():
    # `sudo reboot` is destructive -> blocked outright (safer than confirm).
    ok, _confirm, reason = evaluate_command("sudo reboot")
    assert ok is False and _confirm is False and "Blocked" in reason
    # Non-destructive `sudo` -> confirmation required.
    ok, confirm, _reason = evaluate_command("sudo ls /root")
    assert ok is False and confirm is True


def test_command_gate_allows_safe_commands():
    ok, _confirm, _reason = evaluate_command("ls -la && echo hi")
    assert ok is True and _confirm is False


def test_bridge_resolution_defaults_to_repo_root():
    # NexusTerminal anchors to the MOON repo root, never CWD/cwd-of-launcher.
    b = NexusBridge("127.0.0.1", 8799, 8798)
    assert b.term.cwd.endswith("/Projects/MOON") or b.term.cwd.endswith("/MOON")
    assert b.term.system


def test_bridge_protocol_handshake():
    """Spin the bridge on free ports and verify a NEXUS-UI client gets the
    real terminal-ready handshake + can run a gated command end-to-end."""
    import json

    import websockets

    b = NexusBridge("127.0.0.1", 8799, 8798)

    async def run():
        # Start the WS server only (UI is just static files).
        server = await websockets.serve(b.handler, "127.0.0.1", 8799)
        try:
            async with websockets.connect("ws://127.0.0.1:8799/moon") as ws:
                ready = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert ready["type"] == "terminal.ready"
                assert "moon_owns" in ready and "brain" in ready["moon_owns"]
                await ws.send(json.dumps({"type": "hello", "agent": "T", "role": "UI",
                                          "protocol": "MOON_AGENT_BRIDGE/1"}))
                ack = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert ack["type"] == "hello.ack"
                await ws.send(json.dumps({"type": "terminal.exec", "id": "x1",
                                          "command": "echo NEXUS_BRIDGE_OK"}))
                got = []
                while True:
                    m = json.loads(await asyncio.wait_for(ws.recv(), 8))
                    got.append(m["type"])
                    if m["type"] == "terminal.result":
                        assert m["exit_code"] == 0
                        assert "NEXUS_BRIDGE_OK" in m["stdout"]
                        break
                assert "terminal.start" in got and "terminal.output" in got
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(run())
