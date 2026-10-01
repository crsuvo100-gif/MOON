"""recon_tool.py -- reconnaissance for authorized targets.

Passive (DNS/whois) and active (port/service) reconnaissance. Active probing
requires target authorization (see app.security.authorization).
"""

from __future__ import annotations

import shutil
import socket
import subprocess

from app.security.authorization import require_auth
from app.tools.base import BaseTool


class ReconTool(BaseTool):
    name = "recon"
    description = "Reconnaissance (DNS, whois, port/service scan) against an authorized target."

    async def execute(self, target: str = "", ports: str = "21,22,80,443,445,3306,3389,8080,8443",
                      active: bool = False, authorized: bool = False, **kwargs) -> str:
        if not target:
            return "[recon] no target supplied"
        out = [f"=== Recon: {target} ==="]
        # Passive DNS
        try:
            infos = socket.getaddrinfo(target, None)
            ips = sorted({i[4][0] for i in infos})
            out.append("A/AAAA: " + ", ".join(ips))
        except Exception as exc:  # noqa: BLE001
            out.append(f"DNS resolve failed: {exc}")
        # whois (if present)
        if shutil.which("whois"):
            try:
                r = subprocess.run(["whois", target], capture_output=True, text=True, timeout=20)
                lines = [l for l in r.stdout.splitlines() if any(k in l for k in ("NetRange", "Organization", "OrgName", "Country", "Registrar"))]
                out.append("WHOIS: " + " | ".join(lines[:5]))
            except Exception as exc:  # noqa: BLE001
                out.append(f"whois failed: {exc}")
        # Active port scan (auth-gated)
        if active:
            auth = require_auth(target, confirmed=authorized)
            if not auth.allowed:
                out.append(f"[BLOCKED] active scan refused: {auth.reason}. Set AUTHORIZED_TARGETS or pass authorized=true for your own asset.")
                return "\n".join(out)
            out.append("-- active port scan (authorized) --")
            for p in (ports.split(",") if ports else []):
                p = p.strip()
                if not p.isdigit():
                    continue
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.4)
                try:
                    s.connect((target, int(p)))
                    out.append(f"  port {p}: OPEN")
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    s.close()
        return "\n".join(out)
