"""Explicit natural-language memory commands (spec 12).

"Remember this...", "Save this...", "Forget this...", "Delete that memory...",
"Show what you remember about...", "Forget everything about X."

These must map to DETERMINISTIC memory operations -- no model call, no guessing.
The parser is pure and testable; the CognitiveMemoryManager executes the result.
"""

from __future__ import annotations

import re
from typing import Any

# Ordered: more specific patterns first so "forget everything about X" is not
# captured by the plain "forget X" rule.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("forget", re.compile(
        r"(?i)^\s*(?:please\s+)?forget\s+(?:everything\s+(?:about|regarding|on)\s+)?"
        r"(?:this|that|it)?\s*[:\-]?\s*(?P<payload>.+?)\s*$")),
    ("delete", re.compile(
        r"(?i)^\s*(?:please\s+)?(?:delete|remove|erase)\s+"
        r"(?:that|this|the)?\s*memory\s*(?:about\s+)?[:\-]?\s*(?P<payload>.+?)\s*$")),
    ("remember", re.compile(
        r"(?i)^\s*(?:please\s+)?(?:remember|save|note|store|memorize|keep in mind)\s+"
        r"(?:this|that)?\s*[:\-]?\s*(?P<payload>.+?)\s*$")),
    ("show", re.compile(
        r"(?i)^\s*(?:please\s+)?(?:show|what do you remember about|what do you know about|"
        r"recall|list)\s+(?:me\s+)?(?:what\s+you\s+remember\s+about\s+)?"
        r"(?:my\s+|the\s+)?(?P<payload>.+?)\s*$")),
]

# A trailing "about X" is the subject, not part of the payload for remember.
_ABOUT = re.compile(r"(?i)^about\s+(?P<subject>.+)$")


def parse_memory_command(text: str) -> dict[str, Any] | None:
    """Return {op, payload, raw} or None when this is not a memory command.

    ``op`` is one of: remember | forget | show | delete
    """
    if not text or not text.strip():
        return None
    t = text.strip()
    for op, pat in _RULES:
        m = pat.match(t)
        if not m:
            continue
        payload = (m.group("payload") or "").strip().strip("\"'")
        if not payload:
            continue
        # "remember that X" / "remember about X" -> X
        about = _ABOUT.match(payload)
        if about:
            payload = about.group("subject").strip()
        payload = re.sub(r"(?i)^(?:that|this)\s+", "", payload).strip()
        if not payload:
            continue
        # A pure command word alone is not a command with content.
        if payload.lower() in {"it", "this", "that", "memory"}:
            continue
        if op == "delete":
            op = "forget"
        return {"op": op, "payload": payload, "raw": t}
    return None


def is_memory_command(text: str) -> bool:
    return parse_memory_command(text) is not None


__all__ = ["parse_memory_command", "is_memory_command"]
