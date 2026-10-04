"""Secret detection + separation (spec 43, 44, 45, 76).

Spec 43 is explicit: passwords, API keys, SSH private keys, auth tokens and
database credentials must NEVER be stored as ordinary memory. Spec 44 says the
memory system may REFERENCE a secret without storing it.

This module is deliberately conservative and dependency-free. It returns a
reason, not just a bool, so the caller can log WHY without logging the secret.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (name, compiled pattern) -- ordered most-specific first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key_block",
     re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("openai_key", re.compile(r"\bsk-(?:proj-|live-|test-)?[A-Za-z0-9\-_]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("neon_db_url",
     re.compile(r"\bpostgres(?:ql)?://[^\s:@/]+:[^\s@/]+@[^\s/]+", re.I)),
    ("db_url_password",
     re.compile(r"\b(?:mysql|mariadb|mongodb|redis|amqp)://[^\s:@/]+:[^\s@/]+@", re.I)),
    ("bearer_header", re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]{20,}=*\b", re.I)),
    ("assignment_secret",
     re.compile(r"(?i)\b(?:api[_-]?key|secret|password|passwd|pwd|token|"
                r"client[_-]?secret|private[_-]?key|access[_-]?key)\b"
                r"\s*[:=]\s*[\"']?([^\s\"']{8,})")),
    ("ssh_private_hint", re.compile(r"(?i)\bssh-(?:rsa|ed25519|ecdsa)\s+AAAA[A-Za-z0-9+/]{40,}")),
]

# Values that look like a placeholder rather than a real secret -- do NOT block
# these, or the memory system would reject ordinary documentation.
_PLACEHOLDERS = re.compile(
    r"(?i)^(?:<[^>]*>|\$\{?[A-Z_]+\}?|xxx+|your[_-]?\w*|changeme|placeholder|"
    r"example|redacted|none|null|true|false|\*+)$")


@dataclass
class SecretVerdict:
    is_secret: bool
    reason: str = ""
    kind: str = ""
    # A redacted excerpt safe to log (never the secret itself).
    safe_excerpt: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"is_secret": self.is_secret, "reason": self.reason,
                "kind": self.kind, "safe_excerpt": self.safe_excerpt}


def _redact(text: str, start: int, end: int) -> str:
    """Return a window around the match with the match itself masked."""
    lo = max(0, start - 12)
    hi = min(len(text), end + 12)
    return text[lo:start] + "[REDACTED]" + text[end:hi]


def detect_secret(text: str) -> SecretVerdict:
    """spec 43: does this text contain something that must not be persisted?"""
    if not text:
        return SecretVerdict(False)
    for kind, pat in _PATTERNS:
        for m in pat.finditer(text):
            # For key=value patterns, inspect the captured value.
            value = m.group(1) if m.groups() else m.group(0)
            if value and _PLACEHOLDERS.match(value.strip()):
                continue
            return SecretVerdict(
                is_secret=True,
                kind=kind,
                reason=f"looks like a {kind.replace('_', ' ')} (spec 43)",
                safe_excerpt=_redact(text, m.start(), m.end()),
            )
    return SecretVerdict(False)


def is_secret(text: str) -> bool:
    return detect_secret(text).is_secret


def sanitize(text: str) -> tuple[str, SecretVerdict]:
    """Return (text_with_secrets_masked, verdict).

    Used for logging/export paths (spec 45/48) so a secret is never written to
    a log line or an exported file, even if it slipped in from a tool result.
    """
    if not text:
        return text, SecretVerdict(False)
    out = text
    verdict = SecretVerdict(False)
    for kind, pat in _PATTERNS:
        def _sub(m: re.Match[str]) -> str:
            nonlocal verdict
            value = m.group(1) if m.groups() else m.group(0)
            if value and _PLACEHOLDERS.match(value.strip()):
                return m.group(0)
            if not verdict.is_secret:
                verdict = SecretVerdict(True, kind=kind,
                                        reason=f"masked {kind}",
                                        safe_excerpt="[REDACTED]")
            return "[REDACTED]"
        out = pat.sub(_sub, out)
    return out, verdict


__all__ = ["SecretVerdict", "detect_secret", "is_secret", "sanitize"]
