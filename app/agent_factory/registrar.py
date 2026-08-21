"""Agent Factory: Registrar + Rollback (spec 14, 44, 45 + MOON Factory).

Registrar: writes the generated agent into the structured Agent Registry and
the Factory store, moving it from staging -> approved (spec 14). Rollback:
reverts a generated agent to its previous version (spec 45).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agent_factory.architect import AgentSpec
from app.agent_factory.builder import BuildArtifact
from app.agent_factory.tester import TestResult
from app.agent_factory.reviewer import ReviewResult
from app.agent_factory.evaluator import EvalResult


@dataclass
class Registration:
    agent_id: str
    status: str  # registered | rejected
    stage: str = "approved"
    error: str = ""


class AgentRegistrar:
    """Registers a validated agent into the Agent Registry + Factory store."""

    def register(self, spec: AgentSpec, artifact: BuildArtifact, test: TestResult,
                 review: ReviewResult, eval_result: EvalResult) -> Registration:
        if not (test.passed and review.approved):
            return Registration(agent_id=spec.agent_id, status="rejected",
                                error=f"test={test.passed} security={review.approved}")
        try:
            # 1) structured registry (spec 8) -- update in-memory singleton too
            from app.agents.registry import AgentRegistry, AgentMetadata, get_registry
            reg = get_registry()
            meta = AgentMetadata(
                id=spec.agent_id, name=spec.name, version=spec.version,
                description=spec.description, capabilities=spec.capabilities,
                required_tools=spec.required_tools, permissions=spec.permissions,
                risk_level=spec.risk_level, status="active", source="factory",
                success_criteria=f"overall_eval={eval_result.overall}",
                module_path=artifact.module_path,
            )
            reg.register(meta)  # persists JSON + updates in-memory dict (spec 12 reuse)
            # 2) factory store (spec 39)
            from app.agent_factory.store import AgentStore
            from app.agent_factory.models import AgentFactoryRecord, AgentStatus
            st = AgentStore()
            rec = AgentFactoryRecord(
                agent_id=spec.agent_id, name=spec.name, version=spec.version,
                status=AgentStatus.ACTIVE.value, stage="approved",
                risk_level=spec.risk_level, description=spec.description,
                permissions="|".join(spec.permissions),
                required_tools="|".join(spec.required_tools),
                capabilities="|".join(spec.capabilities),
                module_path=artifact.module_path,
            )
            st.upsert_agent(rec)
            from app.agent_factory.models import AuditEvent
            st.audit(AuditEvent(action="agent.register", agent_id=spec.agent_id,
                                detail=f"registered v{spec.version} eval={eval_result.overall}"))
            return Registration(agent_id=spec.agent_id, status="registered", stage="approved")
        except Exception as e:  # noqa: BLE001
            return Registration(agent_id=spec.agent_id, status="rejected", error=str(e))


class AgentRollback:
    """Rolls a generated agent back to its previous version (spec 45)."""

    def rollback(self, agent_id: str) -> Registration:
        try:
            from app.agent_factory.lifecycle import AgentLifecycle
            r = AgentLifecycle().rollback(agent_id)
            return Registration(agent_id=agent_id, status=r.status, stage="approved")
        except Exception as e:  # noqa: BLE001
            return Registration(agent_id=agent_id, status="rejected", error=str(e))


__all__ = ["AgentRegistrar", "Registration", "AgentRollback"]
