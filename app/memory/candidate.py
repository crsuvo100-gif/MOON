"""Memory candidate pipeline (spec 11, 13, 42, 69).

"Do not save everything." Every potential memory passes through:

    RAW INFORMATION
      -> CANDIDATE DETECTION      (is this worth remembering at all?)
      -> CLASSIFICATION           (type / scope / source)
      -> DUPLICATE CHECK          (spec 13)
      -> IMPORTANCE               (spec 10)
      -> CONFIDENCE               (spec 9)
      -> POLICY CHECK             (spec 42)
      -> PERSIST OR DISCARD

This is the single gate between "something happened" and "MOON remembers it",
so it is where memory pollution (spec 78) and secret leakage (spec 43) are
stopped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from app.memory.record import (
    Importance,
    MemoryRecord,
    MemoryType,
    Scope,
    SourceType,
)
from app.memory.security import detect_secret


# --------------------------------------------------------------------------
# spec 11: candidate detection
# --------------------------------------------------------------------------
# Signals that raw text is worth remembering.
_IMPERATIVE_MEMORY = re.compile(
    r"(?i)\b(remember|note that|keep in mind|don't forget|make a note|"
    r"save (?:this|that)|for future reference|important:)\b")
_DURABLE_FACT = re.compile(
    r"(?i)\b(uses?|is|are|always|never|must|should|prefer|requires?|"
    r"depends? on|configured|installed|version|path|located|owned by)\b")
# Noise: transient tool output, stack traces, huge dumps.
_NOISE = re.compile(
    r"(?i)^(?:traceback|file \"|\s*at \w+\.|\d{4}-\d{2}-\d{2}[T ]\d{2}:|"
    r"\s*[{}\[\],]+\s*$|progress:|downloading|\.\.\.$)")
_TOOL_DUMP_CHARS = 4000


@dataclass
class Candidate:
    """A memory that has survived detection and classification."""

    record: MemoryRecord
    reasons: list[str] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"record": self.record.to_dict(), "reasons": self.reasons,
                "score": round(self.score, 3)}


def detect_candidate(text: str, *, source_type: SourceType,
                     explicit: bool = False,
                     agent_scoped: bool = False) -> tuple[bool, list[str]]:
    """spec 11 + spec 78: should this text become a memory candidate?

    ``agent_scoped`` marks a deliberate agent-private write (spec 40): the
    caller has already decided this belongs in that agent's own memory, so the
    user-facing "durable fact" wording heuristic must not veto it. Noise and
    bulk tool output are still rejected.
    """
    reasons: list[str] = []
    t = (text or "").strip()
    if len(t) < 8:
        return False, ["too short"]
    if explicit:
        return True, ["explicit memory request (spec 12)"]
    if _NOISE.match(t):
        return False, ["transient/noise pattern (spec 78)"]
    # A giant blob is tool output, not a memory (spec 78).
    if len(t) > _TOOL_DUMP_CHARS:
        return False, [f"too large for a memory ({len(t)} chars) -- tool dump"]
    if source_type is SourceType.TOOL and len(t) > 1200:
        return False, ["bulk tool output is not durable memory"]
    if agent_scoped:
        return True, ["deliberate agent-private memory (spec 40)"]
    if _IMPERATIVE_MEMORY.search(t):
        reasons.append("imperative memory cue")
    if _DURABLE_FACT.search(t):
        reasons.append("durable-fact wording")
    # A first-person user statement of preference/fact is durable.
    if source_type is SourceType.USER and re.search(r"(?i)\b(my|i|we)\b", t):
        reasons.append("user-stated fact/preference")
    return bool(reasons), reasons or ["no durable signal"]


# --------------------------------------------------------------------------
# spec 11: classification
# --------------------------------------------------------------------------
def classify(text: str, *, source_type: SourceType,
             agent_id: str = "") -> tuple[MemoryType, Scope]:
    t = (text or "").lower()
    if re.search(r"\b(to |steps?|workflow|procedure|how to|run |deploy|install)\b", t):
        return MemoryType.PROCEDURAL, Scope.PROJECT
    if re.search(r"\b(prefer|like|my |i want|i use)\b", t):
        return MemoryType.USER, Scope.USER
    if re.search(r"\b(project|repo|codebase|architecture|dependency|module)\b", t):
        return MemoryType.PROJECT, Scope.PROJECT
    if re.search(r"\b(error|failed|fixed|occurred|incident|previously|yesterday)\b", t):
        return MemoryType.EPISODIC, Scope.PROJECT
    if agent_id:
        return MemoryType.AGENT, Scope.AGENT
    if source_type is SourceType.USER:
        return MemoryType.SEMANTIC, Scope.USER
    return MemoryType.SEMANTIC, Scope.GLOBAL


# --------------------------------------------------------------------------
# spec 13: deduplication
# --------------------------------------------------------------------------
def _norm(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9_]+", (s or "").lower()))


def similarity(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def find_duplicate(record: MemoryRecord, existing: list[MemoryRecord],
                   *, threshold: float = 0.92) -> MemoryRecord | None:
    """spec 13: exact or near-duplicate detection against the same scope.

    Only compares within the same scope+type so a private agent memory is not
    deduped against a global one (spec 88 boundary).
    """
    for e in existing:
        if e.deleted:
            continue
        if e.scope != record.scope or e.type != record.type:
            continue
        if e.agent_id != record.agent_id:
            continue
        if similarity(e.content, record.content) >= threshold:
            return e
    return None


# --------------------------------------------------------------------------
# spec 10: importance
# --------------------------------------------------------------------------
def score_importance(text: str, *, source_type: SourceType,
                     memory_type: MemoryType,
                     explicit: bool = False,
                     reused: int = 0) -> Importance:
    t = (text or "").lower()
    if explicit:
        return Importance.HIGH
    if re.search(r"\b(critical|must|never|security|password policy|breaking|"
                 r"production|irreversible)\b", t):
        return Importance.CRITICAL
    if source_type is SourceType.USER:
        return Importance.HIGH
    if memory_type in (MemoryType.SEMANTIC, MemoryType.PROJECT,
                       MemoryType.PROCEDURAL):
        return Importance.HIGH
    if reused >= 3:
        return Importance.HIGH          # spec 15: repeated relevance promotes
    if memory_type is MemoryType.EPISODIC:
        return Importance.MEDIUM
    if memory_type is MemoryType.SHORT_TERM:
        return Importance.LOW
    return Importance.MEDIUM


# --------------------------------------------------------------------------
# spec 42: policy engine
# --------------------------------------------------------------------------
class MemoryPolicyEngine:
    """READ / WRITE / UPDATE / DELETE / SHARE / EXPORT (spec 42).

    Considers user, agent, scope, project, task and memory type. Deny-by-default
    for cross-agent access (spec 40/41/88).
    """

    def __init__(self, *, allow_cross_agent_share: bool = False) -> None:
        self._allow_share = allow_cross_agent_share

    def can(self, op: str, *, record: MemoryRecord | None = None,
            agent_id: str = "", scope: Scope | None = None) -> tuple[bool, str]:
        op = op.upper()
        if op in ("READ", "WRITE", "UPDATE", "DELETE"):
            # An agent may only touch its own AGENT-scoped memory.
            if record is not None and record.scope is Scope.AGENT:
                if agent_id and record.agent_id and record.agent_id != agent_id:
                    return False, (f"agent '{agent_id}' cannot {op} "
                                   f"agent-private memory of '{record.agent_id}'")
            return True, "ok"
        if op == "SHARE":
            if record is not None and record.scope is Scope.AGENT and not self._allow_share:
                return False, ("agent-private memory is not shared by default "
                               "(spec 41); publish through the candidate pipeline")
            return True, "ok"
        if op == "EXPORT":
            # spec 48: secrets never leave, whatever the scope.
            if record is not None and detect_secret(record.content).is_secret:
                return False, "refusing to export a record that looks like a secret (spec 43/48)"
            return True, "ok"
        return False, f"unknown operation '{op}'"


# --------------------------------------------------------------------------
# the pipeline
# --------------------------------------------------------------------------
class CandidatePipeline:
    """Runs the spec-11 pipeline and returns a persist/discard verdict."""

    def __init__(self, *, policy: MemoryPolicyEngine | None = None,
                 dedup_threshold: float = 0.92) -> None:
        self._policy = policy or MemoryPolicyEngine()
        self._dedup = dedup_threshold

    def evaluate(self, text: str, *, source_type: SourceType = SourceType.AGENT,
                 agent_id: str = "", project_id: str = "", task_id: str = "",
                 session_id: str = "", explicit: bool = False,
                 existing: list[MemoryRecord] | None = None,
                 reused: int = 0,
                 scope: Scope | None = None) -> dict[str, Any]:
        """Return {persist, record, reasons, duplicate_of}."""
        reasons: list[str] = []

        # 1. spec 43: secrets never enter the pipeline.
        verdict = detect_secret(text)
        if verdict.is_secret:
            return {"persist": False, "record": None,
                    "reasons": [f"SECRET BLOCKED: {verdict.reason}"],
                    "duplicate_of": None, "secret": True}

        # 2. candidate detection
        ok, why = detect_candidate(
            text, source_type=source_type, explicit=explicit,
            agent_scoped=(scope is Scope.AGENT if scope is not None
                          else False))
        reasons.extend(why)
        if not ok:
            return {"persist": False, "record": None, "reasons": reasons,
                    "duplicate_of": None}

        # 3. classification (an explicit scope override wins, spec 5)
        mtype, cls_scope = classify(text, source_type=source_type, agent_id=agent_id)
        if scope is not None:
            cls_scope = scope
        reasons.append(f"classified {mtype.value}/{cls_scope.value}")

        # 4. build + score
        rec = MemoryRecord(
            content=text.strip()[:4000], scope=cls_scope, type=mtype,
            agent_id=agent_id if cls_scope is Scope.AGENT else "",
            project_id=project_id, task_id=task_id, session_id=session_id,
            source_type=source_type,
            importance=score_importance(text, source_type=source_type,
                                        memory_type=mtype, explicit=explicit,
                                        reused=reused),
        ).apply_defaults()
        reasons.append(f"confidence {rec.confidence:.2f} from {source_type.value}")
        reasons.append(f"importance {rec.importance.value}")

        # 5. spec 13 dedup
        dup = find_duplicate(rec, existing or [], threshold=self._dedup)
        if dup is not None:
            reasons.append(f"duplicate of {dup.memory_id}")
            return {"persist": False, "record": rec, "reasons": reasons,
                    "duplicate_of": dup.memory_id}

        # 6. spec 42 policy
        allowed, why_p = self._policy.can("WRITE", record=rec, agent_id=agent_id)
        reasons.append(f"policy: {why_p}")
        if not allowed:
            return {"persist": False, "record": rec, "reasons": reasons,
                    "duplicate_of": None}

        return {"persist": True, "record": rec, "reasons": reasons,
                "duplicate_of": None}


__all__ = [
    "Candidate", "CandidatePipeline", "MemoryPolicyEngine",
    "detect_candidate", "classify", "find_duplicate", "similarity",
    "score_importance",
]
