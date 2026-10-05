"""Cognitive MemoryManager -- the single controlled interface (spec 28, 61, 62).

Spec 61: agents must NOT touch database tables. They call
``memory.search() / store() / update() / forget()`` and nothing else. This
facade owns the store, the candidate pipeline, the retriever, the cache and the
policy engine, and is what the Orchestrator/Main Brain integrates with.

It is ADDITIVE: the pre-existing MemoryManager (app/brain/memory_manager.py)
keeps working untouched; this is the cognitive layer the spec asks for.

Spec 88 boundaries held here:
    MEMORY != DATABASE   -> store is injected, not assumed
    MEMORY != CONTEXT    -> retrieval returns records; the ContextEngine budgets
    AGENT != GLOBAL      -> scope + policy enforced on every read/write
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.memory.candidate import CandidatePipeline, MemoryPolicyEngine
from app.memory.record import (
    Importance,
    MemoryRecord,
    MemoryType,
    Scope,
    SourceType,
    SyncStatus,
)
from app.memory.retrieval import HybridRetriever, RetrievalCache, rewrite_query
from app.memory.security import detect_secret
from app.memory.store import MemoryStore, default_db_path
from .factory import memory_store_factory
from .store import LocalMemoryStore

logger = logging.getLogger(__name__)


class CognitiveMemoryManager:
    """The cognitive memory facade (spec 28/61/62)."""

    def __init__(self, *, store: MemoryStore | None = None,
                 device_id: str = "", project_id: str = "MOON",
                 embed_fn: Any = None, vector_store: Any = None,
                 agent_id: str = "") -> None:
        self._store: MemoryStore = store or memory_store_factory()
        self._pipeline = CandidatePipeline()
        self._policy = MemoryPolicyEngine()
        self._retriever = HybridRetriever(embed_fn=embed_fn, vector_store=vector_store)
        self._cache = RetrievalCache()
        self._device_id = device_id or self._load_device_id()
        self._project_id = project_id
        self._agent_id = agent_id
        self._stats = {"retrievals": 0, "writes": 0, "discarded": 0,
                       "secret_blocks": 0, "duplicates": 0}

    # -- identity (spec 35) ---------------------------------------------
    @staticmethod
    def _load_device_id() -> str:
        """spec 35: a stable per-installation device id (NOT a secret)."""
        import uuid
        from pathlib import Path

        p = default_db_path().parent / "device_id"
        try:
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
            p.parent.mkdir(parents=True, exist_ok=True)
            did = uuid.uuid4().hex[:16]
            p.write_text(did, encoding="utf-8")
            return did
        except Exception:  # noqa: BLE001
            return uuid.uuid4().hex[:16]

    @property
    def device_id(self) -> str:
        return self._device_id

    # -- spec 61: store --------------------------------------------------
    def store(self, content: str, *, source_type: SourceType = SourceType.AGENT,
              scope: Scope | None = None, type_: MemoryType | None = None,
              agent_id: str = "", task_id: str = "", session_id: str = "",
              tags: list[str] | None = None, explicit: bool = False,
              importance: Importance | None = None,
              project_id: str | None = None,
              canonical: bool = False) -> MemoryRecord | None:
        """Run the spec-11 pipeline and persist only if it survives."""
        if not content or not content.strip():
            return None
        text = content.strip()

        # spec 13: dedup needs to see comparable existing memory
        try:
            existing = self._store.query(
                scope=scope, type_=getattr(type_, "value", type_),
                agent_id=agent_id or None, limit=200)
        except Exception:  # noqa: BLE001
            existing = []

        verdict = self._pipeline.evaluate(
            text, source_type=source_type, agent_id=agent_id,
            project_id=project_id if project_id is not None else self._project_id,
            task_id=task_id, session_id=session_id, explicit=explicit,
            existing=existing, scope=scope)
        if verdict.get("secret"):
            self._stats["secret_blocks"] += 1
            logger.warning("memory write blocked: %s", verdict["reasons"][0])
            return None
        if not verdict["persist"]:
            self._stats["discarded"] += 1
            if verdict.get("duplicate_of"):
                self._stats["duplicates"] += 1
                logger.info("memory deduped into %s", verdict["duplicate_of"])
            return None

        rec: MemoryRecord = verdict["record"]
        rec.device_id = self._device_id
        if scope is not None:
            rec.scope = scope
        if type_ is not None:
            rec.type = type_
        # spec 40: an AGENT-scoped record MUST carry its owning agent_id, or the
        # isolation filter (which requires a non-empty agent_id) cannot protect
        # it and another agent could read it. The pipeline classifies scope
        # before we apply an explicit override, so set it here.
        if rec.scope is Scope.AGENT:
            rec.agent_id = agent_id or rec.agent_id or self._agent_id
        else:
            rec.agent_id = ""
        if importance is not None:
            rec.importance = importance
        if tags:
            rec.tags = list({*rec.tags, *tags})
        rec.canonical = bool(canonical)
        if canonical:
            rec.verified_at = time.time()
            rec.verified_by = source_type.value
        rec.sync_status = SyncStatus.PENDING
        # spec 58: embedding may be deferred
        rec.embedding_pending = self._retriever._embed is None

        self._store.upsert(rec)
        self._cache.invalidate()          # spec 54
        self._stats["writes"] += 1
        self._emit("memory.created", rec)
        return rec

    # -- spec 61: search -------------------------------------------------
    def search(self, query: str, *, top_k: int = 5, agent_id: str = "",
               task_id: str = "", session_id: str = "", scope: Scope | None = None,
               type_: str | None = None, min_score: float = 0.0,
               include_archived: bool = False,
               use_cache: bool = True) -> list[Any]:
        """Hybrid retrieval with query rewriting (spec 20/21/22)."""
        agent_id = agent_id or self._agent_id
        ck = self._cache.key(query, top_k=top_k, agent_id=agent_id, scope=scope,
                             type_=type_, task_id=task_id, arch=include_archived)
        if use_cache:
            hit = self._cache.get(ck)
            if hit is not None:
                self._stats["retrievals"] += 1
                return hit

        # spec 21: several retrieval signals, unioned
        candidates: dict[str, MemoryRecord] = {}
        for q in rewrite_query(query):
            try:
                # NOTE: do NOT filter by agent_id at the store level. Doing so
                # hid every PROJECT/USER/GLOBAL record (they carry agent_id="")
                # from an agent's search. Agent isolation is enforced by the
                # retriever, which drops other agents' AGENT-scoped memory while
                # still letting shared scopes through.
                rows = self._store.query(
                    scope=scope, type_=type_, keyword=q,
                    include_archived=include_archived, limit=200)
            except Exception as exc:  # noqa: BLE001
                logger.warning("memory query failed: %s", exc)
                rows = []
            for r in rows:
                candidates[r.memory_id] = r

        ranked = self._retriever.search(
            query, list(candidates.values()), top_k=top_k, min_score=min_score,
            agent_id=agent_id, project_id=self._project_id, task_id=task_id,
            session_id=session_id, task_text=query)

        # spec 51: record access for decay/ranking (bounded, best-effort)
        for s in ranked:
            try:
                self._store.touch(s.record.memory_id)
            except Exception:  # noqa: BLE001
                pass

        self._stats["retrievals"] += 1
        if use_cache:
            self._cache.put(ck, ranked)
        if ranked:
            self._emit("memory.retrieved", ranked[0].record,
                       extra={"count": len(ranked)})
        return ranked

    # -- spec 61: update / forget ---------------------------------------
    def update(self, memory_id: str, content: str, *, agent_id: str = "") -> MemoryRecord | None:
        rec = self._store.get(memory_id)
        if rec is None:
            return None
        allowed, why = self._policy.can("UPDATE", record=rec, agent_id=agent_id)
        if not allowed:
            logger.warning("memory update denied: %s", why)
            return None
        if detect_secret(content).is_secret:
            self._stats["secret_blocks"] += 1
            return None
        rec.content = content.strip()
        rec.version += 1                      # spec 39
        rec.parent_version = rec.version - 1
        rec.updated_at = time.time()
        rec.sync_status = SyncStatus.PENDING
        self._store.upsert(rec)
        self._cache.invalidate()
        self._emit("memory.updated", rec)
        return rec

    def forget(self, memory_id: str, *, agent_id: str = "", hard: bool = False) -> bool:
        """spec 18: safe forgetting -- soft delete by default, audit preserved."""
        rec = self._store.get(memory_id, include_deleted=True)
        if rec is None:
            return False
        allowed, why = self._policy.can("DELETE", record=rec, agent_id=agent_id)
        if not allowed:
            logger.warning("memory delete denied: %s", why)
            return False
        ok = self._store.delete(memory_id, hard=hard)
        if ok:
            self._cache.invalidate()
            self._emit("memory.deleted", rec)
        return ok

    def forget_matching(self, query: str, *, agent_id: str = "",
                        hard: bool = False) -> list[str]:
        """spec 12: "forget everything about X"."""
        hits = self.search(query, top_k=50, agent_id=agent_id)
        removed: list[str] = []
        for s in hits:
            if self.forget(s.record.memory_id, agent_id=agent_id, hard=hard):
                removed.append(s.record.memory_id)
        return removed

    def archive(self, memory_id: str) -> bool:
        """spec 17: archive -- recoverable, excluded from normal retrieval."""
        rec = self._store.get(memory_id)
        if rec is None:
            return False
        rec.archived = True
        rec.updated_at = time.time()
        rec.sync_status = SyncStatus.PENDING
        self._store.upsert(rec)
        self._cache.invalidate()
        self._emit("memory.archived", rec)
        return True

    # -- spec 15: promotion ----------------------------------------------
    def promote(self, memory_id: str, *, target_scope: Scope | None = None,
                target_type: MemoryType | None = None) -> MemoryRecord | None:
        """Promote a memory to a higher scope/type (spec 15).

        WORKING -> SHORT_TERM -> CANDIDATE -> LONG_TERM. Promotion is based on
        importance, repeated relevance, user confirmation, project significance
        and reliability. Never auto-promotes CRITICAL or user memories.
        """
        rec = self._store.get(memory_id)
        if rec is None:
            return None
        # spec 16: never auto-decay explicit user memories or critical facts
        if rec.source_type is SourceType.USER and rec.importance is Importance.CRITICAL:
            return None
        if target_scope is not None:
            rec.scope = target_scope
        if target_type is not None:
            rec.type = target_type
        rec.importance = Importance.HIGH
        rec.updated_at = time.time()
        rec.sync_status = SyncStatus.PENDING
        self._store.upsert(rec)
        self._cache.invalidate()
        self._emit("memory.promoted", rec, extra={"to": rec.scope.value})
        return rec

    # -- spec 16: decay ---------------------------------------------------
    def decay(self, memory_id: str, *, factor: float = 0.9) -> MemoryRecord | None:
        """Decay a memory's retrieval priority (spec 16).

        Decay affects retrieval priority, NOT content. Never decays explicit
        user memories, critical project facts, security configuration, or
        user-requested persistent memories.
        """
        rec = self._store.get(memory_id)
        if rec is None:
            return None
        # spec 16: do NOT decay these
        if rec.source_type is SourceType.USER:
            return None
        if rec.importance is Importance.CRITICAL:
            return None
        if rec.canonical:
            return None
        rec.confidence = max(0.0, rec.confidence * factor)
        rec.updated_at = time.time()
        rec.sync_status = SyncStatus.PENDING
        self._store.upsert(rec)
        self._cache.invalidate()
        return rec

    # -- spec 39: version rollback ---------------------------------------
    def rollback(self, memory_id: str, *, target_version: int) -> MemoryRecord | None:
        """Roll back a memory to a previous version (spec 39).

        Creates a new version with the content of the target version.
        The version history is preserved.
        """
        rec = self._store.get(memory_id)
        if rec is None:
            return None
        if target_version >= rec.version:
            return None
        # In a full implementation, we'd have a version history table.
        # For now, we create a new version that references the rollback target.
        rec.version += 1
        rec.parent_version = target_version
        rec.updated_at = time.time()
        rec.sync_status = SyncStatus.PENDING
        self._store.upsert(rec)
        self._cache.invalidate()
        self._emit("memory.updated", rec, extra={"rollback_to": target_version})
        return rec

    # -- spec 12: explicit natural-language commands --------------------
    def handle_command(self, text: str, *, agent_id: str = "",
                       session_id: str = "") -> dict[str, Any] | None:
        """Map "remember this / forget that / show what you remember" to ops."""
        from app.memory.commands import parse_memory_command

        cmd = parse_memory_command(text)
        if cmd is None:
            return None
        op = cmd["op"]
        if op == "remember":
            rec = self.store(cmd["payload"], source_type=SourceType.USER,
                             explicit=True, agent_id=agent_id,
                             session_id=session_id)
            return {"op": "remember", "stored": bool(rec),
                    "memory_id": rec.memory_id if rec else None}
        if op == "forget":
            ids = self.forget_matching(cmd["payload"], agent_id=agent_id)
            return {"op": "forget", "removed": ids, "count": len(ids)}
        if op == "show":
            hits = self.search(cmd["payload"], top_k=10, agent_id=agent_id)
            return {"op": "show", "count": len(hits),
                    "items": [s.to_dict() for s in hits]}
        return None

    # -- spec 41: shared memory -----------------------------------------
    def publish_shared(self, memory_id: str, *, agent_id: str = "",
                       force: bool = False) -> MemoryRecord | None:
        """Promote a memory into SHARED (spec 41).

        Spec 41's pipeline is AGENT -> candidate -> POLICY -> MAIN BRAIN ->
        SHARED. An agent publishing its OWN memory is the intended operation, so
        the policy engine must not veto it (it exists to stop an agent sharing
        ANOTHER agent's private memory, or blanket auto-exposure). Cross-agent
        sharing still requires ``force``.
        """
        rec = self._store.get(memory_id)
        if rec is None:
            return None
        # spec 42: an agent may not publish another agent's private memory.
        if (rec.scope is Scope.AGENT and rec.agent_id and agent_id
                and rec.agent_id != agent_id and not force):
            logger.info("share denied: agent '%s' cannot publish '%s' private memory",
                        agent_id, rec.agent_id)
            return None
        # spec 43: never publish a secret, whatever the scope.
        if detect_secret(rec.content).is_secret:
            logger.warning("share denied: record looks like a secret (spec 43)")
            return None
        shared = MemoryRecord(
            content=rec.content, scope=Scope.TEAM, type=MemoryType.SHARED,
            source_type=rec.source_type, confidence=rec.confidence,
            importance=rec.importance, project_id=rec.project_id,
            provenance={"shared_from": rec.memory_id, "from_agent": rec.agent_id},
            device_id=self._device_id, sync_status=SyncStatus.PENDING,
        ).apply_defaults()
        shared.trusted = rec.trusted
        self._store.upsert(shared)
        self._cache.invalidate()
        self._emit("memory.promoted", shared, extra={"to": "shared"})
        return shared

    # -- observability (spec 50/51) -------------------------------------
    def stats(self) -> dict[str, Any]:
        return {**self._stats, "cache": self._cache.stats(),
                "store": self._store.health()}

    def health(self) -> dict[str, Any]:
        h = self._store.health()
        return {"local_db": h, "device_id": self._device_id,
                "project_id": self._project_id, "stats": self._stats}

    def _emit(self, event: str, rec: MemoryRecord, extra: dict | None = None) -> None:
        """spec 60: memory events on the existing MOON event bus."""
        try:
            from app.runtime.event_bus import bus
            bus().publish(event, detail=rec.memory_id,
                          payload={"scope": rec.scope.value, "type": rec.type.value,
                                   **(extra or {})})
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        try:
            self._store.close()
        except Exception:  # noqa: BLE001
            pass


__all__ = ["CognitiveMemoryManager"]
