"""Agent Factory: internal Rollback component (spec 45 + MOON Factory).

Thin wrapper over AgentLifecycle.rollback that also records the audit trail and
returns a structured Registration. Separated per the spec directory layout
(agent_factory/rollback.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent_factory.registrar import Registration


class AgentFactoryRollback:
    def rollback(self, agent_id: str) -> Registration:
        try:
            from app.agent_factory.lifecycle import AgentLifecycle
            from app.agent_factory.store import AgentStore
            from app.agent_factory.models import AuditEvent
            r = AgentLifecycle().rollback(agent_id)
            AgentStore().audit(AuditEvent(
                action="agent.rollback", agent_id=agent_id, detail=f"rolled back -> {r.status}"))
            return Registration(agent_id=agent_id, status=r.status, stage="approved")
        except Exception as e:  # noqa: BLE001
            return Registration(agent_id=agent_id, status="rejected", error=str(e))


__all__ = ["AgentFactoryRollback"]
