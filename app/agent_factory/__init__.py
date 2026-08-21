"""MOON Agent Factory -- additive autonomous agent-generation subsystem.

This package adds the *agent generation* half of the MOON Autonomous Agent
Factory spec (sections 13-15, 39, 43-45, 57). The tool/capability half already
exists in ``app.capability`` (CapabilityManager, InstallationManager,
SandboxExecutor, VerificationEngine, ...). This factory REUSES those existing,
working components and adds only what was missing: generating new *agents*
(implementations + metadata + tests), validating them in the existing sandbox,
registering them, versioning, and rolling them back.

NON-DESTRUCTIVE: nothing in app.capability / app.brain / app.tools is modified
or replaced. Generated agents live under data/agents/{staging,approved,
quarantine}/ and are surfaced to the live runtime via an additive hook in
app.brain.agent_registry (EXTRA_AGENT_DEFS).
"""

from app.agent_factory.models import (
    AgentFactoryRecord,
    AgentMetadata,
    AuditEvent,
    FactoryResult,
    GeneratedAgent,
)

__all__ = [
    "AgentFactoryRecord",
    "AgentMetadata",
    "AuditEvent",
    "FactoryResult",
    "GeneratedAgent",
]
