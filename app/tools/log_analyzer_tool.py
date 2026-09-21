"""log_analyzer_tool.py -- detect attacks / IOCs in logs (defensive SOC aid).

Scans provided log text for common attack signatures (brute force, scanning,
web exploits, reverse-shell patterns) and summarizes counts. No auth needed.
"""

from __future__ import annotations

import re
from typing import ClassVar

from app.tools.base import BaseTool


class LogAnalyzerTool(BaseTool):
    name = "log_analyzer"
    description = "Detect attacks/IOCs in log text (brute force, scanning, web exploits, C2 patterns)."

    _SIGS: ClassVar[dict] = {
        "SSH brute-force": r"Failed password for .* from (\d+\.\d+\.\d+\.\d+)",
        "Web exploit attempt": r"(union\s+select|/etc/passwd|base64_decode|<\?php|<script>|cmd\.exe)",
        "Port scan": r"scan detected|flags=.*SYN",
        "Reverse shell": r"(/bin/sh|/bin/bash|nc -e|bash -i|mkfifo)",
        "SQLi": r"('\s*or\s*'|sleep\(\d+\)|information_schema)",
        "Path traversal": r"(\.\./|\.\.\\|/proc/self)",
    }

    async def execute(self, text: str = "", path: str = "", **kwargs) -> str:
        import os

        if path and os.path.isfile(path):
            try:
                text = open(path, errors="replace").read()
            except Exception as exc:  # noqa: BLE001
                return f"[log_analyzer] cannot read {path}: {exc}"
        if not text:
            return "[log_analyzer] supply log text or a path"
        report = ["=== Log analysis ==="]
        total = 0
        for name, pat in self._SIGS.items():
            hits = re.findall(pat, text, re.IGNORECASE)
            if hits:
                total += len(hits)
                sample = hits[0] if isinstance(hits[0], str) else hits[0][0]
                report.append(f"- {name}: {len(hits)} hit(s); e.g. {sample[:60]}")
        report.append(f"Total suspicious events: {total}")
        return "\n".join(report)
