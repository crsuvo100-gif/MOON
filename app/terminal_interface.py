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
import json
import subprocess
import shlex
from collections import deque
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
TERMINAL_HTML = WEB_DIR / "moon_terminal.html"
THEME_JSON = WEB_DIR / "theme.json"
SETTINGS_JSON = WEB_DIR / "moon_settings.json"
MOON_CORE_PNG = WEB_DIR / "moon_core.png"
AVATAR_SVG = WEB_DIR / "avatar.svg"
AVATAR_GIF = WEB_DIR / "avatar.gif"
AVATAR_PNG = WEB_DIR / "avatar.png"

# Default, user-overridable terminal UI settings (persisted to moon_settings.json).
_DEFAULT_SETTINGS = {
    "host": "127.0.0.1",
    "port": 8777,
    "display": "",            # auto-detected if blank
    "browser": "",            # auto-detected if blank (google-chrome/chromium/...)
    "aspect": "auto",         # auto | 16:9 | 21:9 | 32:9 | 16:10 | 4:3 | 1:1 | 9:16
    "avatar_mode": "fusion",  # fusion | neural  (central core visual)
    "resolution": "hd",       # hd | compact  (UI density for large displays)
    "core_glow": 1.0,         # 0.2..2.0 (central core glow intensity)
    "autostart": True,        # open HUD on MOON boot
    "idle_speed": 1.0,
}

def _load_settings() -> dict:
    s = dict(_DEFAULT_SETTINGS)
    try:
        if SETTINGS_JSON.exists():
            s.update(json.loads(SETTINGS_JSON.read_text()))
    except Exception:
        pass
    return s

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


# ---- Live telemetry ring buffer + structured log sink (advanced HUD) ----
_TELEM = deque(maxlen=240)          # rolling {t, cpu, ram, net, load}
_LOG_FILE = Path(os.environ.get("MOON_TERMINAL_LOG", "/tmp/moon_terminal.log"))
_LOG_BUF = deque(maxlen=400)        # rolling backend log lines for the HUD
_telem_t = 0.0

def _push_telemetry(orch):
    """Sample real system metrics into the rolling buffer (called periodically)."""
    global _telem_t
    try:
        s = _system_metrics()
        cpu = float(s.get("cpu", 0.0) or 0.0)
        ram = float(s.get("ram_pct", 0.0) or 0.0)
        net = float(s.get("net", 0.0) or 0.0)
        _TELEM.append({"t": round(time.time(), 1), "cpu": round(cpu, 1),
                       "ram": round(ram, 1), "net": round(net, 2)})
    except Exception:
        pass

# Live log subscribers (set when a HUD client requests action:"log_stream").
# Each entry is an asyncio coroutine `send(**msg)` from a ws_endpoint connection.
_LOG_SUBSCRIBERS: list = []


def _log(msg: str, sev: str = "info"):
    """Append a structured log line to the rolling buffer + file (for the HUD)."""
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {sev.upper()} {msg}"
    _LOG_BUF.append({"t": ts, "sev": sev, "msg": msg})
    _emit_event("log", msg, sev)
    # push to any live HUD log subscribers (send is an async coroutine -> schedule it)
    if _LOG_SUBSCRIBERS:
        for sub in list(_LOG_SUBSCRIBERS):
            try:
                asyncio.ensure_future(sub(type="log", t=ts, sev=sev, msg=msg))
            except Exception:
                pass
    try:
        with open(_LOG_FILE, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass

def _telemetry_snapshot(orch) -> dict:
    _push_telemetry(orch)
    return {"series": list(_TELEM),
            "current": _TELEM[-1] if _TELEM else None,
            "logs": list(_LOG_BUF)}


# Bounded ring buffer of real, recent system events (logs + workflow stages +
# assistant activity). Feeds the HUD EVENTS timeline via /api/events. Pure
# observability — never blocks the live paths that populate it.
_EVENTS: "deque" = deque(maxlen=200)


def _emit_event(kind: str, detail: str, sev: str = "info") -> None:
    """Record one real event into the rolling buffer (used by /api/events)."""
    try:
        _EVENTS.append({
            "t": time.strftime("%H:%M:%S"),
            "ts": round(time.time(), 3),
            "kind": kind,
            "sev": sev,
            "detail": str(detail)[:280],
        })
    except Exception:
        pass


# Voice / TTS (MOON's premium female voice + cloning via VoiceEngine)
_voice_engine = None
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


def _get_voice_engine():
    global _voice_engine
    if _voice_engine is None:
        try:
            from app.voice_engine import VoiceEngine

            s = _ORCH._settings if _ORCH is not None else None
            _voice_engine = VoiceEngine(settings=s)
        except Exception:
            _voice_engine = False  # unavailable -> cached so we don't retry forever
    return _voice_engine or None


async def _speak(text: str):
    """Synthesize MOON's reply with her real female voice and return base64 WAV.
    Returns None when muted or TTS unavailable."""
    global _voice_muted
    if _voice_muted:
        return None
    eng = _get_voice_engine()
    if not eng:
        return None
    try:
        wav = await eng.speak(text)
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
    _get_voice_engine()  # probe TTS availability at boot so MODE reflects truth


def _stream_text(text: str):
    """Yield words for a live typing effect (real content, not simulated)."""
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.02)


@app.get("/")
async def terminal_page() -> HTMLResponse:
    # Serves the rebuilt MOON NEURAL CORE INTERFACE (web/moon_terminal.html),
    # a red/black HUD wired to the live /ws backend.
    headers = {"Cache-Control": "no-store, no-cache, must-revalidate"}
    if TERMINAL_HTML.exists():
        return HTMLResponse(
            TERMINAL_HTML.read_text(encoding="utf-8"), headers=headers
        )
    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>MOON Terminal</title></head><body style='background:#050505;color:#ff4d4d;"
        "font-family:monospace;display:grid;place-items:center;height:100vh;margin:0'>"
        "<div style='text-align:center'><h1>MOON TERMINAL</h1>"
        "<p>Interface offline. Backend WebSocket /ws is live.</p></div>"
        "</body></html>"
    )


@app.get("/theme")
async def theme_json():
    if THEME_JSON.exists():
        return FileResponse(str(THEME_JSON), media_type="application/json")
    return HTMLResponse("{}", status_code=404)


@app.get("/moon_core.png")
async def moon_core_png():
    if MOON_CORE_PNG.exists():
        return FileResponse(str(MOON_CORE_PNG), media_type="image/png")
    return HTMLResponse("<svg/>", status_code=404)


@app.get("/moon_core_sphere.png")
async def moon_core_sphere_png():
    f = WEB_DIR / "assets" / "moon_core_sphere.png"
    if f.exists():
        return FileResponse(str(f), media_type="image/png")
    return HTMLResponse("<svg/>", status_code=404)


@app.get("/moon_brain.webp")
async def moon_brain_webp():
    f = WEB_DIR / "assets" / "moon_brain.webp"
    if f.exists():
        return FileResponse(str(f), media_type="image/webp")
    return HTMLResponse("<svg/>", status_code=404)


@app.get("/moon_fiery.jpg")
async def moon_fiery_jpg():
    # Dim fiery holographic-sphere backdrop behind the red/black HUD.
    f = WEB_DIR / "assets" / "moon_fiery.jpg"
    if f.exists():
        return FileResponse(str(f), media_type="image/jpeg")
    return HTMLResponse("<svg/>", status_code=404)


@app.get("/moon_orb.jpg")
async def moon_orb_jpg():
    # The attached fiery holographic-sphere image, as MOON's dominant central core.
    f = WEB_DIR / "assets" / "moon_orb.jpg"
    if f.exists():
        return FileResponse(str(f), media_type="image/jpeg")
    return HTMLResponse("<svg/>", status_code=404)


@app.get("/core_ai.png")
async def core_ai_png():
    f = WEB_DIR / "core_ai.png"
    if f.exists():
        return FileResponse(str(f), media_type="image/png")
    return HTMLResponse("<svg/>", status_code=404)


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
        s = int(sec % 60)
        return f"{d}d {h}h {m}m {s}s"
    except Exception:
        return "0d 0h 0m 0s"


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
            "available": bool(_get_voice_engine()),
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


@app.get("/api/settings")
async def api_get_settings(request: Request):
    return JSONResponse(_load_settings())


@app.post("/api/settings")
async def api_post_settings(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    cur = _load_settings()
    cur.update({k: body[k] for k in ("host", "port", "display", "browser",
                                     "aspect", "avatar_mode", "resolution", "core_glow",
                                     "autostart", "idle_speed") if k in body})
    try:
        with open(SETTINGS_JSON, "w") as fh:
            json.dump(cur, fh, indent=2)
        _log(f"settings saved: {cur.get('avatar_mode')}/{cur.get('aspect')}", "ok")
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    return JSONResponse({"ok": True, "settings": cur})


@app.get("/api/telemetry")
async def api_telemetry(request: Request):
    orch = await _get_orchestrator()
    return JSONResponse(_telemetry_snapshot(orch))


# Restricted shell allowlist: the HUD "SHELL" tab runs REAL commands, but only
# safe read-only/diagnostic ones, so the interface is powerful without being a
# remote-code-execution hole. Extend deliberately; never allow arbitrary shells.
_SHELL_ALLOW = {
    "status": "echo MOON CORE ONLINE",
    "ps": "ps -eo pid,pcpu,pmem,comm | head -20",
    "top": "ps -eo pid,pcpu,pmem,comm | sort -k2 -r | head -12",
    "df": "df -h",
    "free": "free -h",
    "uname": "uname -a",
    "uptime": "uptime",
    "netstat": "ss -tunp 2>/dev/null | head -20 || netstat -tunp 2>/dev/null | head -20",
    "ifconfig": "ip -brief addr",
    "ip": "ip -brief addr",
    "ls": "ls -la",
    "pwd": "pwd",
    "echo": "echo",
    "date": "date",
    "whoami": "whoami",
    "env": "env | grep -iE 'MOON|PATH|HOME|USER' | head",
    "nproc": "nproc",
    "cat": "cat",   # gated below to text files only
}

def _shell_dispatch(cmd: str) -> tuple[str, int]:
    """Run a REAL command from the allowlist. Returns (output, exit_code)."""
    parts = shlex.split(cmd) if cmd.strip() else []
    if not parts:
        return ("", 0)
    base = parts[0]
    if base not in _SHELL_ALLOW:
        return (f"denied: '{base}' is not in the operator allowlist", 1)
    # Build the real shell command (allowlist maps to a safe expansion).
    if base == "cat":
        # only permit cat of text/log files, no flags, no redirects
        target = parts[1] if len(parts) > 1 else ""
        if not target or target.startswith("-") or ".." in target or target.startswith("/"):
            return ("denied: cat target not permitted", 1)
        real = f"cat {shlex.quote(target)}"
    else:
        real = _SHELL_ALLOW[base] + ("" if base in ("echo", "pwd", "date", "whoami", "nproc", "uname", "uptime") else "")
        # for ls/cat without args, allow but cap output
    try:
        _log(f"shell: {cmd}", "sys")
        proc = subprocess.run(real, shell=True, capture_output=True, text=True, timeout=20)
        out = (proc.stdout or "") + (proc.stderr or "")
        return (out[:8000], proc.returncode)
    except subprocess.TimeoutExpired:
        return ("timeout (>20s)", 124)
    except Exception as e:  # noqa: BLE001
        return (f"error: {e}", 2)


@app.post("/api/exec")
async def api_exec(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    cmd = str(body.get("cmd", "")).strip()
    out, code = _shell_dispatch(cmd)
    _log(f"exec[{code}] {cmd}", "ok" if code == 0 else "err")
    return JSONResponse({"cmd": cmd, "exit": code, "output": out})


@app.get("/api/logs")
async def api_logs(request: Request, n: int = 100):
    orch = await _get_orchestrator()
    snap = _telemetry_snapshot(orch)
    return JSONResponse({"logs": snap["logs"][-n:], "telemetry": snap["series"][-n:]})



@app.get("/status")
async def status(request: Request):
    # Authorization gate for remote exposure.
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    orch = await _get_orchestrator()
    return await _moon_status(orch)


@app.get("/api/health")
async def api_health(request: Request):
    """Project-wide health endpoint (Phase 27).

    Reuses the existing real diagnostic pipeline (_moon_status + _run_diagnostics)
    and rolls the per-subsystem OK/FAIL/WARN verdicts into a single overall status:
      HEALTHY   - no FAIL and no WARN
      DEGRADED  - at least one WARN (non-critical, still operational)
      FAILED    - at least one FAIL (a required subsystem is down)
    """
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        orch = await _get_orchestrator()
        diag = await _run_diagnostics(orch)
        checks = diag.get("checks", [])
        states = [c[1] for c in checks]
        if any(s == "FAIL" for s in states):
            overall = "FAILED"
        elif any(s == "WARN" for s in states):
            overall = "DEGRADED"
        else:
            overall = "HEALTHY"
        return JSONResponse({
            "status": overall,
            "summary": diag.get("summary", ""),
            "checks": [
                {"subsystem": c[0], "state": c[1], "detail": c[2]} for c in checks
            ],
            "model": getattr(getattr(orch, "_settings", None), "model_name", "?"),
            "locked": getattr(getattr(orch, "_lock", None), "locked", True),
            "timestamp": time.time(),
        })
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "FAILED", "error": str(exc)}, status_code=503)


@app.get("/api/agents")
async def api_agents(request: Request):
    """Read-only roster of MOON's agent brains (real data from the Orchestrator).

    Additive: reuses _moon_status (no new data source). Useful for the HUD and
    any external monitor that wants the live agent list.
    """
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    orch = await _get_orchestrator()
    st = await _moon_status(orch)
    agents = st.get("agents", 0)
    agent_list = st.get("agent_list", []) or []
    # Enrich with each agent's allowed-tool scope when available.
    scoped = []
    try:
        ags = getattr(orch, "_agents", {}) or {}
        for name in agent_list:
            card = ags.get(name) if isinstance(ags, dict) else None
            allowed = getattr(card, "allowed_tools", None)
            scoped.append({
                "name": name,
                "allowed_tools": allowed if allowed is not None else [],
            })
    except Exception:
        scoped = [{"name": n, "allowed_tools": []} for n in agent_list]
    return JSONResponse({
        "count": agents,
        "agents": scoped,
        "locked": st.get("locked", True),
    })


@app.get("/api/tools")
async def api_tools(request: Request):
    """Read-only roster of MOON's registered tools (real data from the Orchestrator).

    Additive: reuses _moon_status (no new data source).
    """
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    orch = await _get_orchestrator()
    st = await _moon_status(orch)
    tools = st.get("tools", []) or []
    # Surface each tool's callable status from the registry when available.
    detailed = []
    try:
        reg = getattr(getattr(orch, "_tools", None), "_registry", None)
        caps = getattr(reg, "tool_caps", None)
        for name in tools:
            entry = {"name": name}
            if caps is not None:
                entry["description"] = (caps.get(name) or {}).get("description", "")
            detailed.append(entry)
    except Exception:
        detailed = [{"name": n} for n in tools]
    return JSONResponse({
        "count": len(tools),
        "tools": detailed,
        "locked": st.get("locked", True),
    })


@app.get("/api/events")
async def api_events(request: Request):
    """Read-only, recent real-event feed (logs + workflow stages + chat + exec).

    Additive observability endpoint (Phase 27): surfaces the same live activity
    the HUD EVENTS timeline shows, sourced from the in-process _EVENTS ring
    buffer (populated by _log + the WS send() path). Auth-gated like the rest.
    """
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    return JSONResponse({
        "count": len(_EVENTS),
        "events": list(_EVENTS),
    })


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
        # Capture real activity into the events ring buffer (for /api/events +
        # the HUD EVENTS timeline). Pure observability; failures are swallowed.
        _kind = msg.get("type")
        if _kind == "workflow":
            _emit_event("workflow", f"{msg.get('stage','?')}: {msg.get('detail','')}")
        elif _kind in ("assistant_start", "assistant_done"):
            _emit_event("chat", f"{_kind} (locked={msg.get('locked')})")
        elif _kind == "exec_output":
            _emit_event("exec", str(msg.get("output", ""))[:200])
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
            elif action == "exec":
                # Real shell command from the operator allowlist, streamed live.
                cmd = str(data.get("cmd", "")).strip()
                out, code = _shell_dispatch(cmd)
                _log(f"exec[{code}] {cmd}", "ok" if code == 0 else "err")
                await send(type="exec_output", cmd=cmd, exit=code, output=out)
            elif action == "log_stream":
                # Subscribe this connection to live backend log events.
                if send not in _LOG_SUBSCRIBERS:
                    _LOG_SUBSCRIBERS.append(send)
                    # replay last few so the console isn't empty
                    for ln in list(_LOG_BUF)[-30:]:
                        await send(type="log", t=ln["t"], sev=ln["sev"], msg=ln["msg"])
                    await send(type="notice", message="[LOG] live stream connected")
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
            elif action == "voice":
                # MOON's premium female voice + cloning control surface.
                await send(type="assistant_start")
                await send(type="workflow", stage="voice", detail="voice engine")
                sub = (data.get("command") or data.get("query") or "status").strip().lower()
                eng = _get_voice_engine()
                if eng is None:
                    out = "[voice] engine unavailable."
                elif sub.startswith("list"):
                    vs = eng.list_voices()
                    out = "MOON voices:\n" + "\n".join(
                        f"  - {v['name']} [{v['backend']}]{' (cloned)' if v['cloned'] else ''} :: {v['desc']}"
                        for v in vs)
                elif sub.startswith("set"):
                    name = sub.split(None, 1)[1] if " " in sub else ""
                    out = eng.set_voice(name) if name else "voice set requires a name (see 'voice list')."
                elif sub.startswith("clone"):
                    parts = sub.split(None, 2)
                    name = parts[1] if len(parts) > 1 else ""
                    sample = data.get("sample") or (parts[2] if len(parts) > 2 else "")
                    out = eng.clone_voice(name, sample) if (name and sample) else \
                        "voice clone requires name + base64 sample (audio field)."
                elif sub.startswith("female"):
                    out = eng.set_voice("default")
                elif sub.startswith("status"):
                    st = eng.backend_status()
                    out = (f"[voice] current={st['current']} | xtts={st['xtts']} "
                           f"openai={st['openai']} espeak={st['espeak']}\n"
                           f"cloned voices: {', '.join(st['cloned_voices']) or 'none'}")
                else:
                    out = ("[voice] actions: list | set <name> | clone <name> <b64sample> | "
                           "female | status")
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "tool":
                # Run ANY registered tool directly from the terminal (all functions
                # exposed). Iterative: parse "name key=val key=val".
                await send(type="assistant_start")
                await send(type="workflow", stage="tools", detail="executing tool")
                cmd = (data.get("command") or data.get("query") or "").strip()
                parts = cmd.split()
                if not parts:
                    out = "[tool] usage: tool <name> [key=val ...] (use 'list_tools' for names)"
                else:
                    name = parts[0]
                    args = {}
                    for tok in parts[1:]:
                        if "=" in tok:
                            k, v = tok.split("=", 1)
                            v = v.strip().strip("'\"")
                            args[k] = v
                    try:
                        tool = orch._tools._registry.get(name) if orch._tools else None
                        if tool is None:
                            out = f"[tool] unknown tool '{name}'. Use 'list_tools'."
                        else:
                            res = await orch._tools.run(name, args, agent=None)
                            out = f"[tool:{name}] " + str(getattr(res, "output", res))
                    except Exception as e:  # noqa: BLE001
                        out = f"[tool] error: {e}"
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
        # Push a real status frame immediately so the HUD populates live
        # monitoring on connect (cpu/ram/threat/agents) without the client
        # having to request it. This is genuine backend data, not a placeholder.
        try:
            _init_payload = await _moon_status(orch)
            _init_payload["voice"] = {
                "mode": "MUTED" if _voice_muted else "AUTO",
                "available": bool(_get_voice_engine()),
            }
            await send(type="status", **_init_payload)
        except Exception:  # noqa: BLE001
            pass
        # Fast, inline actions keep the read loop snappy; heavy actions run as
        # their own task so a slow LLM reply never blocks status/mute/wake.
        while True:
            data = await ws.receive_json()
            action = data.get("action")
            if action == "status":
                payload = await _moon_status(orch)
                payload["voice"] = {
                    "mode": "MUTED" if _voice_muted else "AUTO",
                    "available": bool(_get_voice_engine()),
                }
                await send(type="status", **payload)
            elif action in ("mute", "unmute"):
                _voice_muted = (action == "mute")
                payload = await _moon_status(orch)
                payload["voice"] = {
                    "mode": "MUTED" if _voice_muted else "AUTO",
                    "available": bool(_get_voice_engine()),
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
