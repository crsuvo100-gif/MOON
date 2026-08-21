"""AutonomyLevel (spec section 46).

Configurable autonomy gate. MOON must never make high-risk system changes fully
autonomous by default. Levels:
  0 read-only analysis
  1 suggest actions
  2 execute low-risk actions automatically
  3 execute approved tools automatically
  4 create/test agents automatically
  5 propose system improvements automatically

The gate decides whether a given action is permitted at the current level.
Reuses settings for the configured level; defaults to a safe low level.
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Any

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class AutonomyLevel(IntEnum):
    READ_ONLY = 0
    SUGGEST = 1
    EXECUTE_LOW_RISK = 2
    EXECUTE_APPROVED_TOOLS = 3
    CREATE_AGENTS = 4
    PROPOSE_IMPROVEMENTS = 5


# Risk class required per action type at minimum autonomy level.
_ACTION_MIN_LEVEL = {
    "analyze": AutonomyLevel.READ_ONLY,
    "suggest": AutonomyLevel.SUGGEST,
    "exec_low_risk": AutonomyLevel.EXECUTE_LOW_RISK,
    "exec_tool": AutonomyLevel.EXECUTE_APPROVED_TOOLS,
    "create_agent": AutonomyLevel.CREATE_AGENTS,
    "self_improve": AutonomyLevel.PROPOSE_IMPROVEMENTS,
}

# High-risk operations are NEVER auto-approved regardless of level.
_HIGH_RISK = {"delete", "wipe", "format", "modify_security", "install_privileged",
              "expose_secret", "change_system_config"}


class Autonomy:
    def __init__(self, level: int | None = None) -> None:
        self._settings = get_settings()
        # Prefer an explicit level; otherwise derive a safe default.
        self.level = AutonomyLevel(level if level is not None else self._safe_default())

    @staticmethod
    def _safe_default() -> int:
        # Conservative default: execute approved (low-risk) tools, do not
        # autonomously create agents or self-modify.
        return int(AutonomyLevel.EXECUTE_APPROVED_TOOLS)

    def set_level(self, level: int) -> None:
        self.level = AutonomyLevel(max(0, min(5, int(level))))

    def allows(self, action: str, *, high_risk: bool = False) -> tuple[bool, str]:
        if high_risk or action in _HIGH_RISK:
            return False, "high-risk action requires explicit operator authorization (spec 46/47)"
        min_level = _ACTION_MIN_LEVEL.get(action, AutonomyLevel.EXECUTE_APPROVED_TOOLS)
        if self.level >= min_level:
            return True, f"permitted at autonomy level {int(self.level)}"
        return False, f"requires autonomy level >= {int(min_level)} (current {int(self.level)})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": int(self.level),
            "name": self.level.name,
            "high_risk_always_blocked": True,
        }
