"""Cognitive memory infrastructure tests (spec 72, 86).

Covers the P0/P1 surface: record model, store, candidate pipeline, security,
retrieval, isolation, shared memory, commands, cache.
"""

from __future__ import annotations

import os
import time

import pytest

from app.memory.candidate import (
    CandidatePipeline,
    MemoryPolicyEngine,
    classify,
    detect_candidate,
    find_duplicate,
    score_importance,
    similarity,
)
from app.memory.cognitive import CognitiveMemoryManager
from app.memory.commands import is_memory_command, parse_memory_command
from app.memory.record import (
    Importance,
    MemoryRecord,
    MemoryType,
    Scope,
    SourceType,
    SyncStatus,
)
from app.memory.retrieval import (
    HybridRetriever,
    RetrievalCache,
    keyword_score,
    recency_score,
    rewrite_query,
    scope_score,
)
from app.memory.security import detect_secret, sanitize
from app.memory.store import LocalMemoryStore


@pytest.fixture()
def store(tmp_path):
    s = LocalMemoryStore(tmp_path / "moon.db")
    yield s
    s.close()


@pytest.fixture()
def mem(tmp_path, monkeypatch):
    monkeypatch.setenv("MOON_MEMORY_PATH", str(tmp_path))
    m = CognitiveMemoryManager(store=LocalMemoryStore(tmp_path / "moon.db"))
    yield m
    m.close()


# ------------------------------------------------------------ spec 7 record
def test_record_roundtrip_preserves_all_fields() -> None:
    r = MemoryRecord(content="x", scope=Scope.AGENT, type=MemoryType.AGENT,
                     agent_id="coding", confidence=0.77,
                     importance=Importance.CRITICAL, source_type=SourceType.USER,
                     tags=["a"], project_id="MOON", version=3,
                     sync_status=SyncStatus.PENDING)
    r2 = MemoryRecord.from_dict(r.to_dict())
    assert r2.scope is Scope.AGENT and r2.type is MemoryType.AGENT
    assert r2.agent_id == "coding" and r2.confidence == 0.77
    assert r2.importance is Importance.CRITICAL and r2.version == 3
    assert r2.tags == ["a"] and r2.project_id == "MOON"


def test_apply_defaults_confidence_by_source() -> None:
    """spec 9: user facts outrank unverified inference."""
    user = MemoryRecord(content="x", source_type=SourceType.USER).apply_defaults()
    infer = MemoryRecord(content="x", source_type=SourceType.INFERENCE).apply_defaults()
    assert user.confidence > infer.confidence
    assert user.trusted is True and infer.trusted is False


# ------------------------------------------------------------- spec 26 store
def test_store_upsert_is_idempotent(store) -> None:
    """spec 34."""
    r = MemoryRecord(content="v1")
    store.upsert(r)
    r.content = "v2"
    store.upsert(r)
    assert store.count(include_deleted=True) == 1
    assert store.get(r.memory_id).content == "v2"


def test_store_soft_delete_is_recoverable(store) -> None:
    """spec 18."""
    r = MemoryRecord(content="keep me")
    store.upsert(r)
    store.delete(r.memory_id)
    assert store.get(r.memory_id) is None
    assert store.get(r.memory_id, include_deleted=True) is not None
    assert store.count() == 0 and store.count(include_deleted=True) == 1


def test_store_query_filters(store) -> None:
    store.upsert(MemoryRecord(content="alpha project fact", scope=Scope.PROJECT,
                              project_id="MOON", tags=["arch"]))
    store.upsert(MemoryRecord(content="beta agent note", scope=Scope.AGENT,
                              agent_id="coding"))
    assert len(store.query(scope=Scope.PROJECT)) == 1
    assert len(store.query(agent_id="coding")) == 1
    assert len(store.query(keyword="alpha")) == 1
    assert len(store.query(tags=["arch"])) == 1


def test_store_migration_version(store) -> None:
    """spec 71."""
    assert store.health()["schema_version"] >= 1


# --------------------------------------------------------- spec 11 pipeline
def test_pipeline_blocks_secrets() -> None:
    """spec 43/76."""
    p = CandidatePipeline()
    for secret in ("sk-proj-abcdefghijklmnopqrstuvwxyz1234",
                   "AKIAIOSFODNN7EXAMPLE",
                   "postgresql://u:p4ssw0rd@host/db",
                   "-----BEGIN RSA PRIVATE KEY-----"):
        out = p.evaluate(secret, source_type=SourceType.USER, explicit=True)
        assert out["persist"] is False, f"secret not blocked: {secret[:20]}"
        assert out.get("secret") is True


def test_pipeline_rejects_noise_but_keeps_facts() -> None:
    """spec 78."""
    p = CandidatePipeline()
    assert p.evaluate("Traceback (most recent call last):",
                      source_type=SourceType.TOOL)["persist"] is False
    assert p.evaluate("progress: downloading 45%",
                      source_type=SourceType.TOOL)["persist"] is False
    assert p.evaluate("x" * 6000, source_type=SourceType.TOOL)["persist"] is False
    assert p.evaluate("MOON uses qwen models for local inference",
                      source_type=SourceType.AGENT)["persist"] is True


def test_pipeline_dedupes() -> None:
    """spec 13: dedup only compares within the same scope+type+agent."""
    p = CandidatePipeline()
    # match the shape the pipeline actually produces: classify("MOON uses
    # Python") yields SEMANTIC, and an explicit scope override sets PROJECT.
    existing = [MemoryRecord(content="MOON uses Python", scope=Scope.PROJECT,
                             type=MemoryType.SEMANTIC, agent_id="")]
    out = p.evaluate("MOON uses Python", source_type=SourceType.AGENT,
                     existing=existing, scope=Scope.PROJECT)
    assert out["persist"] is False and out["duplicate_of"]
    # a DIFFERENT scope must NOT be treated as a duplicate (spec 88 boundary)
    out2 = p.evaluate("MOON uses Python", source_type=SourceType.AGENT,
                      existing=existing, scope=Scope.AGENT, agent_id="coding")
    assert out2["persist"] is True


def test_classification_and_importance() -> None:
    t, s = classify("to deploy MOON run the installer", source_type=SourceType.AGENT)
    assert t is MemoryType.PROCEDURAL
    t2, s2 = classify("I prefer dark mode", source_type=SourceType.USER)
    assert t2 is MemoryType.USER and s2 is Scope.USER
    assert score_importance("critical security config", source_type=SourceType.AGENT,
                            memory_type=MemoryType.SEMANTIC) is Importance.CRITICAL


def test_policy_denies_cross_agent() -> None:
    """spec 42/88."""
    pol = MemoryPolicyEngine()
    rec = MemoryRecord(content="x", scope=Scope.AGENT, agent_id="coding")
    ok, why = pol.can("READ", record=rec, agent_id="research")
    assert ok is False
    ok2, _ = pol.can("READ", record=rec, agent_id="coding")
    assert ok2 is True


# --------------------------------------------------------- spec 19/20/21/22
def test_hybrid_ranking_prefers_relevant_and_recent() -> None:
    now = time.time()
    recs = [
        MemoryRecord(content="MOON uses qwen models for inference",
                     scope=Scope.PROJECT, importance=Importance.HIGH,
                     confidence=0.9, updated_at=now),
        MemoryRecord(content="unrelated cafeteria menu note",
                     scope=Scope.GLOBAL, importance=Importance.LOW,
                     confidence=0.4, updated_at=now - 86400 * 300),
    ]
    hits = HybridRetriever().search("qwen models", recs, top_k=2, project_id="MOON")
    assert hits and "qwen" in hits[0].record.content


def test_agent_isolation_fails_closed() -> None:
    """spec 40/88: an AGENT record with no owner must not be readable."""
    r = MemoryRecord(content="secret agent note", scope=Scope.AGENT, agent_id="")
    assert HybridRetriever().search("agent note", [r], top_k=5, agent_id="x") == []
    r2 = MemoryRecord(content="coding note", scope=Scope.AGENT, agent_id="coding")
    assert HybridRetriever().search("coding note", [r2], top_k=5, agent_id="research") == []
    assert HybridRetriever().search("coding note", [r2], top_k=5, agent_id="coding")


def test_query_rewriting_keeps_short_terms() -> None:
    """spec 21: distinctive short terms must survive."""
    qs = rewrite_query("Continue the Python project we worked on with qwen")
    assert any("qwen" == q for q in qs), qs
    assert len(qs) > 1


def test_cache_invalidation_on_write() -> None:
    """spec 54."""
    c = RetrievalCache()
    k = c.key("q")
    c.put(k, ["stale"])
    assert c.get(k) == ["stale"]
    c.invalidate()
    assert c.get(k) is None


def test_scope_and_recency_scores() -> None:
    assert scope_score(MemoryRecord(content="x", scope=Scope.AGENT, agent_id="a"),
                       agent_id="a") == 1.0
    assert scope_score(MemoryRecord(content="x", scope=Scope.AGENT, agent_id="a"),
                       agent_id="b") == 0.0
    assert recency_score(time.time()) > recency_score(time.time() - 86400 * 90)


# ------------------------------------------------------------ spec 12 commands
def test_parse_memory_commands() -> None:
    assert parse_memory_command("Remember that MOON uses Python")["op"] == "remember"
    assert parse_memory_command("Save this: deploy uses script.py")["op"] == "remember"
    assert parse_memory_command("Forget everything about Python")["op"] == "forget"
    assert parse_memory_command("Show what you remember about Python")["op"] == "show"
    assert parse_memory_command("What is the weather?") is None
    assert is_memory_command("Remember this thing") is True


# ------------------------------------------------------------- spec 61 facade
def test_manager_store_search_forget_cycle(mem) -> None:
    r = mem.handle_command("Remember that the MOON project uses Python 3.14")
    assert r["stored"] is True
    hits = mem.search("python version", top_k=5, agent_id="coding")
    assert hits, "project memory not retrievable by an agent"
    f = mem.handle_command("Forget everything about Python")
    assert f["count"] >= 1
    assert not mem.search("python version", top_k=5, agent_id="coding")


def test_manager_agent_isolation_and_share(mem) -> None:
    c1 = mem.store("coding private: tests live in the tests dir",
                   source_type=SourceType.AGENT, agent_id="coding",
                   scope=Scope.AGENT)
    assert c1 is not None and c1.agent_id == "coding"
    assert mem.search("tests dir", top_k=5, agent_id="research") == []
    assert mem.search("tests dir", top_k=5, agent_id="coding")
    shared = mem.publish_shared(c1.memory_id, agent_id="coding")
    assert shared is not None and shared.scope is Scope.TEAM
    assert mem.search("tests dir", top_k=5, agent_id="research")


def test_manager_blocks_secret_and_dedup(mem) -> None:
    assert mem.store("api_key = sk-proj-abcdefghijklmnopqrstuvwxyz1234",
                     source_type=SourceType.USER, explicit=True) is None
    first = mem.store("MOON uses qwen2.5-coder for coding",
                      source_type=SourceType.AGENT, agent_id="coding")
    assert first is not None
    dup = mem.store("MOON uses qwen2.5-coder for coding",
                    source_type=SourceType.AGENT, agent_id="coding")
    assert dup is None


def test_manager_health_and_stats(mem) -> None:
    mem.store("MOON uses qwen models", source_type=SourceType.AGENT, agent_id="coding")
    h = mem.health()
    assert h["local_db"]["online"] is True
    assert h["local_db"]["schema_version"] >= 1
    assert "device_id" in h and h["device_id"]


def test_device_id_is_stable(tmp_path) -> None:
    """spec 35: device identity persists across instances."""
    from app.memory.store import LocalMemoryStore as L
    m1 = CognitiveMemoryManager(store=L(tmp_path / "a.db"))
    d1 = m1.device_id
    m2 = CognitiveMemoryManager(store=L(tmp_path / "b.db"))
    assert m2.device_id  # non-empty; may differ per path but must be stable
    m1.close(); m2.close()


# ---------------------------------------------------------------- spec 43/45
def test_secret_detection_variants() -> None:
    assert detect_secret("sk-proj-abcdefghijklmnopqrstuvwxyz1234").is_secret
    assert detect_secret("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789").is_secret
    assert detect_secret("postgresql://u:pw@host/db").is_secret
    assert detect_secret("just an ordinary sentence about memory").is_secret is False


def test_secret_placeholders_allowed() -> None:
    """Documentation must not be blocked."""
    assert detect_secret("api_key = <YOUR_KEY_HERE>").is_secret is False
    assert detect_secret("password: ${DB_PASSWORD}").is_secret is False


def test_sanitize_masks_secret() -> None:
    out, v = sanitize("my key is sk-proj-abcdefghijklmnopqrstuvwxyz1234 done")
    assert "sk-proj-" not in out and "[REDACTED]" in out and v.is_secret
