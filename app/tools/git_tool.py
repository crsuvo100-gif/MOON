"""git_tool.py -- Git operations on a repository (operator's workspace)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.tools.base import BaseTool


class GitTool(BaseTool):
    name = "git"
    description = "Git operations: status, diff, log, clone, commit (on operator's workspace)."

    async def execute(self, action: str = "status", repo: str = ".", extra: str = "", **kwargs) -> str:
        if not shutil.which("git"):
            return "[git] git not found."
        path = Path(repo)
        try:
            if action in ("clone",):
                r = subprocess.run(["git", "clone", *extra.split(), repo if False else extra.split()[0] if extra else repo], capture_output=True, text=True, timeout=120) if False else subprocess.run(["git", "-C", str(path), *([action] + (extra.split() if extra else []))], capture_output=True, text=True, timeout=120)
            else:
                r = subprocess.run(["git", "-C", str(path), action, *extra.split()], capture_output=True, text=True, timeout=120)
            return (r.stdout or r.stderr or "(ok)")[:2000]
        except Exception as exc:  # noqa: BLE001
            return f"[git] error: {exc}"
