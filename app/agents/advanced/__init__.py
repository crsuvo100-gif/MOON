"""Advanced agent system — professional-grade agent infrastructure.

Provides multi-stage pipeline, blackboard coordination, lifecycle management,
performance tracking, self-learning, context sharing, error recovery,
tool optimization, state management, and a unified professional workflow.
"""

from app.agents.advanced.pipeline import AgentPipeline, PipelineResult, PipelineStage
from app.agents.advanced.blackboard import Blackboard, BlackboardEntry
from app.agents.advanced.lifecycle import AgentLifecycle, AgentState, StateTransition, LifecycleEvent
from app.agents.advanced.performance import PerformanceTracker, TaskExecution
from app.agents.advanced.learning import AgentLearning, LearningRecord
from app.agents.advanced.coordination import CoordinationProtocol, CoordinationMode, TaskAnnouncement
from app.agents.advanced.context_sharing import ContextSharing, SharedContext
from app.agents.advanced.error_recovery import ErrorRecovery, ErrorCategory, ErrorSeverity, AgentError, RecoveryResult
from app.agents.advanced.tool_optimizer import ToolOptimizer, ToolUsage
from app.agents.advanced.state_manager import AgentStateManager, AgentState as PersistedState
from app.agents.advanced.orchestrator import AdvancedAgentOrchestrator
from app.agents.advanced.workflow import ProfessionalAgentWorkflow, WorkflowResult

__all__ = [
    "AgentPipeline",
    "PipelineResult",
    "PipelineStage",
    "Blackboard",
    "BlackboardEntry",
    "AgentLifecycle",
    "AgentState",
    "StateTransition",
    "LifecycleEvent",
    "PerformanceTracker",
    "TaskExecution",
    "AgentLearning",
    "LearningRecord",
    "CoordinationProtocol",
    "CoordinationMode",
    "TaskAnnouncement",
    "ContextSharing",
    "SharedContext",
    "ErrorRecovery",
    "ErrorCategory",
    "ErrorSeverity",
    "AgentError",
    "RecoveryResult",
    "ToolOptimizer",
    "ToolUsage",
    "AgentStateManager",
    "PersistedState",
    "AdvancedAgentOrchestrator",
    "ProfessionalAgentWorkflow",
    "WorkflowResult",
]
