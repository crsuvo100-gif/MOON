"""Multi-Model Consensus — critical decision validation.

For important decisions, queries multiple LLM backends and uses
consensus algorithms to determine the most reliable answer. Reduces
single-model bias and hallucination risk.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class ConsensusStrategy(Enum):
    MAJORITY = "majority"
    WEIGHTED = "weighted"
    UNANIMOUS = "unanimous"
    BEST_SCORE = "best_score"


class ConfidenceLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ModelResponse:
    """A response from a single model."""
    model_name: str
    response: str
    latency: float
    confidence: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConsensusResult:
    """Result of multi-model consensus."""
    answer: str
    confidence: float
    level: ConfidenceLevel
    strategy: ConsensusStrategy
    responses: list[ModelResponse] = field(default_factory=list)
    agreement_ratio: float = 0.0
    execution_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class MultiModelConsensus:
    """Multi-model consensus for critical decisions.

    Queries multiple LLM backends and uses consensus algorithms
    to determine the most reliable answer.
    """

    def __init__(
        self,
        *,
        strategy: ConsensusStrategy = ConsensusStrategy.WEIGHTED,
        min_agreement: float = 0.6,
        max_models: int = 3,
        timeout: float = 30.0,
    ) -> None:
        self._strategy = strategy
        self._min_agreement = min_agreement
        self._max_models = max_models
        self._timeout = timeout
        self._model_weights: dict[str, float] = {}
        self._metrics: dict[str, int] = defaultdict(int)

    def set_model_weight(self, model: str, weight: float) -> None:
        """Set a weight for a model (higher = more trusted)."""
        self._model_weights[model] = max(0.1, min(1.0, weight))

    async def reach_consensus(
        self,
        *,
        prompt: str,
        models: list[tuple[str, Any]],  # (name, llm_service)
        system_prompt: str = "",
        temperature: float = 0.3,
    ) -> ConsensusResult:
        """Query multiple models and reach consensus.

        Args:
            prompt: The prompt to send to all models.
            models: List of (name, llm_service) tuples.
            system_prompt: Optional system prompt.
            temperature: Sampling temperature.

        Returns:
            ConsensusResult with the consensus answer.
        """
        start_time = time.time()
        self._metrics["consensus_requests"] += 1

        # Query all models in parallel
        tasks = []
        for name, llm in models[:self._max_models]:
            tasks.append(self._query_model(name, llm, prompt, system_prompt, temperature))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter successful responses
        responses: list[ModelResponse] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Model query failed: %s", result)
                self._metrics["model_failures"] += 1
            elif isinstance(result, ModelResponse):
                responses.append(result)

        if not responses:
            return ConsensusResult(
                answer="",
                confidence=0.0,
                level=ConfidenceLevel.LOW,
                strategy=self._strategy,
                execution_time=time.time() - start_time,
            )

        if len(responses) == 1:
            return ConsensusResult(
                answer=responses[0].response,
                confidence=responses[0].confidence * 0.7,  # Reduced confidence with single model
                level=ConfidenceLevel.LOW,
                strategy=self._strategy,
                responses=responses,
                agreement_ratio=1.0,
                execution_time=time.time() - start_time,
            )

        # Apply consensus strategy
        if self._strategy == ConsensusStrategy.MAJORITY:
            answer, agreement = self._majority_vote(responses)
        elif self._strategy == ConsensusStrategy.WEIGHTED:
            answer, agreement = self._weighted_consensus(responses)
        elif self._strategy == ConsensusStrategy.UNANIMOUS:
            answer, agreement = self._unanimous_consensus(responses)
        else:  # BEST_SCORE
            answer, agreement = self._best_score(responses)

        # Determine confidence level
        confidence = self._calculate_confidence(responses, agreement)
        level = self._determine_level(confidence, agreement)

        execution_time = time.time() - start_time
        self._metrics["consensus_success"] += 1

        return ConsensusResult(
            answer=answer,
            confidence=confidence,
            level=level,
            strategy=self._strategy,
            responses=responses,
            agreement_ratio=agreement,
            execution_time=execution_time,
            metadata={
                "models_queried": len(models),
                "models_responded": len(responses),
                "model_names": [r.model_name for r in responses],
            },
        )

    async def _query_model(
        self,
        name: str,
        llm: Any,
        prompt: str,
        system_prompt: str,
        temperature: float,
    ) -> ModelResponse:
        """Query a single model."""
        start = time.time()
        try:
            response = await asyncio.wait_for(
                llm.complete(
                    prompt=prompt,
                    system=system_prompt,
                    temperature=temperature,
                    max_tokens=2048,
                ),
                timeout=self._timeout,
            )
            latency = time.time() - start
            text = response if isinstance(response, str) else str(response)
            return ModelResponse(
                model_name=name,
                response=text,
                latency=latency,
                confidence=0.7,  # Base confidence
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Model %s query failed: %s", name, exc)
            raise

    def _majority_vote(self, responses: list[ModelResponse]) -> tuple[str, float]:
        """Simple majority vote based on response similarity."""
        if not responses:
            return "", 0.0

        # Group similar responses
        groups: list[list[ModelResponse]] = []
        for r in responses:
            placed = False
            for group in groups:
                if self._responses_similar(r.response, group[0].response):
                    group.append(r)
                    placed = True
                    break
            if not placed:
                groups.append([r])

        # Find largest group
        largest = max(groups, key=len)
        agreement = len(largest) / len(responses)

        # Return the most confident response from the largest group
        best = max(largest, key=lambda r: r.confidence)
        return best.response, agreement

    def _weighted_consensus(self, responses: list[ModelResponse]) -> tuple[str, float]:
        """Weighted consensus based on model weights and confidence."""
        if not responses:
            return "", 0.0

        # Group similar responses
        groups: list[list[ModelResponse]] = []
        for r in responses:
            placed = False
            for group in groups:
                if self._responses_similar(r.response, group[0].response):
                    group.append(r)
                    placed = True
                    break
            if not placed:
                groups.append([r])

        # Calculate weighted score for each group
        best_group = None
        best_score = -1.0
        for group in groups:
            score = sum(
                r.confidence * self._model_weights.get(r.model_name, 0.5)
                for r in group
            )
            if score > best_score:
                best_score = score
                best_group = group

        if not best_group:
            return "", 0.0

        agreement = len(best_group) / len(responses)
        # Return the response from the highest-weighted model in the group
        best = max(best_group, key=lambda r: self._model_weights.get(r.model_name, 0.5))
        return best.response, agreement

    def _unanimous_consensus(self, responses: list[ModelResponse]) -> tuple[str, float]:
        """Require unanimous agreement."""
        if not responses:
            return "", 0.0

        # Check if all responses are similar
        first = responses[0].response
        all_similar = all(self._responses_similar(r.response, first) for r in responses[1:])

        if all_similar:
            return first, 1.0
        else:
            # Fall back to majority
            return self._majority_vote(responses)

    def _best_score(self, responses: list[ModelResponse]) -> tuple[str, float]:
        """Pick the response with the highest confidence score."""
        if not responses:
            return "", 0.0

        best = max(responses, key=lambda r: r.confidence * self._model_weights.get(r.model_name, 0.5))
        # Calculate agreement as ratio of models with similar responses
        similar_count = sum(1 for r in responses if self._responses_similar(r.response, best.response))
        agreement = similar_count / len(responses)
        return best.response, agreement

    def _responses_similar(self, a: str, b: str, threshold: float = 0.7) -> bool:
        """Check if two responses are similar using token overlap."""
        if not a or not b:
            return False

        # Normalize
        a_tokens = set(re.findall(r"\b\w+\b", a.lower()))
        b_tokens = set(re.findall(r"\b\w+\b", b.lower()))

        if not a_tokens or not b_tokens:
            return False

        # Jaccard similarity
        intersection = len(a_tokens & b_tokens)
        union = len(a_tokens | b_tokens)
        similarity = intersection / union if union > 0 else 0.0

        return similarity >= threshold

    def _calculate_confidence(self, responses: list[ModelResponse], agreement: float) -> float:
        """Calculate overall confidence score."""
        if not responses:
            return 0.0

        # Average confidence of all responses
        avg_confidence = sum(r.confidence for r in responses) / len(responses)

        # Weight by agreement
        confidence = avg_confidence * (0.5 + 0.5 * agreement)

        # Boost for multiple models
        model_boost = min(0.1, len(responses) * 0.03)

        return min(1.0, confidence + model_boost)

    def _determine_level(self, confidence: float, agreement: float) -> ConfidenceLevel:
        """Determine confidence level."""
        if confidence >= 0.8 and agreement >= 0.8:
            return ConfidenceLevel.HIGH
        elif confidence >= 0.5 and agreement >= self._min_agreement:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def get_metrics(self) -> dict[str, Any]:
        return dict(self._metrics)
