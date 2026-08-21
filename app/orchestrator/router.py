"""Agent Router (spec sections 12, 6: orchestrator/router.py).

Re-exports the real AgentRouter from app.runtime.agent_router (non-destructive
compatibility layer for the spec directory layout).
"""

from app.runtime.agent_router import AgentRouter  # noqa: F401
from app.agents.registry import get_registry  # noqa: F401

__all__ = ["AgentRouter", "get_registry"]
