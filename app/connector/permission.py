"""Connector permission manager -- least-privilege egress control.

Reuses the Capability system's PermissionManager policy tiers (SAFE /
CONFIRMATION / NEVER) and adds connector-specific scopes. Every outbound
connection is evaluated here before it is opened. Allowlisted hosts (operator
config) are SAFE; everything else is CONFIRMATION (asks Psycho) unless denied.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass

from app.capability.permission_manager import PermissionManager, PolicyLevel


# Network scopes used by the connector (added on top of the base manager).
NETWORK_SCOPES = (
    "network.egress",
    "network.service",
    "network.agent",
    "network.webhook",
)

# Hosts that are always safe to egress to (operator-owned / public utility).
_DEFAULT_SAFE_HOSTS = {
    "api.github.com",
    "github.com",
    "raw.githubusercontent.com",
    "pypi.org",
    "registry.npmjs.org",
    "ollama",
    "localhost",
    "127.0.0.1",
}


def _allowed_set() -> set[str]:
    raw = os.environ.get("ALLOWED_EGRESS_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _is_private(host: str) -> bool:
    h = host.lower()
    if h in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        return ipaddress.ip_address(h).is_private
    except ValueError:
        return False


@dataclass
class EgressDecision:
    allowed: bool
    tier: PolicyLevel
    reason: str


class ConnectorPermissionManager(PermissionManager):
    """Permission checks for outbound connections, layered on PermissionManager."""

    def egress_decision(self, host: str, scope: str = "network.egress") -> EgressDecision:
        """Decide if a connection to `host` under `scope` may proceed.

        - ALLOWED_EGRESS_HOSTS / default-safe hosts / private lab -> SAFE.
        - secrets.read scope -> NEVER (operator must supply at runtime, never auto).
        - everything else -> CONFIRMATION (ask Psycho) unless globally denied.
        """
        if scope == "secrets.read":
            return EgressDecision(False, PolicyLevel.NEVER, "credential reads require explicit operator supply")
        h = (host or "").lower()
        safe = _allowed_set() | _DEFAULT_SAFE_HOSTS
        if h in safe or _is_private(h):
            return EgressDecision(True, PolicyLevel.SAFE, f"host '{h}' is allowlisted/private")
        return EgressDecision(
            False, PolicyLevel.CONFIRMATION,
            f"outbound connection to '{h}' needs operator confirmation (not allowlisted)",
        )

    def may_auto(self, scope: str, host: str = "") -> bool:
        """True only when this connection may proceed WITHOUT operator confirmation."""
        if scope in ("secrets.read",):
            return False
        d = self.egress_decision(host, scope)
        return d.allowed and d.tier == PolicyLevel.SAFE
