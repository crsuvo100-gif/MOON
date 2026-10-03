"""Advanced brain system for MOON — professional-grade agent cognition.

Modules:
  react              — ReAct (Reasoning + Acting) loop
  dag_planner        — DAG-based task planning with dependency resolution
  working_memory     — working memory with attention and decay
  metacognition      — metacognitive monitoring and control
  context_compressor — context window compression and summarization
  tool_composer      — tool composition and chaining
  uncertainty        — uncertainty estimation and confidence calibration
  reflection         — deep reflection and self-critique
  goal_tracker       — goal tracking and progress monitoring
  brain_orchestrator  — unified brain orchestrator
"""

from app.brain.advanced.react import ReActLoop, ReActStep, ReActResult
from app.brain.advanced.dag_planner import DAGPlanner, DAGNode, DAGPlan
from app.brain.advanced.working_memory import WorkingMemory, MemoryItem
from app.brain.advanced.metacognition import Metacognition, MetaState
from app.brain.advanced.context_compressor import ContextCompressor, CompressedContext
from app.brain.advanced.tool_composer import ToolComposer, ToolChain, ToolChainResult
from app.brain.advanced.uncertainty import UncertaintyEstimator, UncertaintyResult
from app.brain.advanced.reflection import DeepReflection, ReflectionResult
from app.brain.advanced.goal_tracker import GoalTracker, Goal, GoalStatus
from app.brain.advanced.brain_orchestrator import BrainOrchestrator

__all__ = [
    "ReActLoop", "ReActStep", "ReActResult",
    "DAGPlanner", "DAGNode", "DAGPlan",
    "WorkingMemory", "MemoryItem",
    "Metacognition", "MetaState",
    "ContextCompressor", "CompressedContext",
    "ToolComposer", "ToolChain", "ToolChainResult",
    "UncertaintyEstimator", "UncertaintyResult",
    "DeepReflection", "ReflectionResult",
    "GoalTracker", "Goal", "GoalStatus",
    "BrainOrchestrator",
]
