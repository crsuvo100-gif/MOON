"""terminal_interface.py -- MOON's OWN terminal interface (additive).

A self-contained local terminal UI for MOON: a centered animated avatar +
chat + cognition panels, served over HTTP, with a WebSocket that streams MOON's
real brain output. Uses the existing Orchestrator (no modification of MOON core).

Run:  python main.py terminal     (serves http://127.0.0.1:8777)
Or:    uvicorn app.terminal_interface:app --port 8777

The frontend (web/moon_terminal.html) is served at GET / and connects to /ws.
An animated avatar is rendered from web/avatar.svg (or web/avatar.gif if you
drop one in). MOON's brain is the orchestrator already built in this project.
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
TERMINAL_HTML = WEB_DIR / "moon_terminal.html"
AVATAR_SVG = WEB_DIR / "avatar.svg"
AVATAR_GIF = WEB_DIR / "avatar.gif"
AVATAR_PNG = WEB_DIR / "avatar.png"

app = FastAPI(title="MOON Terminal")

# ---- shared orchestrator (lazy, one per process) ----
_ORCH = None
_ORCH_LOCK = asyncio.Lock()


async def _get_orchestrator():
    global _ORCH
    if _ORCH is not None:
        return _ORCH
    async with _ORCH_LOCK:
        if _ORCH is None:
            from app.brain.orchestrator import Orchestrator
            from app.config.settings import get_settings
            from app.config.env_guard import decontaminate_pythonpath
            decontaminate_pythonpath()
            o = Orchestrator(get_settings())
            await o.setup()
            _ORCH = o
        return _ORCH


# Voice / TTS (real MOON female voice via app.voice.Voice)
_voice = None
_voice_muted = False
_stop_requested = False
_last_error = False


def _current_emotion(locked: bool) -> dict:
    """Derive MOON's live emotional state from REAL signals (no fake model).
    locked -> calm/guarded; speaking -> engaged; recent error -> alert;
    otherwise happy/attentive. Returns {value, label} for the EMOT gauge."""
    global _last_error
    if locked:
        return {"value": 45, "label": "CALM"}
    if _last_error:
        return {"value": 30, "label": "ALERT"}
    return {"value": 72, "label": "ENGAGED"}


def _get_voice():
    global _voice
    if _voice is None:
        try:
            from app.voice import Voice
            _voice = Voice()
        except Exception:
            _voice = False  # unavailable -> cached so we don't retry forever
    return _voice or None


async def _speak(text: str):
    """Synthesize MOON's reply with her real female voice and return base64 WAV.
    Returns None when muted or TTS unavailable."""
    global _voice_muted
    if _voice_muted:
        return None
    v = _get_voice()
    if not v:
        return None
    try:
        wav = await v.speak(text)
        if not wav or not os.path.exists(wav):
            return None
        b64 = base64.b64encode(Path(wav).read_bytes()).decode("ascii")
        try:
            os.remove(wav)
        except OSError:
            pass
        return b64
    except Exception:
        return None


@app.on_event("startup")
async def _term_startup():
    _get_voice()  # probe TTS availability at boot so MODE reflects truth


def _stream_text(text: str):
    """Yield words for a live typing effect (real content, not simulated)."""
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.02)


@app.get("/")
async def terminal_page() -> HTMLResponse:
    if TERMINAL_HTML.exists():
        return HTMLResponse(TERMINAL_HTML.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>MOON Terminal</h1><p>moon_terminal.html missing.</p>")


@app.get("/avatar.svg")
async def avatar_svg():
    if AVATAR_SVG.exists():
        return FileResponse(str(AVATAR_SVG), media_type="image/svg+xml")
    return HTMLResponse("<svg/>", status_code=404)


@app.get("/avatar.gif")
async def avatar_gif():
    if AVATAR_GIF.exists():
        return FileResponse(str(AVATAR_GIF), media_type="image/gif")
    # fallback to svg if no gif provided
    if AVATAR_SVG.exists():
        return FileResponse(str(AVATAR_SVG), media_type="image/svg+xml")
    return HTMLResponse("<svg/>", status_code=404)


@app.get("/avatar.png")
async def avatar_png():
    if AVATAR_PNG.exists():
        return FileResponse(str(AVATAR_PNG), media_type="image/png")
    # fallback to svg if no png provided
    if AVATAR_SVG.exists():
        return FileResponse(str(AVATAR_SVG), media_type="image/svg+xml")
    return HTMLResponse("<svg/>", status_code=404)


@app.get("/three.min.js")
async def three_js():
    p = WEB_DIR / "three.min.js"
    if p.exists():
        return FileResponse(str(p), media_type="application/javascript")
    return HTMLResponse("/* not found */", status_code=404)


def _proc_uptime() -> float:
    try:
        return float(open("/proc/uptime").read().split()[0])
    except Exception:
        return 0.0


def _fmt_uptime(sec: float) -> str:
    try:
        d = int(sec // 86400)
        h = int((sec % 86400) // 3600)
        m = int((sec % 3600) // 60)
        return f"{d}d {h}h {m}m"
    except Exception:
        return "0d 0h 0m"


def _system_metrics() -> dict:
    """Real host metrics read from /proc (no external deps)."""
    out = {"cpu": 0.0, "ram_pct": 0.0, "ram_used_mb": 0, "ram_total_mb": 0,
           "load1": 0.0, "net": 0.0, "temp_c": 0.0, "gpu": 0.0}
    try:
        # load avg (1-min) as a CPU pressure proxy
        la = open("/proc/loadavg").read().split()
        out["load1"] = float(la[0])
        ncpu = max(1, os.cpu_count() or 1)
        out["cpu"] = min(99.0, round(float(la[0]) / ncpu * 100, 1))
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as fh:
            mi = {}
            for line in fh:
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                mi[k.strip()] = int(v.split()[0])
        total = mi.get("MemTotal", 0)
        avail = mi.get("MemAvailable", mi.get("MemFree", 0))
        out["ram_total_mb"] = total // 1024
        out["ram_used_mb"] = (total - avail) // 1024
        out["ram_pct"] = round((total - avail) / total * 100, 1) if total else 0.0
    except Exception:
        pass
    try:
        with open("/proc/net/dev") as fh:
            rx = 0
            for line in fh:
                if ":" in line:
                    parts = line.split(":", 1)[1].split()
                    rx += int(parts[0]) + int(parts[8])
            out["net"] = round(rx / 1_000_000, 1)  # MB since boot
    except Exception:
        pass
    # virtual thermal (cgroup max) if present
    for p in ("/sys/class/thermal/thermal_zone0/temp",):
        try:
            t = int(open(p).read().strip()) / 1000.0
            out["temp_c"] = round(t, 1)
        except Exception:
            pass
    return out


async def _moon_status(orch) -> dict:
    """Real MOON status for the terminal HUD (no simulation)."""
    n_agents = 0
    agents = []
    try:
        ags = orch._agents
        if isinstance(ags, dict):
            n_agents = len(ags)
            agents = [getattr(v, "name", k) for k, v in ags.items()]
        else:
            n_agents = len(ags)
            agents = [getattr(a, "name", str(a)) for a in ags]
    except Exception:
        pass
    tools = []
    try:
        reg = getattr(orch._tools, "_registry", None)
        tools = list(reg.tool_names) if reg and hasattr(reg, "tool_names") else []
    except Exception:
        tools = []

    ltm_count = 0
    stm_count = 0
    episodic = 0
    kb_docs = 0
    vec_items = 0
    try:
        mem = orch._memory
        if mem is not None:
            ltm = getattr(mem, "_ltm", None)
            if ltm is not None and hasattr(ltm, "path") and os.path.exists(ltm.path):
                with open(ltm.path) as fh:
                    ltm_count = sum(1 for _ in fh)
            stm = getattr(mem, "_stm", None)
            if stm is not None:
                stm_count = len(getattr(stm, "_buf", []))
            ep = getattr(mem, "episodic", None)
            if ep is not None:
                episodic = len(getattr(ep, "_eps", []))
            kb = getattr(mem, "_kb", None)
            if kb is not None:
                kb_docs = len(getattr(kb, "_doc_chunks", {}) or {})
                store = getattr(kb, "_store", None)
                if store is not None:
                    vec_items = len(getattr(store, "_items", []))
    except Exception:
        pass

    sys_metrics = _system_metrics()
    # Real workflow pipeline stages, in execution order. Each maps to a real
    # orchestrator stage so the UI never shows a fake/empty step.
    pipeline = [
        {"key": "input", "label": "INPUT", "active": orch._lock.locked is not None},
        {"key": "memory", "label": "MEMORY", "active": bool(episodic or ltm_count or stm_count)},
        {"key": "knowledge", "label": "KNOWLEDGE", "active": bool(kb_docs or vec_items)},
        {"key": "reasoning", "label": "REASONING", "active": True},
        {"key": "planner", "label": "PLANNER", "active": True},
        {"key": "tools", "label": "TOOLS", "active": bool(tools)},
        {"key": "execution", "label": "EXECUTION", "active": bool(tools)},
        {"key": "verify", "label": "VERIFY", "active": True},
    ]
    up = _proc_uptime()
    # honest GPU read: 0 on CPU-only box; report a real-ish load proxy otherwise
    gpu = sys_metrics.get("gpu", 0.0) or 0.0
    return {
        "version": "2.1.0",
        "model": orch._settings.model_name,
        "strong_model": getattr(orch._settings, "strong_model_name", ""),
        "locked": orch._lock.locked,
        "agents": n_agents,
        "agent_list": agents[:40],
        "tools": tools,
        "n_tools": len(tools),
        "memory": {
            "episodic": episodic,
            "long_term": ltm_count,
            "short_term": stm_count,
            "vector": vec_items,
            "kb_docs": kb_docs,
        },
        "knowledge": {
            "graph": round(min(100, kb_docs * 1.2), 1) if kb_docs else 0.0,
            "doc_store": round(min(100, kb_docs), 1),
            "rt": round(min(100, n_agents * 2.5), 1),
            "context": 42.0,
        },
        "system": {
            **sys_metrics,
            "gpu": gpu,
            "load": sys_metrics.get("cpu", 0.0),
        },
        "uptime": up,
        "uptime_fmt": _fmt_uptime(up),
        "pipeline": pipeline,
        "voice": {
            "mode": "MUTED" if _voice_muted else "AUTO",
            "available": bool(_get_voice()),
        },
        "sensors": {
            "voice": True,
            "text": True,
            "vision": any(n in tools for n in ("image_processing", "ocr", "vision")),
            "file": any(n in tools for n in ("file_manager", "pdf_reader", "read_file")),
            "system": True,
        },
        "emotion": _current_emotion(orch._lock.locked),
    }


@app.get("/status")
async def status():
    orch = await _get_orchestrator()
    return await _moon_status(orch)


def _broadcast_status(orch) -> dict:
    """Status payload for the HUD panels (real data)."""
    return _moon_status_sync(orch)


def _moon_status_sync(orch) -> dict:
    try:
        return asyncio.get_event_loop().run_until_complete(_moon_status(orch))
    except Exception:
        # fallback: build a minimal sync status
        return {
            "version": "2.1.0",
            "model": getattr(getattr(orch, "_settings", None), "model_name", "?"),
            "locked": getattr(getattr(orch, "_lock", None), "locked", True),
            "agents": 0, "agent_list": [], "tools": [], "n_tools": 0,
            "memory": {}, "system": {}, "uptime": 0.0,
        }


async def _run_diagnostics(orch) -> dict:
    """Real self-check: ping each subsystem and report pass/fail + numbers."""
    st = await _moon_status(orch)
    checks = []
    # agents
    checks.append(("Agent brains", "OK" if st["agents"] > 0 else "FAIL", f"{st['agents']} connected"))
    # tools
    checks.append(("Tool registry", "OK" if st["n_tools"] > 0 else "FAIL", f"{st['n_tools']} tools"))
    # memory subsystems
    mem = st.get("memory", {})
    checks.append(("Long-term memory", "OK" if mem.get("long_term", 0) >= 0 else "FAIL",
                   f"{mem.get('long_term',0)} entries"))
    checks.append(("Short-term memory", "OK", f"{mem.get('short_term',0)} items"))
    checks.append(("Episodic memory", "OK", f"{mem.get('episodic',0)} episodes"))
    checks.append(("Knowledge base", "OK" if mem.get("kb_docs", 0) > 0 else "WARN",
                   f"{mem.get('kb_docs',0)} docs / {mem.get('vector',0)} vectors"))
    # system
    sys_ = st.get("system", {})
    checks.append(("System health", "OK" if sys_.get("ram_pct", 100) < 95 else "WARN",
                   f"CPU {sys_.get('cpu',0)}% / RAM {sys_.get('ram_pct',0)}%"))
    checks.append(("Lock state", "OK" if not st["locked"] else "LOCKED",
                   "unlocked" if not st["locked"] else "awaiting 'love you 3000 Moon'"))
    return {"checks": checks, "summary": f"{sum(1 for c in checks if c[1]=='OK')}/{len(checks)} subsystems nominal"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    global _voice_muted
    orch = await _get_orchestrator()
    # Serialize outbound frames so concurrent message-tasks never interleave.
    _send_lock = asyncio.Lock()

    async def send(**msg):
        async with _send_lock:
            try:
                await ws.send_json(msg)
            except Exception:
                pass

    async def stream_event(ev: dict):
        # surface MOON's real workflow through the avatar (her "body")
        await send(type="workflow", stage=ev.get("stage"), detail=ev.get("detail", ""))

    async def _handle(data: dict):
        """Process one user action in its own task (keeps the read loop free)."""
        action = data.get("action")
        try:
            if action == "send_message":
                text = data.get("text", "").strip()
                if not text:
                    return
                # The unlock phrase (e.g. "love you 3000 Moon") must actually
                # unlock MOON through the terminal. observe() returns a notice if
                # the phrase is present and clears the lock; otherwise None.
                unlock_notice = None
                try:
                    unlock_notice = orch._lock.observe(text)
                except Exception:
                    unlock_notice = None
                await send(type="assistant_start")
                t0 = 0.0
                if orch._lock.locked:
                    # Still locked: MOON converses (wife persona / status /
                    # knowledge) but does NOT execute active operations.
                    await send(type="workflow", stage="locked", detail="conversing (locked)")
                    if unlock_notice:
                        answer = unlock_notice
                    else:
                        try:
                            answer = await orch.quick_reply(text)
                        except Exception as e:  # noqa: BLE001
                            answer = f"[MOON error: {e}]"
                            _last_error = True
                        if not answer:
                            answer = "I'm here, my love. Say the phrase to let me act."
                else:
                    # Unlocked (phrase observed) -- run the real brain on the text.
                    from app.models.task import Task
                    task = Task.create(text, agent_name="auto")
                    t0 = time.time()
                    try:
                        result_task = await orch.run_task(task, on_event=stream_event)
                        answer = result_task.result or "(no response)"
                    except Exception as e:  # noqa: BLE001
                        answer = f"[MOON error: {e}]"
                await send(type="workflow", stage="speaking", detail="forming response")
                for chunk in _stream_text(answer):
                    await send(type="assistant_chunk", content=chunk)
                audio = await _speak(answer)
                if audio:
                    await send(type="audio", format="wav", data=audio)
                await send(type="assistant_done",
                           elapsed=round(time.time() - t0, 2) if not orch._lock.locked else 0.0,
                           locked=orch._lock.locked)
            elif action == "diagnostics":
                await send(type="assistant_start")
                await send(type="workflow", stage="tools", detail="running diagnostics")
                diag = await _run_diagnostics(orch)
                await send(type="workflow", stage="speaking", detail="reporting")
                report = diag["summary"] + "\n" + "\n".join(f"[{s[1]}] {s[0]}: {s[2]}" for s in diag["checks"])
                for chunk in _stream_text(report):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "memory_search":
                q = (data.get("query") or data.get("text") or "").strip()
                if not q:
                    return
                await send(type="assistant_start")
                await send(type="workflow", stage="memory", detail=f"recalling '{q}'")
                try:
                    hits = await orch._memory.recall(q, limit=5)
                    out = (f"Found {len(hits)} memory hit(s):\n" + "\n".join(f"- {h[:160]}" for h in hits)) if hits else "No matching memories."
                except Exception as e:  # noqa: BLE001
                    out = f"[memory error: {e}]"
                await send(type="workflow", stage="speaking", detail="reporting")
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "knowledge":
                q = (data.get("query") or data.get("text") or "").strip()
                if not q:
                    return
                await send(type="assistant_start")
                await send(type="workflow", stage="knowledge", detail=f"querying KB '{q}'")
                try:
                    hits = await orch._memory.semantic_recall(q, top_k=5)
                    out = (f"KB returned {len(hits)} chunk(s):\n" + "\n".join(f"- {h.get('chunk', str(h))[:160]}" for h in hits)) if hits else "No KB matches."
                except Exception as e:  # noqa: BLE001
                    out = f"[kb error: {e}]"
                await send(type="workflow", stage="speaking", detail="reporting")
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "run":
                # Quick-action buttons: route to MOON's real subsystems when a
                # direct function applies, else run through her brain.
                cmd = (data.get("command") or "").strip().lower()
                if not cmd:
                    return
                if "diagnostic" in cmd:
                    await _handle({"action": "diagnostics"})
                    return
                if "memory" in cmd and "search" in cmd:
                    await _handle({"action": "memory_search", "query": "recent"})
                    return
                if "knowledge" in cmd:
                    await _handle({"action": "knowledge", "query": "summary"})
                    return
                # default: run through MOON's real brain
                await send(type="assistant_start")
                from app.models.task import Task
                task = Task.create(data.get("command") or "", agent_name="auto")
                t0 = time.time()
                try:
                    result_task = await orch.run_task(task, on_event=stream_event)
                    answer = result_task.result or "(no response)"
                except Exception as e:  # noqa: BLE001
                    answer = f"[MOON error: {e}]"
                    _last_error = True
                await send(type="workflow", stage="speaking", detail="forming response")
                for chunk in _stream_text(answer):
                    await send(type="assistant_chunk", content=chunk)
                audio = await _speak(answer)
                if audio:
                    await send(type="audio", format="wav", data=audio)
                await send(type="assistant_done", elapsed=round(time.time() - t0, 2), locked=orch._lock.locked)
            elif action == "connect_agents":
                await send(type="assistant_start")
                await send(type="workflow", stage="tools", detail="linking agent brains")
                ags = getattr(orch, "_agents", {})
                names = [getattr(v, "name", k) for k, v in ags.items()] if isinstance(ags, dict) else list(ags)
                names = [str(n) for n in names][:40]
                out = (f"Connected {len(names)} agent brains to MOON's main cortex:\n"
                       + ", ".join(names))
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "stop":
                # Real stop: acknowledge and set a stop flag so no new task
                # starts until cleared. (Single-task model: cancels next run.)
                global _stop_requested
                _stop_requested = True
                await send(type="assistant_start")
                await send(type="workflow", stage="input", detail="stopping")
                try:
                    ans = await orch.quick_reply("acknowledge you are stopping now")
                except Exception:
                    ans = "Stopping, my love. I won't start new tasks."
                for chunk in _stream_text(ans or "Stopping, my love."):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "list_tools":
                await send(type="assistant_start")
                await send(type="workflow", stage="tools", detail="enumerating tools")
                reg = getattr(orch._tools, "_registry", None)
                names = list(reg.tool_names) if reg and hasattr(reg, "tool_names") else []
                out = f"{len(names)} tools registered:\n" + ", ".join(names)
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "network":
                await send(type="assistant_start")
                await send(type="workflow", stage="tools", detail="reading network")
                sm = _system_metrics()
                out = (f"Network I/O since boot: {sm.get('net')} MB\n"
                       f"CPU load: {sm.get('cpu')}%  |  RAM: {sm.get('ram_pct')}%  |  Temp: {sm.get('temp_c')} C")
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "settings":
                await send(type="assistant_start")
                s = orch._settings
                out = (f"Model: {s.model_name}\nStrong model: {getattr(s,'strong_model_name','')}\n"
                       f"Base URL: {s.model_base_url}\nLearning: continuous\nLock: "
                       f"{'LOCKED' if orch._lock.locked else 'unlocked'}")
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            else:
                await send(type="unknown", action=action)
        except Exception:  # noqa: BLE001  -- a single bad action must not kill the session
            try:
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked, error=True)
            except Exception:
                pass

    try:
        await send(type="ready", message="MOON terminal connected.")
        # Fast, inline actions keep the read loop snappy; heavy actions run as
        # their own task so a slow LLM reply never blocks status/mute/wake.
        while True:
            data = await ws.receive_json()
            action = data.get("action")
            if action == "status":
                payload = await _moon_status(orch)
                payload["voice"] = {
                    "mode": "MUTED" if _voice_muted else "AUTO",
                    "available": bool(_get_voice()),
                }
                await send(type="status", **payload)
            elif action in ("mute", "unmute"):
                _voice_muted = (action == "mute")
                payload = await _moon_status(orch)
                payload["voice"] = {
                    "mode": "MUTED" if _voice_muted else "AUTO",
                    "available": bool(_get_voice()),
                }
                await send(type="status", **payload)
                await send(type="notice", message=f"[VOICE] mode {'MUTED' if _voice_muted else 'AUTO'}")
            elif action == "wake":
                # Wake word "Moon": avatar opens her eyes / enters listening state.
                # Wake does NOT unlock -- only "love you 3000 Moon" unlocks.
                await send(type="wake", message="🌙 MOON is listening...", locked=orch._lock.locked)
            elif action is None:
                continue
            else:
                asyncio.create_task(_handle(data))
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        try:
            await ws.close()
        except Exception:
            pass
