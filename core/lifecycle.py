"""Lifecycle (spec 6: core/lifecycle.py). Re-exports the Agent Factory lifecycle
(additive; the real generated-agent lifecycle lives in app.agent_factory.lifecycle)."""

from app.agent_factory.lifecycle import AgentLifecycle  # noqa: F401

__all__ = ["AgentLifecycle"]
