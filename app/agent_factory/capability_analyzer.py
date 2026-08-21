"""Agent Factory: Capability Analyzer (spec 13 + MOON Factory design).

Analyzes a capability request, checks the live Agent Registry for an existing
match, and decides REUSE vs NEEDS_NEW. Never invents capabilities that already
exist (spec 13: SEARCH EXISTING -> IF EXISTING REUSE).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.registry import AgentRegistry, get_registry


@dataclass
class CapabilityNeed:
    raw: str
    normalized: str
    keywords: list[str]
    existing_match: str | None  # agent id if reusable
    decision: str  # REUSE | CREATE


class CapabilityAnalyzer:
    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self._reg = registry or get_registry()

    def analyze(self, request: str) -> CapabilityNeed:
        raw = (request or "").strip()
        norm = raw.lower()
        # keyword extraction: split on spaces / common stopwords
        stop = {"a", "an", "the", "agent", "capable", "of", "that", "can", "create",
                "analyze", "analysis", "for", "to", "and", "in", "my", "project"}
        kws = [w for w in norm.replace(",", " ").split() if w not in stop and len(w) > 2]
        # search registry by capability/name/keyword
        match = None
        cands = self._reg.select(capability=" ".join(kws)) if kws else []
        if cands:
            match = cands[0].id
        # also direct substring name match
        if not match:
            for m in self._reg.all():
                if m.status == "active" and (m.id in norm or m.name.lower() in norm):
                    match = m.id
                    break
        decision = "REUSE" if match else "CREATE"
        return CapabilityNeed(raw=raw, normalized=norm, keywords=kws,
                              existing_match=match, decision=decision)

    def report(self, need: CapabilityNeed) -> dict[str, Any]:
        return {
            "raw": need.raw, "keywords": need.keywords,
            "existing_match": need.existing_match, "decision": need.decision,
        }


__all__ = ["CapabilityAnalyzer", "CapabilityNeed"]
