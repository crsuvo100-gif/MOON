"""Memory reasoning engine -- deductive, inductive, and abductive reasoning.

Professional AI assistants don't just retrieve memories -- they REASON over
them. This module provides three reasoning modes:

1. Deductive: Apply general rules to specific memories (if all X are Y, and
   this is X, then it is Y)
2. Inductive: Extract general patterns from specific memories (these 5
   memories about API failures suggest a pattern)
3. Abductive: Infer the most likely explanation for an observation (the
   service is down, the most likely cause from memory is X)

The reasoning engine operates on the existing memory store and returns
structured reasoning results with confidence scores.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ReasoningResult:
    """A single reasoning result."""
    conclusion: str
    reasoning_type: str  # "deductive", "inductive", "abductive"
    confidence: float    # 0.0 - 1.0
    premises: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conclusion": self.conclusion,
            "reasoning_type": self.reasoning_type,
            "confidence": round(self.confidence, 4),
            "premises": self.premises,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }


@dataclass
class ReasoningChain:
    """A chain of reasoning steps leading to a conclusion."""
    steps: list[ReasoningResult] = field(default_factory=list)
    final_conclusion: str = ""
    overall_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "final_conclusion": self.final_conclusion,
            "overall_confidence": round(self.overall_confidence, 4),
        }


class MemoryReasoningEngine:
    """Reasons over stored memories to derive new insights.

    Usage:
        engine = MemoryReasoningEngine(memory_manager)
        results = engine.reason("Why did the API fail?", mode="abductive")
        chain = engine.reason_chain("Is this a recurring problem?")
    """

    def __init__(self, memory_manager=None) -> None:
        self._mm = memory_manager
        self._reasoning_count = 0
        self._last_reasoning = 0.0

    def reason(
        self,
        query: str,
        mode: str = "abductive",
        top_k: int = 10,
        min_confidence: float = 0.3,
    ) -> list[ReasoningResult]:
        """Reason over memories to answer a query.

        Args:
            query: The question to reason about.
            mode: "deductive", "inductive", or "abductive".
            top_k: Maximum memories to consider.
            min_confidence: Minimum confidence threshold.

        Returns:
            List of ReasoningResult sorted by confidence.
        """
        if not query or not query.strip():
            return []

        self._reasoning_count += 1
        self._last_reasoning = time.time()

        # Retrieve relevant memories
        memories = self._retrieve_memories(query, top_k)
        if not memories:
            return []

        if mode == "deductive":
            return self._deductive_reason(query, memories, min_confidence)
        elif mode == "inductive":
            return self._inductive_reason(query, memories, min_confidence)
        else:
            return self._abductive_reason(query, memories, min_confidence)

    def reason_chain(
        self,
        query: str,
        max_steps: int = 5,
        min_confidence: float = 0.3,
    ) -> ReasoningChain:
        """Build a multi-step reasoning chain.

        Each step uses the previous step's conclusion as additional context.
        """
        chain = ReasoningChain()
        current_query = query

        for step in range(max_steps):
            results = self.reason(current_query, mode="abductive", min_confidence=min_confidence)
            if not results:
                break

            best = results[0]
            chain.steps.append(best)

            # Use the conclusion as context for the next step
            current_query = f"{query} (considering: {best.conclusion})"

            if best.confidence >= 0.8:
                break  # High confidence, no need to continue

        if chain.steps:
            chain.final_conclusion = chain.steps[-1].conclusion
            # Overall confidence is the product of all step confidences
            conf = 1.0
            for s in chain.steps:
                conf *= s.confidence
            chain.overall_confidence = conf

        return chain

    def _retrieve_memories(self, query: str, top_k: int) -> list[Any]:
        """Retrieve relevant memories from the memory manager."""
        if self._mm is None:
            return []
        try:
            results = self._mm.search(query, top_k=top_k)
            return results
        except Exception as exc:
            logger.debug("Reasoning memory retrieval failed: %s", exc)
            return []

    def _deductive_reason(
        self,
        query: str,
        memories: list[Any],
        min_confidence: float,
    ) -> list[ReasoningResult]:
        """Apply general rules from memories to the specific query.

        Looks for patterns like "all X are Y" or "X causes Y" in memories,
        then applies them to the query context.
        """
        results: list[ReasoningResult] = []
        query_lower = query.lower()

        # Extract potential rules from memories
        rules = self._extract_rules(memories)
        for rule in rules:
            # Check if the rule applies to the query
            if self._rule_applies(rule, query_lower):
                confidence = rule.get("confidence", 0.5) * 0.9  # Deduction is strong
                if confidence >= min_confidence:
                    results.append(ReasoningResult(
                        conclusion=rule.get("conclusion", ""),
                        reasoning_type="deductive",
                        confidence=confidence,
                        premises=[rule.get("premise", "")],
                        evidence=rule.get("evidence", []),
                    ))

        # Also check for direct implications
        for mem in memories:
            content = self._get_content(mem)
            if "always" in content.lower() or "never" in content.lower():
                # This memory states a general rule
                confidence = 0.7
                if confidence >= min_confidence:
                    results.append(ReasoningResult(
                        conclusion=f"Based on stored rule: {content[:200]}",
                        reasoning_type="deductive",
                        confidence=confidence,
                        premises=[content[:200]],
                        evidence=[content[:200]],
                    ))

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def _inductive_reason(
        self,
        query: str,
        memories: list[Any],
        min_confidence: float,
    ) -> list[ReasoningResult]:
        """Extract general patterns from specific memories.

        Looks for common themes, repeated patterns, or trends across
        multiple memories.
        """
        results: list[ReasoningResult] = []
        if len(memories) < 2:
            return results

        # Extract common keywords across memories
        all_words: dict[str, int] = {}
        for mem in memories:
            content = self._get_content(mem)
            words = set(re.findall(r"[a-z_]{3,}", content.lower()))
            for w in words:
                all_words[w] = all_words.get(w, 0) + 1

        # Find words that appear in multiple memories (potential patterns)
        common_words = {w: c for w, c in all_words.items() if c >= len(memories) * 0.5}
        if common_words:
            # Sort by frequency
            sorted_words = sorted(common_words.items(), key=lambda x: x[1], reverse=True)
            pattern_words = [w for w, _ in sorted_words[:5]]

            confidence = min(0.9, 0.3 + 0.1 * len(pattern_words))
            if confidence >= min_confidence:
                results.append(ReasoningResult(
                    conclusion=f"Pattern detected: {', '.join(pattern_words)} "
                              f"(appears in {len(memories)} memories)",
                    reasoning_type="inductive",
                    confidence=confidence,
                    premises=[self._get_content(m)[:100] for m in memories[:3]],
                    evidence=[self._get_content(m)[:100] for m in memories],
                ))

        # Check for temporal patterns (e.g., "this happens every time")
        temporal_patterns = self._find_temporal_patterns(memories)
        for pattern in temporal_patterns:
            if pattern["confidence"] >= min_confidence:
                results.append(ReasoningResult(
                    conclusion=pattern["description"],
                    reasoning_type="inductive",
                    confidence=pattern["confidence"],
                    premises=pattern["premises"],
                    evidence=pattern["evidence"],
                ))

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def _abductive_reason(
        self,
        query: str,
        memories: list[Any],
        min_confidence: float,
    ) -> list[ReasoningResult]:
        """Infer the most likely explanation for an observation.

        Given a query describing a situation, find the most likely cause
        or explanation from stored memories.
        """
        results: list[ReasoningResult] = []
        query_lower = query.lower()

        # Score each memory as a potential explanation
        scored_explanations: list[tuple[float, str, str]] = []
        for mem in memories:
            content = self._get_content(mem)
            content_lower = content.lower()

            # Check for causal language
            causal_score = 0.0
            if any(word in content_lower for word in ["because", "caused", "due to", "reason", "why"]):
                causal_score += 0.3
            if any(word in content_lower for word in ["failed", "error", "broken", "issue", "problem"]):
                causal_score += 0.2

            # Keyword overlap
            query_words = set(re.findall(r"[a-z_]{3,}", query_lower))
            content_words = set(re.findall(r"[a-z_]{3,}", content_lower))
            if query_words:
                overlap = len(query_words & content_words) / len(query_words)
                causal_score += overlap * 0.5

            if causal_score > 0:
                scored_explanations.append((causal_score, content, content))

        # Sort by score
        scored_explanations.sort(key=lambda x: x[0], reverse=True)

        for score, content, premise in scored_explanations[:5]:
            confidence = min(0.95, score)
            if confidence >= min_confidence:
                results.append(ReasoningResult(
                    conclusion=f"Most likely explanation: {content[:300]}",
                    reasoning_type="abductive",
                    confidence=confidence,
                    premises=[premise[:200]],
                    evidence=[content[:200]],
                ))

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def _extract_rules(self, memories: list[Any]) -> list[dict[str, Any]]:
        """Extract potential rules from memories."""
        rules: list[dict[str, Any]] = []
        for mem in memories:
            content = self._get_content(mem)
            content_lower = content.lower()

            # Look for "X causes Y" patterns
            if "causes" in content_lower or "leads to" in content_lower:
                rules.append({
                    "premise": content[:200],
                    "conclusion": f"Cause identified: {content[:200]}",
                    "confidence": 0.7,
                    "evidence": [content[:200]],
                })

            # Look for "X always/never Y" patterns
            if "always" in content_lower or "never" in content_lower:
                rules.append({
                    "premise": content[:200],
                    "conclusion": f"General rule: {content[:200]}",
                    "confidence": 0.8,
                    "evidence": [content[:200]],
                })

        return rules

    def _rule_applies(self, rule: dict[str, Any], query: str) -> bool:
        """Check if a rule applies to the query."""
        premise = rule.get("premise", "").lower()
        # Simple keyword overlap check
        premise_words = set(re.findall(r"[a-z_]{3,}", premise))
        query_words = set(re.findall(r"[a-z_]{3,}", query))
        if not premise_words:
            return False
        overlap = len(premise_words & query_words) / len(premise_words)
        return overlap >= 0.3

    def _find_temporal_patterns(self, memories: list[Any]) -> list[dict[str, Any]]:
        """Find temporal patterns across memories."""
        patterns: list[dict[str, Any]] = []

        # Check for repeated failures
        failure_count = 0
        for mem in memories:
            content = self._get_content(mem).lower()
            if any(w in content for w in ["failed", "error", "timeout", "crash"]):
                failure_count += 1

        if failure_count >= 3:
            patterns.append({
                "description": f"Recurring issue detected: {failure_count} related failures found",
                "confidence": min(0.9, 0.4 + 0.1 * failure_count),
                "premises": [self._get_content(m)[:100] for m in memories[:3]],
                "evidence": [self._get_content(m)[:100] for m in memories],
            })

        return patterns

    @staticmethod
    def _get_content(mem: Any) -> str:
        """Extract content from a memory result."""
        if hasattr(mem, "content"):
            return str(mem.content)
        if hasattr(mem, "record"):
            return str(mem.record.content)
        return str(mem)

    def stats(self) -> dict[str, Any]:
        """Return reasoning engine statistics."""
        return {
            "reasoning_count": self._reasoning_count,
            "last_reasoning": self._last_reasoning,
        }
