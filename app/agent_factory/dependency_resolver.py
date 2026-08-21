"""Agent Factory: Dependency Resolver component (spec 16 / agent_factory/dependency_resolver.py).

Re-exports the resolver implemented in ``builder.py`` so the spec's component
layout is satisfied without duplicating logic.
"""

from __future__ import annotations

from app.agent_factory.builder import DependencyResolver  # noqa: F401

__all__ = ["DependencyResolver"]
