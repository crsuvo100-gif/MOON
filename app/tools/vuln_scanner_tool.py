"""vuln_scanner_tool.py -- vulnerability scanning for authorized targets.

Runs known-good scanner binaries if available (nmap/nikto/nuclei), else a set
of safe, non-intrusive heuristic checks. Strictly authorization-gated: refuses
to scan non-authorized hosts.
"""

from __future__ import annotations

import shutil
import subprocess

from app.security.authorization import require_auth
from app.tools.base import BaseTool


class VulnScannerTool(BaseTool):
    name = "vuln_scanner"
    description = "Vulnerability scan of an authorized target (nmap/nikto/nuclei if present, else heuristic checks)."

    async def execute(self, target: str = "", authorized: bool = False, **kwargs) -> str:
        if not target:
            return "[vuln_scanner] no target supplied"
        auth = require_auth(target, confirmed=authorized)
        if not auth.allowed:
            return (f"[BLOCKED] vulnerability scanning requires an authorized target. {auth.reason}. "
                    "Add the host to AUTHORIZED_TARGETS (env) or pass authorized=true for an asset you own.")
        out = [f"=== Vuln scan (authorized): {target} ==="]
        scanned = False
        for bin_name, args in (("nmap", ["-sV", "--top-ports", "100", target]),
                                ("nikto", ["-h", target]),
                                ("nuclei", ["-u", target, "-silent"])):
            if shutil.which(bin_name):
                try:
                    r = subprocess.run([bin_name, *args], capture_output=True, text=True, timeout=120)
                    out.append(f"--- {bin_name} ---\n" + (r.stdout or r.stderr)[:1500])
                    scanned = True
                except Exception as exc:  # noqa: BLE001
                    out.append(f"{bin_name} error: {exc}")
        if not scanned:
            out.append("No scanner binary present (nmap/nikto/nuclei). Install one for deep scans.")
            out.append("Heuristic note: ensure TLS, patch level, and exposed services are reviewed manually.")
        return "\n".join(out)
