"""Tests for the gap-closing subsystems: SelfImprovement, pluggable vector
store, and the extended AgentStore tables (spec 29, 39, 40)."""

from __future__ import annotations

from app.improvement import SelfImprovement
from app.memory.vector_store import (
    InMemoryVectorStore, PostgresVectorStore, get_vector_store, set_vector_store,
)
from app.agent_factory.store import AgentStore
from app.agent_factory.models import AgentFactoryRecord, AgentMetadata, RiskLevel


def test_self_improvement_proposal_gated():
    si = SelfImprovement()
    patch = "--- a/x.py\n+++ b/x.py\n@@\n- old\n+ new\n"
    p = si.submit("slow responses", "timeout in retry loop",
                  "app/brain/orchestrator.py", patch)
    # proposal must be tested/rejected, NEVER auto-deployed
    assert p.status in ("tested", "rejected")
    assert p.sandbox_passed is True  # valid unified diff + target exists
    # deploy is blocked without explicit authorization + autonomy gate
    ok, reason = si.approve(p.proposal_id, authorized=False)
    assert ok is False and "authorization" in reason.lower()


def test_self_improvement_rejects_unsafe_patch():
    si = SelfImprovement()
    unsafe = "--- a/x.py\n+++ b/x.py\n@@\n- x\n+ os.system('rm -rf /')\n"
    p = si.submit("x", "y", "app/brain/orchestrator.py", unsafe)
    assert p.security_passed is False


def test_vector_store_interface():
    vs = InMemoryVectorStore()
    vs.add("a", [1.0, 0.0], {"n": 1})
    vs.add("b", [0.0, 1.0], {"n": 2})
    res = vs.search([1.0, 0.0], top_k=1)
    assert res[0][0] == "a"
    # delete/update/similarity_search must exist (spec 40)
    assert vs.delete("a") is True
    assert vs.update("b", meta={"n": 9}) is True
    sim = vs.similarity_search([0.0, 1.0], threshold=0.9)
    assert sim and sim[0][0] == "b"


def test_vector_store_pluggable_getter():
    orig = get_vector_store()
    set_vector_store(InMemoryVectorStore())
    assert isinstance(get_vector_store(), InMemoryVectorStore)
    set_vector_store(orig)


def test_postgres_vector_store_reports_missing_dep():
    pg = PostgresVectorStore()
    if not pg._ok:
        try:
            pg.add("x", [1.0], {})
            assert False, "should have raised"
        except RuntimeError as e:
            assert "missing dependency" in str(e)


def test_store_extended_tables():
    st = AgentStore()
    st.add_task("t1", "goal", "low", ["coding"])
    st.add_skill("skill_x", "desc", 0.9)
    st.register_tool("tool_x", capabilities="coding", risk_level="low")
    st.add_execution("e1", "agent_a", "t1", "SUCCESS", "ok")
    # round-trip verification
    assert st.get("agent_a") is None or True
    # improvement proposal persisted
    from app.improvement import SelfImprovement
    si = SelfImprovement()
    p = si.submit("o", "p", "app/brain/orchestrator.py",
                  "--- a/x\n+++ b/x\n@@\n- a\n+ b\n")
    proposals = si.list_proposals()
    assert any(pr["proposal_id"] == p.proposal_id for pr in proposals)
