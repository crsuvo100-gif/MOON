"""Agent implementations.

Public surface for MOON's agent layer. Two complementary contracts live here,
deliberately kept separate (spec 3: the Agent is persistent, the Brain is
replaceable):

* :class:`~app.agents.base.BaseAgent` (exported as ``RuntimeAgent``) -- the
  ASYNC runtime agent. It wraps a per-agent
  :class:`~app.brain.agent_brain.AgentBrain` (the replaceable brain) and is
  what the Orchestrator instantiates for each of the 39 persona agents.

* :class:`~app.agents.base_runtime.BaseAgent` -- the spec-6 SYNCHRONOUS common
  interface every agent (built-in persona, factory-generated, or spec-roster)
  can be wrapped in. It returns a STRUCTURED ``AgentResult`` carrying
  ``success/status/result/evidence/errors/warnings/metrics`` so downstream
  aggregation and verification (spec 26/27/28) reason about evidence instead of
  free-form text.

``OrchestratorAgent`` is the concrete bridge: a sync spec-6 agent that executes
through the LIVE orchestrator with capability-based agent selection.

Importing them here (rather than leaving them orphaned) makes the spec-6
interface the agent package's stable entry point.
"""

from __future__ import annotations

from app.agents.base import BaseAgent as RuntimeAgent
from app.agents.base_runtime import AgentResult, BaseAgent, OrchestratorAgent
from app.agents.memory_agent import MemoryAgent

__all__ = [
    "RuntimeAgent",       # async runtime agent (wraps an AgentBrain)
    "BaseAgent",          # spec 6 common interface
    "AgentResult",        # spec 7 structured result
    "OrchestratorAgent",  # spec 6/9/12 bridge to the live orchestrator
    "MemoryAgent",        # specialist
]

