"""Memory API router (spec 29, 30, 45, 51).

Mounts the cognitive memory surface on MOON's EXISTING FastAPI app
(app/terminal_interface.py) rather than starting a second server -- spec 1 says
reuse the existing infrastructure.

Security model (spec 29/45):
  * spec 29: the cloud/DB credentials are never exposed to clients. The API
    returns memory records only; connection strings stay server-side.
  * spec 30: create / read / update / search / delete / sync / health /
    export.
  * spec 51: retrieval counts and latencies are reported; memory CONTENT is
    never written to logs.

The router is intentionally thin: it delegates to CognitiveMemoryManager.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"])

# A single lazily-created cognitive manager per process.
_MANAGER: Any = None


def _get_manager() -> Any:
    """Lazily build the cognitive manager (keeps startup cheap, spec 52)."""
    global _MANAGER
    if _MANAGER is None:
        from app.memory.cognitive import CognitiveMemoryManager

        _MANAGER = CognitiveMemoryManager()
    return _MANAGER


def set_manager(mgr: Any) -> None:
    """Allow the orchestrator to inject its instance (spec 62)."""
    global _MANAGER
    _MANAGER = mgr


def _err(msg: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=code)


@router.get("/health")
async def memory_health() -> JSONResponse:
    """spec 50: structured memory health."""
    try:
        from app.memory.health import MemoryHealthService

        m = _get_manager()
        rep = MemoryHealthService(manager=m).check()
        return JSONResponse(rep.to_dict())
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory health failed: %s", exc)
        return _err(str(exc), 500)


@router.get("/status")
async def memory_status() -> JSONResponse:
    """spec 59: the terminal panel payload."""
    try:
        from app.memory.health import MemoryHealthService

        m = _get_manager()
        svc = MemoryHealthService(manager=m)
        return JSONResponse({"panel": svc.terminal_status(),
                             "health": svc.check().to_dict(),
                             "stats": m.stats()})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@router.post("/search")
async def memory_search(request: Request) -> JSONResponse:
    """spec 30/20: hybrid retrieval."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _err("invalid JSON body")
    query = str((body or {}).get("query", "")).strip()
    if not query:
        return _err("query is required")
    t0 = time.perf_counter()
    try:
        hits = _get_manager().search(
            query, top_k=int(body.get("top_k", 5)),
            agent_id=str(body.get("agent_id", "") or ""),
            task_id=str(body.get("task_id", "") or ""),
            session_id=str(body.get("session_id", "") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory search failed: %s", exc)
        return _err(str(exc), 500)
    return JSONResponse({
        "query": query, "count": len(hits),
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        "results": [s.to_dict() for s in hits],
    })


@router.post("/store")
async def memory_store(request: Request) -> JSONResponse:
    """spec 30/61: create a memory through the candidate pipeline."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _err("invalid JSON body")
    content = str((body or {}).get("content", "")).strip()
    if not content:
        return _err("content is required")
    try:
        from app.memory.record import Scope, SourceType

        def _enum(name: str, cls: Any, default: Any) -> Any:
            raw = (body or {}).get(name)
            if not raw:
                return default
            try:
                return cls(str(raw).upper())
            except Exception:  # noqa: BLE001
                return default

        rec = _get_manager().store(
            content,
            source_type=_enum("source_type", SourceType, SourceType.USER),
            scope=_enum("scope", Scope, None),
            agent_id=str(body.get("agent_id", "") or ""),
            task_id=str(body.get("task_id", "") or ""),
            session_id=str(body.get("session_id", "") or ""),
            tags=list(body.get("tags") or []),
            explicit=bool(body.get("explicit", False)),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory store failed: %s", exc)
        return _err(str(exc), 500)
    if rec is None:
        # Not an error: the pipeline legitimately discards noise/dupes/secrets.
        return JSONResponse({"stored": False,
                             "reason": "rejected by the memory pipeline "
                                       "(noise, duplicate, or secret)"},
                            status_code=200)
    return JSONResponse({"stored": True, "memory_id": rec.memory_id,
                         "scope": rec.scope.value, "type": rec.type.value,
                         "importance": rec.importance.value,
                         "confidence": rec.confidence})


@router.get("/{memory_id}")
async def memory_get(memory_id: str) -> JSONResponse:
    """spec 30: read one record."""
    try:
        rec = _get_manager()._store.get(memory_id)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)
    if rec is None:
        return _err("not found", 404)
    return JSONResponse(rec.to_dict())


@router.post("/{memory_id}/update")
async def memory_update(memory_id: str, request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _err("invalid JSON body")
    content = str((body or {}).get("content", "")).strip()
    if not content:
        return _err("content is required")
    rec = _get_manager().update(memory_id, content,
                                agent_id=str(body.get("agent_id", "") or ""))
    if rec is None:
        return _err("not found or not permitted", 404)
    return JSONResponse({"updated": True, "version": rec.version})


@router.delete("/{memory_id}")
async def memory_delete(memory_id: str, hard: bool = False) -> JSONResponse:
    """spec 18: soft delete by default."""
    ok = _get_manager().forget(memory_id, hard=hard)
    return JSONResponse({"deleted": ok, "hard": hard},
                        status_code=200 if ok else 404)


@router.post("/forget")
async def memory_forget(request: Request) -> JSONResponse:
    """spec 12: "forget everything about X"."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _err("invalid JSON body")
    query = str((body or {}).get("query", "")).strip()
    if not query:
        return _err("query is required")
    ids = _get_manager().forget_matching(query)
    return JSONResponse({"removed": ids, "count": len(ids)})


@router.post("/command")
async def memory_command(request: Request) -> JSONResponse:
    """spec 12: deterministic NL command handling."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _err("invalid JSON body")
    text = str((body or {}).get("text", "")).strip()
    if not text:
        return _err("text is required")
    out = _get_manager().handle_command(
        text, agent_id=str(body.get("agent_id", "") or ""),
        session_id=str(body.get("session_id", "") or ""))
    if out is None:
        return JSONResponse({"command": None, "note": "not a memory command"})
    return JSONResponse(out)


@router.post("/share")
async def memory_share(request: Request) -> JSONResponse:
    """spec 41: publish an agent memory into shared memory."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _err("invalid JSON body")
    mid = str((body or {}).get("memory_id", "")).strip()
    if not mid:
        return _err("memory_id is required")
    rec = _get_manager().publish_shared(
        mid, agent_id=str(body.get("agent_id", "") or ""))
    if rec is None:
        return _err("not found, not permitted, or looks like a secret", 403)
    return JSONResponse({"shared": True, "memory_id": rec.memory_id,
                         "scope": rec.scope.value})


@router.get("/sync/status")
async def sync_status() -> JSONResponse:
    """spec 32/59: sync queue state (local-first; cloud optional)."""
    try:
        m = _get_manager()
        pending = m._store.count(sync_status="PENDING")
        return JSONResponse({"pending": pending,
                             "status": "SYNCED" if pending == 0 else "PENDING",
                             "cloud": "not configured"})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@router.get("/export")
async def memory_export(limit: int = 0) -> JSONResponse:
    """spec 48: portable export (secrets always excluded)."""
    try:
        from app.memory.backup import export_records

        recs = export_records(_get_manager()._store, limit=limit)
        return JSONResponse({"count": len(recs), "records": recs})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@router.post("/backup")
async def memory_backup(request: Request) -> JSONResponse:
    """spec 46/47: create a rotated backup."""
    try:
        from app.memory.backup import create_backup

        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        p = create_backup(_get_manager()._store,
                          keep=int((body or {}).get("keep", 7)))
        return JSONResponse({"created": True, "path": str(p),
                             "size_bytes": p.stat().st_size})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@router.get("/backups")
async def memory_backups() -> JSONResponse:
    from app.memory.backup import list_backups

    return JSONResponse({"backups": list_backups()})


__all__ = ["router", "set_manager", "_get_manager"]
