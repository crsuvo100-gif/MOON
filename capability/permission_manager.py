"""PermissionManager -- minimal default permissions + policy/approval levels.

Capability permissions are granular scopes, e.g.
  filesystem.read, filesystem.write, network.http, github.read, process.execute,
  system.package_install, docker.execute, secrets.read.

Default scope for any newly discovered capability is MINIMAL -- a GitHub repo
reader gets {github.read, network.http}, never secrets.read / system.admin /
filesystem.root. Operations that exceed the minimal/automatic tier require
explicit user confirmation or are NEVER autonomous.
"""

from __future__ import annotations

import enum
import logging

logger = logging.getLogger(__name__)


class PolicyLevel(enum.Enum):
    """Authorization tier for an action."""

    SAFE = "safe"                 # automatic, no prompt
    CONFIRMATION = "confirmation"  # ask the user first
    NEVER = "never"               # must not run autonomously


# Actions that always require explicit user confirmation regardless of source.
CONFIRMATION_ACTIONS = (
    "system.package_install",
    "system.service_modify",
    "firewall.modify",
    "ssh.config_modify",
    "private.repo_access",
    "secrets.read",
    "filesystem.root",
    "destructive.fs",
)

# Actions that MOON must never perform autonomously (security boundaries).
NEVER_ACTIONS = (
    "security.bypass",
    "auth.bypass",
    "destructive.fs_unrecoverable",
)

# A minimal, safe default permission set granted to a freshly inspected
# (not-yet-trusted) capability.
MINIMAL_PERMISSIONS = ("workspace.read", "workspace.write")

# What a trusted GitHub repository READER is allowed by default.
GITHUB_READER_PERMISSIONS = ("github.read", "network.http")


class PermissionManager:
    def __init__(self, confirmation_callback=None) -> None:
        # callback(reason: str) -> bool  (ask the user; return True to allow)
        self._confirm = confirmation_callback

    # ------------------------------------------------------------------
    def minimal_for(self, kind: str) -> tuple[str, ...]:
        if kind == "github.reader":
            return GITHUB_READER_PERMISSIONS
        return MINIMAL_PERMISSIONS

    def level_for(self, permission: str) -> PolicyLevel:
        if permission in NEVER_ACTIONS:
            return PolicyLevel.NEVER
        if permission in CONFIRMATION_ACTIONS:
            return PolicyLevel.CONFIRMATION
        return PolicyLevel.SAFE

    def is_granted(self, requested: tuple[str, ...], granted: tuple[str, ...]) -> bool:
        granted_set = set(granted)
        for perm in requested:
            if perm in granted_set:
                continue
            lvl = self.level_for(perm)
            if lvl == PolicyLevel.NEVER:
                return False
            if lvl == PolicyLevel.CONFIRMATION:
                if self._confirm is None:
                    # No operator available -> do not assume consent.
                    return False
                if not self._confirm(f"capability requests '{perm}' (confirmation required)"):
                    return False
        return True

    def check_suspicious(self, op: str) -> bool:
        """Heuristic: is the operation obviously destructive / privileged?"""
        low = (op or "").lower()
        markers = (
            "rm -rf /", "rm -rf ~", "mkfs", "dd if=/dev", "shutdown", "reboot",
            "format ", ":(){", "chmod -r 777 /", "curl | sh", "wget | sh",
            "| sh", "| bash", "|sh",
            "sudo ", ">/etc/shadow", "ssh-copy-id", "crontab -r",
            "iptables -f", "ufw disable", "systemctl disable",
        )
        return any(m in low for m in markers)
