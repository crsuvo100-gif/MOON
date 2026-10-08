"""decision_making.py — structured decision analysis and optimization.

Professional AI agents make complex decisions under uncertainty, balancing
multiple criteria, stakeholders, and constraints. This module provides
decision-making frameworks including multi-criteria analysis, decision trees,
expected utility theory, and risk assessment.

Decision-making methods:
- MCDA: Multi-Criteria Decision Analysis (weighted scoring)
- DECISION_TREE: Tree-based decision with probabilities
- EXPECTED_UTILITY: Expected utility maximization
- PROS_CONS: Structured pros/cons analysis
- DECISION_MATRIX: Pugh matrix for option comparison
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

from app.config.logging import get_logger

logger = get_logger(__name__)


class DecisionMethod(str, Enum):
    MCDA = "mcda"
    DECISION_TREE = "decision_tree"
    EXPECTED_UTILITY = "expected_utility"
    PROS_CONS = "pros_cons"
    DECISION_MATRIX = "decision_matrix"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionStatus(str, Enum):
    PENDING = "pending"
    ANALYZED = "analyzed"
    DECIDED = "decided"
    IMPLEMENTED = "implemented"
    REVIEWED = "reviewed"


@dataclass
class DecisionCriterion:
    criterion_id: str
    name: str
    weight: float = 1.0  # relative importance
    description: str = ""
    is_benefit: bool = True  # True = higher is better, False = lower is better
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionOption:
    option_id: str
    name: str
    description: str = ""
    scores: dict[str, float] = field(default_factory=dict)  # criterion_id -> score
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    risk_description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def weighted_score(self) -> float:
        """Compute weighted score across all criteria."""
        if not self.scores:
            return 0.0
        total_weight = sum(
            self.scores.get(c, 0.0) for c in self.scores
        )
        return total_weight / max(len(self.scores), 1)


@dataclass
class DecisionOutcome:
    outcome_id: str
    option_id: str
    probability: float = 1.0
    utility: float = 0.0
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionAnalysis:
    analysis_id: str
    topic: str
    method: DecisionMethod
    criteria: list[DecisionCriterion] = field(default_factory=list)
    options: list[DecisionOption] = field(default_factory=list)
    outcomes: list[DecisionOutcome] = field(default_factory=list)
    recommended_option: str | None = None
    confidence: float = 0.0
    reasoning: str = ""
    status: DecisionStatus = DecisionStatus.PENDING
    context: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionRecord:
    record_id: str
    analysis_id: str
    topic: str
    chosen_option: str
    rationale: str = ""
    outcome: str = ""
    status: DecisionStatus = DecisionStatus.DECIDED
    timestamp: float = field(default_factory=time.time)


class DecisionMaker:
    """Structured decision analysis and optimization engine."""

    def __init__(
        self,
        llm_agent: Callable[[str, str], Awaitable[str]] | None = None,
    ) -> None:
        self._llm = llm_agent
        self._analyses: dict[str, DecisionAnalysis] = {}
        self._records: dict[str, DecisionRecord] = {}

    async def analyze(
        self,
        topic: str,
        options: list[DecisionOption],
        criteria: list[DecisionCriterion] | None = None,
        method: DecisionMethod = DecisionMethod.MCDA,
        context: str = "",
    ) -> DecisionAnalysis:
        """Run decision analysis."""
        analysis = DecisionAnalysis(
            analysis_id=str(uuid.uuid4())[:8],
            topic=topic,
            method=method,
            options=options,
            criteria=criteria or [],
            context=context,
        )

        if method == DecisionMethod.MCDA:
            analysis = await self._run_mcda(analysis)
        elif method == DecisionMethod.DECISION_TREE:
            analysis = await self._run_decision_tree(analysis)
        elif method == DecisionMethod.EXPECTED_UTILITY:
            analysis = await self._run_expected_utility(analysis)
        elif method == DecisionMethod.PROS_CONS:
            analysis = await self._run_pros_cons(analysis)
        elif method == DecisionMethod.DECISION_MATRIX:
            analysis = await self._run_decision_matrix(analysis)

        analysis.status = DecisionStatus.ANALYZED
        self._analyses[analysis.analysis_id] = analysis
        return analysis

    async def _run_mcda(self, analysis: DecisionAnalysis) -> DecisionAnalysis:
        """Multi-Criteria Decision Analysis."""
        if not analysis.criteria:
            # Generate default criteria
            analysis.criteria = [
                DecisionCriterion(criterion_id="effectiveness", name="Effectiveness", weight=0.4),
                DecisionCriterion(criterion_id="cost", name="Cost", weight=0.3, is_benefit=False),
                DecisionCriterion(criterion_id="risk", name="Risk", weight=0.3, is_benefit=False),
            ]

        # Normalize weights
        total_weight = sum(c.weight for c in analysis.criteria)
        if total_weight > 0:
            for c in analysis.criteria:
                c.weight /= total_weight

        # Score each option
        for option in analysis.options:
            weighted_sum = 0.0
            for criterion in analysis.criteria:
                score = option.scores.get(criterion.criterion_id, 0.5)
                if not criterion.is_benefit:
                    score = 1.0 - score  # invert for cost-type criteria
                weighted_sum += score * criterion.weight
            option.scores["_weighted_total"] = weighted_sum

        # Rank options
        ranked = sorted(analysis.options, key=lambda o: o.scores.get("_weighted_total", 0), reverse=True)
        if ranked:
            analysis.recommended_option = ranked[0].option_id
            analysis.confidence = ranked[0].scores.get("_weighted_total", 0.5)

        # Build reasoning
        analysis.reasoning = self._build_mcda_reasoning(analysis, ranked)

        # LLM enhancement
        if self._llm:
            try:
                prompt = self._build_decision_prompt(analysis)
                response = await self._llm(prompt, "decision_analysis")
                analysis.reasoning = response[:500]
            except Exception as e:
                logger.warning("LLM MCDA enhancement failed: %s", e)

        return analysis

    async def _run_decision_tree(self, analysis: DecisionAnalysis) -> DecisionAnalysis:
        """Decision tree analysis with probabilities."""
        # Build outcomes for each option
        for option in analysis.options:
            # Simulate possible outcomes
            outcomes = [
                DecisionOutcome(
                    outcome_id=str(uuid.uuid4())[:8],
                    option_id=option.option_id,
                    probability=0.6,
                    utility=option.scores.get("success", 0.7),
                    description="Positive outcome",
                ),
                DecisionOutcome(
                    outcome_id=str(uuid.uuid4())[:8],
                    option_id=option.option_id,
                    probability=0.3,
                    utility=option.scores.get("partial", 0.4),
                    description="Partial success",
                ),
                DecisionOutcome(
                    outcome_id=str(uuid.uuid4())[:8],
                    option_id=option.option_id,
                    probability=0.1,
                    utility=option.scores.get("failure", 0.1),
                    description="Negative outcome",
                ),
            ]
            analysis.outcomes.extend(outcomes)

        # Compute expected utility per option
        option_utils: dict[str, float] = {}
        for option in analysis.options:
            expected = sum(o.probability * o.utility for o in analysis.outcomes if o.option_id == option.option_id)
            option_utils[option.option_id] = expected

        if option_utils:
            best = max(option_utils.items(), key=lambda x: x[1])
            analysis.recommended_option = best[0]
            analysis.confidence = best[1]

        analysis.reasoning = self._build_tree_reasoning(analysis, option_utils)
        return analysis

    async def _run_expected_utility(self, analysis: DecisionAnalysis) -> DecisionAnalysis:
        """Expected utility maximization."""
        return await self._run_decision_tree(analysis)  # Same logic

    async def _run_pros_cons(self, analysis: DecisionAnalysis) -> DecisionAnalysis:
        """Pros/cons analysis."""
        for option in analysis.options:
            pros_score = len(option.pros) * 0.1
            cons_score = len(option.cons) * 0.1
            net = pros_score - cons_score
            option.scores["_pros_cons_net"] = net

        ranked = sorted(analysis.options, key=lambda o: o.scores.get("_pros_cons_net", 0), reverse=True)
        if ranked:
            analysis.recommended_option = ranked[0].option_id
            analysis.confidence = min(abs(ranked[0].scores.get("_pros_cons_net", 0)), 1.0)

        analysis.reasoning = self._build_pros_cons_reasoning(analysis, ranked)
        return analysis

    async def _run_decision_matrix(self, analysis: DecisionAnalysis) -> DecisionAnalysis:
        """Pugh decision matrix."""
        if not analysis.options:
            return analysis

        # Use first option as baseline
        baseline = analysis.options[0]
        for option in analysis.options[1:]:
            score = 0.0
            for criterion in analysis.criteria:
                baseline_score = baseline.scores.get(criterion.criterion_id, 0.5)
                option_score = option.scores.get(criterion.criterion_id, 0.5)
                diff = option_score - baseline_score
                score += diff * criterion.weight
            option.scores["_matrix_score"] = score

        ranked = sorted(analysis.options, key=lambda o: o.scores.get("_matrix_score", 0), reverse=True)
        if ranked:
            analysis.recommended_option = ranked[0].option_id
            analysis.confidence = min(abs(ranked[0].scores.get("_matrix_score", 0)) + 0.5, 1.0)

        analysis.reasoning = self._build_matrix_reasoning(analysis, ranked)
        return analysis

    def decide(self, analysis_id: str, chosen_option: str, rationale: str = "") -> DecisionRecord:
        """Record a decision."""
        analysis = self._analyses.get(analysis_id)
        if not analysis:
            raise ValueError(f"Analysis {analysis_id} not found")

        record = DecisionRecord(
            record_id=str(uuid.uuid4())[:8],
            analysis_id=analysis_id,
            topic=analysis.topic,
            chosen_option=chosen_option,
            rationale=rationale,
        )
        analysis.status = DecisionStatus.DECIDED
        self._records[record.record_id] = record
        return record

    def get_analysis(self, analysis_id: str) -> DecisionAnalysis | None:
        return self._analyses.get(analysis_id)

    def get_record(self, record_id: str) -> DecisionRecord | None:
        return self._records.get(record_id)

    def list_analyses(self) -> list[str]:
        return list(self._analyses.keys())

    def list_records(self) -> list[str]:
        return list(self._records.keys())

    def _build_mcda_reasoning(self, analysis: DecisionAnalysis, ranked: list[DecisionOption]) -> str:
        parts = [f"MCDA Analysis for: {analysis.topic}"]
        if ranked:
            best = ranked[0]
            parts.append(f"Recommended: {best.name} (score: {best.scores.get('_weighted_total', 0):.3f})")
            parts.append("Top options:")
            for i, opt in enumerate(ranked[:3]):
                parts.append(f"  {i+1}. {opt.name}: {opt.scores.get('_weighted_total', 0):.3f}")
        return "\n".join(parts)

    def _build_tree_reasoning(self, analysis: DecisionAnalysis, option_utils: dict[str, float]) -> str:
        parts = [f"Decision Tree Analysis for: {analysis.topic}"]
        for opt_id, util in sorted(option_utils.items(), key=lambda x: x[1], reverse=True):
            parts.append(f"  {opt_id}: expected utility = {util:.3f}")
        return "\n".join(parts)

    def _build_pros_cons_reasoning(self, analysis: DecisionAnalysis, ranked: list[DecisionOption]) -> str:
        parts = [f"Pros/Cons Analysis for: {analysis.topic}"]
        if ranked:
            best = ranked[0]
            parts.append(f"Recommended: {best.name}")
            parts.append(f"  Pros: {best.pros}")
            parts.append(f"  Cons: {best.cons}")
        return "\n".join(parts)

    def _build_matrix_reasoning(self, analysis: DecisionAnalysis, ranked: list[DecisionOption]) -> str:
        parts = [f"Decision Matrix Analysis for: {analysis.topic}"]
        if ranked:
            best = ranked[0]
            parts.append(f"Recommended: {best.name} (matrix score: {best.scores.get('_matrix_score', 0):.3f})")
        return "\n".join(parts)

    def _build_decision_prompt(self, analysis: DecisionAnalysis) -> str:
        parts = [
            f"Decision analysis for: {analysis.topic}",
            f"Method: {analysis.method.value}",
            f"Options: {[(o.name, o.scores) for o in analysis.options]}",
            f"Criteria: {[(c.name, c.weight) for c in analysis.criteria]}",
            "Provide your recommendation and reasoning:",
        ]
        return "\n".join(parts)
