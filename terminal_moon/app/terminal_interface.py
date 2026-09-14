"""
Terminal interface — FastAPI + WebSocket backend for MOON Terminal.

Run: uvicorn app.terminal_interface:app --port 8777 --host 127.0.0.1
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.config.settings import get_settings
from app.config.logging import get_logger
from app.brain.orchestrator import Orchestrator, Task
from app.brain.lock import SessionLock
from app.brain.intent_detector import detect_intent
from app.brain.tool_manager import ToolManager
from app.runtime.event_bus import bus, EventType, Event
from app.services.llm_service import ChatMessage
from app.services.embedding_service import EmbeddingService
from app.memory.short_term import ShortTermMemory
from app.memory.long_term import LongTermMemory
from app.memory.episodic_memory import EpisodicMemory
from app.memory.vector_db import InMemoryVectorStore
from app.memory.knowledge_base import KnowledgeBase
from app.memory.conversation_history import ConversationHistory
from app.tools.base import ToolRegistry
from app.tools.registry import ToolRegistry as TR


logger = get_logger("moontm.terminal")
# _get_orchestrator is defined below as an async function

# ── app ────────────────────────────────────────────────────────────────────
app = FastAPI(title="MOON Terminal", version="1.0.0")

# ── settings + auth ────────────────────────────────────────────────────────
TDEFAULTS = {
    "host": "127.0.0.1",
    "port": 8777,
    "autostart": True,
    "auto_voice": True,
    "idle_speed": 0.5,
}


def _load_settings() -> dict:
    s = get_settings()
    return {
        "host": s.host,
        "port": s.port,
        "autostart": s.autostart,
        "auto_voice": s.auto_voice,
        "idle_speed": s.idle_speed,
    }


TERMINAL_TOKEN = os.environ.get("MOON_TERMINAL_TOKEN", get_settings().terminal_access_token or "")


def _token_ok(request: Optional[Request] = None, headers: Optional[dict] = None) -> bool:
    if not TERMINAL_TOKEN:
        return True  # local-only default
    hdr = None
    if request:
        hdr = request.headers.get("Authorization", "")
    elif headers:
        hdr = headers.get("Authorization", "")
    if not hdr.startswith("Bearer "):
        return False
    return hdr.split("Bearer ", 1)[1] == TERMINAL_TOKEN


# ── orchestrator lazy singleton ────────────────────────────────────────────
_OR_CH = None
_ORCH_LOCK = asyncio.Lock()
_ORCH_SETUP = False


async def _get_orchestrator() -> Orchestrator:
    if _OR_CH is None:
        async with _ORCH_LOCK:
            if _OR_CH is None:
                settings = get_settings()
                _OR_CH = Orchestrator(settings, lock_state_file=settings.lock_state_path)
                await _OR_CH.setup()
                _ORCH_SETUP = True
                logger.info("Orchestrator initialized for terminal backend")
    return _OR_CH


# ── telemetry + logs + events ring buffers ────────────────────────────────
_TELEM = deque(maxlen=240)
_LOG_BUF = deque(maxlen=400)
_EVENTS = deque(maxlen=200)
_LOG_FILE = Path("logs") / "moontm.log"
_LOG_SUBSCRIBERS: list[Callable[[str], None]] = []


def _push_telemetry(orch: Orchestrator) -> None:
    """Read /proc metrics (Linux)."""
    cpu = 0.0
    ram_pct = 0.0
    net_rx, net_tx = 0, 0
    temp = 0.0
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            cpu = float(parts[0]) if parts else 0.0
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        total = ram = 0
        for line in lines:
            if line.startswith("MemTotal:"):
                total = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                ram = int(line.split()[1])
        ram_pct = round((1 - ram / total) * 100, 1) if total else 0.0
    except Exception:
        pass
    try:
        with open("/proc/net/dev") as f:
            lines = f.readlines()[2:]
            for line in lines:
                parts = line.split()
                if parts and parts[0].startswith("eth") or parts[0] == "lo":
                    net_rx = int(parts[1]) if len(parts) > 1 else 0
                    net_tx = int(parts[9]) if len(parts) > 9 else 0
                    break
    except Exception:
        pass
    try:
        zones = list(Path("/sys/class/thermal/thermal_zone*").glob("*"))
        for z in zones:
            tfile = z / "temp"
            if tfile.exists():
                try:
                    temp = int(tfile.read_text().strip()) / 1000.0
                    break
                except Exception:
                    pass
    except Exception:
        pass

    _TELEM.append({
        "timestamp": datetime.now().isoformat(),
        "cpu": cpu,
        "ram_pct": ram_pct,
        "net_rx": net_rx,
        "net_tx": net_tx,
        "temp_c": round(temp, 1),
    })


def _log(msg: str, sev: str = "INFO") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{sev}] {msg}"
    _LOG_BUF.append(line)
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    for fn in _LOG_SUBSCRIBERS:
        try:
            fn(line)
        except Exception:
            pass
    _emit_event("log", msg[:200], sev=sev)


def _emit_event(kind: str, detail: str, sev: str = "normal",
                aspect: Optional[str] = None, agent_id: str = "") -> None:
    """Append to _EVENTS ring buffer."""
    _EVENTS.append({
        "type": kind,
        "detail": detail,
        "severity": sev,
        "aspect": aspect or kind,
        "agent_id": agent_id,
        "timestamp": datetime.now().isoformat(),
    })


def _telemetry_snapshot(orch: Orchestrator) -> dict:
    _push_telemetry(orch)
    return {
        "series": list(_TELEM),
        "current": _TELEM[-1] if _TELEM else {},
        "logs": list(_LOG_BUF)[-50:],
    }


# ── voice helpers ───────────────────────────────────────────────────────────
_VOICE_ENGINE: Optional[Any] = None
_VOICE_MUTED = False
_STOP_REQUESTED = False
_LAST_ERROR = False


def _get_voice_engine():
    global _VOICE_ENGINE
    if _VOICE_ENGINE is None:
        try:
            from app.voice_engine import VoiceEngine
            _VOICE_ENGINE = VoiceEngine(get_settings())
        except Exception as exc:
            logger.warning("Voice engine init failed: %s", exc)
            _VOICE_ENGINE = None
    return _VOICE_ENGINE


async def _speak(text: str, lang: Optional[str] = None) -> Optional[str]:
    if _VOICE_MUTED:
        return None
    ve = _get_voice_engine()
    if not ve:
        return None
    try:
        return await ve.speak(text, lang)
    except Exception as exc:
        logger.warning("Speak failed: %s", exc)
        return None


def _moon_status_impl(orch: Orchestrator) -> dict:
    """Real status payload from orchestrator."""
    try:
        agent_cards = orch._agents if hasattr(orch, '_agents') else {}
        agent_count = len(agent_cards)
        agent_names = list(agent_cards.keys())[:20]

        tool_names = list(orch._tool_registry.tool_names) if orch._tool_registry else []
        tool_count = len(tool_names)

        stm = orch._memory._stm if orch._memory and hasattr(orch._memory, '_stm') else None
        ltm_count = 0
        kb_count = 0
        episodic_count = 0
        if orch._memory:
            episodic_count = len(orch._memory._episodic._episodes) if hasattr(orch._memory._episodic, '_episodes') else 0
            kb_count = len(orch._memory._kb) if hasattr(orch._memory, '_kb') else 0
            if orch._memory._ltm._path.exists():
                with open(orch._memory._ltm._path, "r", encoding="utf-8") as f:
                    ltm_count = sum(1 for _ in f)

        stm_len = len(stm) if stm else 0

        voice = _get_voice_engine()
        voice_mode = "MUTED" if _VOICE_MUTED else "AUTO"
        voice_available = bool(voice)
        auto_voice = get_settings().auto_voice

        # system metrics
        cpu = 0.0
        ram_pct = 0.0
        try:
            with open("/proc/loadavg") as f:
                cpu = float(f.read().split()[0])
        except Exception:
            pass
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            total = ram = 0
            for line in lines:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    ram = int(line.split()[1])
            ram_pct = round((1 - ram / total) * 100, 1) if total else 0.0
        except Exception:
            pass

        # emotion
        emotion = "calm" if orch._lock.locked else "engaged"

        pipeline = [
            {"stage": "INPUT", "active": True},
            {"stage": "MEMORY", "active": episodic_count > 0 or ltm_count > 0},
            {"stage": "KNOWLEDGE", "active": kb_count > 0},
            {"stage": "REASONING", "active": True},
            {"stage": "PLANNER", "active": True},
            {"stage": "TOOLS", "active": tool_count > 0},
            {"stage": "EXECUTION", "active": True},
            {"stage": "VERIFY", "active": True},
        ]

        return {
            "agents": {
                "count": agent_count,
                "names": agent_names,
            },
            "tools": {
                "count": tool_count,
                "names": tool_names[:30],
            },
            "memory": {
                "episodic": episodic_count,
                "ltm_lines": ltm_count,
                "stm": stm_len,
                "kb_chunks": kb_count,
            },
            "pipeline": pipeline,
            "system": {
                "cpu_load": cpu,
                "ram_pct": ram_pct,
            },
            "voice": {
                "mode": voice_mode,
                "available": voice_available,
                "auto_voice": auto_voice,
            },
            "sensors": {
                "voice": voice_available,
                "text": True,
                "vision": False,
                "file": True,
                "system": True,
            },
            "emotion": emotion,
            "locked": orch._lock.locked,
            "uptime_s": int(time.time()) - int(_START_TIME),
            "session_id": "main",
        }
    except Exception as exc:
        logger.exception("Status build error: %s", exc)
        return {"error": str(exc)}


_START_TIME = time.time()


def _moon_status_sync(orch: Orchestrator) -> dict:
    """Sync wrapper for status (used in REST endpoints)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            return concurrent.futures.ThreadPoolExecutor().submit(lambda: _moon_status_impl(orch)).result(timeout=5)
        return _moon_status_impl(orch)
    except Exception:
        return {"error": "status unavailable"}


def _run_diagnostics(orch: Orchestrator) -> dict:
    checks = []

    # LLM
    try:
        if orch._llm:
            checks.append({"name": "llm_main", "state": "PASS",
                           "detail": f"{orch._settings.model_name} @ {orch._settings.model_base_url}"})
        else:
            checks.append({"name": "llm_main", "state": "FAIL", "detail": "not initialized"})
    except Exception as exc:
        checks.append({"name": "llm_main", "state": "WARN", "detail": str(exc)[:100]})

    # memory
    try:
        if orch._memory:
            checks.append({"name": "memory", "state": "PASS",
                           "detail": f"stm={len(orch._memory._stm)}, ltm_lines={ltm_lines()}",
                           })
        else:
            checks.append({"name": "memory", "state": "FAIL", "detail": "not initialized"})
    except Exception:
        checks.append({"name": "memory", "state": "WARN", "detail": "check failed"})

    # voice
    try:
        ve = _get_voice_engine()
        if ve:
            st = ve.backend_status()
            checks.append({"name": "voice", "state": "PASS",
                           "detail": f"current={ve.current_voice()}, backends={st}"})
        else:
            checks.append({"name": "voice", "state": "WARN", "detail": "engine not init"})
    except Exception as exc:
        checks.append({"name": "voice", "state": "WARN", "detail": str(exc)[:100]})

    # lock
    try:
        state = "LOCKED" if orch._lock.locked else "UNLOCKED"
        checks.append({"name": "session_lock", "state": "PASS", "detail": state})
    except Exception:
        checks.append({"name": "session_lock", "state": "WARN", "detail": "check failed"})

    summary = "HEALTHY" if all(c["state"] != "FAIL" for c in checks) else "DEGRADED"
    if any(c["state"] == "FAIL" for c in checks):
        summary = "FAILED"
    return {"checks": checks, "summary": summary}


def _shell_dispatch(cmd: str) -> tuple[str, int]:
    """Allow-listed shell dispatch."""
    _SHELL_ALLOW = {
        "status": "echo 'status OK'",
        "ps": "ps aux --sort=-%mem | head -20",
        "top": "top -bn1 | head -25",
        "df": "df -h",
        "free": "free -h",
        "uname": "uname -a",
        "uptime": "uptime",
        "netstat": "netstat -tulpn 2>/dev/null || ss -tulpn",
        "ifconfig": "ifconfig 2>/dev/null || ip addr",
        "ip": "ip addr",
        "ls": "ls -la",
        "pwd": "pwd",
        "date": "date",
        "whoami": "whoami",
        "env": "env",
        "nproc": "nproc",
    }
    cmd = cmd.strip()
    if cmd.startswith("echo "):
        return " ".join(cmd.split()[1:]), 0
    if cmd.startswith("cat "):
        rest = cmd[4:].strip()
        if any(c in rest for c in '>|&;$`\\'):
            return "[cat] forbidden characters", 1
        if rest.startswith("/") or rest.startswith("..") or rest.startswith("~"):
            return "[cat] path not allowed", 1
        import os
        cur = os.getcwd()
        target = os.path.join(cur, rest)
        if not os.path.isfile(target):
            return f"[cat] not found: {rest}", 1
        try:
            with open(target, "r", errors="replace") as f:
                out = f.read(8000)
            if len(out) == 8000:
                out += "\n[...] (truncated)"
            return out, 0
        except Exception as e:
            return f"[cat] {e}", 1
    if cmd not in _SHELL_ALLOW:
        return f"'{cmd}' not in allowlist", 1
    try:
        r = subprocess.run(_SHELL_ALLOW[cmd], shell=True, capture_output=True,
                           text=True, timeout=20)
        out = (r.stdout or "") + (r.stderr or "")
        if len(out) > 8000:
            out = out[:8000] + "\n[...] (truncated)"
        return out, r.returncode
    except subprocess.TimeoutExpired:
        return "[command timed out (20s)]", 1
    except Exception as e:
        return str(e), 1


# ── brain stats ────────────────────────────────────────────────────────────
_BRAIN_STATS_PATH = Path("data") / "brain_stats.json"


def _load_brain_stats() -> dict:
    if not _BRAIN_STATS_PATH.exists():
        return {"total": 0, "tiers": {}, "aspect": {}, "by_agent": {}, "maturity": {}}
    try:
        return json.loads(_BRAIN_STATS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"total": 0, "tiers": {}, "aspect": {}, "by_agent": {}, "maturity": {}}


def _save_brain_stats(stats: dict) -> None:
    try:
        _BRAIN_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _BRAIN_STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    except Exception:
        pass


def _bump_brain_stats(tier: str, aspect: str, agent_id: str = "") -> dict:
    stats = _load_brain_stats()
    stats["total"] = stats.get("total", 0) + 1
    stats["tiers"][tier] = stats["tiers"].get(tier, 0) + 1
    stats["aspect"][aspect] = stats["aspect"].get(aspect, 0) + 1
    if agent_id:
        stats["by_agent"][agent_id] = stats["by_agent"].get(agent_id, 0) + 1
    stats["maturity"][tier] = stats["maturity"].get(tier, 0) + 1
    _save_brain_stats(stats)
    return stats


# ── severity classification ───────────────────────────────────────────────
_RISKY_PATTERNS = ["exploit", "scan", "vuln", "cve", "malware", "attack",
                    "crack", "reverse shell", "payload", "reconnaissance"]
_AGGRESSIVE_STAGES = ["tool_call", "exec", "exploit", "attack", "scan"]
_NORMAL_STAGES = ["thinking", "reasoning", "planning", "chat", "reply"]


def _classify_severity(stage: str, detail: str, risk_level: str = "normal") -> str:
    combined = f"{stage} {detail}".lower()
    if risk_level == "dangerous" or risk_level == "aggressive":
        return "dangerous"
    if any(p in combined for p in _RISKY_PATTERNS):
        return "dangerous"
    if stage in _AGGRESSIVE_STAGES:
        return "aggressive"
    if any(s in stage for s in _NORMAL_STAGES):
        return "normal"
    return "working"


_ASPECT_FROM_EVENT = {
    "tool_selected": "tools",
    "tool_completed": "tools",
    "agent_selected": "agents",
    "agent_completed": "agents",
    "verification_passed": "verify",
    "verification_failed": "verify",
    "memory_updated": "memory",
    "task_created": "orchestrator",
    "task_started": "orchestrator",
    "task_completed": "orchestrator",
    "error": "orchestrator",
}

_AGENT_OFFENSIVE = {"red_team", "reverse_eng", "autonomous", "executor"}


def _classify_event(ev_type: str, detail: str, agent_id: str = "",
                    risk_level: str = "normal") -> tuple[str, str]:
    aspect = _ASPECT_FROM_EVENT.get(ev_type, ev_type)
    sev = _classify_severity(ev_type.value, detail, risk_level)
    if agent_id in _AGENT_OFFENSIVE:
        sev = "dangerous"
    return sev, aspect


# ── REST endpoints ──────────────────────────────────────────────────────────


@app.get("/api/settings")
async def api_settings():
    return _load_settings()


@app.post("/api/settings")
async def api_settings_post(body: dict):
    return _load_settings()


@app.get("/api/telemetry")
async def api_telemetry():
    orch = await _get_orchestrator()
    return _telemetry_snapshot(orch)


@app.post("/api/exec")
async def api_exec(cmd: str, request: Request):
    if not _token_ok(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    out, code = _shell_dispatch(cmd)
    return {"output": out, "exit_code": code}


@app.get("/api/logs")
async def api_logs():
    return {"logs": list(_LOG_BUF)[-100:], "recent": list(_TELEM)[-10:]}


@app.get("/api/capabilities")
async def api_capabilities():
    return {"capabilities": ["web_search", "terminal", "file_manager",
                              "python_executor", "voice", "memory", "knowledge"]}


@app.get("/api/connections")
async def api_connections():
    return {"connections": [{"name": "moon_local", "kind": "loopback",
                              "url": "http://127.0.0.1:8777", "enabled": True}]}


@app.get("/api/voice/status")
async def api_voice_status():
    ve = _get_voice_engine()
    if ve:
        return ve.backend_status()
    return {"error": "voice engine unavailable"}


@app.post("/api/voice/clone")
async def api_voice_clone(body: dict):
    ve = _get_voice_engine()
    if not ve:
        return {"error": "voice engine unavailable"}
    name = body.get("name", "cloned_voice")
    sample = body.get("sample", "")
    transcript = body.get("transcript", "")
    result = asyncio.run(_speak(""))  # no-op to warm loop
    result = asyncio.run(ve.clone_voice(name, sample, transcript))
    return {"result": result}


@app.post("/api/voice/set")
async def api_voice_set(body: dict):
    ve = _get_voice_engine()
    if not ve:
        return {"error": "voice engine unavailable"}
    name = body.get("name", "aria")
    ok = ve.set_voice(name)
    return {"ok": ok, "current": ve.current_voice()}


@app.get("/api/health")
async def api_health():
    orch = await _get_orchestrator()
    diag = _run_diagnostics(orch)
    return {
        "status": diag["summary"],
        "checks": diag["checks"],
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/brain-stats")
async def api_brain_stats():
    return _load_brain_stats()


@app.get("/api/agents")
async def api_agents():
    orch = await _get_orchestrator()
    return list(orch._agents.values()) if hasattr(orch, '_agents') else []


@app.get("/api/tools")
async def api_tools():
    orch = await _get_orchestrator()
    if orch._tool_registry:
        return [{"name": n, "description": ""} for n in orch._tool_registry.tool_names]
    return []


@app.get("/api/events")
async def api_events():
    return list(_EVENTS)


@app.get("/api/memory/search")
async def api_memory_search(q: str = ""):
    orch = await _get_orchestrator()
    if orch._memory:
        results = orch._memory.recall(keyword=q, limit=5)
        return {"results": results}
    return {"results": []}


@app.get("/api/knowledge/search")
async def api_knowledge_search(q: str = ""):
    orch = await _get_orchestrator()
    if orch._memory and hasattr(orch._memory, '_kb'):
        import asyncio
        results = asyncio.run(orch._memory.semantic_recall(q, top_k=5))
        return {"results": results}
    return {"results": []}


@app.get("/api/tasks")
async def api_tasks():
    return {"tasks": []}  # stub


@app.get("/api/executions/{exec_id}")
async def api_executions(exec_id: str):
    return {"execution": {"id": exec_id, "status": "unknown"}}


@app.get("/api/metrics")
async def api_metrics():
    return _telemetry_snapshot(await _get_orchestrator())


# ── WebSocket /ws ───────────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()

    if not _token_ok(websocket):
        await websocket.send_json({"type": "error", "message": "unauthorized"})
        await websocket.close()
        return

    orch = await _get_orchestrator()
    _send_lock = asyncio.Lock()

    async def send(**msg: Any) -> None:
        async with _send_lock:
            sev = "normal"
            aspect = msg.get("type", "event")
            if msg.get("type") in ("workflow", "exec", "assistant_start"):
                sev = _classify_severity(msg.get("stage", ""), msg.get("detail", ""),
                                         msg.get("risk_level", "normal"))
            elif msg.get("type") == "event":
                sev, aspect = _classify_event(msg.get("event_type", ""), msg.get("detail", ""))
            _bump_brain_stats(sev, aspect, msg.get("agent_id", ""))
            _emit_event(aspect, msg.get("detail", "")[:200], sev,
                        aspect=aspect, agent_id=msg.get("agent_id", ""))
            await websocket.send_json(msg)

    # subscribe to event bus
    ev_bus = bus()
    def _on_event(ev: Event) -> None:
        asyncio.create_task(send(
            type="event",
            event_type=ev.type.value,
            detail=ev.detail[:200],
            agent_id=ev.agent_id,
            aspect=ev.type.value,
        ))
    ev_bus.subscribe(_on_event)

    try:
        # initial payload
        status = _moon_status_impl(orch)
        await send(type="ready")
        await send(type="status", **status)

        # read loop
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=60.0)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break
            except Exception:
                break

            action = data.get("action", "")

            if action == "status":
                await send(type="status", **_moon_status_impl(orch))
                continue

            if action == "stop":
                globals()['_STOP_REQUESTED'] = True
                await send(type="notice", detail="Stop requested.")
                continue

            if action == "mute":
                globals()['_VOICE_MUTED'] = True
                await send(type="voice", detail="muted")
                continue

            if action == "unmute":
                globals()['_VOICE_MUTED'] = False
                await send(type="voice", detail="unmuted")
                continue

            if action == "wake":
                notice = orch._lock.hear("moon")
                await send(type="wake", detail=notice.get("notice", "Listening..."))
                continue

            if action == "voice":
                sub = data.get("sub", "list")
                ve = _get_voice_engine()
                if not ve:
                    await send(type="voice", detail="voice engine unavailable")
                    continue
                if sub == "list":
                    await send(type="voice", voices=ve.list_voices())
                elif sub == "set":
                    name = data.get("name", "aria")
                    ok = ve.set_voice(name)
                    await send(type="voice", detail=f"Voice set to {name}", ok=ok)
                elif sub == "clone":
                    result = await ve.clone_voice(
                        data.get("name", "cloned"),
                        data.get("sample", ""),
                        data.get("transcript", ""),
                    )
                    await send(type="voice", detail=result)
                elif sub == "status":
                    await send(type="voice", **ve.backend_status())
                continue

            if action == "exec":
                cmd = data.get("cmd", "")
                out, code = _shell_dispatch(cmd)
                await send(type="exec_output", cmd=cmd, output=out, exit_code=code)
                continue

            if action == "diagnostics":
                diag = _run_diagnostics(orch)
                for check in diag["checks"]:
                    await send(type="diagnostic", **check)
                await send(type="diagnostics_done", summary=diag["summary"])
                continue

            if action == "memory_search":
                q = data.get("query", "")
                if orch._memory:
                    results = orch._memory.recall(keyword=q, limit=5)
                    for r in results:
                        await send(type="memory_result", content=r)
                continue

            if action == "knowledge":
                q = data.get("query", "")
                if orch._memory and hasattr(orch._memory, '_kb'):
                    import asyncio as aio
                    results = await orch._memory.semantic_recall(q, top_k=5)
                    for r in results:
                        await send(type="knowledge_result", **r)
                continue

            if action == "list_tools":
                if orch._tool_registry:
                    await send(type="tools_list", tools=orch._tool_registry.tool_names)
                continue

            if action == "tool":
                name = data.get("name", "")
                args = data.get("args", {})
                result = await orch._tools.run(name, args) if orch._tools else None
                await send(type="tool_result", name=name, **result.to_dict() if result else {})
                continue

            if action == "network":
                import psutil
                net = psutil.net_io_counters()
                await send(type="network", rx=net.bytes_recv, tx=net.bytes_sent)
                continue

            if action == "capabilities":
                await send(type="capabilities", capabilities=["web_search", "terminal",
                                                               "file_manager", "python_executor"])
                continue

            if action == "github":
                await send(type="github", detail="GitHub integration stub")
                continue

            if action == "connect":
                await send(type="connect", peers=["moon_local"])
                continue

            if action == "agents":
                await send(type="agents_list", agents=list(orch._agents.values()))
                continue

            if action == "tools":
                await send(type="tools_list", tools=orch._tool_registry.tool_names if orch._tool_registry else [])
                continue

            if action == "skills":
                await send(type="skills_list", skills=[])
                continue

            if action == "tasks":
                await send(type="tasks_list", tasks=[])
                continue

            if action == "executions":
                await send(type="executions_list", executions=[])
                continue

            if action == "audit":
                await send(type="audit", entries=[])
                continue

            if action == "factory":
                await send(type="factory", components=[])
                continue

            if action == "settings":
                await send(type="settings", **_load_settings())
                continue

            if action == "security":
                await send(type="security", token=bool(TERMINAL_TOKEN),
                           locked=orch._lock.locked)
                continue

            if action == "automation":
                await send(type="automation", auto_voice=get_settings().auto_voice)
                continue

            if action == "dashboard":
                await send(type="dashboard", **_moon_status_impl(orch))
                continue

            if action == "help":
                await send(type="help",
                           commands=["send_message", "exec", "diagnostics", "memory_search",
                                     "knowledge", "run", "stop", "list_tools", "voice",
                                     "tool", "network", "capabilities", "github", "connect",
                                     "agents", "tools", "skills", "tasks", "executions",
                                     "audit", "factory", "settings", "security", "automation",
                                     "dashboard", "help", "status", "mute", "unmute", "wake"])
                continue

            if action == "send_message":
                text = data.get("text", "").strip()
                if not text:
                    await send(type="error", detail="empty message")
                    continue

                # lock check
                notice = orch._lock.observe(text)
                if notice:
                    await send(type="assistant_start", detail="lock")
                    await send(type="assistant_done",
                               answer=notice, elapsed=0.1, locked=orch._lock.locked)
                    continue

                if _STOP_REQUESTED:
                    await send(type="notice", detail="Stop requested — message blocked.")
                    continue

                await send(type="assistant_start")

                # simple chat fast path
                is_simple = len(text) <= 240 and not any(f in text.lower()
                    for f in ("http://", "https://", "file:", "/home", "write",
                              "create", "generate", "run", "execute", "open"))
                try:
                    if is_simple:
                        # quick_reply
                        async def _quick():
                            return orch.quick_reply(text)
                        answer = await asyncio.wait_for(_quick(), timeout=60.0)
                    else:
                        # full task
                        task = Task.create(text, agent_name="auto")
                        async def _run():
                            return await orch.run_task(task)
                        task = await asyncio.wait_for(_run(), timeout=180.0)
                        answer = task.result or ""
                        if not answer:
                            # fallback to quick_reply
                            answer = await asyncio.wait_for(
                                asyncio.coroutine(lambda: orch.quick_reply(text))(), timeout=150.0)
                except asyncio.TimeoutError:
                    logger.warning("Task timed out — falling back to quick reply")
                    try:
                        answer = await asyncio.wait_for(
                            asyncio.coroutine(lambda: orch.quick_reply(text))(), timeout=150.0)
                    except Exception:
                        answer = "[response timed out]"
                except Exception as exc:
                    logger.exception("send_message error: %s", exc)
                    answer = f"[error: {exc}]"

                # stream answer
                chunks = _stream_text(answer)
                for chunk in chunks:
                    await send(type="assistant_chunk", text=chunk)

                # speak
                audio = await _speak(answer)
                if audio:
                    try:
                        b64 = base64.b64encode(Path(audio).read_bytes()).decode()
                        await send(type="audio", data=b64, format="wav")
                    except Exception:
                        pass

                await send(type="assistant_done", answer=answer,
                           elapsed=data.get("elapsed", 0), locked=orch._lock.locked)

            elif action == "run":
                text = data.get("text", "").strip()
                task = Task.create(text, agent_name=data.get("agent", "auto"))
                try:
                    task = await asyncio.wait_for(
                        orch.run_task(task),
                        timeout=180.0,
                    )
                    answer = task.result or ""
                except asyncio.TimeoutError:
                    answer = "[task timed out]"
                except Exception as exc:
                    answer = f"[task error: {exc}]"

                for chunk in _stream_text(answer):
                    await send(type="assistant_chunk", text=chunk)
                await send(type="assistant_done", answer=answer)

            else:
                await send(type="error", detail=f"unknown action: {action}")

    finally:
        ev_bus.unsubscribe(_on_event)


# ── /ws/agent/{agent_id} ────────────────────────────────────────────────────
@app.websocket("/ws/agent/{agent_id}")
async def ws_agent(websocket: WebSocket, agent_id: str):
    await websocket.accept()
    if not _token_ok(websocket):
        await websocket.close()
        return
    orch = await _get_orchestrator()
    ev_bus = bus()

    def _filter(ev: Event) -> None:
        if ev.agent_id == agent_id:
            asyncio.create_task(websocket.send_json({
                "type": "event",
                "event_type": ev.type.value,
                "detail": ev.detail[:200],
                "agent_id": ev.agent_id,
            }))
    ev_bus.subscribe(_filter)
    try:
        await websocket.send_json({"type": "ready", "agent_id": agent_id})
        while True:
            await websocket.receive_json()
    finally:
        ev_bus.unsubscribe(_filter)


# ── /ws/events ─────────────────────────────────────────────────────────────
@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await websocket.accept()
    if not _token_ok(websocket):
        await websocket.close()
        return
    try:
        await websocket.send_json({"type": "ready", "stream": "events"})
        for ev in _EVENTS:
            await websocket.send_json(ev)
        while True:
            await asyncio.sleep(1)
            for ev in list(_EVENTS):
                await websocket.send_json(ev)
    finally:
        pass


# ── utility ────────────────────────────────────────────────────────────────
def _stream_text(text: str, yield_every: int = 1):
    """Generator yielding text in chunks for WS streaming."""
    if not text:
        return
    buf = ""
    for ch in text:
        buf += ch
        if len(buf) >= yield_every:
            yield buf
            buf = ""
    if buf:
        yield buf


def ltm_lines() -> int:
    """Count lines in LTM file."""
    p = get_settings().long_term_path
    if not p.exists():
        return 0
    try:
        return sum(1 for _ in p.read_text(encoding="utf-8").splitlines())
    except Exception:
        return 0


# ── run ────────────────────────────────────────────────────────────────────
def main():
    settings = get_settings()
    logger.info("Starting MOON Terminal on %s:%d", settings.host, settings.port)
    uvicorn.run(
        "app.terminal_interface:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
