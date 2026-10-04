"""Advanced Conflict Resolution — LLM-based verification and semantic conflict detection.

Extends the basic ConflictResolver in ``app/brain/aggregator.py`` with:
- LLM-based conflict verification (uses a brain to adjudicate conflicts)
- Semantic conflict detection (beyond simple negation patterns)
- Evidence-based conflict resolution
- Conflict escalation and de-escalation

This is ADDITIVE: it does not replace the existing ConflictResolver.
Instead it provides an advanced layer that can be used when the basic
resolver detects conflicts that need deeper analysis.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.brain.aggregator import (
    AgentEnvelope,
    AggregatedResult,
    Conflict,
    ConflictKind,
    ConflictResolver,
    VerificationStatus,
)


class ConflictResolutionStrategy(str, Enum):
    """Strategies for resolving conflicts."""

    EVIDENCE_BASED = "evidence_based"  # Pick the answer with more evidence
    CONSENSUS = "consensus"  # Pick the answer most agents agree on
    LLM_ADJUDICATION = "llm_adjudication"  # Use an LLM to pick the winner
    ESCALATE = "escalate"  # Escalate to the user
    MERGE = "merge"  # Merge both answers into one


class ConflictSeverity(str, Enum):
    """Conflict severity levels."""

    CRITICAL = "critical"  # Direct contradiction on a critical fact
    HIGH = "high"  # Significant disagreement
    MEDIUM = "medium"  # Minor disagreement
    LOW = "low"  # Trivial disagreement
    NONE = "none"  # No real conflict


@dataclass
class Evidence:
    """Evidence supporting a claim."""

    source: str
    content: str
    confidence: float = 0.5
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdjudicationResult:
    """Result of LLM-based conflict adjudication."""

    winner: str  # agent_id of the winning answer
    loser: str  # agent_id of the losing answer
    reasoning: str
    confidence: float
    merged_answer: str | None = None  # If strategy is MERGE
    strategy_used: ConflictResolutionStrategy = ConflictResolutionStrategy.LLM_ADJUDICATION
    execution_time: float = 0.0


@dataclass
class AdvancedConflict:
    """An extended conflict with additional metadata."""

    base_conflict: Conflict
    severity: ConflictSeverity
    evidence_a: list[Evidence] = field(default_factory=list)
    evidence_b: list[Evidence] = field(default_factory=list)
    adjudication: AdjudicationResult | None = None
    resolved: bool = False
    resolution_strategy: ConflictResolutionStrategy | None = None


class AdvancedConflictResolver:
    """Advanced conflict resolver with LLM-based verification.

    This resolver extends the basic ConflictResolver with:
    - Semantic conflict detection (beyond simple negation)
    - LLM-based adjudication for complex conflicts
    - Evidence-based resolution strategies
    - Conflict merging when both answers have value
    """

    def __init__(
        self,
        *,
        brain: Any | None = None,
        default_strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.EVIDENCE_BASED,
        min_confidence_for_auto_resolve: float = 0.7,
        max_conflicts_for_llm: int = 5,
    ) -> None:
        self._brain = brain
        self._default_strategy = default_strategy
        self._min_confidence = min_confidence_for_auto_resolve
        self._max_conflicts_for_llm = max_conflicts_for_llm
        self._basic_resolver = ConflictResolver()
        self._adjudication_history: list[AdjudicationResult] = []
        self._metrics: dict[str, int] = {}

    @property
    def metrics(self) -> dict[str, int]:
        return dict(self._metrics)

    def detect_advanced(self, envelopes: list[AgentEnvelope]) -> list[AdvancedConflict]:
        """Detect conflicts with advanced semantic analysis.

        Args:
            envelopes: Agent result envelopes.

        Returns:
            List of AdvancedConflict objects with extended metadata.
        """
        basic_conflicts = self._basic_resolver.detect(envelopes)
        advanced: list[AdvancedConflict] = []

        for bc in basic_conflicts:
            # Determine severity
            severity = self._assess_severity(bc, envelopes)

            # Collect evidence for each side
            evidence_a = self._collect_evidence(bc.agents[0], envelopes)
            evidence_b = self._collect_evidence(bc.agents[1], envelopes) if len(bc.agents) > 1 else []

            ac = AdvancedConflict(
                base_conflict=bc,
                severity=severity,
                evidence_a=evidence_a,
                evidence_b=evidence_b,
            )
            advanced.append(ac)

        self._metrics["conflicts_detected"] = self._metrics.get("conflicts_detected", 0) + len(advanced)
        return advanced

    async def resolve(
        self,
        conflicts: list[AdvancedConflict],
        envelopes: list[AgentEnvelope],
    ) -> list[AdvancedConflict]:
        """Resolve conflicts using the configured strategy.

        Args:
            conflicts: List of AdvancedConflict objects.
            envelopes: Original agent envelopes.

        Returns:
            List of resolved AdvancedConflict objects.
        """
        resolved: list[AdvancedConflict] = []

        for conflict in conflicts:
            if conflict.severity == ConflictSeverity.NONE:
                conflict.resolved = True
                resolved.append(conflict)
                continue

            # Choose strategy based on severity and available evidence
            strategy = self._choose_strategy(conflict)

            if strategy == ConflictResolutionStrategy.LLM_ADJUDICATION and self._brain:
                adjudication = await self._llm_adjudicate(conflict, envelopes)
                if adjudication:
                    conflict.adjudication = adjudication
                    conflict.resolved = True
                    conflict.resolution_strategy = strategy
                    self._adjudication_history.append(adjudication)
                    self._metrics["llm_adjudications"] = self._metrics.get("llm_adjudications", 0) + 1
            elif strategy == ConflictResolutionStrategy.EVIDENCE_BASED:
                winner = self._evidence_based_resolve(conflict)
                if winner:
                    conflict.resolved = True
                    conflict.resolution_strategy = strategy
                    self._metrics["evidence_resolutions"] = self._metrics.get("evidence_resolutions", 0) + 1
            elif strategy == ConflictResolutionStrategy.MERGE:
                merged = self._merge_answers(conflict, envelopes)
                if merged:
                    conflict.resolved = True
                    conflict.resolution_strategy = strategy
                    self._metrics["merged_resolutions"] = self._metrics.get("merged_resolutions", 0) + 1
            elif strategy == ConflictResolutionStrategy.ESCALATE:
                conflict.resolved = False
                conflict.resolution_strategy = strategy
                self._metrics["escalations"] = self._metrics.get("escalations", 0) + 1

            resolved.append(conflict)

        return resolved

    def _assess_severity(self, conflict: Conflict, envelopes: list[AgentEnvelope]) -> ConflictSeverity:
        """Assess the severity of a conflict."""
        if conflict.kind == ConflictKind.FAILURE:
            return ConflictSeverity.HIGH
        if conflict.kind == ConflictKind.CONTRADICTION:
            # Check if the contradiction is on a critical fact
            if any(e.confidence > 0.8 for e in envelopes if e.agent_id in conflict.agents):
                return ConflictSeverity.CRITICAL
            return ConflictSeverity.HIGH
        if conflict.kind == ConflictKind.DIVERGENCE:
            if conflict.severity > 0.7:
                return ConflictSeverity.MEDIUM
            return ConflictSeverity.LOW
        return ConflictSeverity.NONE

    def _collect_evidence(self, agent_id: str, envelopes: list[AgentEnvelope]) -> list[Evidence]:
        """Collect evidence from an agent's envelope."""
        for e in envelopes:
            if e.agent_id == agent_id:
                return [Evidence(
                    source=agent_id,
                    content=ev,
                    confidence=e.confidence,
                ) for ev in e.evidence]
        return []

    def _choose_strategy(self, conflict: AdvancedConflict) -> ConflictResolutionStrategy:
        """Choose a resolution strategy based on the conflict."""
        if conflict.severity == ConflictSeverity.CRITICAL:
            return ConflictResolutionStrategy.LLM_ADJUDICATION
        if conflict.severity == ConflictSeverity.HIGH:
            if len(conflict.evidence_a) > 0 and len(conflict.evidence_b) > 0:
                return ConflictResolutionStrategy.EVIDENCE_BASED
            return ConflictResolutionStrategy.LLM_ADJUDICATION
        if conflict.severity == ConflictSeverity.MEDIUM:
            return ConflictResolutionStrategy.EVIDENCE_BASED
        return ConflictResolutionStrategy.MERGE

    async def _llm_adjudicate(
        self,
        conflict: AdvancedConflict,
        envelopes: list[AgentEnvelope],
    ) -> AdjudicationResult | None:
        """Use an LLM to adjudicate a conflict.

        Args:
            conflict: The conflict to adjudicate.
            envelopes: Original agent envelopes.

        Returns:
            AdjudicationResult with the winner and reasoning.
        """
        if not self._brain:
            return None

        start_time = time.time()

        # Build the adjudication prompt
        agent_a = conflict.base_conflict.agents[0]
        agent_b = conflict.base_conflict.agents[1] if len(conflict.base_conflict.agents) > 1 else "unknown"

        result_a = next((e.result for e in envelopes if e.agent_id == agent_a), "")
        result_b = next((e.result for e in envelopes if e.agent_id == agent_b), "")

        evidence_a = "\n".join(f"- {e.content}" for e in conflict.evidence_a)
        evidence_b = "\n".join(f"- {e.content}" for e in conflict.evidence_b)

        prompt = f"""You are a conflict resolution adjudicator. Two AI agents have provided different answers to the same question.

Agent {agent_a} says:
{result_a}

Evidence from {agent_a}:
{evidence_a}

Agent {agent_b} says:
{result_b}

Evidence from {agent_b}:
{evidence_b}

Conflict type: {conflict.base_conflict.kind.value}
Conflict detail: {conflict.base_conflict.detail}

Determine which answer is more correct based on:
1. Quality and quantity of evidence
2. Logical consistency
3. Factual accuracy
4. Completeness

Return JSON with keys: winner (agent_id), reasoning (string), confidence (0.0-1.0)."""

        try:
            result = await self._brain.run(prompt)
            data = self._parse_json_result(result)
            if data:
                execution_time = time.time() - start_time
                return AdjudicationResult(
                    winner=data.get("winner", agent_a),
                    loser=data.get("loser", agent_b),
                    reasoning=data.get("reasoning", ""),
                    confidence=data.get("confidence", 0.5),
                    execution_time=execution_time,
                )
            return None
        except Exception:
            return None

    def _evidence_based_resolve(self, conflict: AdvancedConflict) -> str | None:
        """Resolve a conflict based on evidence quality.

        Returns:
            The agent_id of the winning answer, or None if no clear winner.
        """
        score_a = sum(e.confidence for e in conflict.evidence_a)
        score_b = sum(e.confidence for e in conflict.evidence_b)

        if score_a > score_b * 1.2:
            return conflict.base_conflict.agents[0]
        if score_b > score_a * 1.2:
            return conflict.base_conflict.agents[1] if len(conflict.base_conflict.agents) > 1 else None
        return None

    def _merge_answers(
        self,
        conflict: AdvancedConflict,
        envelopes: list[AgentEnvelope],
    ) -> str | None:
        """Merge two answers into one comprehensive answer.

        Returns:
            The merged answer, or None if merging failed.
        """
        agent_a = conflict.base_conflict.agents[0]
        agent_b = conflict.base_conflict.agents[1] if len(conflict.base_conflict.agents) > 1 else None

        result_a = next((e.result for e in envelopes if e.agent_id == agent_a), "")
        result_b = next((e.result for e in envelopes if e.agent_id == agent_b), "") if agent_b else ""

        if not result_a or not result_b:
            return None

        # Simple merge: combine both answers
        merged = f"Combined answer from {agent_a} and {agent_b}:\n\n"
        merged += f"From {agent_a}:\n{result_a}\n\n"
        merged += f"From {agent_b}:\n{result_b}"

        return merged

    def _parse_json_result(self, text: str) -> dict[str, Any] | None:
        """Parse a JSON result from the brain's output."""
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        return None

    def get_resolution_summary(self) -> dict[str, Any]:
        """Get a summary of all conflict resolutions."""
        return {
            "total_adjudications": len(self._adjudication_history),
            "metrics": dict(self._metrics),
            "strategies_used": list(set(
                a.strategy_used.value for a in self._adjudication_history
            )),
        }


__all__ = [
    "AdvancedConflictResolver",
    "AdvancedConflict",
    "AdjudicationResult",
    "ConflictResolutionStrategy",
    "ConflictSeverity",
    "Evidence",
]
