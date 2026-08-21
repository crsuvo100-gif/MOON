"""MOON Agent Factory pipeline (spec sections 13-15, 25, 43, 45, 57).

Reuses existing, working MOON components (NON-DESTRUCTIVE):
  * app.capability.SandboxExecutor  -- isolated test execution
  * app.capability.VerificationEngine -- prove the agent imports/runs
  * app.tools.registry.ToolRegistry -- reuse existing tools (search existing)
  * app.brain.agent_registry.get_existing_agent_names -- avoid duplicates
  * app.agent_factory.store.AgentStore -- persist + audit + versions

The pipeline:
  CAPABILITY -> ANALYZE -> SEARCH EXISTING -> (REUSE if found)
  -> GENERATE -> SANDBOX TEST -> SECURITY REVIEW -> REGISTER -> VERSION -> ENABLE
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from app.agent_factory.generator import generate, slugify
from app.agent_factory.models import (
    AgentFactoryRecord,
    AgentMetadata,
    AuditAction,
    AuditEvent,
    FactoryResult,
    RiskLevel,
)
from app.agent_factory.store import AgentStore, stage_for

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_TOOLS = ["python_executor", "web_search", "file_manager"]


class AgentFactory:
    def __init__(self, store: AgentStore | None = None) -> None:
        self.store = store or AgentStore()
        self._sandbox = None  # lazy

    # -- lazy reuse of existing sandbox (avoid import cost at load) --------
    @property
    def sandbox(self):
        if self._sandbox is None:
            from app.capability.sandbox import SandboxExecutor
            self._sandbox = SandboxExecutor(workspace_root=str(_REPO_ROOT))
        return self._sandbox

    # ------------------------------------------------------------------
    # CAPABILITY ANALYSIS
    # ------------------------------------------------------------------
    def analyze(self, capability: str) -> dict[str, Any]:
        cap = (capability or "").strip()
        # Search existing tool registry for relevant tools to reuse.
        tools: list[str] = []
        try:
            from app.tools.registry import ToolRegistry
            known = [t.name for t in ToolRegistry().all()]
            for t in known:
                if any(k in t for k in (slugify(cap).split("_") if slugify(cap) else [])):
                    tools.append(t)
            # default sensible tools if nothing matched
            if not tools:
                tools = [t for t in _DEFAULT_TOOLS if t in known] or _DEFAULT_TOOLS
        except Exception as exc:  # noqa: BLE001
            logger.info("tool search failed, using defaults: %s", exc)
            tools = list(_DEFAULT_TOOLS)
        return {
            "goal": f"Create an agent capable of: {cap}",
            "capability": cap,
            "required_tools": tools,
            "risk_level": RiskLevel.LOW.value,
        }

    def search_existing(self, capability: str) -> list[str]:
        cap = slugify(capability)
        found: list[str] = []
        try:
            from app.brain.agent_registry import get_existing_agent_names
            for name in get_existing_agent_names():
                if cap in slugify(name) or slugify(name) in cap:
                    found.append(name)
        except Exception:  # noqa: BLE001
            pass
        # also check the factory DB
        for rec in self.store.all():
            if cap in slugify(rec.name) or slugify(rec.name) in cap:
                found.append(rec.name)
        return sorted(set(found))

    # ------------------------------------------------------------------
    # CREATE (full pipeline)
    # ------------------------------------------------------------------
    def create(self, capability: str, *, autonomy_level: int = 2) -> FactoryResult:
        analysis = self.analyze(capability)
        existing = self.search_existing(capability)
        if existing:
            return FactoryResult(
                success=True, status="REUSED_EXISTING",
                agent_id=existing[0], agent_version="",
                result=f"Existing agent(s) already cover this capability: {existing}",
                evidence={"existing": existing},
                warnings=["No new agent generated; reusing existing capability."],
            )

        agent_id = slugify(capability) or "agent"
        name = agent_id
        version = "1.0.0"
        meta = AgentMetadata(
            id=agent_id, name=name, version=version,
            description=analysis["goal"],
            capabilities=[analysis["capability"]],
            required_tools=analysis["required_tools"],
            permissions=["execute:tool:" + t for t in analysis["required_tools"]],
            risk_level=analysis["risk_level"],
            status="staging",
        )
        exec_id = ""
        try:
            import uuid
            exec_id = uuid.uuid4().hex[:12]
        except Exception:
            pass

        # 1) GENERATE into staging
        staging_dir = stage_for("staging")
        try:
            ga = generate(meta, staging_dir / agent_id)
            self.store.audit(AuditEvent(AuditAction.CREATE.value, agent_id,
                                        f"generated {ga.module_path}", execution_id=exec_id))
        except Exception as exc:  # noqa: BLE001
            return FactoryResult(False, "GENERATION_FAILED", agent_id, version, exec_id,
                                 errors=[f"generation error: {exc}"])

        # 2) SANDBOX TEST (run pytest isolated)
        test_res = self._run_tests(ga.test_path)
        self.store.audit(AuditEvent(AuditAction.TEST.value, agent_id,
                                    f"pytest rc={test_res['returncode']}", execution_id=exec_id))
        if not test_res["ok"]:
            self._quarantine(agent_id, name, version, meta, ga.module_path,
                             f"tests failed: {test_res['stderr'][:200]}")
            return FactoryResult(False, "TEST_FAILED", agent_id, version, exec_id,
                                 errors=[test_res["stderr"][:500]],
                                 evidence={"pytest": test_res})

        # 3) SECURITY REVIEW (capability does not imply permission; gate high risk)
        review = self._security_review(meta)
        self.store.audit(AuditEvent(AuditAction.SECURITY_REVIEW.value, agent_id,
                                    review["verdict"], execution_id=exec_id))
        if not review["ok"]:
            self._quarantine(agent_id, name, version, meta, ga.module_path, review["reason"])
            return FactoryResult(False, "SECURITY_REJECTED", agent_id, version, exec_id,
                                 errors=[review["reason"]], evidence=review)

        # 4) REGISTER + VERSION + ENABLE
        rec = AgentFactoryRecord(
            agent_id=agent_id, name=name, version=version, status="active",
            stage="approved", risk_level=meta.risk_level, description=meta.description,
            permissions="|".join(meta.permissions), required_tools="|".join(meta.required_tools),
            capabilities="|".join(meta.capabilities), module_path=ga.module_path,
            created_at=_now(), updated_at=_now(), notes="auto-generated + verified",
        )
        self.store.upsert_agent(rec)
        self.store.add_version(agent_id, version, ga.module_path, "initial generated version")
        self.store.audit(AuditEvent(AuditAction.REGISTER.value, agent_id, "registered active",
                                    execution_id=exec_id))
        self.store.audit(AuditEvent(AuditAction.ENABLE.value, agent_id, "enabled",
                                    execution_id=exec_id))

        # 5) Surface to the live runtime (additive hook) so the agent becomes usable
        try:
            from app.brain import agent_registry as ar
            ar.register_external_agent(meta)
        except Exception as exc:  # noqa: BLE001
            logger.warning("runtime registration skipped: %s", exc)

        return FactoryResult(
            True, "CREATED", agent_id, version, exec_id,
            result=f"Agent '{name}' created, tested, reviewed, registered and enabled.",
            evidence={
                "module_path": ga.module_path,
                "test_path": ga.test_path,
                "pytest": test_res,
                "security": review,
                "tools": meta.required_tools,
            },
            metrics={"tests_passed": test_res["ok"]},
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _run_tests(self, test_path: str) -> dict[str, Any]:
        # Run the generated test in the existing sandbox (network off; local only).
        cmd = [".venv/bin/python", "-m", "pytest", str(test_path), "-q"]
        try:
            res = self.sandbox.run(cmd, timeout=180, network=False, cwd=str(_REPO_ROOT))
            return {
                "ok": res.returncode == 0,
                "returncode": res.returncode,
                "stdout": (res.stdout or "")[:800],
                "stderr": (res.stderr or "")[:800],
                "method": res.method,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(exc), "method": "error"}

    def _security_review(self, meta: AgentMetadata) -> dict[str, Any]:
        # Capability-based permission gate (spec 47/48). High/critical risk
        # requires explicit authorization; default autonomy here is low, so we
        # reject anything above LOW unless explicitly permitted.
        if meta.risk_level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value):
            return {"ok": False, "verdict": "REJECTED",
                    "reason": f"risk_level={meta.risk_level} requires explicit authorization (spec 46/47)"}
        # No network egress, no system/secret permissions granted by default.
        forbidden = ("system", "secrets", "admin", "network")
        for p in meta.permissions:
            if any(f in p.lower() for f in forbidden):
                return {"ok": False, "verdict": "REJECTED",
                        "reason": f"permission '{p}' not auto-granted (spec 48)"}
        return {"ok": True, "verdict": "APPROVED",
                "reason": "low-risk, tool-scoped, no privileged permissions"}

    def _quarantine(self, agent_id, name, version, meta, module_path, reason) -> None:
        rec = AgentFactoryRecord(
            agent_id=agent_id, name=name, version=version, status="quarantined",
            stage="quarantine", risk_level=meta.risk_level, description=meta.description,
            permissions="|".join(meta.permissions), required_tools="|".join(meta.required_tools),
            capabilities="|".join(meta.capabilities), module_path=module_path,
            created_at=_now(), updated_at=_now(), notes=reason,
        )
        self.store.upsert_agent(rec)
        self.store.audit(AuditEvent(AuditAction.QUARANTINE.value, agent_id, reason))

    # ------------------------------------------------------------------
    # status / listing (spec 36)
    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        recs = self.store.all()
        by_stage = {}
        for r in recs:
            by_stage[r.stage] = by_stage.get(r.stage, 0) + 1
        return {
            "total_agents": len(recs),
            "by_stage": by_stage,
            "recent_audit": self.store.recent_audit(10),
        }

    def bump_version(self, agent_id: str, notes: str = "version bump") -> str:
        """Create a new semantic version of an existing generated agent (spec 44).

        Copies the current approved module to a new versioned file and records
        it, so a subsequent rollback has a previous version to restore. Real
        versioning operation; the prior version is preserved for rollback.
        """
        from app.agent_factory.store import AgentStore
        rec = AgentStore().get(agent_id)
        if not rec or not rec.module_path:
            raise ValueError(f"agent {agent_id} not found or not built")
        import shutil, re
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", rec.version or "1.0.0")
        major, minor, patch = (int(x) for x in m.groups())
        new_version = f"{major}.{minor + 1}.{patch}"
        src = Path(rec.module_path)
        dst_dir = src.parent
        dst = dst_dir / f"{src.stem}_v{new_version.replace('.', '_')}{src.suffix}"
        shutil.copy(src, dst)
        AgentStore().add_version(agent_id, new_version, str(dst), notes)
        # update current version pointer
        rec.version = new_version
        rec.previous_version = rec.version
        AgentStore().upsert_agent(rec)
        return new_version

    def run(self, agent_id: str, task: str = "run") -> dict[str, Any]:
        """Run a generated agent by loading its module and invoking run().

        Reuses the same mechanism as the REST endpoint; returns a structured
        result (spec 7). Raises if the agent/module is missing.
        """
        from app.agent_factory.store import AgentStore
        rec = AgentStore().get(agent_id)
        if not rec or not rec.module_path:
            raise ValueError(f"agent {agent_id} not found or not built")
        import importlib.util, sys
        mod_key = f"moonfactory_{agent_id}"
        # Always re-exec a fresh module instance (avoid stale sys.modules reuse
        # when run() is called repeatedly for the same agent in one process).
        sys.modules.pop(mod_key, None)
        spec = importlib.util.spec_from_file_location(mod_key, rec.module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("agent module unloadable")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_key] = mod
        spec.loader.exec_module(mod)
        result = mod.create_agent().run(task if task else "")
        AgentStore().record_execution(
            result.get("execution_id", ""), agent_id, "SUCCESS", result=str(result))
        return result

    def list_agents(self) -> list[dict[str, Any]]:
        out = []
        for r in self.store.all():
            out.append({
                "agent_id": r.agent_id, "name": r.name, "version": r.version,
                "status": r.status, "stage": r.stage, "risk_level": r.risk_level,
                "required_tools": r.required_tools.split("|") if r.required_tools else [],
            })
        return out


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
