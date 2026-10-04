"""Comprehensive cognitive memory infrastructure tests (spec 72).

Covers:
- Memory model (spec 7)
- Classification (spec 11)
- Importance (spec 10)
- Confidence (spec 9)
- Deduplication (spec 13)
- Retrieval (spec 19/20)
- Ranking (spec 20)
- Permissions (spec 42)
- Agent isolation (spec 40)
- Context budget (spec 25)
- Sync (spec 32)
- Conflicts (spec 36/37)
- Versioning (spec 39)
- Backup (spec 46)
- Restore (spec 46)
- Promotion (spec 15)
- Decay (spec 16)
- Events (spec 60)
- Security (spec 43)
- Offline mode (spec 31)
- Multi-device (spec 35)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.memory.backup import create_backup, export_json, export_jsonl, import_records, list_backups, restore_backup
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
from app.memory.context_engine import ContextEngine, ContextItem, estimate_tokens
from app.memory.health import MemoryHealthService
from app.memory.record import (
    Importance,
    MemoryRecord,
    MemoryType,
    Scope,
    SourceType,
    SyncStatus,
)
from app.memory.retrieval import HybridRetriever, RetrievalCache, keyword_score, recency_score, rewrite_query, scope_score
from app.memory.security import detect_secret, is_secret, sanitize
from app.memory.store import LocalMemoryStore, MemoryStore, default_db_path
from app.memory.sync import (
    ChangeEntry,
    ChangeLog,
    CloudMemoryProvider,
    Conflict,
    ConflictEngine,
    ConflictType,
    NullCloudProvider,
    Operation,
    SyncEngine,
    payload_hash,
)


# ===========================================================================
# Memory Model (spec 7)
# ===========================================================================

class TestMemoryModel:
    def test_record_creation(self):
        rec = MemoryRecord(content="test memory")
        assert rec.content == "test memory"
        assert rec.memory_id.startswith("mem_")
        assert rec.scope is Scope.GLOBAL
        assert rec.type is MemoryType.SEMANTIC
        assert rec.version == 1
        assert rec.deleted is False
        assert rec.archived is False
        assert rec.trusted is False

    def test_record_to_dict(self):
        rec = MemoryRecord(content="test", scope=Scope.USER, type=MemoryType.EPISODIC)
        d = rec.to_dict()
        assert d["content"] == "test"
        assert d["scope"] == "USER"
        assert d["type"] == "episodic"

    def test_record_from_dict(self):
        rec = MemoryRecord(content="test", scope=Scope.PROJECT, confidence=0.9)
        d = rec.to_dict()
        rec2 = MemoryRecord.from_dict(d)
        assert rec2.content == "test"
        assert rec2.scope is Scope.PROJECT
        assert rec2.confidence == 0.9

    def test_record_from_dict_with_string_enums(self):
        d = {"content": "test", "scope": "AGENT", "type": "agent", "importance": "HIGH"}
        rec = MemoryRecord.from_dict(d)
        assert rec.scope is Scope.AGENT
        assert rec.type is MemoryType.AGENT
        assert rec.importance is Importance.HIGH

    def test_apply_defaults(self):
        rec = MemoryRecord(content="test", source_type=SourceType.USER)
        rec.apply_defaults()
        assert rec.confidence == 0.95
        assert rec.trusted is True

    def test_apply_defaults_inference(self):
        rec = MemoryRecord(content="test", source_type=SourceType.INFERENCE)
        rec.apply_defaults()
        assert rec.confidence == 0.40
        assert rec.trusted is False

    def test_importance_score(self):
        rec = MemoryRecord(content="test", importance=Importance.CRITICAL)
        assert rec.importance_score == 1.0
        rec2 = MemoryRecord(content="test", importance=Importance.TEMPORARY)
        assert rec2.importance_score == 0.1


# ===========================================================================
# Classification (spec 11)
# ===========================================================================

class TestClassification:
    def test_classify_procedural(self):
        mtype, scope = classify("To deploy MOON, run the deployment workflow", source_type=SourceType.AGENT)
        assert mtype is MemoryType.PROCEDURAL
        assert scope is Scope.PROJECT

    def test_classify_user(self):
        mtype, scope = classify("I prefer using Python for scripting", source_type=SourceType.USER)
        assert mtype is MemoryType.USER
        assert scope is Scope.USER

    def test_classify_project(self):
        mtype, scope = classify("The project uses FastAPI and uvicorn", source_type=SourceType.AGENT)
        assert mtype is MemoryType.PROJECT
        assert scope is Scope.PROJECT

    def test_classify_episodic(self):
        mtype, scope = classify("The API failed yesterday with a 500 error", source_type=SourceType.AGENT)
        assert mtype is MemoryType.EPISODIC
        assert scope is Scope.PROJECT

    def test_classify_agent_scoped(self):
        mtype, scope = classify("I learned something", source_type=SourceType.AGENT, agent_id="coding")
        assert mtype is MemoryType.AGENT
        assert scope is Scope.AGENT

    def test_detect_candidate_explicit(self):
        ok, reasons = detect_candidate("remember this important fact", source_type=SourceType.USER, explicit=True)
        assert ok is True
        assert any("explicit" in r for r in reasons)

    def test_detect_candidate_noise(self):
        ok, reasons = detect_candidate("Traceback (most recent call last):", source_type=SourceType.TOOL)
        assert ok is False

    def test_detect_candidate_too_short(self):
        ok, reasons = detect_candidate("hi", source_type=SourceType.USER)
        assert ok is False

    def test_detect_candidate_tool_dump(self):
        ok, reasons = detect_candidate("x" * 5000, source_type=SourceType.TOOL)
        assert ok is False
        assert any("too large" in r for r in reasons)


# ===========================================================================
# Importance (spec 10)
# ===========================================================================

class TestImportance:
    def test_explicit_high(self):
        imp = score_importance("remember this", source_type=SourceType.USER, memory_type=MemoryType.SEMANTIC, explicit=True)
        assert imp is Importance.HIGH

    def test_critical_keywords(self):
        imp = score_importance("This is a critical security configuration", source_type=SourceType.AGENT, memory_type=MemoryType.SEMANTIC)
        assert imp is Importance.CRITICAL

    def test_user_source_high(self):
        imp = score_importance("my preference", source_type=SourceType.USER, memory_type=MemoryType.SEMANTIC)
        assert imp is Importance.HIGH

    def test_semantic_high(self):
        imp = score_importance("MOON uses Python", source_type=SourceType.AGENT, memory_type=MemoryType.SEMANTIC)
        assert imp is Importance.HIGH

    def test_reused_promotes(self):
        imp = score_importance("fact", source_type=SourceType.AGENT, memory_type=MemoryType.SEMANTIC, reused=3)
        assert imp is Importance.HIGH

    def test_episodic_medium(self):
        imp = score_importance("something happened", source_type=SourceType.AGENT, memory_type=MemoryType.EPISODIC)
        assert imp is Importance.MEDIUM


# ===========================================================================
# Confidence (spec 9)
# ===========================================================================

class TestConfidence:
    def test_user_confidence(self):
        rec = MemoryRecord(content="test", source_type=SourceType.USER)
        rec.apply_defaults()
        assert rec.confidence == 0.95

    def test_inference_confidence(self):
        rec = MemoryRecord(content="test", source_type=SourceType.INFERENCE)
        rec.apply_defaults()
        assert rec.confidence == 0.40

    def test_web_confidence(self):
        rec = MemoryRecord(content="test", source_type=SourceType.WEB)
        rec.apply_defaults()
        assert rec.confidence == 0.55

    def test_agent_confidence(self):
        rec = MemoryRecord(content="test", source_type=SourceType.AGENT)
        rec.apply_defaults()
        assert rec.confidence == 0.60


# ===========================================================================
# Deduplication (spec 13)
# ===========================================================================

class TestDeduplication:
    def test_similarity_identical(self):
        assert similarity("hello world", "hello world") == 1.0

    def test_similarity_different(self):
        assert similarity("hello", "world") < 0.5

    def test_find_duplicate(self):
        existing = [MemoryRecord(content="MOON uses Python", scope=Scope.PROJECT, type=MemoryType.PROJECT)]
        new = MemoryRecord(content="MOON uses Python", scope=Scope.PROJECT, type=MemoryType.PROJECT)
        dup = find_duplicate(new, existing)
        assert dup is not None

    def test_no_duplicate_different_scope(self):
        existing = [MemoryRecord(content="MOON uses Python", scope=Scope.PROJECT, type=MemoryType.PROJECT)]
        new = MemoryRecord(content="MOON uses Python", scope=Scope.GLOBAL, type=MemoryType.SEMANTIC)
        dup = find_duplicate(new, existing)
        assert dup is None

    def test_no_duplicate_different_agent(self):
        existing = [MemoryRecord(content="test", scope=Scope.AGENT, type=MemoryType.AGENT, agent_id="coding")]
        new = MemoryRecord(content="test", scope=Scope.AGENT, type=MemoryType.AGENT, agent_id="research")
        dup = find_duplicate(new, existing)
        assert dup is None


# ===========================================================================
# Retrieval (spec 19/20)
# ===========================================================================

class TestRetrieval:
    def test_keyword_score(self):
        assert keyword_score("python project", "python project") > 0.5
        assert keyword_score("python", "javascript") < 0.3

    def test_recency_score(self):
        now = time.time()
        assert recency_score(now) == pytest.approx(1.0)
        assert recency_score(now - 86400 * 30) < 0.6  # 30 days old

    def test_scope_score_agent_match(self):
        rec = MemoryRecord(content="test", scope=Scope.AGENT, agent_id="coding")
        assert scope_score(rec, agent_id="coding") == 1.0

    def test_scope_score_agent_mismatch(self):
        rec = MemoryRecord(content="test", scope=Scope.AGENT, agent_id="coding")
        assert scope_score(rec, agent_id="research") == 0.0

    def test_scope_score_global(self):
        rec = MemoryRecord(content="test", scope=Scope.GLOBAL)
        assert scope_score(rec) == 0.7

    def test_rewrite_query(self):
        queries = rewrite_query("Continue the Python project we worked on")
        assert len(queries) > 1
        assert any("python" in q.lower() for q in queries)

    def test_rewrite_query_empty(self):
        assert rewrite_query("") == []

    def test_hybrid_retriever_basic(self):
        retriever = HybridRetriever()
        records = [
            MemoryRecord(content="MOON uses Python", scope=Scope.PROJECT, importance=Importance.HIGH),
            MemoryRecord(content="The weather is nice", scope=Scope.GLOBAL),
        ]
        results = retriever.search("MOON Python", records, top_k=2)
        assert len(results) > 0
        assert results[0].record.content == "MOON uses Python"

    def test_retrieval_cache(self):
        cache = RetrievalCache(ttl=1.0)
        key = ("query", ("agent_id", "coding"))
        cache.put(key, ["result"])
        assert cache.get(key) == ["result"]
        cache.invalidate()
        assert cache.get(key) is None


# ===========================================================================
# Permissions (spec 42)
# ===========================================================================

class TestPermissions:
    def test_policy_read_own_agent_memory(self):
        policy = MemoryPolicyEngine()
        rec = MemoryRecord(content="test", scope=Scope.AGENT, agent_id="coding")
        ok, _ = policy.can("READ", record=rec, agent_id="coding")
        assert ok is True

    def test_policy_read_other_agent_memory_denied(self):
        policy = MemoryPolicyEngine()
        rec = MemoryRecord(content="test", scope=Scope.AGENT, agent_id="coding")
        ok, _ = policy.can("READ", record=rec, agent_id="research")
        assert ok is False

    def test_policy_share_denied_by_default(self):
        policy = MemoryPolicyEngine()
        rec = MemoryRecord(content="test", scope=Scope.AGENT, agent_id="coding")
        ok, _ = policy.can("SHARE", record=rec, agent_id="coding")
        assert ok is False

    def test_policy_export_secret_denied(self):
        policy = MemoryPolicyEngine()
        rec = MemoryRecord(content="api_key=sk-1234567890abcdefghij", scope=Scope.GLOBAL)
        ok, _ = policy.can("EXPORT", record=rec)
        assert ok is False

    def test_policy_export_normal_allowed(self):
        policy = MemoryPolicyEngine()
        rec = MemoryRecord(content="MOON uses Python", scope=Scope.GLOBAL)
        ok, _ = policy.can("EXPORT", record=rec)
        assert ok is True


# ===========================================================================
# Agent Isolation (spec 40)
# ===========================================================================

class TestAgentIsolation:
    def test_agent_memory_isolated(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)

        # Store agent-private memory
        mgr.store("coding agent secret", scope=Scope.AGENT, agent_id="coding", explicit=True)
        mgr.store("research agent secret", scope=Scope.AGENT, agent_id="research", explicit=True)

        # Coding agent should only see its own
        results = mgr.search("secret", agent_id="coding", top_k=10)
        assert all(r.record.agent_id == "coding" for r in results)

        # Research agent should only see its own
        results = mgr.search("secret", agent_id="research", top_k=10)
        assert all(r.record.agent_id == "research" for r in results)

    def test_shared_memory_visible_to_all(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)

        mgr.store("shared fact", scope=Scope.TEAM, type_=MemoryType.SHARED, explicit=True)

        results = mgr.search("shared", agent_id="coding", top_k=10)
        assert len(results) > 0


# ===========================================================================
# Context Budget (spec 25)
# ===========================================================================

class TestContextBudget:
    def test_estimate_tokens(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("hello") >= 1
        assert estimate_tokens("hello world") >= 2

    def test_context_engine_basic(self):
        engine = ContextEngine(window=8192, output_reserve=1024)
        items = [
            ContextItem(memory_id="1", content="fact 1", score=0.9),
            ContextItem(memory_id="2", content="fact 2", score=0.8),
        ]
        result = engine.build(memories=items)
        assert result.tokens > 0
        assert len(result.included) > 0

    def test_context_engine_budget_enforced(self):
        engine = ContextEngine(window=200, output_reserve=50, memory_budget_ratio=0.3)
        items = [
            ContextItem(memory_id=str(i), content="x" * 100, score=0.5)
            for i in range(20)
        ]
        result = engine.build(memories=items)
        assert result.tokens <= engine.memory_token_budget() + 100  # some overhead

    def test_context_engine_fit(self):
        engine = ContextEngine(window=200, output_reserve=50)
        items = [
            ContextItem(memory_id="1", content="critical fact", score=0.9, importance="CRITICAL"),
            ContextItem(memory_id="2", content="low priority", score=0.1, importance="LOW"),
        ]
        result = engine.build(memories=items)
        fitted = engine.fit(result, system_prompt="x" * 500, user_input="y" * 500)
        assert fitted.budget.get("fitted", False) is True


# ===========================================================================
# Sync (spec 32)
# ===========================================================================

class TestSync:
    def test_change_log_append(self, tmp_path):
        log = ChangeLog(path=tmp_path / "changelog.jsonl")
        rec = MemoryRecord(content="test")
        entry = log.append(rec, Operation.CREATE, device_id="dev1")
        assert entry.operation_id
        assert entry.memory_id == rec.memory_id
        assert entry.status == "pending"

    def test_change_log_idempotent(self, tmp_path):
        log = ChangeLog(path=tmp_path / "changelog.jsonl")
        rec = MemoryRecord(content="test")
        e1 = log.append(rec, Operation.CREATE, device_id="dev1")
        e2 = log.append(rec, Operation.CREATE, device_id="dev1")
        assert e1.operation_id == e2.operation_id

    def test_payload_hash_stable(self):
        rec = MemoryRecord(content="test", scope=Scope.GLOBAL, type=MemoryType.SEMANTIC, version=1)
        h1 = payload_hash(rec)
        h2 = payload_hash(rec)
        assert h1 == h2

    def test_sync_engine_local_only(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        engine = SyncEngine(store=store, provider=NullCloudProvider(), device_id="dev1")
        result = engine.sync()
        assert result["local_only"] is True

    def test_sync_engine_status(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        engine = SyncEngine(store=store, provider=NullCloudProvider(), device_id="dev1")
        status = engine.status()
        assert status["local_only"] is True
        assert status["provider"] == "none"


# ===========================================================================
# Conflicts (spec 36/37)
# ===========================================================================

class TestConflicts:
    def test_conflict_detect_none(self):
        engine = ConflictEngine()
        rec = MemoryRecord(content="test")
        assert engine.detect(rec, rec) is None

    def test_conflict_detect_content(self):
        engine = ConflictEngine()
        local = MemoryRecord(content="port 8000", version=1)
        remote = MemoryRecord(content="port 9000", version=1)
        c = engine.detect(local, remote)
        assert c is not None
        assert c.type is ConflictType.CONTENT_CONFLICT

    def test_conflict_detect_update_update(self):
        engine = ConflictEngine()
        local = MemoryRecord(content="A", version=2)
        remote = MemoryRecord(content="B", version=3)
        c = engine.detect(local, remote)
        assert c is not None
        assert c.type is ConflictType.UPDATE_UPDATE

    def test_conflict_detect_delete_update(self):
        engine = ConflictEngine()
        local = MemoryRecord(content="A", deleted=True)
        remote = MemoryRecord(content="B")
        c = engine.detect(local, remote)
        assert c is not None
        assert c.type is ConflictType.DELETE_UPDATE

    def test_conflict_resolve_content_manual(self):
        engine = ConflictEngine()
        local = MemoryRecord(content="port 8000", version=1)
        remote = MemoryRecord(content="port 9000", version=1)
        c = engine.detect(local, remote)
        resolved = engine.resolve(c)
        assert resolved.resolution == "manual"

    def test_conflict_resolve_version_mismatch(self):
        engine = ConflictEngine()
        local = MemoryRecord(content="same", version=3)
        remote = MemoryRecord(content="same", version=2)
        c = engine.detect(local, remote)
        resolved = engine.resolve(c)
        assert resolved.resolution == "local_wins"


# ===========================================================================
# Versioning (spec 39)
# ===========================================================================

class TestVersioning:
    def test_version_increment_on_update(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        rec = mgr.store("remember this important fact", explicit=True)
        assert rec.version == 1
        updated = mgr.update(rec.memory_id, "updated content here")
        assert updated.version == 2
        assert updated.parent_version == 1

    def test_rollback(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        rec = mgr.store("remember this original fact", explicit=True)
        mgr.update(rec.memory_id, "changed content here")
        rolled = mgr.rollback(rec.memory_id, target_version=1)
        assert rolled is not None
        assert rolled.version == 3
        assert rolled.parent_version == 1


# ===========================================================================
# Backup (spec 46)
# ===========================================================================

class TestBackup:
    def test_create_backup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MOON_BACKUP_PATH", str(tmp_path / "backups"))
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        store.upsert(MemoryRecord(content="test", scope=Scope.GLOBAL))
        path = create_backup(store, keep=3)
        assert path.exists()
        assert path.suffix == ".json"

    def test_backup_rotation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MOON_BACKUP_PATH", str(tmp_path / "backups"))
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        store.upsert(MemoryRecord(content="test", scope=Scope.GLOBAL))
        for i in range(5):
            create_backup(store, name=f"backup_{i}", keep=3)
        backups = list_backups()
        assert len(backups) <= 3

    def test_export_json(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        store.upsert(MemoryRecord(content="test", scope=Scope.GLOBAL))
        path = export_json(store, tmp_path / "export.json")
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data) > 0

    def test_export_jsonl(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        store.upsert(MemoryRecord(content="test", scope=Scope.GLOBAL))
        path = export_jsonl(store, tmp_path / "export.jsonl")
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) > 0

    def test_import_records(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        data = [{"content": "imported fact", "scope": "GLOBAL", "type": "semantic"}]
        rep = import_records(store, data)
        assert rep.inserted == 1

    def test_import_dedup(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        data = [{"content": "fact", "scope": "GLOBAL", "type": "semantic"}]
        import_records(store, data)
        rep = import_records(store, data)
        assert rep.duplicates == 1

    def test_import_rejects_secret(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        data = [{"content": "api_key=sk-1234567890abcdefghij"}]
        rep = import_records(store, data)
        assert rep.rejected_secret == 1

    def test_restore_backup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MOON_BACKUP_PATH", str(tmp_path / "backups"))
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        store.upsert(MemoryRecord(content="test", scope=Scope.GLOBAL))
        path = create_backup(store, keep=3)

        # Clear and restore
        store2 = LocalMemoryStore(db_path=tmp_path / "test2.db")
        rep = restore_backup(store2, path)
        assert rep.inserted > 0


# ===========================================================================
# Promotion (spec 15)
# ===========================================================================

class TestPromotion:
    def test_promote_memory(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        rec = mgr.store("important fact", explicit=True)
        promoted = mgr.promote(rec.memory_id, target_scope=Scope.GLOBAL)
        assert promoted is not None
        assert promoted.scope is Scope.GLOBAL
        assert promoted.importance is Importance.HIGH

    def test_promote_critical_user_blocked(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        rec = mgr.store("critical user fact", source_type=SourceType.USER, explicit=True,
                        importance=Importance.CRITICAL)
        result = mgr.promote(rec.memory_id)
        assert result is None


# ===========================================================================
# Decay (spec 16)
# ===========================================================================

class TestDecay:
    def test_decay_reduces_confidence(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        rec = mgr.store("remember this fact", explicit=True)
        original_confidence = rec.confidence
        decayed = mgr.decay(rec.memory_id, factor=0.5)
        assert decayed is not None
        assert decayed.confidence < original_confidence

    def test_decay_user_memory_blocked(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        rec = mgr.store("remember this user fact", source_type=SourceType.USER, explicit=True)
        result = mgr.decay(rec.memory_id)
        assert result is None

    def test_decay_critical_blocked(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        rec = mgr.store("remember this critical fact", importance=Importance.CRITICAL, explicit=True)
        result = mgr.decay(rec.memory_id)
        assert result is None


# ===========================================================================
# Events (spec 60)
# ===========================================================================

class TestEvents:
    def test_memory_events_emitted(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        # These should not raise
        rec = mgr.store("remember this test fact", explicit=True)
        assert rec is not None
        mgr.archive(rec.memory_id)
        mgr.promote(rec.memory_id)
        mgr.forget(rec.memory_id)

    def test_sync_events(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        engine = SyncEngine(store=store, provider=NullCloudProvider(), device_id="dev1")
        # Should not raise
        engine.sync()


# ===========================================================================
# Security (spec 43)
# ===========================================================================

class TestSecurity:
    def test_detect_openai_key(self):
        v = detect_secret("sk-1234567890abcdefghij")
        assert v.is_secret is True

    def test_detect_github_token(self):
        v = detect_secret("ghp_1234567890abcdefghij1234567890")
        assert v.is_secret is True

    def test_detect_private_key(self):
        v = detect_secret("-----BEGIN RSA PRIVATE KEY-----")
        assert v.is_secret is True

    def test_detect_normal_text(self):
        v = detect_secret("MOON uses Python")
        assert v.is_secret is False

    def test_sanitize(self):
        text = "key=sk-1234567890abcdefghij"
        sanitized, verdict = sanitize(text)
        assert verdict.is_secret is True
        assert "sk-1234567890" not in sanitized

    def test_store_rejects_secret(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        rec = mgr.store("api_key=sk-1234567890abcdefghij", explicit=True)
        assert rec is None


# ===========================================================================
# Offline Mode (spec 31)
# ===========================================================================

class TestOfflineMode:
    def test_local_write_succeeds_without_cloud(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        rec = mgr.store("offline fact", explicit=True)
        assert rec is not None
        assert rec.sync_status is SyncStatus.PENDING

    def test_local_read_succeeds_without_cloud(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        mgr.store("offline fact", explicit=True)
        results = mgr.search("offline", top_k=5)
        assert len(results) > 0


# ===========================================================================
# Multi-Device (spec 35)
# ===========================================================================

class TestMultiDevice:
    def test_device_id_generated(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        assert mgr.device_id
        assert len(mgr.device_id) == 16

    def test_device_id_stable(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr1 = CognitiveMemoryManager(store=store)
        mgr2 = CognitiveMemoryManager(store=store)
        assert mgr1.device_id == mgr2.device_id


# ===========================================================================
# Commands (spec 12)
# ===========================================================================

class TestCommands:
    def test_parse_remember(self):
        cmd = parse_memory_command("remember that MOON uses Python")
        assert cmd is not None
        assert cmd["op"] == "remember"

    def test_parse_forget(self):
        cmd = parse_memory_command("forget everything about the old API")
        assert cmd is not None
        assert cmd["op"] == "forget"

    def test_parse_show(self):
        cmd = parse_memory_command("show what you remember about Python")
        assert cmd is not None
        assert cmd["op"] == "show"

    def test_is_memory_command(self):
        assert is_memory_command("remember this fact") is True
        assert is_memory_command("hello world") is False

    def test_handle_command_remember(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        result = mgr.handle_command("remember that MOON uses Python")
        assert result is not None
        assert result["op"] == "remember"
        assert result["stored"] is True

    def test_handle_command_forget(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        mgr.store("MOON uses Python", explicit=True)
        result = mgr.handle_command("forget everything about MOON")
        assert result is not None
        assert result["op"] == "forget"
        assert result["count"] > 0


# ===========================================================================
# Health (spec 50)
# ===========================================================================

class TestHealth:
    def test_health_service(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        svc = MemoryHealthService(manager=mgr)
        report = svc.check()
        assert report.ok is True
        assert "local_db" in report.components

    def test_terminal_status(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        svc = MemoryHealthService(manager=mgr)
        status = svc.terminal_status()
        assert "MOON MEMORY" in status
        assert "Local DB" in status

    def test_task_summary(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        svc = MemoryHealthService(manager=mgr)
        summary = svc.task_summary(retrieved=8, used=5, filtered=3)
        assert "Memory Retrieved: 8" in summary
        assert "Relevant: 5" in summary


# ===========================================================================
# Shared Memory (spec 41)
# ===========================================================================

class TestSharedMemory:
    def test_publish_shared(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        rec = mgr.store("coding insight", scope=Scope.AGENT, agent_id="coding", explicit=True)
        shared = mgr.publish_shared(rec.memory_id, agent_id="coding")
        assert shared is not None
        assert shared.scope is Scope.TEAM
        assert shared.type is MemoryType.SHARED

    def test_publish_other_agent_denied(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        rec = mgr.store("coding secret", scope=Scope.AGENT, agent_id="coding", explicit=True)
        result = mgr.publish_shared(rec.memory_id, agent_id="research")
        assert result is None


# ===========================================================================
# Store (spec 26/28)
# ===========================================================================

class TestStore:
    def test_upsert_and_get(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        rec = MemoryRecord(content="test", scope=Scope.GLOBAL)
        store.upsert(rec)
        fetched = store.get(rec.memory_id)
        assert fetched is not None
        assert fetched.content == "test"

    def test_soft_delete(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        rec = MemoryRecord(content="test")
        store.upsert(rec)
        store.delete(rec.memory_id)
        assert store.get(rec.memory_id) is None
        assert store.get(rec.memory_id, include_deleted=True) is not None

    def test_hard_delete(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        rec = MemoryRecord(content="test")
        store.upsert(rec)
        store.delete(rec.memory_id, hard=True)
        assert store.get(rec.memory_id, include_deleted=True) is None

    def test_query_by_scope(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        store.upsert(MemoryRecord(content="user fact", scope=Scope.USER))
        store.upsert(MemoryRecord(content="project fact", scope=Scope.PROJECT))
        results = store.query(scope=Scope.USER)
        assert len(results) == 1
        assert results[0].content == "user fact"

    def test_query_by_keyword(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        store.upsert(MemoryRecord(content="Python is great"))
        store.upsert(MemoryRecord(content="JavaScript is ok"))
        results = store.query(keyword="Python")
        assert len(results) == 1

    def test_count(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        store.upsert(MemoryRecord(content="a"))
        store.upsert(MemoryRecord(content="b"))
        assert store.count() == 2

    def test_health(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        h = store.health()
        assert h["online"] is True
        assert h["store"] == "local_sqlite"

    def test_mark_synced(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        rec = MemoryRecord(content="test", sync_status=SyncStatus.PENDING)
        store.upsert(rec)
        store.mark_synced([rec.memory_id], SyncStatus.SYNCED)
        assert store.get(rec.memory_id).sync_status is SyncStatus.SYNCED


# ===========================================================================
# Integration: Full Pipeline
# ===========================================================================

class TestFullPipeline:
    def test_store_search_forget(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)

        # Store
        rec = mgr.store("MOON uses Python 3.14", source_type=SourceType.USER, explicit=True)
        assert rec is not None

        # Search
        results = mgr.search("Python", top_k=5)
        assert len(results) > 0

        # Forget
        assert mgr.forget(rec.memory_id) is True
        results = mgr.search("Python", top_k=5)
        assert len(results) == 0

    def test_agent_isolation_full(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)

        # Two agents store private memories
        mgr.store("coding secret", scope=Scope.AGENT, agent_id="coding", explicit=True)
        mgr.store("research secret", scope=Scope.AGENT, agent_id="research", explicit=True)

        # Each sees only their own
        coding_results = mgr.search("secret", agent_id="coding", top_k=10)
        assert all(r.record.agent_id == "coding" for r in coding_results)

        research_results = mgr.search("secret", agent_id="research", top_k=10)
        assert all(r.record.agent_id == "research" for r in research_results)

    def test_context_engine_integration(self, tmp_path):
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)
        engine = ContextEngine(window=4096, output_reserve=512)

        # Store some memories
        mgr.store("MOON uses Python", explicit=True)
        mgr.store("MOON uses FastAPI", explicit=True)
        mgr.store("MOON uses SQLite", explicit=True)

        # Retrieve
        hits = mgr.search("MOON technology", top_k=5)
        assert len(hits) > 0

        # Build context
        result = engine.build(memories=hits)
        assert result.tokens > 0
        assert len(result.included) > 0

    def test_backup_restore_integration(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MOON_BACKUP_PATH", str(tmp_path / "backups"))
        store = LocalMemoryStore(db_path=tmp_path / "test.db")
        mgr = CognitiveMemoryManager(store=store)

        # Store memories
        mgr.store("remember fact one", explicit=True)
        mgr.store("remember fact two", explicit=True)

        # Backup
        path = create_backup(mgr._store, keep=3)
        assert path.exists()

        # New store, restore
        store2 = LocalMemoryStore(db_path=tmp_path / "test2.db")
        rep = restore_backup(store2, path)
        assert rep.inserted > 0

        # Verify
        results = store2.query(limit=10)
        assert len(results) >= 2
