"""Result aggregation + conflict resolution (spec sections 26, 27, 28, 39).

MOON's orchestrator collects results from specialist agents. Before those
results reach the Main Brain for synthesis they must be NORMALIZED, DEDUPED,
RANKED, and CHECKED FOR CONTRADICTIONS -- "never simply concatenate all agent
responses" (spec 26). If two agents disagree, the system must NOT arbitrarily
pick one (spec 27): it records the conflict, weighs the evidence, and marks the
outcome for verification or escalation.

This module is additive: it introduces the missing aggregation stage without
replacing any existing orchestrator logic. Everything is pure-Python and
synchronous so it can be unit-tested without a live model.

Statuses follow spec 28:
    VERIFIED / PARTIALLY_VERIFIED / UNVERIFIED / FAILED
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Any


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    FAILED = "FAILED"


class ConflictKind(str, Enum):
    CONTRADICTION = "contradiction"   # mutually exclusive claims
    DIVERGENCE = "divergence"         # same question, materially different answers
    FAILURE = "failure"               # one agent failed, another succeeded


@dataclass
class AgentEnvelope:
    """Structured agent result (spec 24 communication protocol).

    Every agent -> Main Brain message carries these fields. ``evidence`` is what
    makes a claim checkable; an envelope with no evidence can never be VERIFIED.
    """

    task_id: str = ""
    agent_id: str = ""
    status: str = "completed"
    objective: str = ""
    result: str = ""
    evidence: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    confidence: float = 0.5
    next_action: str = ""
    message_type: str = "TASK_RESULT"

    @property
    def succeeded(self) -> bool:
        return self.status in ("completed", "success", "done") and not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "agent_id": self.agent_id, "status": self.status,
            "objective": self.objective, "result": self.result, "evidence": self.evidence,
            "errors": self.errors, "warnings": self.warnings, "artifacts": self.artifacts,
            "confidence": self.confidence, "next_action": self.next_action,
            "message_type": self.message_type,
        }


@dataclass
class Conflict:
    kind: ConflictKind
    agents: list[str]
    detail: str
    severity: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "agents": self.agents,
                "detail": self.detail, "severity": round(self.severity, 3)}


@dataclass
class AggregatedResult:
    task_id: str = ""
    primary: str = ""
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    contributing_agents: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    duplicates_removed: int = 0
    failed_agents: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "primary": self.primary, "status": self.status.value,
            "contributing_agents": self.contributing_agents, "evidence": self.evidence,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "duplicates_removed": self.duplicates_removed,
            "failed_agents": self.failed_agents, "notes": self.notes,
            "has_conflict": self.has_conflict,
        }


_NEGATORS = ("not ", "no ", "never", "cannot", "can't", "isn't", "is not",
             "doesn't", "does not", "failed", "false", "incorrect", "wrong")
_WORD = re.compile(r"[a-z0-9_]+")


def _norm(text: str) -> str:
    return " ".join(_WORD.findall((text or "").lower()))


def _similarity(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _polarity(text: str) -> bool:
    """True when the text carries a negating/failure polarity marker."""
    t = (text or "").lower()
    return any(n in t for n in _NEGATORS)


class ConflictResolver:
    """Detect and triage disagreement between agent results (spec 27)."""

    def __init__(self, *, divergence_threshold: float = 0.55) -> None:
        self._threshold = divergence_threshold

    def detect(self, envelopes: list[AgentEnvelope]) -> list[Conflict]:
        conflicts: list[Conflict] = []
        ok = [e for e in envelopes if e.succeeded and (e.result or "").strip()]
        bad = [e for e in envelopes if not e.succeeded]

        # A failed agent alongside a successful one is a real conflict: the
        # Main Brain must not report success (spec 27 worked example).
        if bad and ok:
            conflicts.append(Conflict(
                kind=ConflictKind.FAILURE,
                agents=[e.agent_id for e in bad] + [e.agent_id for e in ok],
                detail=(f"{len(bad)} agent(s) failed while {len(ok)} succeeded: "
                        + "; ".join(f"{e.agent_id}: {(e.errors or ['failed'])[0]}" for e in bad[:3])),
                severity=0.9,
            ))

        # Pairwise contradiction / divergence between successful answers.
        for i in range(len(ok)):
            for j in range(i + 1, len(ok)):
                a, b = ok[i], ok[j]
                sim = _similarity(a.result, b.result)
                if sim >= 0.92:
                    continue  # agreement
                same_polarity = _polarity(a.result) == _polarity(b.result)
                if not same_polarity:
                    conflicts.append(Conflict(
                        kind=ConflictKind.CONTRADICTION,
                        agents=[a.agent_id, b.agent_id],
                        detail=(f"opposite polarity: {a.agent_id}={a.result[:60]!r} vs "
                                f"{b.agent_id}={b.result[:60]!r}"),
                        severity=round(1.0 - sim, 3),
                    ))
                elif sim < self._threshold:
                    conflicts.append(Conflict(
                        kind=ConflictKind.DIVERGENCE,
                        agents=[a.agent_id, b.agent_id],
                        detail=(f"similarity {sim:.2f} below threshold "
                                f"{self._threshold}: {a.agent_id} vs {b.agent_id}"),
                        severity=round(1.0 - sim, 3),
                    ))
        return conflicts

    def resolve(self, agg: AggregatedResult, envelopes: list[AgentEnvelope]) -> dict[str, Any]:
        """Decide what the Main Brain must do about detected conflicts.

        Returns a directive -- never silently picks a winner for a
        CONTRADICTION (spec 27).
        """
        if not agg.conflicts:
            return {"action": "accept", "reason": "no conflicts", "requires_verification": False}

        worst = max(c.severity for c in agg.conflicts)
        kinds = {c.kind for c in agg.conflicts}
        if ConflictKind.CONTRADICTION in kinds or ConflictKind.FAILURE in kinds:
            return {
                "action": "verify_then_maybe_escalate",
                "reason": f"{len(agg.conflicts)} conflict(s), max severity {worst:.2f}",
                "requires_verification": True,
                "request_from": sorted({a for c in agg.conflicts for a in c.agents}),
            }
        return {
            "action": "reconcile",
            "reason": f"divergence only (max severity {worst:.2f})",
            "requires_verification": worst > 0.7,
            "request_from": sorted({a for c in agg.conflicts for a in c.agents}),
        }


class ResultAggregator:
    """Normalize, dedupe, rank and verify multi-agent results (spec 26/28/39)."""

    def __init__(self, *, resolver: ConflictResolver | None = None,
                 min_confidence: float = 0.4) -> None:
        self._resolver = resolver or ConflictResolver()
        self._min_confidence = min_confidence

    def aggregate(self, envelopes: list[AgentEnvelope]) -> AggregatedResult:
        agg = AggregatedResult(task_id=next((e.task_id for e in envelopes if e.task_id), ""))

        # 1. Split successes / failures (never drop a failure silently).
        ok = [e for e in envelopes if e.succeeded and (e.result or "").strip()]
        agg.failed_agents = [e.agent_id for e in envelopes if not e.succeeded]

        # 2. Deduplicate near-identical results, keeping the highest confidence.
        unique: list[AgentEnvelope] = []
        removed = 0
        for e in sorted(ok, key=lambda x: x.confidence, reverse=True):
            if any(_similarity(e.result, u.result) >= 0.92 for u in unique):
                removed += 1
                continue
            unique.append(e)
        agg.duplicates_removed = removed

        # 3. Rank by confidence; primary = highest-confidence answer.
        unique.sort(key=lambda x: (x.confidence, len(x.evidence)), reverse=True)
        if unique:
            agg.primary = unique[0].result
        agg.contributing_agents = [e.agent_id for e in unique]

        # 4. Preserve ALL evidence (spec 26) -- aggregation must not lose proof.
        seen: set[str] = set()
        for e in unique:
            for ev in e.evidence:
                if ev not in seen:
                    seen.add(ev)
                    agg.evidence.append(ev)

        # 5. Conflict detection + resolution directive.
        agg.conflicts = self._resolver.detect(envelopes)
        directive = self._resolver.resolve(agg, envelopes)
        agg.notes.append(f"resolution: {directive['action']} ({directive['reason']})")

        # 6. Verification status (spec 28).
        agg.status = self._status_for(agg, unique, directive)
        return agg

    def _status_for(self, agg: AggregatedResult, unique: list[AgentEnvelope],
                    directive: dict[str, Any]) -> VerificationStatus:
        if not unique:
            return VerificationStatus.FAILED
        if agg.failed_agents and not unique:
            return VerificationStatus.FAILED
        if agg.conflicts and directive.get("requires_verification"):
            # Conflicting + unverifiable evidence => never claim VERIFIED.
            return (VerificationStatus.PARTIALLY_VERIFIED if agg.evidence
                    else VerificationStatus.UNVERIFIED)
        confident = unique[0].confidence >= self._min_confidence
        if agg.evidence and confident and not agg.conflicts:
            return VerificationStatus.VERIFIED
        if agg.evidence or confident:
            return VerificationStatus.PARTIALLY_VERIFIED
        return VerificationStatus.UNVERIFIED


__all__ = [
    "AgentEnvelope", "AggregatedResult", "Conflict", "ConflictKind",
    "ConflictResolver", "ResultAggregator", "VerificationStatus",
]
