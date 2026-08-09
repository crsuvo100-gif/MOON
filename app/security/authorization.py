"""authorization.py -- authorization gate for active security operations.

MOON is a capable defensive + offensive cyber agent. To stay legitimate, any
ACTIVE operation (scanning, exploiting, probing) against a target REQUIRES that
the target be authorized: either listed in AUTHORIZED_TARGETS (env) or
explicitly confirmed by the operator at runtime. Passive/defensive analysis of
material the user already provides (logs, a file, their own config) never
requires authorization.

This is the same authorization model used by professional red-team tooling
(nmap/Nessus/Metasploit are dual-use and legal only on authorized targets).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


# Targets the operator owns / is authorized to test. Comma-separated hosts or
# CIDRs in .env (AUTHORIZED_TARGETS). "127.0.0.1", "localhost", and RFC1918
# private ranges are treated as implicitly authorized (your own lab).
def _authorized_set() -> set[str]:
    raw = os.environ.get("AUTHORIZED_TARGETS", "")
    return {t.strip().lower() for t in raw.split(",") if t.strip()}


_PRIVATE = re.compile(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|127\.\d+\.\d+\.\d+$|::1$|localhost$)")


@dataclass
class AuthDecision:
    allowed: bool
    reason: str


def is_authorized(target: str) -> AuthDecision:
    t = (target or "").strip().lower()
    if not t:
        return AuthDecision(False, "empty target")
    if t in _authorized_set():
        return AuthDecision(True, "explicitly authorized (AUTHORIZED_TARGETS)")
    if _PRIVATE.search(t):
        return AuthDecision(True, "private/loopback address (your lab)")
    return AuthDecision(False, "target not in AUTHORIZED_TARGETS; confirm ownership before active ops")


def require_auth(target: str, *, confirmed: bool = False) -> AuthDecision:
    """Active-op gate. `confirmed` is set when the operator explicitly approves."""
    if confirmed:
        return AuthDecision(True, "operator confirmed authorization at runtime")
    return is_authorized(target)
