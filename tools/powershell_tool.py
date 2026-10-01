"""powershell_tool.py -- Windows PowerShell execution (operator's Windows host)."""

from __future__ import annotations

import shutil
import subprocess

from app.tools.base import BaseTool


class PowerShellTool(BaseTool):
    name = "powershell"
    description = "Run PowerShell commands on a Windows host (requires pwsh)."

    async def execute(self, script: str = "", **kwargs) -> str:
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if not pwsh:
            return "[powershell] pwsh/powershell not found on this host (non-Windows or not installed)."
        try:
            r = subprocess.run([pwsh, "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=120)
            return (r.stdout or "") + (r.stderr or "")
        except Exception as exc:  # noqa: BLE001
            return f"[powershell] error: {exc}"
