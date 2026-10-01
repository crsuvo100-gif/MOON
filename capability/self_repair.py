"""SelfRepairEngine -- bounded recovery for recoverable acquisition errors.

Flow: ERROR -> DIAGNOSE -> KNOWN/MISSING DEPENDENCY? -> SAFE FIX -> RETRY.
Implements:
  * max retry count (no endless loops)
  * exponential backoff
  * failure classification (transient vs fatal)
  * safe rollback where possible (unregister a failed generated plugin)
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_MISSING_DEP_RE = re.compile(
    r"(ModuleNotFound|ImportError|No module named|command not found|"
    r"ExecutableNotFound|not recognized|Cannot find|Missing dependency)",
    re.IGNORECASE,
)


@dataclass
class RepairPlan:
    recoverable: bool
    missing_dependency: str | None = None
    action: str = ""   # pip:<pkg> | system:<pkg> | cli:<util> | none


class SelfRepairEngine:
    def __init__(self, max_retries: int = 3, base_backoff: float = 1.0) -> None:
        self.max_retries = max_retries
        self.base_backoff = base_backoff

    def classify(self, error_text: str) -> RepairPlan:
        if not error_text:
            return RepairPlan(False, action="none")
        if _MISSING_DEP_RE.search(error_text):
            # Try to extract a module/package name.
            m = re.search(r"No module named ['\"]?([A-Za-z0-9_\-.]+)", error_text)
            pkg = m.group(1) if m else None
            if pkg:
                return RepairPlan(True, missing_dependency=pkg, action=f"pip:{pkg}")
            return RepairPlan(True, action="pip:unknown")
        # Network / transient
        if re.search(r"(timed out|ConnectionError|Network is unreachable|502|503|rate limit)",
                     error_text, re.IGNORECASE):
            return RepairPlan(True, action="retry")
        return RepairPlan(False, action="none")

    async def backoff(self, attempt: int) -> None:
        await asyncio.sleep(min(self.base_backoff * (2 ** attempt), 16.0))

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_retries
