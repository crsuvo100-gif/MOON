"""docker_tool.py -- Docker operations (operator's host). Read + lifecycle."""

from __future__ import annotations

import shutil
import subprocess

from app.tools.base import BaseTool


class DockerTool(BaseTool):
    name = "docker"
    description = "Docker operations: ps, images, run, exec, logs, build (on operator's host)."

    async def execute(self, subcommand: str = "ps", args: str = "-a", **kwargs) -> str:
        if not shutil.which("docker"):
            return "[docker] docker CLI not found on this host."
        try:
            r = subprocess.run(["docker", subcommand, *args.split()], capture_output=True, text=True, timeout=120)
            return (r.stdout or r.stderr or "(no output)")[:2000]
        except Exception as exc:  # noqa: BLE001
            return f"[docker] error: {exc}"
