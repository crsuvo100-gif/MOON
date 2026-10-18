"""Cyclone REST router -- the Cyclone API contract, implemented as a FastAPI router.

Mirrors the Cyclone Node server (``server.js``) surface, with two bridges into
MOON on the same process:

  * ``POST /api/ai``  -> low-latency single-call brain via
                          ``Orchestrator.quick_reply`` (chat/WS/voice path).
  * ``GET /v1/chat/completions`` -> OpenAI-compatible completion shim that
                          reuses the same brain.

Every file/state endpoint works on Cyclone's own tree
(``CYCLONE_TERMINAL_AI_V10/.data``) so Cyclone stays self-contained and
independent of MOON's repo, while the browser still points at MOON
(``/cyclone/api``) through ``cyclone/config.js``.

Run Cyclone standalone (Node) on port 8778:  node server.js
Host it inside MOON:  app/terminal_interface.py mounts it at /cyclone
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from .config import (
    CYCLONE_DIR,
    DATA_DIR,
    DEFAULT_PROVIDERS,
    PROVIDERS_FILE,
    SNAPSHOTS_DIR,
    STATE_FILE,
    BINDINGS_FILE,
    WORKFLOWS_FILE,
    _load_json,
    _save_json,
)
from .state import StateStore

router = APIRouter()


# --------------------------------------------------------------------------
# small utilities
# --------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_rel(path: str) -> Path:
    """Normalise a caller-supplied relative path inside CYCLONE_DIR."""
    p = Path(path).expanduser()
    if p.is_absolute() or ".." in p.parts:
        raise HTTPException(status_code=400, detail="path must stay inside the Cyclone tree")
    return p.resolve()


def _read_state() -> dict:
    try:
        return StateStore.load(STATE_FILE)
    except Exception:
        return {"version": 1, "created": _now(), "memories": [], "history": {}}


def _store_state(state: dict) -> None:
    _save_json(STATE_FILE, state)


def _default_providers() -> list:
    # Prefer MOON's model when the brain is reachable, else the local defaults.
    try:
        from app.config.settings import settings  # type: ignore
        if getattr(settings, "default_provider", None):
            p = {"name": settings.default_provider,
                 "model": settings.model or "qwen3.5:8b",
                 "base_url": settings.ollama_url or settings.model_provider.get("base_url", "http://127.0.0.1:11434/v1"),
                 "type": "ollama", "default": True}
            return [p]
    except Exception:
        pass
    return list(DEFAULT_PROVIDERS)


# --------------------------------------------------------------------------
# Cyclone API surface (mirrors Cyclone Node server)
# --------------------------------------------------------------------------

@router.get("/api/health")
async def cyclone_health(request: Request):
    """Alive probe the browser pane calls on page load."""
    st = _read_state()
    return JSONResponse({
        "status": "ok",
        "cyclone": "3.0.0",
        "tree": CYCLONE_DIR,
        "backend": "alive",
    })


@router.get("/api/persistence")
async def cyclone_persistence(request: Request):
    """Persisted brain state: running states + captured memories + history."""
    st = _read_state()
    return JSONResponse({
        "state_version": st.get("version", 1),
        "created": st.get("created", _now()),
        "memories": st.get("memories", []),
        "history": st.get("history", {}),
        "store_file": STATE_FILE,
    })


@router.get("/api/fs")
async def cyclone_fs(request: Request):
    """List a directory inside the Cyclone tree."""
    path = request.query_params.get("path", ".")
    try:
        p = _safe_rel(path)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="bad path")
    if not p.is_dir():
        raise HTTPException(status_code=404, detail=f"not a directory: {path}")
    entries = []
    for child in sorted(p.iterdir()):
        st = child.stat()
        entries.append({
            "name": child.name,
            "path": str(child.relative_to(CYCLONE_DIR)),
            "type": "dir" if child.is_dir() else "file",
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    return JSONResponse({"entries": entries, "dir": str(path)})


@router.get("/api/read")
async def cyclone_read(request: Request):
    """Read a file (text, capped)."""
    path = request.query_params.get("path", "")
    try:
        p = _safe_rel(path)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="bad path")
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"not found: {path}")
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse({"content": text[:1_000_000], "path": str(p.relative_to(CYCLONE_DIR))})


@router.get("/api/search")
async def cyclone_search(request: Request):
    """Grep filename + content across the Cyclone tree (case-insensitive)."""
    query = (request.query_params.get("q") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="q required")
    qp = re.compile(re.escape(query), re.IGNORECASE)
    hits = []
    for dirpath, dirnames, filenames in os.walk(CYCLONE_DIR):
        dirnames[:] = [d for d in dirnames if d not in (".data", ".git", "node_modules")]
        for name in filenames:
            full = Path(dirpath) / name
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = ""
            if qp.search(name) or qp.search(text):
                hits.append({"path": str(full.relative_to(CYCLONE_DIR)),
                             "name": name})
                if len(hits) >= 200:
                    break
        if len(hits) >= 200:
            break
    return JSONResponse({"query": query, "matches": hits})


@router.get("/api/providers")
async def cyclone_providers_get():
    """List Cyclone AI providers (reflects MOON's model when the brain is up)."""
    return JSONResponse({"providers": _default_providers()})


@router.post("/api/providers")
async def cyclone_providers_post(req: dict = Body(...)):
    providers = _default_providers()
    name = (req.get("name") or "").strip()
    model = (req.get("model") or "").strip()
    base_url = (req.get("base_url") or "http://127.0.0.1:11434/v1").strip()
    prov = {"name": name or f"cyc-{_now()}", "type": "ollama",
            "model": model or "qwen3.5:8b", "base_url": base_url, "default": bool(name)}
    if prov.get("default"):
        providers = [prov]
    _save_json(PROVIDERS_FILE, providers)
    return JSONResponse({"ok": True, "providers": providers})


@router.get("/api/agent-bindings")
async def cyclone_bindings_get():
    return JSONResponse({"bindings": _load_json(BINDINGS_FILE, {})})


@router.post("/api/agent-bindings")
async def cyclone_bindings_post(req: dict = Body(...)):
    key = (req.get("name") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="name required")
    bindings = _load_json(BINDINGS_FILE, {})
    bindings[key] = {"agent": (req.get("agent") or "default"),
                     "model": (req.get("model") or ""), "created": _now(),
                     "params": {k: v for k, v in req.items() if k not in ("name", "agent", "model")}}
    _save_json(BINDINGS_FILE, bindings)
    return JSONResponse({"ok": True, "bindings": bindings})


@router.post("/api/agents")
async def cyclone_agents_post(req: dict = Body(...)):
    """Register (and immediately run) a Cyclone agent binding."""
    name = (req.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    bindings = _load_json(BINDINGS_FILE, {})
    bindings[name] = {"agent": req.get("agent", "default"),
                      "model": req.get("model", ""),
                      "created": _now(),
                      "params": {k: v for k, v in req.items() if k not in ("name", "agent", "model")}}
    _save_json(BINDINGS_FILE, bindings)
    return JSONResponse({"ok": True, "agent": name, "registered": True,
                         "bindings": bindings})


@router.get("/api/workflows")
async def cyclone_workflows_get():
    return JSONResponse({"workflows": _load_json(WORKFLOWS_FILE, {})})


@router.post("/api/workflows")
async def cyclone_workflows_post(req: dict = Body(...)):
    key = (req.get("name") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="name required")
    workflows = _load_json(WORKFLOWS_FILE, {})
    workflows[key] = {"steps": req.get("steps", []), "created": _now(),
                      "params": {k: v for k, v in req.items() if k not in ("name", "steps")}}
    _save_json(WORKFLOWS_FILE, workflows)
    return JSONResponse({"ok": True, "workflow": key, "registered": True})


@router.post("/api/diff")
async def cyclone_diff(req: dict = Body(...)):
    """Unified diff between two files (or a file vs. its Cyclone snapshot)."""
    a = (req.get("a") or "").strip()
    b = (req.get("b") or "").strip()
    if a and b:
        def _load(p):
            try:
                return Path(p).read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            except Exception:
                return []
        left = _load(a) or []
        right = _load(b) or []
        diff = list(difflib.unified_diff(left, right, fromfile=a, tofile=b, lineterm=""))
        return JSONResponse({"diff": "".join(diff) or "(identical)"})
    # path vs. its Cyclone snapshot
    path = (req.get("path") or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="a+b or path required")
    p = _safe_rel(path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"not a file: {path}")
    snaps = sorted(SNAPSHOTS_DIR.glob("*.json")) if SNAPSHOTS_DIR.exists() else []
    if not snaps:
        return JSONResponse({"diff": "(no baseline snapshot saved yet)"})
    base = snaps[-1].stem
    current = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    snap_state = _load_json(snaps[-1], {})
    snap_content = snap_state.get("content", "")
    if not isinstance(snap_content, str):
        snap_content = ""
    old = snap_content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old, current, fromfile=f"snapshot:{base}", tofile=path, lineterm=""))
    return JSONResponse({"diff": "".join(diff) or "(identical to snapshot)"})


@router.get("/api/rollback")
async def cyclone_rollback_list():
    snaps = sorted(SNAPSHOTS_DIR.glob("*.json")) if SNAPSHOTS_DIR.exists() else []
    lst = []
    for s in snaps:
        sd = _load_json(s, {})
        lst.append({"backupId": s.stem,
                    "file": sd.get("path", ""),
                    "size": sd.get("size", 0),
                    "ts": sd.get("ts", _now()),
                    "sha256": sd.get("sha256", "")})
    return JSONResponse({"snapshots": lst})


@router.post("/api/rollback")
async def cyclone_rollback(req: dict = Body(...)):
    """Restore a Cyclone file snapshot over the current file."""
    backup = (req.get("backupId") or "").strip()
    snaps = sorted(SNAPSHOTS_DIR.glob("*.json")) if SNAPSHOTS_DIR.exists() else []
    target = None
    for s in snaps:
        if s.stem == backup:
            target = s
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"no snapshot {backup!r}")
    snap = _load_json(target, {})
    src = Path(snap.get("path", ""))
    if not src.is_file():
        raise HTTPException(status_code=404, detail="snapshot target missing")
    dst = _safe_rel(snap.get("rel", "")).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    return JSONResponse({"ok": True, "restored": str(dst.relative_to(CYCLONE_DIR))})


@router.post("/api/write")
async def cyclone_write(req: dict = Body(...)):
    """Write a file into the Cyclone tree; save a rollback snapshot first."""
    path = (req.get("path") or "").strip()
    content = req.get("content")
    if not path:
        raise HTTPException(status_code=400, detail="path required")
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="content must be a string")
    p = _safe_rel(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    snap = {
        "path": str(p), "rel": str(p.relative_to(CYCLONE_DIR)),
        "content": content, "size": len(content.encode("utf-8")),
        "ts": _now(), "sha256": _sha256(content),
        "ended": _now(),
    }
    _save_json(SNAPSHOTS_DIR / f"{_now().replace(':','').replace('T','')}_{p.name}.json", snap)
    return JSONResponse({"ok": True, "path": str(p.relative_to(CYCLONE_DIR)),
                         "bytes": len(content.encode("utf-8")), "snapshot": True})


@router.post("/api/ai")
async def cyclone_ai(req: dict = Body(...)):
    """MOON-brain single-call reply (the core of Cyclone inside MOON)."""
    message = (req.get("message") or "").strip()
    voice = bool(req.get("voice", False))
    memory = req.get("memory") or None
    context = req.get("context") or None
    if not message:
        return JSONResponse({"ok": True, "reply": "", "voice": voice})
    text = ""
    used = None
    try:
        orch = get_orchestrator()
        if orch is not None and hasattr(orch, "quick_reply"):
            used = "orch.quick_reply"
            res = await orch.quick_reply(None, message, context=context, memory=memory, voice=voice)
            text = res if isinstance(res, str) else ""
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    if not text:
        text = f"[CYCLONE: no MOON brain reachable] quick_reply used={used}"
    return JSONResponse({"ok": True, "reply": text, "voice": voice,
                         "tts_bytes": len(text.encode("utf-8")) if isinstance(text, str) else 0})


@router.post("/v1/chat/completions")
async def cyclone_v1_chat_completions(req: dict = Body(...)):
    """OpenAI-compatible completion shim (best-effort) reusing Cyclone's brain."""
    messages = req.get("messages") or []
    model = req.get("model") or "cyclone-3.0"
    text = ""
    if messages:
        text = (messages[-1].get("content") or "").strip()
    orch = get_orchestrator()
    used = None
    if orch is not None and hasattr(orch, "quick_reply"):
        try:
            used = "orch.quick_reply"
            res = await orch.quick_reply(None, text or "(open-ai compat message)")
            text = res if isinstance(res, str) else ""
        except Exception:
            pass
    if not text:
        text = "(no MOON brain reachable)"
    return {
        "id": f"chatcmpl-cyclone-{int(time.time()*1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


# --------------------------------------------------------------------------
# router factory
# --------------------------------------------------------------------------

def get_cyclone_router():
    """Build and return the Cyclone APIRouter (mounts fresh every call)."""
    return router


def get_cyclone_static_files():
    """Starlette StaticFiles mount serving the Cyclone UI tree."""
    from .static import get_cyclone_static_files as _g
    return _g()
