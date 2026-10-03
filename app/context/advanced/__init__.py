"""Advanced context self-function system for MOON.

Every agent, brain, and tool can use this package to manage its own
context like a professional AI assistant:

- ContextWindow: token-budgeted context with automatic eviction
- ContextAwareness: self-monitoring and health assessment
- ContextInjector: prompt injection with multiple formats
- ContextLifecycle: lifecycle state machine for context items
- ContextRetriever: intelligent retrieval with semantic search
- ContextCompressor: compression when context is full
- ContextAnalytics: usage analytics and health scoring
- ContextOrchestrator: unified orchestrator tying it all together
"""

from app.context.advanced.context_window import ContextWindow, ContextItem, EvictionPolicy
from app.context.advanced.context_awareness import ContextAwareness, ContextHealth, ContextAwarenessState
from app.context.advanced.context_injector import ContextInjector, InjectionFormat, InjectionResult
from app.context.advanced.context_lifecycle import ContextLifecycle, ContextPhase, LifecycleEvent
from app.context.advanced.context_retriever import ContextRetriever, RetrievalResult
from app.context.advanced.context_compressor import ContextCompressor, CompressionStrategy, CompressionResult
from app.context.advanced.context_analytics import ContextAnalytics, ContextAnalyticsTracker
from app.context.advanced.context_orchestrator import ContextOrchestrator, ContextSnapshot

__all__ = [
    "ContextWindow",
    "ContextItem",
    "EvictionPolicy",
    "ContextAwareness",
    "ContextHealth",
    "ContextAwarenessState",
    "ContextInjector",
    "InjectionFormat",
    "InjectionResult",
    "ContextLifecycle",
    "ContextPhase",
    "LifecycleEvent",
    "ContextRetriever",
    "RetrievalResult",
    "ContextCompressor",
    "CompressionStrategy",
    "CompressionResult",
    "ContextAnalytics",
    "ContextAnalyticsTracker",
    "ContextOrchestrator",
    "ContextSnapshot",
]
