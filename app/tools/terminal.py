"""Shell command execution tool (hosted, guarded)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

_DANGEROUS = ("rm -rf", "shutdown", "reboot", "dd if=")


class TerminalTool(BaseTool):
    name = "terminal"
    description = "Execute a safe shell command on the host."

    async def execute(self, command: str = "", **kwargs: Any) -> str:
        if not command:
            return "[no command]"
        low = command.lower()
        if any(d in low for d in _DANGEROUS):
            return "[refused: potentially dangerous command]"
        try:
            proc = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
            return (out or b"").decode(errors="replace")[:2000] + (err or b"").decode(errors="replace")[:500]
        except Exception as exc:  # noqa: BLE001
            return f"[terminal error: {exc}]"
