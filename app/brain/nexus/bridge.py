"""MOON NEXUS bridge (ADDITIVE, optional).

This is the genuine value-add from the attached ``MOON_NEXUS_SINGLE_FILE.py``
payload, re-homed into MOON WITHOUT replacing any existing code.

The attached ``futuristic/`` UI speaks the ``MOON_AGENT_BRIDGE/1`` protocol over
``ws://<host>:8765/moon`` and a static HTTP server on ``:8787``. It expects a
MOON agent to connect, then shows a live avatar + terminal driven by MOON's
REAL runtime state. This bridge provides exactly that server, wired to MOON's
own Orchestrator brain -- so the NEXUS UI becomes a real, brain-connected
front-end on top of MOON.

It is fully additive:
  * MOON's existing terminal interface (port 8777, app/terminal_interface.py)
    is NOT touched.
  * This runs only when you launch it explicitly (see run_nexus_bridge.py).
  * The terminal bridge is bound to 127.0.0.1 and reuses MOON's security
    policy concept (the attached security/policy.py is embedded as the gate).

Run:  python web/nexus/run_nexus_bridge.py
Then open the NEXUS UI at http://127.0.0.1:8787/
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

import websockets

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
UI_DIR = HERE / "futuristic"          # the attached UI files, dropped in verbatim
DEFAULT_HOST = "127.0.0.1"
DEFAULT_WS_PORT = 8765                # NEXUS UI connects here at /moon
DEFAULT_UI_PORT = 8787                # NEXUS UI served here


# ---------------------------------------------------------------------------
# Conservative command gate (re-used from the attached security/policy.py).
# The NEXUS terminal can run real shell commands on the operator's box, so the
# same "safe by default" policy MOON uses is applied here too.
# ---------------------------------------------------------------------------
BLOCKED = [
    r"rm\s+-rf\s+(/|~|\$HOME|\.)",
    r"mkfs(\s|$)",
    r"dd\s+.*of=/dev/",
    r":\(\)\s*\{\s*:|:&\s*\}$",
    r"(^|\s)(shutdown|reboot)(\s|$)",
    r"Remove-Item\s+.*-Recurse.*-Force",
    r"Stop-Computer",
    r"Restart-Computer",
    r"format\s+[A-Za-z]:",
]
CONFIRM = [
    r"\bsudo\b", r"\bsu\b", r"\brm\s+", r"\bmv\s+", r"\bchmod\b", r"\bchown\b",
    r"\bmount\b", r"\bumount\b", r"\bkill\b", r"\bpkill\b", r"\btaskkill\b",
    r"\bwinget\s+uninstall\b", r"\bapt(-get)?\s+(remove|purge|autoremove)\b",
]


def evaluate_command(command: str) -> tuple[bool, bool, str]:
    """(allowed, needs_confirmation, reason)."""
    if not command.strip():
        return False, False, "Empty command"
    for p in BLOCKED:
        if re.search(p, command, re.IGNORECASE):
            return False, False, "Blocked destructive command"
    for p in CONFIRM:
        if re.search(p, command, re.IGNORECASE):
            return False, True, "Explicit confirmation required"
    return True, False, "OK"


# ---------------------------------------------------------------------------
# Terminal executor (real, but gated + bound to the operator's own host only).
# ---------------------------------------------------------------------------
import os
import platform
import signal


class NexusTerminal:
    def __init__(self, cwd: str | None = None) -> None:
        self.system = platform.system()
        # Default to the MOON repo root so command execution is anchored to the
        # project regardless of how the bridge process was launched.
        repo = Path(__file__).resolve().parents[3]
        self.cwd = os.path.abspath(cwd or repo)

    def shell(self) -> str:
        if self.system == "Windows":
            root = os.environ.get("SystemRoot", r"C:\Windows")
            ps = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
            return ps if os.path.exists(ps) else os.environ.get("COMSPEC", "cmd.exe")
        return os.environ.get("SHELL", "/bin/sh")

    def argv(self, command: str) -> list[str]:
        sh = self.shell()
        if self.system == "Windows":
            if sh.lower().endswith("cmd.exe"):
                return [sh, "/d", "/s", "/c", command]
            return [sh, "-NoLogo", "-NoProfile", "-Command", command]
        return [sh, "-lc", command]

    async def run(self, command: str, timeout: float = 300):
        proc = await asyncio.create_subprocess_exec(
            *self.argv(command), cwd=self.cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=(self.system != "Windows"),
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as exc:  # noqa: BLE001
                logger.warning("term SIGTERM failed, killing: %s", exc)
                proc.kill()
            return proc.returncode or 124, "", "Timed out and terminated."
        return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")


# ---------------------------------------------------------------------------
# WebSocket bridge: connects the NEXUS UI to MOON's real brain.
# ---------------------------------------------------------------------------
class NexusBridge:
    def __init__(self, ws_host: str, ws_port: int, ui_port: int, orchestrator=None) -> None:
        self.ws_host = ws_host
        self.ws_port = ws_port
        self.ui_port = ui_port
        self.orch = orchestrator
        self.term = NexusTerminal()
        self.clients: set = set()
        self.moon_clients: set = set()

    async def publish_from_moon(self, text: str) -> None:
        """Push an avatar 'speak' event to connected NEXUS UIs (driven by MOON)."""
        msg = json.dumps({"type": "avatar.speak", "text": text})
        dead = set()
        for ws in list(self.clients):
            try:
                await ws.send(msg)
            except Exception as exc:  # noqa: BLE001
                logger.debug("nexus UI send failed, dropping client: %s", exc)
                dead.add(ws)
        self.clients -= dead

    async def handler(self, ws):
        self.clients.add(ws)
        try:
            await ws.send(json.dumps({
                "type": "terminal.ready",
                "protocol": "MOON_AGENT_BRIDGE/1",
                "role": "avatar_terminal",
                "system": {"os": self.term.system, "shell": self.term.shell(), "cwd": self.term.cwd},
                "capabilities": [
                    "terminal.exec", "terminal.cancel", "terminal.cwd",
                    "avatar.state", "avatar.speak", "system.info",
                    "moon.event.passthrough", "moon.capability.sync",
                ],
                "moon_owns": ["brain", "memory", "retriever", "planner",
                              "tool_selection", "personality", "agent_functions"],
            }))
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.debug("nexus bridge dropped non-JSON frame: %s", exc)
                    continue
                await self.process(ws, msg)
        finally:
            self.clients.discard(ws)
            self.moon_clients.discard(ws)

    async def process(self, ws, msg) -> None:
        typ = msg.get("type")
        if typ == "hello":
            await ws.send(json.dumps({
                "type": "hello.ack", "agent": "MOON NEXUS BRIDGE", "protocol": "MOON_AGENT_BRIDGE/1",
                "message": "MOON remains the owner of all agent functions.",
            }))
            return
        if typ == "system.info":
            await ws.send(json.dumps({"type": "system.info",
                                      "system": {"os": self.term.system, "shell": self.term.shell(), "cwd": self.term.cwd}}))
            return
        if typ == "terminal.exec":
            command = str(msg.get("command", "")).strip()
            req_id = msg.get("id")
            allowed, confirm, reason = evaluate_command(command)
            if not allowed:
                await ws.send(json.dumps({"type": "terminal.result", "id": req_id,
                                          "exit_code": 1, "stdout": "",
                                          "stderr": f"[MOON NEXUS] blocked: {reason}"}))
                return
            if confirm:
                await ws.send(json.dumps({"type": "terminal.result", "id": req_id,
                                          "exit_code": 1, "stdout": "",
                                          "stderr": f"[MOON NEXUS] needs confirmation: {reason} (run from a shell, not the UI)."}))
                return
            await ws.send(json.dumps({"type": "terminal.start", "id": req_id, "command": command}))
            code, out, err = await self.term.run(command)
            await ws.send(json.dumps({"type": "terminal.output", "id": req_id, "stream": "stdout", "data": out + err}))
            await ws.send(json.dumps({"type": "terminal.result", "id": req_id, "exit_code": code, "stdout": out, "stderr": err}))
            return
        # moon.chat / moon.* -> route to the REAL MOON brain (Orchestrator).
        # Uses run_task so the UI receives MOON's genuine cognition stages and
        # reasoning trace, and the final reply is streamed as avatar.speak.
        if typ in ("moon.chat", "chat") or str(typ).startswith("moon."):
            text = str(msg.get("text") or msg.get("payload") or "")
            if self.orch is not None and text:
                req_id = msg.get("id") or "chat"
                await ws.send(json.dumps({"type": "avatar.state", "state": "thinking",
                                          "detail": "MOON is reasoning…"}))

                async def on_event(ev: dict) -> None:
                    stage = ev.get("stage")
                    detail = ev.get("detail", "")
                    if stage == "routing":
                        await ws.send(json.dumps({"type": "avatar.state", "state": "routing",
                                                  "detail": f"routing -> {detail}"}))
                    elif stage == "thinking":
                        await ws.send(json.dumps({"type": "avatar.state", "state": "thinking",
                                                  "detail": detail}))
                    elif stage == "tool_call":
                        await ws.send(json.dumps({"type": "avatar.state", "state": "tool",
                                                  "detail": f"tool: {detail}"}))
                    elif stage == "reflection":
                        await ws.send(json.dumps({"type": "avatar.state", "state": "reflecting",
                                                  "detail": detail}))
                    elif stage == "consistency":
                        await ws.send(json.dumps({"type": "avatar.state", "state": "verifying",
                                                  "detail": detail}))

                try:
                    from app.models.task import Task

                    task = Task.create(text)
                    task.mark_running()
                    result = await self.orch.run_task(task, on_event=on_event)
                    reply = result.result or ""
                    await ws.send(json.dumps({"type": "avatar.speak", "id": req_id, "text": reply}))
                    await ws.send(json.dumps({"type": "avatar.state", "state": "idle", "detail": "ready"}))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("nexus moon.chat failed: %s", exc)
                    # Best-effort fallback to the fast single-call path.
                    try:
                        reply = await self.orch.quick_reply(text)
                        await ws.send(json.dumps({"type": "avatar.speak", "id": req_id, "text": reply}))
                    except Exception as exc2:  # noqa: BLE001
                        logger.warning("nexus fallback quick_reply failed: %s", exc2)
            return

    async def run_forever(self) -> None:
        async with websockets.serve(self.handler, self.ws_host, self.ws_port, ping_interval=20, ping_timeout=20):
            logger.info("MOON NEXUS bridge on ws://%s:%s/moon", self.ws_host, self.ws_port)
            await asyncio.Future()  # run forever
