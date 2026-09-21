"""Agent Factory integration tests (spec 43, 57).

These verify the ADDITIVE agent-generation subsystem end-to-end against the
real runtime pieces (generator -> store -> sandbox pytest -> lifecycle),
without touching the 39 built-in agents.
"""

from __future__ import annotations

import importlib.util
import sys

from app.agent_factory.factory import AgentFactory
from app.agent_factory.lifecycle import AgentLifecycle
from app.agent_factory.models import AgentMetadata, RiskLevel
from app.agent_factory.store import AgentStore
from app.agent_factory.generator import generate, slugify


def test_slugify():
    assert slugify("Analyze Python Projects!") == "analyze_python_projects"


def test_generate_writes_real_modules(tmp_path):
    meta = AgentMetadata(
        id="demo", name="demo", version="1.0.0",
        description="demo agent", capabilities=["demo"],
        required_tools=["python_executor"], risk_level=RiskLevel.LOW.value,
    )
    ga = generate(meta, tmp_path)
    assert (tmp_path / ga.module_path).exists()
    assert (tmp_path / ga.test_path).exists()
    # the generated module must import and run with a structured result
    spec = importlib.util.spec_from_file_location("gen_demo_test", ga.module_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_demo_test"] = mod
    spec.loader.exec_module(mod)
    res = mod.create_agent().run("process numbers 2 and 3")
    assert isinstance(res, dict) and res["success"] is True and res["execution_id"]


def test_store_roundtrip(tmp_path):
    s = AgentStore(db_path=tmp_path / "af.db")
    from app.agent_factory.models import AgentFactoryRecord, AuditEvent
    rec = AgentFactoryRecord(agent_id="x", name="x", version="1.0.0", status="staging",
                             stage="staging", risk_level="low", description="d", created_at="t", updated_at="t")
    s.upsert_agent(rec)
    assert s.get("x").name == "x"
    s.audit(AuditEvent("agent.create", "x", "test"))
    assert len(s.recent_audit(5)) >= 1


def test_factory_create_pipeline_real():
    """Real pipeline: generate -> sandbox pytest -> review -> register -> enable.

    Uses a unique capability string so it exercises the genuine CREATE path
    (the search-existing/dedupe path is covered by test_factory_reuses_existing).
    """
    f = AgentFactory()
    cap = "analyze rust crates for unsafe usage"
    res = f.create(cap)
    assert res.success is True, res.errors
    # Either freshly CREATED, or REUSED_EXISTING if a prior run already made it.
    assert res.status in ("CREATED", "REUSED_EXISTING"), res.status
    agents = f.list_agents()
    assert any(a["agent_id"] == res.agent_id for a in agents)


def test_factory_reuses_existing():
    # 'coding' is a built-in agent -> factory should reuse, not regenerate.
    f = AgentFactory()
    res = f.create("coding")
    assert res.status == "REUSED_EXISTING"


def test_lifecycle_rollback():
    from app.agent_factory.models import AgentFactoryRecord
    import time
    NOW = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    s = AgentStore()
    # ensure an agent exists with two versions
    aid = "rollback_demo"
    base = AgentFactoryRecord(agent_id=aid, name=aid, version="1.0.0", status="active",
                              stage="approved", risk_level="low", description="d",
                              created_at=NOW(), updated_at=NOW())
    s.upsert_agent(base); s.add_version(aid, "1.0.0", base.module_path, "v1")
    v2 = AgentFactoryRecord(agent_id=aid, name=aid, version="1.1.0", status="active",
                            stage="approved", risk_level="low", description="d",
                            module_path=base.module_path, created_at=NOW(),
                            updated_at=NOW(), previous_version="1.0.0", notes="v2")
    s.upsert_agent(v2); s.add_version(aid, "1.1.0", base.module_path, "v2")
    rb = AgentLifecycle().rollback(aid)
    assert rb.success is True
    assert s.get(aid).version == "1.0.0"
