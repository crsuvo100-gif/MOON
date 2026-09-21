"""
Self-improvement — proposal-only improvement submission (never auto-applied).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("moontm.improvement")


@dataclass
class ImprovementProposal:
    failure_mode: str
    proposal: str
    severity: str = "normal"


class SelfImprovement:
    """Submits improvement proposals on failure — never auto-applies them."""

    def __init__(self) -> None:
        self._proposals: list[ImprovementProposal] = []

    def submit(self, failure_mode: str, proposal: str, severity: str = "normal") -> ImprovementProposal:
        p = ImprovementProposal(failure_mode=failure_mode, proposal=proposal, severity=severity)
        self._proposals.append(p)
        logger.info("SelfImprovement: PROPOSED (%s): %s", severity, proposal[:100])
        return p
