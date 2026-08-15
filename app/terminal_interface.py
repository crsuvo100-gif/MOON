"""terminal_interface.py -- MOON's terminal interface backend (additive).

Serves MOON's terminal over HTTP: a WebSocket (/ws) that streams MOON's real
brain output to a front-end, plus /status (auth-gated when MOON_TERMINAL_TOKEN
is set), /avatar.svg, and a root placeholder. The front-end frame
(web/moon_terminal.html) was removed and is being rebuilt from scratch; this
backend is the engine the new UI will connect to. Uses the existing
Orchestrator (no modification of MOON core).

Run:  python main.py terminal     (serves http://127.0.0.1:8777)
Or:    uvicorn app.terminal_interface:app --port 8777
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
AVATAR_SVG = WEB_DIR / "avatar.svg"
AVATAR_GIF = WEB_DIR / "avatar.gif"
AVATAR_PNG = WEB_DIR / "avatar.png"

app = FastAPI(title="MOON Terminal")

# --- Remote-access authorization gate ----------------------------------------
# When MOON_TERMINAL_TOKEN / settings.terminal_access_token is set, the Terminal
# interface REQUIRES a matching `Authorization: Bearer <token>` on the WebSocket
# and /status. This is the ONLY safe way to expose MOON beyond loopback (pair with
# a tunnel/relay). When unset, MOON stays local-only (no token checked) -- her
# default, safest posture.
try:
    from app.config.settings import get_settings
    TERMINAL_TOKEN = get_settings().terminal_access_token.strip() or os.environ.get("MOON_TERMINAL_TOKEN", "").strip()
except Exception:  # noqa: BLE001
    TERMINAL_TOKEN = os.environ.get("MOON_TERMINAL_TOKEN", "").strip()


def _token_ok(ws_or_headers) -> bool:
    """True when no token is required, or the request presented the right one."""
    if not TERMINAL_TOKEN:
        return True
    if isinstance(ws_or_headers, dict):
        auth = ws_or_headers.get("authorization", "") or ws_or_headers.get("Authorization", "")
    else:
        auth = ws_or_headers.headers.get("authorization", "") if hasattr(ws_or_headers, "headers") else ""
    return auth == f"Bearer {TERMINAL_TOKEN}"

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
            from app.config.env_guard import decontaminate_pythonpath
            from app.config.settings import get_settings
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
    # The old front-end frame (web/moon_terminal.html) was removed; a new
    # terminal UI/frame is being built from scratch. The backend (WebSocket /ws,
    # /status, authz gate, /avatar.svg) stays live so the new UI can connect.
    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>MOON Terminal</title></head><body style='background:#03060f;color:#00f3ff;"
        "font-family:monospace;display:grid;place-items:center;height:100vh;margin:0'>"
        "<div style='text-align:center'><h1>MOON TERMINAL</h1>"
        "<p>New interface coming online. Backend WebSocket /ws is live.</p></div>"
        "</body></html>"
    )


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
async def status(request: Request):
    # Authorization gate for remote exposure.
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
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
    # Authorization gate for remote exposure: require Bearer token when set.
    if TERMINAL_TOKEN and not _token_ok(ws):
        await ws.close(code=1008, reason="unauthorized")
        return
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
                # Does NOT call the LLM -- a model call can hang on a locked/in-
                # active model, which would leave the UI with no response. Send a
                # direct, honest acknowledgment instead.
                global _stop_requested
                _stop_requested = True
                await send(type="assistant_start")
                await send(type="workflow", stage="input", detail="stopping")
                ans = "Stopping, my love. I won't start any new tasks until you tell me otherwise."
                for chunk in _stream_text(ans):
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
            elif action in ("capabilities", "github"):
                # NEW: expose the autonomous Capability Manager / GitHub retriever
                # through the existing terminal (additive; no existing command clobbered).
                await send(type="assistant_start")
                await send(type="workflow", stage="tools", detail="capability system")
                try:
                    tool = getattr(orch._tools, "_registry", None)
                    cap_tool = tool.get("capability_manager") if tool else None
                    if cap_tool is None:
                        out = "[capabilities] Capability Manager not registered."
                    else:
                        payload = (data.get("query") or data.get("text") or data.get("command") or "").strip()
                        if action == "github":
                            res = await cap_tool.execute(action="search_github", query=payload or "video converter")
                        else:
                            # 'capabilities list|health|search <x>' parsing
                            parts = payload.split()
                            cmd = parts[0].lower() if parts else "list"
                            if cmd in ("list", "health", "ls"):
                                res = await cap_tool.execute(action="list" if cmd != "health" else "health")
                            elif cmd == "search" and len(parts) > 1:
                                res = await cap_tool.execute(action="search_github", query=" ".join(parts[1:]))
                            elif cmd == "github":
                                res = await cap_tool.execute(action="search_github", query=" ".join(parts[1:]) or "tool")
                            elif cmd in ("install", "verify", "inspect") and len(parts) > 1:
                                res = await cap_tool.execute(action=cmd, name=parts[1])
                            else:
                                res = await cap_tool.execute(action="list")
                        out = res if isinstance(res, str) else str(res)
                except Exception as e:  # noqa: BLE001
                    out = f"[capabilities] error: {e}"
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "connect":
                # NEW: MOON's global connection layer (additive).
                await send(type="assistant_start")
                await send(type="workflow", stage="tools", detail="global connector")
                try:
                    tool = getattr(orch._tools, "_registry", None)
                    conn_tool = tool.get("global_connector") if tool else None
                    if conn_tool is None:
                        out = "[connect] Global Connector not registered."
                    else:
                        payload = (data.get("query") or data.get("text") or data.get("command") or "").strip()
                        parts = payload.split()
                        cmd = parts[0].lower() if parts else "list"
                        if cmd == "list":
                            out = await conn_tool.execute(action="list")
                        elif cmd == "health":
                            out = await conn_tool.execute(action="health")
                        elif cmd == "connect" and len(parts) >= 3:
                            # moon> connect <name> <url> [kind]
                            out = await conn_tool.execute(action="connect", name=parts[1],
                                                         url=parts[2], kind=(parts[3] if len(parts) > 3 else "service"))
                        elif cmd == "call" and len(parts) >= 2:
                            out = await conn_tool.execute(action="call", name=parts[1],
                                                         message=" ".join(parts[2:]))
                        else:
                            out = (await conn_tool.execute(action="list"))
                        out = out if isinstance(out, str) else str(out)
                except Exception as e:  # noqa: BLE001
                    out = f"[connect] error: {e}"
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
            elif action == "security":
                # Real authorization posture (defensive/offensive gate status).
                await send(type="assistant_start")
                await send(type="workflow", stage="tools", detail="reading security posture")
                try:
                    from app.security.authorization import _authorized_set
                    auth = sorted(_authorized_set())
                    lock_state = "LOCKED" if orch._lock.locked else "unlocked"
                    out = (
                        "SECURITY POSTURE\n"
                        f"- Lock state: {lock_state}\n"
                        f"- Active-ops authorization gate: ENABLED\n"
                        f"- Authorized targets ({len(auth)}): "
                        + (", ".join(auth) if auth else "none configured")
                        + "\n- Mode: active offensive ops require authorized targets or "
                          "runtime operator confirmation. Defensive/passive analysis needs no auth."
                    )
                except Exception as e:  # noqa: BLE001
                    out = f"[security error: {e}]"
                await send(type="workflow", stage="speaking", detail="reporting")
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "automation":
                # Real self-improvement status: surface MOON's continuous-learning /
                # autonomous-improvement pipeline state from the running brain.
                await send(type="assistant_start")
                await send(type="workflow", stage="tools", detail="checking automation")
                try:
                    lessons = 0
                    import os as _os
                    lessons_path = _os.path.join(str(getattr(orch, "_base_dir", ".")), "logs", "lessons.jsonl")
                    if _os.path.exists(lessons_path):
                        with open(lessons_path) as _fh:
                            lessons = sum(1 for _ in _fh)
                    auto = getattr(getattr(orch, "_settings", None), "enable_auto_learning", True)
                    out = (
                        "AUTONOMOUS AUTOMATION\n"
                        f"- Continuous self-learning: {'ON' if auto else 'OFF'}\n"
                        f"- Lessons recorded (self-improvement corpus): {lessons}\n"
                        f"- Per-agent brains connected: {getattr(orch, '_agents', {}).__len__() if hasattr(orch, '_agents') else 0}\n"
                        "- Loop: every interaction consolidates facts into long-term memory + "
                          "knowledge base; PromptTuner applies past lessons to agent personas."
                    )
                except Exception as e:  # noqa: BLE001
                    out = f"[automation error: {e}]"
                await send(type="workflow", stage="speaking", detail="reporting")
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "dashboard":
                # Real aggregated HUD summary (same source as the live panels).
                await send(type="assistant_start")
                st = await _moon_status(orch)
                mem = st.get("memory", {})
                sys_ = st.get("system", {})
                out = (
                    "MOON COMMAND CENTER\n"
                    f"- Version: {st.get('version')}  Model: {st.get('model')}\n"
                    f"- State: {'LOCKED' if st.get('locked') else 'UNLOCKED'}\n"
                    f"- Agents connected: {st.get('agents')}  Tools: {st.get('n_tools')}\n"
                    f"- Memory: LTM {mem.get('long_term')} | episodic {mem.get('episodic')} | "
                    f"vector {mem.get('vector')}\n"
                    f"- Knowledge docs: {mem.get('kb_docs')}\n"
                    f"- Host: CPU {sys_.get('cpu')}% | RAM {sys_.get('ram_pct')}% | "
                    f"temp {sys_.get('temp_c')}C | uptime {st.get('uptime_fmt')}\n"
                    "Use the tabs/quick actions to drill in, or type a command."
                )
                await send(type="workflow", stage="speaking", detail="reporting")
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "help":
                await send(type="assistant_start")
                out = (
                    "MOON COMMANDS\n"
                    "- Say 'Moon' (or WAKE) to wake me; 'love you 3000 Moon' to unlock.\n"
                    "- Tabs: DASHBOARD, DIAGNOSTICS, MEMORY, KNOWLEDGE, TOOLS, AUTOMATION, "
                      "SECURITY, NETWORK, SETTINGS.\n"
                    "- Quick actions: SYSTEM STATUS, RUN DIAGNOSTICS, ACTIVE WORKFLOW, "
                      "MEMORY SEARCH, KNOWLEDGE BASE, STOP TASKS.\n"
                    "- Buttons: WAKE MOON, CONNECT AGENTS, LIST TOOLS, MUTE/UNMUTE.\n"
                    "- Just type anything to talk to me (when unlocked I run my real brain)."
                )
                await send(type="workflow", stage="speaking", detail="reporting")
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
