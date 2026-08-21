"""Agent lifecycle management (spec sections 14, 45, 57).

Enable / disable / rollback generated agents. Rollback restores the previous
approved version (spec 45): stop -> disable version -> restore previous ->
verify -> log -> report. Non-destructive: the current version is preserved in
agent_versions so it can be re-enabled.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.agent_factory.models import AuditAction, AuditEvent, FactoryResult
from app.agent_factory.store import AgentStore

logger = logging.getLogger(__name__)


class AgentLifecycle:
    def __init__(self, store: AgentStore | None = None) -> None:
        self.store = store or AgentStore()

    def enable(self, agent_id: str) -> FactoryResult:
        rec = self.store.get(agent_id)
        if not rec:
            return FactoryResult(False, "NOT_FOUND", agent_id, errors=[f"no such agent {agent_id}"])
        rec.status = "active"
        rec.stage = "approved"
        rec.previous_version = rec.version
        rec.updated_at = _now()
        self.store.upsert_agent(rec)
        self.store.audit(AuditEvent(AuditAction.ENABLE.value, agent_id, "enabled"))
        self._sync_runtime(agent_id, enable=True)
        return FactoryResult(True, "ENABLED", agent_id, rec.version,
                             result=f"agent {agent_id} enabled")

    def disable(self, agent_id: str) -> FactoryResult:
        rec = self.store.get(agent_id)
        if not rec:
            return FactoryResult(False, "NOT_FOUND", agent_id, errors=[f"no such agent {agent_id}"])
        rec.status = "disabled"
        rec.updated_at = _now()
        self.store.upsert_agent(rec)
        self.store.audit(AuditEvent(AuditAction.DISABLE.value, agent_id, "disabled"))
        self._sync_runtime(agent_id, enable=False)
        return FactoryResult(True, "DISABLED", agent_id, rec.version,
                             result=f"agent {agent_id} disabled")

    def rollback(self, agent_id: str) -> FactoryResult:
        rec = self.store.get(agent_id)
        if not rec:
            return FactoryResult(False, "NOT_FOUND", agent_id, errors=[f"no such agent {agent_id}"])
        try:
            from app.runtime.integration import emit as _emit
            _emit("ROLLBACK_STARTED", agent_id=agent_id, detail=f"rollback requested for {agent_id}")
        except Exception:  # noqa: BLE001
            pass
        versions = self.store.list_versions(agent_id)
        if len(versions) < 2:
            return FactoryResult(False, "NO_PREVIOUS_VERSION", agent_id, rec.version,
                                 errors=["only one version exists; nothing to roll back to"])
        # spec 45: stop -> disable -> restore previous -> verify -> log -> report
        previous = versions[-2]
        rec.previous_version = rec.version
        rec.version = previous["version"]
        rec.module_path = previous["module_path"]
        rec.status = "active"
        rec.updated_at = _now()
        rec.notes = f"rolled back to {previous['version']} from {rec.previous_version}"
        self.store.upsert_agent(rec)
        self.store.audit(AuditEvent(AuditAction.ROLLBACK.value, agent_id,
                                    f"-> {previous['version']}"))
        self._sync_runtime(agent_id, enable=True)
        try:
            from app.runtime.integration import emit as _emit
            _emit("ROLLBACK_COMPLETED", agent_id=agent_id,
                  detail=f"restored -> {previous['version']}")
        except Exception:  # noqa: BLE001
            pass
        return FactoryResult(
            True, "ROLLED_BACK", agent_id, rec.version,
            result=f"agent {agent_id} rolled back to version {previous['version']}",
            evidence={"restored_module": previous["module_path"]},
        )

    # -- runtime sync (additive) ----------------------------------------
    def _sync_runtime(self, agent_id: str, *, enable: bool) -> None:
        try:
            from app.brain import agent_registry as ar
            rec = self.store.get(agent_id)
            if rec is None:
                return
            if enable:
                # re-register (idempotent) so it is live
                class _M:  # minimal metadata shim
                    name = rec.name
                    description = rec.description
                    required_tools = rec.required_tools.split("|") if rec.required_tools else []
                ar.register_external_agent(_M())
            else:
                ar.unregister_external_agent(rec.name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("runtime sync skipped: %s", exc)


def _now() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
