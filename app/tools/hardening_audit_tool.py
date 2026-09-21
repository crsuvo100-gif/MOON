"""hardening_audit_tool.py -- defensive configuration / system hardening review.

Analyzes a provided config snippet or the local system for common weakness
patterns. Pure static analysis; no target authorization needed (you supply the
material or audit your own host).
"""

from __future__ import annotations

import os
import re
from typing import ClassVar

from app.tools.base import BaseTool


class HardeningAuditTool(BaseTool):
    name = "hardening_audit"
    description = "Review a config/file or the local host for hardening gaps (defensive)."

    _CHECKS: ClassVar[list] = [
        ("Telnet enabled", r"^\s*[^#]*(telnet|23/tcp)\b", "Disable telnet; use SSH."),
        ("Password auth without MFA", r"PasswordAuthentication\s+yes", "Prefer key auth + MFA."),
        ("Weak cipher", r"(des-cbc|rc4|md5)", "Replace weak ciphers/hashes."),
        ("Root login allowed", r"PermitRootLogin\s+yes", "Set PermitRootLogin no."),
        ("Debug mode on", r"debug\s*=\s*true", "Disable debug in prod."),
        ("World-writable", r"^.*\s+[r-]w[r-]-w[r-]--w-?\s", "Tighten file perms."),
    ]

    async def execute(self, path: str = "", text: str = "", **kwargs) -> str:
        material = text or ""
        if path and os.path.isfile(path):
            try:
                material = open(path, errors="replace").read()
            except Exception as exc:  # noqa: BLE001
                return f"[hardening_audit] cannot read {path}: {exc}"
        if not material:
            # audit local host basics
            findings = []
            sshd = "/etc/ssh/sshd_config"
            if os.path.isfile(sshd):
                material = open(sshd, errors="replace").read()
            else:
                return "[hardening_audit] supply a config path/text, or run on a host with /etc/ssh/sshd_config."
        findings = []
        for name, pat, fix in self._CHECKS:
            if re.search(pat, material, re.MULTILINE | re.IGNORECASE):
                findings.append(f"- {name}: {fix}")
        if not findings:
            return "No obvious hardening gaps found in the supplied material."
        return "Hardening findings:\n" + "\n".join(findings)
