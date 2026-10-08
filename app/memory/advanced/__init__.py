"""Advanced memory system -- unified search, consolidation, proactive surfacing,
reasoning, conflict resolution, importance scoring, temporal reasoning, lifecycle
management, summarization, clustering, and recommendations.

Professional AI assistants don't just store memories; they actively manage
them: search across ALL memory types simultaneously, consolidate important
findings across subsystems, proactively surface relevant context, maintain
cross-session continuity, reason over stored knowledge, resolve conflicts,
score importance, manage lifecycle, summarize, cluster, and recommend.

Additive only -- never replaces existing modules.
"""

from app.memory.advanced.reasoning import MemoryReasoningEngine, ReasoningResult, ReasoningChain
from app.memory.advanced.conflict_resolver import ConflictResolver, Conflict, Resolution
from app.memory.advanced.importance_scorer import ImportanceScorer, ImportanceScore
from app.memory.advanced.temporal_reasoning import TemporalReasoner, TemporalFact, TemporalDiff
from app.memory.advanced.lifecycle import LifecycleManager, LifecycleAction, LifecycleReport
from app.memory.advanced.summarization import MemorySummarizer, MemorySummary
from app.memory.advanced.clustering import MemoryClustering, MemoryCluster
from app.memory.advanced.recommendation import MemoryRecommender, MemoryRecommendation

__all__ = [
    "MemoryReasoningEngine",
    "ReasoningResult",
    "ReasoningChain",
    "ConflictResolver",
    "Conflict",
    "Resolution",
    "ImportanceScorer",
    "ImportanceScore",
    "TemporalReasoner",
    "TemporalFact",
    "TemporalDiff",
    "LifecycleManager",
    "LifecycleAction",
    "LifecycleReport",
    "MemorySummarizer",
    "MemorySummary",
    "MemoryClustering",
    "MemoryCluster",
    "MemoryRecommender",
    "MemoryRecommendation",
]
