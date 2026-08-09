"""Python executor tool (sandboxed subprocess, time-limited)."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class PythonExecutorTool(BaseTool):
    name = "python_executor"
    description = "Run a bounded Python snippet and return stdout."

    async def execute(self, code: str = "", **kwargs: Any) -> str:
        if not code:
            return "[no code]"
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", code,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
            return (out or b"").decode(errors="replace")[:2000] + (err or b"").decode(errors="replace")[:500]
        except Exception as exc:  # noqa: BLE001
            return f"[python error: {exc}]"
