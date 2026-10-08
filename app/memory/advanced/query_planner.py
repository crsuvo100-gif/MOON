"""Query planner -- plan complex multi-step memory queries.

Professional AI assistants often need to answer questions that require
combining information from multiple memory subsystems. This module:

1. Parses a natural-language query into sub-queries.
2. Determines which memory subsystems to search for each sub-query.
3. Plans the execution order (parallel vs sequential).
4. Merges results from multiple subsystems.
5. Ranks final results by combined relevance.

Example:
    "What did we learn about API auth last week, and how does it
    relate to the current vulnerability assessment?"

    Plan:
    1. Search LTM for "API auth" (time-filtered to last week)
    2. Search episodic for "vulnerability assessment"
    3. Search graph for associations between the two
    4. Merge and rank results
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SubQuery:
    """A single sub-query within a larger query plan."""
    query_text: str
    target_sources: list[str]     # ["ltm", "episodic", "graph", "kb", "stm"]
    time_range: tuple[float, float] | None = None  # (start, end) timestamps
    keywords: list[str] = field(default_factory=list)
    priority: int = 1             # 1 = highest

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_text": self.query_text,
            "target_sources": self.target_sources,
            "time_range": self.time_range,
            "keywords": self.keywords,
            "priority": self.priority,
        }


@dataclass
class QueryPlan:
    """A complete query plan with multiple sub-queries."""
    original_query: str
    sub_queries: list[SubQuery]
    execution_strategy: str       # "parallel", "sequential", "mixed"
    estimated_cost: int           # rough cost estimate

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_query": self.original_query,
            "sub_queries": [sq.to_dict() for sq in self.sub_queries],
            "execution_strategy": self.execution_strategy,
            "estimated_cost": self.estimated_cost,
        }


@dataclass
class PlannedResult:
    """A result from executing a query plan."""
    sub_query: SubQuery
    results: list[Any]            # UnifiedResult or similar
    execution_time: float         # seconds
    success: bool = True
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sub_query": self.sub_query.to_dict(),
            "result_count": len(self.results),
            "execution_time": round(self.execution_time, 4),
            "success": self.success,
            "error": self.error,
        }


class QueryPlanner:
    """Plans and executes complex multi-step memory queries.

    Usage:
        planner = QueryPlanner(memory_manager)
        plan = planner.plan("What did we learn about API auth?")
        results = await planner.execute(plan)
    """

    # Keywords that indicate which memory sources to search
    SOURCE_INDICATORS = {
        "ltm": ["learned", "learn", "know", "fact", "remember", "stored", "documented"],
        "episodic": ["did", "happened", "task", "attempt", "tried", "executed", "ran"],
        "graph": ["related", "associated", "connected", "linked", "similar"],
        "kb": ["document", "wiki", "knowledge", "article", "reference"],
        "stm": ["recent", "just", "current", "last", "latest", "moment"],
    }

    # Time range indicators
    TIME_PATTERNS = [
        (r"last week", 7),
        (r"last month", 30),
        (r"last (\d+) days?", None),  # capture group
        (r"yesterday", 1),
        (r"today", 0),
        (r"this week", 7),
        (r"this month", 30),
    ]

    def __init__(self, memory_manager=None, searcher=None) -> None:
        self._mm = memory_manager
        self._searcher = searcher
        self._plan_count = 0

    def plan(self, query: str) -> QueryPlan:
        """Create a query plan from a natural-language query.

        Args:
            query: The natural-language query.

        Returns:
            QueryPlan with sub-queries and execution strategy.
        """
        self._plan_count += 1
        query_lower = query.lower()

        # Split into sub-queries based on conjunctions and question structure
        sub_queries = self._decompose_query(query)

        # Determine target sources for each sub-query
        for sq in sub_queries:
            sq.target_sources = self._infer_sources(sq.query_text)
            sq.keywords = self._extract_keywords(sq.query_text)
            sq.time_range = self._extract_time_range(sq.query_text)

        # Determine execution strategy
        strategy = self._determine_strategy(sub_queries)
        cost = len(sub_queries) * len(sub_queries[0].target_sources) if sub_queries else 0

        return QueryPlan(
            original_query=query,
            sub_queries=sub_queries,
            execution_strategy=strategy,
            estimated_cost=cost,
        )

    def _decompose_query(self, query: str) -> list[SubQuery]:
        """Decompose a complex query into sub-queries.

        Splits on conjunctions and question boundaries.
        """
        # Split on common conjunctions that indicate separate information needs
        split_patterns = [
            r"\s+and\s+how\s+",
            r"\s+and\s+what\s+",
            r"\s+and\s+why\s+",
            r"\s+and\s+when\s+",
            r"\s+and\s+where\s+",
            r"\s+and\s+which\s+",
            r"\s+also\s+",
            r"\s+additionally\s+",
            r"\s+moreover\s+",
            r"\s+then\s+",
            r";\s*",
        ]

        parts = [query]
        for pattern in split_patterns:
            new_parts: list[str] = []
            for part in parts:
                new_parts.extend(re.split(pattern, part, flags=re.IGNORECASE))
            parts = [p.strip() for p in new_parts if p.strip()]

        # If no split occurred, treat as single sub-query
        if len(parts) <= 1:
            return [SubQuery(query_text=query, target_sources=[])]

        # Create sub-queries with priorities
        sub_queries: list[SubQuery] = []
        for i, part in enumerate(parts):
            # First part is usually the primary query
            priority = 1 if i == 0 else 2
            sub_queries.append(SubQuery(
                query_text=part,
                target_sources=[],
                priority=priority,
            ))

        return sub_queries

    def _infer_sources(self, query_text: str) -> list[str]:
        """Infer which memory sources to search based on query content."""
        text_lower = query_text.lower()
        sources: list[str] = []

        for source, indicators in self.SOURCE_INDICATORS.items():
            for indicator in indicators:
                if indicator in text_lower:
                    sources.append(source)
                    break

        # Default to all sources if no indicators found
        if not sources:
            sources = ["ltm", "episodic", "stm"]

        return sources

    def _extract_keywords(self, query_text: str) -> list[str]:
        """Extract important keywords from a query."""
        # Remove common stop words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "about", "like", "through", "after", "over",
            "between", "out", "against", "during", "without", "before",
            "under", "around", "among", "what", "which", "who", "whom",
            "this", "that", "these", "those", "i", "me", "my", "we",
            "our", "you", "your", "he", "him", "his", "she", "her",
            "it", "its", "they", "them", "their", "and", "but", "or",
            "not", "no", "so", "if", "then", "than", "when", "where",
            "why", "how", "all", "each", "every", "both", "few", "more",
            "most", "other", "some", "such", "only", "own", "same",
        }
        words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", query_text.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        return list(dict.fromkeys(keywords))  # dedupe preserving order

    def _extract_time_range(self, query_text: str) -> tuple[float, float] | None:
        """Extract time range from query text."""
        text_lower = query_text.lower()
        now = time.time()

        for pattern, days in self.TIME_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                if days is None:
                    # Extract number from capture group
                    try:
                        days = int(match.group(1))
                    except (IndexError, ValueError):
                        continue
                start = now - (days * 86400)
                return (start, now)

        return None

    def _determine_strategy(self, sub_queries: list[SubQuery]) -> str:
        """Determine execution strategy based on sub-query dependencies."""
        if len(sub_queries) <= 1:
            return "sequential"
        # If sub-queries have different time ranges or sources, they can run in parallel
        sources_set = [set(sq.target_sources) for sq in sub_queries]
        # If all sub-queries search the same sources, sequential may be better
        if all(s == sources_set[0] for s in sources_set):
            return "sequential"
        return "parallel"

    async def execute(self, plan: QueryPlan) -> list[PlannedResult]:
        """Execute a query plan and return results.

        Args:
            plan: The QueryPlan to execute.

        Returns:
            List of PlannedResult, one per sub-query.
        """
        results: list[PlannedResult] = []

        for sq in plan.sub_queries:
            start_time = time.time()
            try:
                if self._searcher is not None:
                    search_results = await self._searcher.search(
                        sq.query_text,
                        top_k=10,
                        min_score=0.1,
                        include_sources=sq.target_sources,
                    )
                else:
                    search_results = []

                results.append(PlannedResult(
                    sub_query=sq,
                    results=search_results,
                    execution_time=time.time() - start_time,
                    success=True,
                ))
            except Exception as exc:
                results.append(PlannedResult(
                    sub_query=sq,
                    results=[],
                    execution_time=time.time() - start_time,
                    success=False,
                    error=str(exc),
                ))

        return results

    def merge_results(
        self,
        planned_results: list[PlannedResult],
        top_k: int = 10,
    ) -> list[Any]:
        """Merge and rank results from multiple sub-queries.

        Uses a weighted combination of scores, with higher priority
        sub-queries contributing more to the final ranking.
        """
        all_results: list[tuple[Any, float]] = []

        for pr in planned_results:
            priority_weight = 1.0 / pr.sub_query.priority
            for result in pr.results:
                base_score = getattr(result, 'score', 0.5)
                weighted_score = base_score * priority_weight
                all_results.append((result, weighted_score))

        # Sort by weighted score descending
        all_results.sort(key=lambda x: x[1], reverse=True)
        return [r for r, _ in all_results[:top_k]]

    def stats(self) -> dict[str, Any]:
        """Return query planner statistics."""
        return {
            "plan_count": self._plan_count,
        }
