"""context_reasoning.py — situational awareness and contextual reasoning.

Professional AI agents understand and reason about the context in which
they operate, including environmental factors, social dynamics, temporal
constraints, and situational nuances. This module provides context reasoning
capabilities including context modeling, situational analysis, and adaptive
behavior based on contextual factors.

Context reasoning capabilities:
- Context modeling and representation
- Situational analysis and classification
- Context-aware reasoning and adaptation
- Temporal and spatial context reasoning
- Social and environmental context analysis
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


class ContextType(str, Enum):
    ENVIRONMENTAL = "environmental"
    SOCIAL = "social"
    TEMPORAL = "temporal"
    SPATIAL = "spatial"
    TASK = "task"
    EMOTIONAL = "emotional"
    CULTURAL = "cultural"


class ContextPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SituationType(str, Enum):
    ROUTINE = "routine"
    NOVEL = "novel"
    COMPLEX = "complex"
    CRISIS = "crisis"
    AMBIGUOUS = "ambiguous"


@dataclass
class ContextFactor:
    factor_id: str
    name: str
    context_type: ContextType
    value: Any
    priority: ContextPriority = ContextPriority.MEDIUM
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ContextModel:
    model_id: str
    name: str
    factors: dict[str, ContextFactor] = field(default_factory=dict)
    situation: SituationType = SituationType.ROUTINE
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def add_factor(self, factor: ContextFactor) -> None:
        self.factors[factor.factor_id] = factor
        self.updated_at = time.time()

    def get_factors_by_type(self, context_type: ContextType) -> list[ContextFactor]:
        return [f for f in self.factors.values() if f.context_type == context_type]

    def get_factors_by_priority(self, priority: ContextPriority) -> list[ContextFactor]:
        return [f for f in self.factors.values() if f.priority == priority]

    def get_critical_factors(self) -> list[ContextFactor]:
        return self.get_factors_by_priority(ContextPriority.CRITICAL)


@dataclass
class SituationalAnalysis:
    analysis_id: str
    context_model_id: str
    situation_type: SituationType = SituationType.ROUTINE
    key_factors: list[str] = field(default_factory=list)
    implications: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ContextAdaptation:
    adaptation_id: str
    context_model_id: str
    original_behavior: str
    adapted_behavior: str = ""
    trigger_factors: list[str] = field(default_factory=list)
    adaptation_rationale: str = ""
    timestamp: float = field(default_factory=time.time)


class ContextReasoner:
    """Contextual reasoning and situational awareness engine."""

    def __init__(
        self,
        llm_agent: Callable[[str, str], Awaitable[str]] | None = None,
    ) -> None:
        self._llm = llm_agent
        self._models: dict[str, ContextModel] = {}
        self._analyses: dict[str, SituationalAnalysis] = {}
        self._adaptations: dict[str, ContextAdaptation] = {}

    def create_model(self, name: str, description: str = "") -> ContextModel:
        """Create a new context model."""
        model = ContextModel(
            model_id=str(uuid.uuid4())[:8],
            name=name,
            summary=description,
        )
        self._models[model.model_id] = model
        return model

    def get_model(self, model_id: str) -> ContextModel | None:
        return self._models.get(model_id)

    def add_context_factor(
        self,
        model_id: str,
        name: str,
        context_type: ContextType,
        value: Any,
        priority: ContextPriority = ContextPriority.MEDIUM,
        description: str = "",
    ) -> ContextFactor | None:
        """Add a context factor to a model."""
        model = self._models.get(model_id)
        if not model:
            return None
        factor = ContextFactor(
            factor_id=str(uuid.uuid4())[:8],
            name=name,
            context_type=context_type,
            value=value,
            priority=priority,
            description=description,
        )
        model.add_factor(factor)
        return factor

    async def analyze_situation(
        self,
        model_id: str,
        query: str = "",
    ) -> SituationalAnalysis:
        """Analyze the current situation based on context model."""
        model = self._models.get(model_id)
        if not model:
            raise ValueError(f"Context model {model_id} not found")

        analysis = SituationalAnalysis(
            analysis_id=str(uuid.uuid4())[:8],
            context_model_id=model_id,
        )

        # Determine situation type
        analysis.situation_type = self._classify_situation(model)

        # Identify key factors
        critical = model.get_critical_factors()
        high = model.get_factors_by_priority(ContextPriority.HIGH)
        analysis.key_factors = [f.factor_id for f in critical + high]

        # Generate implications
        analysis.implications = self._generate_implications(model, analysis.situation_type)

        # Generate recommended actions
        analysis.recommended_actions = self._generate_recommendations(model, analysis.situation_type)

        # Identify risks and opportunities
        analysis.risks = self._identify_risks(model)
        analysis.opportunities = self._identify_opportunities(model)

        # Compute confidence
        analysis.confidence = self._compute_analysis_confidence(model, analysis)

        # Build reasoning
        analysis.reasoning = self._build_situational_reasoning(model, analysis)

        # LLM enhancement
        if self._llm:
            try:
                prompt = self._build_situational_prompt(model, analysis, query)
                response = await self._llm(prompt, "situational_analysis")
                analysis.reasoning = response[:500]
            except Exception as e:
                logger.warning("LLM situational analysis failed: %s", e)

        self._analyses[analysis.analysis_id] = analysis
        return analysis

    async def adapt_behavior(
        self,
        model_id: str,
        original_behavior: str,
        query: str = "",
    ) -> ContextAdaptation:
        """Adapt behavior based on context."""
        model = self._models.get(model_id)
        if not model:
            raise ValueError(f"Context model {model_id} not found")

        adaptation = ContextAdaptation(
            adaptation_id=str(uuid.uuid4())[:8],
            context_model_id=model_id,
            original_behavior=original_behavior,
        )

        # Identify trigger factors
        critical = model.get_critical_factors()
        adaptation.trigger_factors = [f.factor_id for f in critical]

        # Generate adapted behavior
        if self._llm:
            prompt = (
                f"Adapt the following behavior based on context:\n"
                f"Original behavior: {original_behavior}\n"
                f"Context factors: {[(f.name, f.value) for f in model.factors.values()]}\n"
                f"Situation: {model.situation}\n"
                f"Query: {query}\n"
                f"Provide adapted behavior:"
            )
            try:
                response = await self._llm(prompt, "behavior_adaptation")
                adaptation.adapted_behavior = response[:500]
            except Exception as e:
                logger.warning("LLM behavior adaptation failed: %s", e)
                adaptation.adapted_behavior = original_behavior
        else:
            adaptation.adapted_behavior = self._default_adaptation(original_behavior, model)

        adaptation.adaptation_rationale = self._build_adaptation_rationale(model, adaptation)

        self._adaptations[adaptation.adaptation_id] = adaptation
        return adaptation

    def _classify_situation(self, model: ContextModel) -> SituationType:
        """Classify the situation type based on context factors."""
        critical_count = len(model.get_critical_factors())
        high_count = len(model.get_factors_by_priority(ContextPriority.HIGH))
        total_factors = len(model.factors)

        if critical_count >= 3:
            return SituationType.CRISIS
        elif critical_count >= 1 or high_count >= 3:
            return SituationType.COMPLEX
        elif total_factors == 0:
            return SituationType.AMBIGUOUS
        elif total_factors <= 3:
            return SituationType.ROUTINE
        else:
            return SituationType.NOVEL

    def _generate_implications(self, model: ContextModel, situation: SituationType) -> list[str]:
        """Generate implications based on context."""
        implications = []
        for factor in model.factors.values():
            if factor.priority in (ContextPriority.HIGH, ContextPriority.CRITICAL):
                implications.append(f"{factor.name}: {factor.description or factor.value}")
        if situation == SituationType.CRISIS:
            implications.append("Immediate action required")
        elif situation == SituationType.COMPLEX:
            implications.append("Careful analysis needed before action")
        return implications

    def _generate_recommendations(self, model: ContextModel, situation: SituationType) -> list[str]:
        """Generate recommended actions based on context."""
        recs = []
        if situation == SituationType.CRISIS:
            recs.append("Prioritize critical factors")
            recs.append("Take immediate corrective action")
        elif situation == SituationType.COMPLEX:
            recs.append("Analyze multiple approaches")
            recs.append("Consider trade-offs carefully")
        elif situation == SituationType.NOVEL:
            recs.append("Explore new strategies")
            recs.append("Learn from the situation")
        elif situation == SituationType.AMBIGUOUS:
            recs.append("Gather more information")
            recs.append("Clarify the situation")
        else:
            recs.append("Follow standard procedures")
        return recs

    def _identify_risks(self, model: ContextModel) -> list[str]:
        """Identify risks from context factors."""
        risks = []
        for factor in model.factors.values():
            if factor.priority == ContextPriority.CRITICAL:
                risks.append(f"Critical risk: {factor.name}")
            elif factor.context_type == ContextType.EMOTIONAL and factor.priority == ContextPriority.HIGH:
                risks.append(f"Emotional risk: {factor.name}")
        return risks

    def _identify_opportunities(self, model: ContextModel) -> list[str]:
        """Identify opportunities from context factors."""
        opportunities = []
        for factor in model.factors.values():
            if factor.context_type == ContextType.SOCIAL and factor.priority == ContextPriority.HIGH:
                opportunities.append(f"Social opportunity: {factor.name}")
            elif factor.context_type == ContextType.TASK and factor.priority == ContextPriority.MEDIUM:
                opportunities.append(f"Task opportunity: {factor.name}")
        return opportunities

    def _compute_analysis_confidence(self, model: ContextModel, analysis: SituationalAnalysis) -> float:
        """Compute confidence in situational analysis."""
        if not model.factors:
            return 0.3
        # More factors = higher confidence
        factor_coverage = min(len(model.factors) / 10, 0.5)
        # Critical factors increase confidence
        critical_bonus = min(len(model.get_critical_factors()) * 0.1, 0.3)
        # Key factors identified
        key_factor_bonus = min(len(analysis.key_factors) * 0.05, 0.2)
        return min(factor_coverage + critical_bonus + key_factor_bonus, 1.0)

    def _build_situational_reasoning(self, model: ContextModel, analysis: SituationalAnalysis) -> str:
        """Build human-readable situational reasoning."""
        parts = [
            f"Situational Analysis for: {model.name}",
            f"Situation type: {analysis.situation_type.value}",
            f"Key factors: {len(analysis.key_factors)}",
            f"Implications: {analysis.implications}",
            f"Recommendations: {analysis.recommended_actions}",
        ]
        return "\n".join(parts)

    def _build_situational_prompt(self, model: ContextModel, analysis: SituationalAnalysis, query: str) -> str:
        """Build prompt for LLM-enhanced situational analysis."""
        parts = [
            f"Situational analysis for: {model.name}",
            f"Context factors: {[(f.name, f.context_type.value, f.value) for f in model.factors.values()]}",
            f"Situation type: {analysis.situation_type.value}",
            f"Query: {query}",
            "Provide deeper situational analysis:",
        ]
        return "\n".join(parts)

    def _default_adaptation(self, original_behavior: str, model: ContextModel) -> str:
        """Default behavior adaptation when LLM is unavailable."""
        critical = model.get_critical_factors()
        if critical:
            return f"Adapted for critical context: {original_behavior} (considering {', '.join(f.name for f in critical)})"
        return original_behavior

    def _build_adaptation_rationale(self, model: ContextModel, adaptation: ContextAdaptation) -> str:
        """Build adaptation rationale."""
        parts = [f"Behavior adapted based on context: {model.name}"]
        if adaptation.trigger_factors:
            parts.append(f"Trigger factors: {adaptation.trigger_factors}")
        parts.append(f"Original: {adaptation.original_behavior[:100]}")
        parts.append(f"Adapted: {adaptation.adapted_behavior[:100]}")
        return "\n".join(parts)

    def list_models(self) -> list[str]:
        return list(self._models.keys())

    def list_analyses(self) -> list[str]:
        return list(self._analyses.keys())

    def list_adaptations(self) -> list[str]:
        return list(self._adaptations.keys())
