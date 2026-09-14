"""
TerminalTool — run allow-listed shell commands.
"""
from __future__ import annotations

import shlex
import subprocess
from typing import Any

from app.tools.base import BaseTool


_SHELL_ALLOW = {
    "status": "echo 'status OK'",
    "ps": "ps aux --sort=-%mem | head -20",
    "top": "top -bn1 | head -25",
    "df": "df -h",
    "free": "free -h",
    "uname": "uname -a",
    "uptime": "uptime",
    "netstat": "netstat -tulpn 2>/dev/null || ss -tulpn",
    "ifconfig": "ifconfig 2>/dev/null || ip addr",
    "ip": "ip addr",
    "ls": "ls -la",
    "pwd": "pwd",
    "echo": None,       # handled specially
    "date": "date",
    "whoami": "whoami",
    "env": "env",
    "nproc": "nproc",
    "cat": None,        # gated separately
}


class TerminalTool(BaseTool):
    name = "terminal"
    description = "Run a safe, allow-listed shell command and return output."

    async def execute(self, cmd: str = "", **kwargs: Any) -> str:
        if not cmd:
            return "[terminal] no command given"

        cmd = cmd.strip()

        # echo expansion
        if cmd.startswith("echo "):
            parts = shlex.split(cmd, posix=False)
            if len(parts) > 1:
                return " ".join(parts[1:])
            return ""

        # cat gating — only text/log files, no flags/redirects/absolute paths
        if cmd.startswith("cat "):
            rest = cmd[4:].strip()
            if any(c in rest for c in '>|&;$`\\'):
                return "[terminal] cat: forbidden characters in path"
            if rest.startswith("/") or rest.startswith("..") or rest.startswith("~"):
                return "[terminal] cat: absolute/relative paths not allowed"
            if any(rest.startswith(f"-{f}") for f in "nbcvxrRZ0123456789"):
                return "[terminal] cat: flags not allowed"
            import os
            cur = os.getcwd()
            target = os.path.join(cur, rest)
            if not os.path.isfile(target):
                return f"[terminal] cat: file not found: {rest}"
            try:
                with open(target, "r", errors="replace") as f:
                    out = f.read(8000)
                if len(out) == 8000:
                    out += "\n[...] (truncated at 8000 chars)"
                return out
            except Exception as e:
                return f"[terminal] cat: {e}"

        if cmd not in _SHELL_ALLOW:
            return f"[terminal] '{cmd}' not in allowlist"

        expand = _SHELL_ALLOW[cmd]
        if expand is None:
            return f"[terminal] '{cmd}' has no expansion"

        try:
            r = subprocess.run(
                expand,
                shell=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            out = (r.stdout or "") + (r.stderr or "")
            if len(out) > 8000:
                out = out[:8000] + "\n[...] (truncated)"
            return out
        except subprocess.TimeoutExpired:
            return "[terminal] command timed out (20s)"
        except Exception as e:
            return f"[terminal] {e}"
