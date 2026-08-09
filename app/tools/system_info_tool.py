"""system_info_tool.py -- cross-OS host reconnaissance (defensive/IT).

Reports OS, kernel, hostname, CPU, memory, disks, network interfaces, and
top processes using stdlib (psutil if available). Pure read-only recon of the
operator's own host.
"""

from __future__ import annotations

import platform
import shutil

from app.tools.base import BaseTool


class SystemInfoTool(BaseTool):
    name = "system_info"
    description = "Cross-OS host recon: OS, kernel, hostname, CPU, memory, disks, network, processes."

    async def execute(self, section: str = "all", **kwargs) -> str:
        out = [f"=== System info ({platform.system()} {platform.release()}) ==="]
        out.append(f"node: {platform.node()} | arch: {platform.machine()} | python: {platform.python_version()}")
        if section in ("all", "mem", "cpu") and shutil.which("free") is not None:
            try:
                import subprocess
                out.append("memory: " + subprocess.run(["free", "-h"], capture_output=True, text=True).stdout.strip().splitlines()[-1])
            except Exception:  # noqa: BLE001
                pass
        if section in ("all", "disk"):
            try:
                import shutil as sh
                _du = sh.disk_usage("/")
                total, used = _du.total, _du.used
                out.append(f"disk /: {used//(1024**3)}G used / {total//(1024**3)}G total")
            except Exception:  # noqa: BLE001
                pass
        if section in ("all", "net"):
            try:
                import socket
                out.append("hostname: " + socket.gethostname())
            except Exception:  # noqa: BLE001
                pass
        if section in ("all", "proc"):
            try:
                import subprocess
                ps = shutil.which("ps")
                if ps:
                    r = subprocess.run([ps, "-eo", "pid,comm,%cpu,%mem", "--sort=-%cpu"], capture_output=True, text=True, timeout=10)
                    out.append("top procs:\n" + "\n".join(r.stdout.splitlines()[:6]))
            except Exception:  # noqa: BLE001
                pass
        return "\n".join(out)
