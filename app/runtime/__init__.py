"""MOON runtime subsystems (spec sections 3, 9, 10, 12, 28, 30, 41, 46, 57).

Additive integration layer that fills the spec's named components which were
not yet present in MOON:

  * TaskAnalyzer    (§10)  -- user request -> structured goal JSON
  * GoalManager     (§9)   -- goal lifecycle, memory/knowledge lookup
  * AgentRouter     (§12)  -- capability/performance/risk-based agent selection
  * ModelRouter     (§30)  -- pick model by complexity / privacy / latency
  * EvaluationEngine(§28)  -- score correctness/reliability/verification/...
  * AutonomyLevel   (§46)  -- config-driven autonomy gate
  * SkillSystem     (§24)  -- manage the existing skills/ corpus + scores
  * EventBus        (§3/41)-- internal event system -> terminal_interface._emit_event

Every module reuses existing MOON components (AgentStore, ToolRegistry,
settings, LLMService backends) and adds only what was missing. Nothing in the
existing brain/capability/tools layers is modified.
"""

from app.runtime.task_analyzer import TaskAnalyzer, GoalSpec
from app.runtime.goal_manager import GoalManager
from app.runtime.agent_router import AgentRouter
from app.runtime.model_router import ModelRouter
from app.runtime.evaluation import EvaluationEngine, ScoreCard
from app.runtime.autonomy import AutonomyLevel, Autonomy
from app.runtime.skill_system import SkillSystem
from app.runtime.event_bus import EventBus, EventType

__all__ = [
    "TaskAnalyzer", "GoalSpec", "GoalManager", "AgentRouter", "ModelRouter",
    "EvaluationEngine", "ScoreCard", "AutonomyLevel", "Autonomy", "SkillSystem",
    "EventBus", "EventType",
]
