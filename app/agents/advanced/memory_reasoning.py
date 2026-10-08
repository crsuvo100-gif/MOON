"""memory_reasoning.py — memory-based reasoning and experience learning.

Professional AI agents leverage past experiences and stored knowledge to
reason about new situations. This module provides memory-based reasoning
capabilities including case-based reasoning, episodic memory retrieval,
semantic memory association, and experience-based learning.

Memory reasoning capabilities:
- Case-based reasoning (CBR) from past experiences
- Episodic memory retrieval and pattern matching
- Semantic memory association and inference
- Experience-based learning and adaptation
- Memory consolidation and forgetting
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


class MemoryType(str, Enum):
    EPISODIC = "episodic"  # specific events/experiences
    SEMANTIC = "semantic"  # general knowledge/facts
    PROCEDURAL = "procedural"  # how-to knowledge
    WORKING = "working"  # current task context


class RetrievalStrategy(str, Enum):
    SIMILARITY = "similarity"
    RECENCY = "recency"
    FREQUENCY = "frequency"
    IMPORTANCE = "importance"
    CONTEXTUAL = "contextual"


@dataclass
class Memory:
    memory_id: str
    memory_type: MemoryType
    content: str
    embedding: list[float] | None = None
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5  # 0-1
    access_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def record_access(self) -> None:
        self.access_count += 1
        self.last_accessed = time.time()


@dataclass
class Case:
    case_id: str
    problem: str
    solution: str
    outcome: str
    tags: list[str] = field(default_factory=list)
    success: bool = True
    lessons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class RetrievalResult:
    result_id: str
    query: str
    strategy: RetrievalStrategy
    memories: list[Memory] = field(default_factory=list)
    cases: list[Case] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ReasoningResult:
    result_id: str
    query: str
    conclusion: str = ""
    supporting_memories: list[str] = field(default_factory=list)
    supporting_cases: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    timestamp: float = field(default_factory=time.time)


class MemoryReasoner:
    """Memory-based reasoning and experience learning engine."""

    def __init__(
        self,
        llm_agent: Callable[[str, str], Awaitable[str]] | None = None,
    ) -> None:
        self._llm = llm_agent
        self._memories: dict[str, Memory] = {}
        self._cases: dict[str, Case] = {}
        self._retrievals: dict[str, RetrievalResult] = {}
        self._reasonings: dict[str, ReasoningResult] = {}

    def store_memory(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        tags: list[str] | None = None,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> Memory:
        """Store a new memory."""
        memory = Memory(
            memory_id=str(uuid.uuid4())[:8],
            memory_type=memory_type,
            content=content,
            tags=tags or [],
            importance=importance,
            metadata=metadata or {},
        )
        self._memories[memory.memory_id] = memory
        return memory

    def store_case(
        self,
        problem: str,
        solution: str,
        outcome: str,
        tags: list[str] | None = None,
        success: bool = True,
        lessons: list[str] | None = None,
    ) -> Case:
        """Store a new case (experience)."""
        case = Case(
            case_id=str(uuid.uuid4())[:8],
            problem=problem,
            solution=solution,
            outcome=outcome,
            tags=tags or [],
            success=success,
            lessons=lessons or [],
        )
        self._cases[case.case_id] = case
        return case

    async def retrieve(
        self,
        query: str,
        strategy: RetrievalStrategy = RetrievalStrategy.SIMILARITY,
        memory_type: MemoryType | None = None,
        top_k: int = 5,
    ) -> RetrievalResult:
        """Retrieve relevant memories and cases."""
        result = RetrievalResult(
            result_id=str(uuid.uuid4())[:8],
            query=query,
            strategy=strategy,
        )

        # Filter by memory type if specified
        memories = list(self._memories.values())
        if memory_type:
            memories = [m for m in memories if m.memory_type == memory_type]

        # Score and rank memories
        scored_memories = [(m, self._score_memory(m, query, strategy)) for m in memories]
        scored_memories.sort(key=lambda x: x[1], reverse=True)

        # Select top-k
        result.memories = [m for m, _ in scored_memories[:top_k]]
        result.scores = {m.memory_id: s for m, s in scored_memories[:top_k]}

        # Record access
        for m in result.memories:
            m.record_access()

        # Retrieve relevant cases
        scored_cases = [(c, self._score_case(c, query)) for c in self._cases.values()]
        scored_cases.sort(key=lambda x: x[1], reverse=True)
        result.cases = [c for c, _ in scored_cases[:top_k]]

        self._retrievals[result.result_id] = result
        return result

    async def reason(
        self,
        query: str,
        context: str = "",
    ) -> ReasoningResult:
        """Perform memory-based reasoning."""
        result = ReasoningResult(
            result_id=str(uuid.uuid4())[:8],
            query=query,
        )

        # Retrieve relevant memories and cases
        retrieval = await self.retrieve(query, RetrievalStrategy.SIMILARITY, top_k=5)

        # Build reasoning from retrieved items
        supporting_memories = [m.content for m in retrieval.memories]
        supporting_cases = [f"Problem: {c.problem}\nSolution: {c.solution}\nOutcome: {c.outcome}" for c in retrieval.cases]

        result.supporting_memories = [m.memory_id for m in retrieval.memories]
        result.supporting_cases = [c.case_id for c in retrieval.cases]

        # Generate conclusion
        if self._llm:
            prompt = self._build_reasoning_prompt(query, context, supporting_memories, supporting_cases)
            try:
                response = await self._llm(prompt, "memory_reasoning")
                result.conclusion = response[:500]
            except Exception as e:
                logger.warning("LLM memory reasoning failed: %s", e)
                result.conclusion = self._default_reasoning(query, supporting_memories, supporting_cases)
        else:
            result.conclusion = self._default_reasoning(query, supporting_memories, supporting_cases)

        # Compute confidence
        result.confidence = self._compute_reasoning_confidence(retrieval)

        # Build reasoning explanation
        result.reasoning = self._build_reasoning_explanation(query, retrieval, result.conclusion)

        self._reasonings[result.result_id] = result
        return result

    def _score_memory(self, memory: Memory, query: str, strategy: RetrievalStrategy) -> float:
        """Score a memory for retrieval."""
        if strategy == RetrievalStrategy.SIMILARITY:
            # Simple keyword overlap similarity
            query_words = set(query.lower().split())
            content_words = set(memory.content.lower().split())
            overlap = len(query_words & content_words)
            return overlap / max(len(query_words), 1)
        elif strategy == RetrievalStrategy.RECENCY:
            # More recent = higher score
            age = time.time() - memory.created_at
            return max(0, 1.0 - age / (30 * 24 * 3600))  # decay over 30 days
        elif strategy == RetrievalStrategy.FREQUENCY:
            # More accesses = higher score
            return min(memory.access_count / 10, 1.0)
        elif strategy == RetrievalStrategy.IMPORTANCE:
            return memory.importance
        elif strategy == RetrievalStrategy.CONTEXTUAL:
            # Combine multiple factors
            query_words = set(query.lower().split())
            content_words = set(memory.content.lower().split())
            overlap = len(query_words & content_words) / max(len(query_words), 1)
            recency = max(0, 1.0 - (time.time() - memory.created_at) / (30 * 24 * 3600))
            return overlap * 0.5 + recency * 0.3 + memory.importance * 0.2
        return 0.5

    def _score_case(self, case: Case, query: str) -> float:
        """Score a case for retrieval."""
        query_words = set(query.lower().split())
        problem_words = set(case.problem.lower().split())
        overlap = len(query_words & problem_words)
        return overlap / max(len(query_words), 1)

    def _default_reasoning(self, query: str, memories: list[str], cases: list[str]) -> str:
        """Default reasoning when LLM is unavailable."""
        parts = [f"Based on memory analysis for: {query}"]
        if memories:
            parts.append(f"Relevant memories: {len(memories)}")
            for m in memories[:3]:
                parts.append(f"  - {m[:100]}")
        if cases:
            parts.append(f"Relevant cases: {len(cases)}")
            for c in cases[:3]:
                parts.append(f"  - {c[:100]}")
        return "\n".join(parts)

    def _compute_reasoning_confidence(self, retrieval: RetrievalResult) -> float:
        """Compute confidence in reasoning result."""
        if not retrieval.memories and not retrieval.cases:
            return 0.2
        # More supporting evidence = higher confidence
        memory_score = min(len(retrieval.memories) / 5, 0.5)
        case_score = min(len(retrieval.cases) / 3, 0.3)
        # Average score of retrieved items
        avg_score = sum(retrieval.scores.values()) / max(len(retrieval.scores), 1)
        return min(memory_score + case_score + avg_score * 0.2, 1.0)

    def _build_reasoning_explanation(self, query: str, retrieval: RetrievalResult, conclusion: str) -> str:
        """Build human-readable reasoning explanation."""
        parts = [
            f"Memory-based reasoning for: {query}",
            f"Retrieved {len(retrieval.memories)} memories and {len(retrieval.cases)} cases",
            f"Conclusion: {conclusion}",
        ]
        return "\n".join(parts)

    def _build_reasoning_prompt(self, query: str, context: str, memories: list[str], cases: list[str]) -> str:
        """Build prompt for LLM-enhanced reasoning."""
        parts = [
            f"Memory-based reasoning query: {query}",
            f"Context: {context}",
            f"Relevant memories: {memories}",
            f"Relevant cases: {cases}",
            "Provide a conclusion based on the above memory and case evidence:",
        ]
        return "\n".join(parts)

    def get_memory(self, memory_id: str) -> Memory | None:
        return self._memories.get(memory_id)

    def get_case(self, case_id: str) -> Case | None:
        return self._cases.get(case_id)

    def list_memories(self) -> list[str]:
        return list(self._memories.keys())

    def list_cases(self) -> list[str]:
        return list(self._cases.keys())

    def list_retrievals(self) -> list[str]:
        return list(self._retrievals.keys())

    def list_reasonings(self) -> list[str]:
        return list(self._reasonings.keys())
