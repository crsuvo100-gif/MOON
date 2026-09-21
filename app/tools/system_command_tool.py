"""System command tool -- controlled host command execution (additive).

Replaces the earlier hard-coded shell passthrough with the same safe guard
rails as TerminalTool, so it can be wired into both the agent tool registry
and the orchestrator's inline list without duplicating logic.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

_REFUSE = ("rm -rf", "shutdown", "reboot", "dd if=")


class SystemCommandTool(BaseTool):
    name = "system_command"
    description = "Run a controlled system command (guarded)."

    async def execute(self, command: str = "", **kwargs: Any) -> str:
        if not command:
            return "[no command]"
        low = command.lower()
        if any(d in low for d in _REFUSE):
            return "[refused: potentially dangerous command]"
        try:
            proc = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
            return (out or b"").decode(errors="replace")[:2000] + (err or b"").decode(errors="replace")[:500]
        except Exception as exc:  # noqa: BLE001
            return f"[system_command error: {exc}]"
