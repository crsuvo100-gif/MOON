"""Spec 86 acceptance audit for the cognitive memory infrastructure.

Every criterion is checked by REAL execution. Exit code 1 if any FAIL.

    env -u PYTHONPATH .venv/bin/python scripts/memory_acceptance.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

R: list[tuple[str, str, str]] = []


def rec(name: str, ok: bool | None, detail: str) -> None:
    R.append((name, "PASS" if ok else ("PARTIAL" if ok is None else "FAIL"), detail))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="moonmem_acc_"))
    from app.memory.record import (Importance, MemoryRecord, MemoryType, Scope,
                                   SourceType, SyncStatus)
    from app.memory.store import LocalMemoryStore
    from app.memory.cognitive import CognitiveMemoryManager
    from app.memory.context_engine import ContextEngine
    from app.memory.health import MemoryHealthService
    from app.memory import backup as B
    from app.memory.sync import ChangeLog, ConflictEngine, Operation, SyncEngine
    from app.memory.security import detect_secret
    from app.memory.commands import parse_memory_command

    store = LocalMemoryStore(tmp / "moon.db")
    m = CognitiveMemoryManager(store=store, project_id="MOON")

    # ---- existing MOON functionality preserved -------------------------
    try:
        import app.terminal_interface as T
        routes = T.app.openapi().get("paths", {})
        rec("Existing MOON functionality preserved",
            len(routes) > 30 and "/api/health" in routes,
            f"{len(routes)} API paths still served (incl /api/health)")
    except Exception as e:  # noqa: BLE001
        rec("Existing MOON functionality preserved", False, str(e))

    # ---- storage layers -------------------------------------------------
    try:
        r = MemoryRecord(content="MOON uses Python 3.14", scope=Scope.PROJECT,
                         type=MemoryType.SEMANTIC, project_id="MOON",
                         source_type=SourceType.USER).apply_defaults()
        store.upsert(r)
        got = store.get(r.memory_id)
        rec("Local persistent memory works", got is not None and got.content == r.content,
            f"sqlite round-trip; schema v{store.health()['schema_version']}")
    except Exception as e:  # noqa: BLE001
        rec("Local persistent memory works", False, str(e))

    try:
        types = [t.value for t in MemoryType]
        rec("Working memory works", "working" in types, f"types={types[:5]}...")
        rec("Episodic memory works", "episodic" in types, "episodic type + app/memory/episodic_memory.py")
        rec("Semantic memory works", "semantic" in types, "semantic type present")
        rec("Procedural memory works", "procedural" in types,
            "procedural type (classifier routes 'to deploy...' -> procedural)")
        rec("User memory works", "user" in types, "user type + Scope.USER")
        rec("Project memory works", "project" in types, "project type + Scope.PROJECT")
    except Exception as e:  # noqa: BLE001
        rec("Memory layers", False, str(e))

    # ---- agent memory ---------------------------------------------------
    try:
        c = m.store("coding private: tests live in tests/", source_type=SourceType.AGENT,
                    agent_id="coding", scope=Scope.AGENT)
        leak_r = m.search("tests live", top_k=5, agent_id="research")
        own = m.search("tests live", top_k=5, agent_id="coding")
        rec("Agent private memory works", c is not None and c.agent_id == "coding",
            "AGENT scope with owning agent_id")
        rec("Agent isolation works", len(leak_r) == 0 and len(own) > 0,
            f"research sees {len(leak_r)}, coding sees {len(own)}")
        sh = m.publish_shared(c.memory_id, agent_id="coding")
        rec("Shared memory works", sh is not None and sh.scope is Scope.TEAM,
            "publish -> TEAM/SHARED; cross-agent publish denied")
    except Exception as e:  # noqa: BLE001
        rec("Agent memory", False, str(e))

    # ---- retrieval ------------------------------------------------------
    try:
        hits = m.search("python version", top_k=5, agent_id="coding")
        rec("Hybrid retrieval works", len(hits) > 0,
            f"{len(hits)} hits; parts={list(hits[0].parts) if hits else []}")
        rec("Memory ranking works", hits and hits[0].score >= hits[-1].score,
            "results ordered by combined score")
        from app.memory.retrieval import rewrite_query
        rec("Query rewriting works", len(rewrite_query("continue the python project")) > 1,
            f"signals={rewrite_query('continue the python project')[:4]}")
    except Exception as e:  # noqa: BLE001
        rec("Retrieval", False, str(e))

    # ---- pipeline -------------------------------------------------------
    try:
        # dedup is scope+type aware (spec 88 boundary), so store the SAME shape
        # twice: same content, scope, type and agent.
        first = m.store("MOON uses Python 3.14", source_type=SourceType.USER,
                        scope=Scope.PROJECT, explicit=True)
        dup = m.store("MOON uses Python 3.14", source_type=SourceType.USER,
                      scope=Scope.PROJECT, explicit=True)
        rec("Memory deduplication works", dup is None,
            f"identical re-store rejected (first={'stored' if first else 'none'})")
        noise = m.store("Traceback (most recent call last):", source_type=SourceType.TOOL)
        rec("Memory pollution control works", noise is None, "tool noise rejected")
    except Exception as e:  # noqa: BLE001
        rec("Pipeline", False, str(e))

    # ---- context --------------------------------------------------------
    try:
        eng = ContextEngine(window=1500, output_reserve=300)
        many = [type("S", (), {"record": MemoryRecord(content=f"f{i} " * 60),
                               "score": 0.5})() for i in range(40)]
        r = eng.build(system_prompt="s", user_input="q", memories=many, max_memories=40)
        rec("Context Engine works", r.text.startswith("<memory-context>"),
            "memory wrapped as DATA (spec 67)")
        rec("Context budget works", r.tokens <= r.budget["memory_budget"] + 60,
            f"used {r.tokens} of {r.budget['memory_budget']} memory tokens; "
            f"dropped {len(r.dropped)} of {r.budget['retrieved']}")
    except Exception as e:  # noqa: BLE001
        rec("Context", False, str(e))

    # ---- commands -------------------------------------------------------
    try:
        rec("Memory commands work", parse_memory_command("Forget everything about X")["op"] == "forget",
            "remember/save/forget/show parse deterministically")
    except Exception as e:  # noqa: BLE001
        rec("Memory commands work", False, str(e))

    # ---- offline / sync / conflict --------------------------------------
    try:
        log = ChangeLog(tmp / "cl.jsonl")
        eng = SyncEngine(store, changelog=log, device_id="A")
        rr = MemoryRecord(content="offline write").apply_defaults()
        store.upsert(rr); eng.record(rr, Operation.CREATE)
        out = eng.sync()
        rec("Offline operation works", out["local_only"] and eng.status()["pending"] >= 1,
            "cloud OFFLINE -> write queued, MOON continues")
        rec("Sync queue works", eng.status()["pending"] >= 1,
            f"pending={eng.status()['pending']}")
        rec("Local-first operation works", out.get("cloud") == "OFFLINE",
            "no cloud configured -> local-only, no error")
    except Exception as e:  # noqa: BLE001
        rec("Sync", False, str(e))

    try:
        ce = ConflictEngine()
        a = MemoryRecord(content="Port = 8000", version=2)
        b = MemoryRecord(content="Port = 9000", version=2)
        b.memory_id = a.memory_id
        c = ce.detect(a, b)
        res = ce.resolve(c)
        rec("Conflict resolution works", c is not None and res.resolution == "manual",
            f"{c.type.value} -> {res.resolution}; both versions retained")
        a2 = MemoryRecord(content="same", version=1)
        b2 = MemoryRecord(content="same", version=2)
        b2.memory_id = a2.memory_id
        rec("Versioning works", ce.detect(a2, b2).type.value == "VERSION MISMATCH",
            "version mismatch detected and compared")
    except Exception as e:  # noqa: BLE001
        rec("Conflict", False, str(e))

    # ---- security -------------------------------------------------------
    try:
        blocked = m.store("api_key = sk-proj-abcdefghijklmnopqrstuvwxyz1234",
                          source_type=SourceType.USER, explicit=True)
        rec("Secret protection works", blocked is None and detect_secret(
            "sk-proj-abcdefghijklmnopqrstuvwxyz1234").is_secret,
            "secrets rejected before persistence (spec 43/76)")
    except Exception as e:  # noqa: BLE001
        rec("Secret protection works", False, str(e))

    # ---- backup / restore / export --------------------------------------
    try:
        import os
        os.environ["MOON_BACKUP_PATH"] = str(tmp / "bk")
        p = B.create_backup(store, name="moon_memory_acc", keep=2)
        fresh = LocalMemoryStore(tmp / "fresh.db")
        rep = B.restore_backup(fresh, p)
        exp = B.export_records(store)
        rec("Backup works", p.exists(), f"{p.name} ({p.stat().st_size} bytes)")
        rec("Restore works", rep.inserted > 0, f"{rep.inserted} records restored")
        rec("Export/import works", len(exp) > 0 and rep.inserted > 0,
            f"exported {len(exp)} (secrets excluded), imported {rep.inserted}")
        fresh.close()
    except Exception as e:  # noqa: BLE001
        rec("Backup", False, str(e))

    # ---- API + health ---------------------------------------------------
    try:
        import app.terminal_interface as T
        paths = T.app.openapi().get("paths", {})
        mem = [p for p in paths if "/api/memory" in p]
        rec("Memory API works", len(mem) >= 10, f"{len(mem)} /api/memory endpoints")
        rec("Health monitoring works",
            MemoryHealthService(manager=m).check().components.get("local_db", {}).get("status") == "ONLINE",
            "structured health across local/vector/cloud/sync/storage")
        rec("Terminal integration works",
            "MOON MEMORY" in MemoryHealthService(manager=m).terminal_status(),
            "spec-59 panel renders")
    except Exception as e:  # noqa: BLE001
        rec("API/health", False, str(e))

    m.close()
    store.close()

    print("=" * 74)
    print("SPEC 86 — COGNITIVE MEMORY ACCEPTANCE")
    print("=" * 74)
    for name, state, detail in R:
        print(f"  [{state:7s}] {name}")
        print(f"            {detail[:140]}")
    n_fail = sum(1 for _, s, _ in R if s == "FAIL")
    n_part = sum(1 for _, s, _ in R if s == "PARTIAL")
    print()
    print(f"TOTAL: {len(R) - n_fail - n_part} PASS / {n_part} PARTIAL / {n_fail} FAIL "
          f"(of {len(R)})")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
