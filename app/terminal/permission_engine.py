"""Permission engine – decides whether a command may be executed.

The policy is defined in ``permission_policy.yaml``.  The file contains a list of
rules, each with a ``pattern`` (wildcard glob) and an ``action`` which can be
``allow``, ``deny`` or ``ask``.  Rules are evaluated in order; the first match
wins.

If a command matches a rule with ``action: ask`` the engine raises a
``PermissionRequired`` exception carrying the reason.  The UI layer can catch
this exception, prompt the user, and re‑invoke the execution engine with the
same request.

A default policy is provided that ``allow`` everything under ``/home/meow``
(and therefore the current project) and ``ask`` for any destructive command
(``rm``, ``dd``, ``mkfs`` …).  The file is deliberately tiny – real deployments
should customise it to the organisation's security posture.
"""

from __future__ import annotations

import fnmatch
import yaml
from pathlib import Path
from typing import List, Dict

from .models import ExecutionRequest

# ---------------------------------------------------------------------------
# Exceptions – raised by ``check`` when a request is not auto‑allowed.
# ---------------------------------------------------------------------------

class PermissionRequired(Exception):
    """Raised when a command needs explicit user approval.

    The ``reason`` attribute contains a short human‑readable explanation.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Denied(Exception):
    """Raised when a command is explicitly denied by policy."""

    pass


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

class PermissionEngine:
    """Load a YAML policy and evaluate ``ExecutionRequest`` objects.

    The policy file lives next to this module so that it is packaged with the
    library.  Users can override it by placing a file with the same name in the
    project root – the engine will prefer the external file when present.
    """

    _DEFAULT_POLICY = """
    - pattern: "*rm *"
      action: ask
    - pattern: "*dd *"
      action: ask
    - pattern: "*mkfs *"
      action: deny
    - pattern: "*"
      action: allow
    """

    def __init__(self, policy_path: Path | None = None):
        # Resolve policy location – external file overrides built‑in default.
        if policy_path is None:
            candidate = Path.cwd() / "permission_policy.yaml"
            self.policy_path = candidate if candidate.is_file() else None
        else:
            self.policy_path = Path(policy_path)
        self.rules: List[Dict[str, str]] = self._load_policy()

    # -------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------
    def _load_policy(self) -> List[Dict[str, str]]:
        if self.policy_path and self.policy_path.is_file():
            raw = self.policy_path.read_text()
        else:
            raw = self._DEFAULT_POLICY
        try:
            parsed = yaml.safe_load(raw) or []
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse permission policy: {exc}")
        return parsed

    def _match_rule(self, command: str) -> Dict[str, str] | None:
        for rule in self.rules:
            pattern = rule.get("pattern", "*")
            if fnmatch.fnmatch(command, pattern):
                return rule
        return None

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------
    def check(self, request: ExecutionRequest, risk_level: str | None = None) -> None:
        """Validate *request* against the policy.

        *risk_level* is optional – callers may pass a risk classification such
        as ``high``.  The current implementation does not use it, but keeping
        the argument preserves a stable signature for future extensions.
        """
        rule = self._match_rule(request.command)
        if rule is None:
            # No rule matched – safe default is to ``allow``.
            return
        action = rule.get("action", "allow").lower()
        if action == "allow":
            return
        if action == "deny":
            raise Denied(f"Command denied by policy: {request.command}")
        # ``ask`` or any unknown action -> require explicit approval.
        raise PermissionRequired(
            f"Permission required for command: {request.command} (matched rule: {rule})"
        )

# End of permission_engine.py
