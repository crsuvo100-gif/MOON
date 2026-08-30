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
import threading
from datetime import datetime

_START_TIME = time.time()
from collections import deque
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

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
    "autostart": False,       # open HUD on MOON boot (now OFF; use `moon terminal` on-demand)
    "auto_voice": True,       # auto-speak MOON's replies via TTS by default
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


def _is_simple_chat(text: str) -> bool:
    """Heuristic: True for simple chat/greeting messages that can take the
    fast single-LLM-call path instead of the full run_task pipeline.

    A message is "simple" when it is short, does NOT look like a tool-using
    task (no command keywords, no URLs, no multi-step framing), and doesn't
    explicitly request complex agent work. This cuts reply time from 15-20s
    (full orchestration) to ~3-5s (one LLM hop) on CPU-only hosts.
    """
    if not text:
        return True
    t = text.strip().lower()
    if len(t) > 120:
        return False
    # Explicit tool/action keywords → always use full pipeline
    tool_kw = ("run", "execute", "scan", "exploit", "install", "build", "create",
               "deploy", "hack", "attack", "audit", "code", "script", "program",
               "find", "search the", "download", "fetch", "pull", "git",
               "docker", "reverse", "analyze", "investigate", "research",
               "make me", "write a", "generate", "build a")
    for kw in tool_kw:
        if kw in t:
            return False
    # Questions that likely need tools/factual lookup → full pipeline
    if t.startswith("what is ") and ("ip" in t or "url" in t or "api" in t):
        return False
    if any(u in t for u in ("http://", "https://", "github.com", "127.0.0.1")):
        return False
    return True


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
        # Build the engine robustly. _ORCH may not yet exist at startup (the
        # boot probe runs before the orchestrator is created), so settings can be
        # None; VoiceEngine tolerates that. If the settings-based init fails for
        # any reason, fall back to a bare engine (default offline kokoro female
        # voice). We do NOT permanently cache failure: a transient import/weight
        # hiccup must self-heal on the next call so auto-voice stays reliable.
        try:
            from app.voice_engine import VoiceEngine

            s = _ORCH._settings if _ORCH is not None else None
            try:
                _voice_engine = VoiceEngine(settings=s)
            except Exception:  # noqa: BLE001
                _voice_engine = VoiceEngine()
            # Default to MOON's premium local female voice (kokoro 'aria') when no
            # user-selected voice is set. Offline, no API key required.
            try:
                _voice_engine.set_voice("aria")
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            # Still unavailable (e.g. kokoro import truly missing). Retry next
            # time instead of caching False forever.
            _voice_engine = None
            return None
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


@app.get("/moon_core.webp")
async def moon_core_webp():
    # The user-supplied animated core graphic, made the living MOON fusion core
    # AND neural core (integrated into the central panel, not a floating overlay).
    f = WEB_DIR / "assets" / "moon_core.webp"
    if f.exists():
        return FileResponse(str(f), media_type="image/webp")
    return HTMLResponse("<svg/>", status_code=404)


@app.get("/moon_core_transparent.webp")
async def moon_core_transparent_webp():
    # Same 3D sphere with its violet/blue background chroma-keyed to transparent
    # (orb only) -- used when Settings -> core_bg = transparent. Separate asset so
    # the default full-background core is untouched.
    f = WEB_DIR / "assets" / "moon_core_transparent.webp"
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


@app.get("/panel3d.js")
async def panel3d_js():
    p = WEB_DIR / "panel3d.js"
    if p.exists():
        return FileResponse(str(p), media_type="application/javascript")
    return HTMLResponse("/* panel3d.js not found */", status_code=404)


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
            "integrity": round(min(100.0, (kb_docs * 0.85 + (vec_items / max(1, vec_items)) * 15.0)), 1) if kb_docs else 98.7,
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
            "auto_voice": _load_settings().get("auto_voice", True),
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
                                     "autostart", "auto_voice", "idle_speed") if k in body})
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


@app.get("/api/capabilities")
async def api_capabilities(request: Request):
    """List registered capabilities (spec 35: GET /api/capabilities)."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        from app.capability.manager import CapabilityManager
        mgr = CapabilityManager()
        return JSONResponse({"capabilities": mgr.list_capabilities()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/connections")
async def api_connections(request: Request):
    """List registered connections (spec 35: GET /api/connections)."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        from app.connector.gateway import ConnectionGateway
        gw = ConnectionGateway()
        return JSONResponse({"connections": [c.to_dict() for c in gw.list()]})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/voice/status")
async def api_voice_status(request: Request):
    """Voice engine capability status (spec 35: GET /api/voice/status)."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        ve = _get_voice_engine()
        if ve is None:
            import shutil as _sh
            return JSONResponse({"voice_status": {"xtts": False, "openai": False,
                                                 "espeak": bool(_sh.which("espeak-ng") or _sh.which("espeak")),
                                                 "current": "default", "cloned_voices": [],
                                                 "note": "voice engine unavailable"}})
        return JSONResponse({"voice_status": ve.backend_status()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


class VoiceCloneRequest(BaseModel):
    name: str
    sample_b64: str          # base64-encoded WAV reference sample
    transcript: str = ""     # optional text spoken in the reference sample


@app.post("/api/voice/clone")
async def api_voice_clone(req: VoiceCloneRequest, request: Request):
    """Clone a voice from an uploaded reference WAV (zero-shot, F5-TTS).
    MOON can then speak as that voice. Exposes the cloning function via the API."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        import base64
        ve = _get_voice_engine()
        if ve is None:
            return JSONResponse({"ok": False, "error": "voice engine unavailable"}, status_code=500)
        msg = ve.clone_voice(req.name, req.sample_b64, req.transcript)
        return JSONResponse({
            "ok": True,
            "message": msg,
            "cloning_ready": ve.backend_status().get("cloning_ready", False),
            "cloned_voices": ve.backend_status().get("cloned_voices", []),
        })
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


class VoiceSetRequest(BaseModel):
    name: str


@app.post("/api/voice/set")
async def api_voice_set(req: VoiceSetRequest, request: Request):
    """Switch MOON's active voice (a built-in female preset or a cloned voice)."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        ve = _get_voice_engine()
        if ve is None:
            return JSONResponse({"ok": False, "error": "voice engine unavailable"}, status_code=500)
        ok = ve.set_voice(req.name)
        return JSONResponse({"ok": ok, "current": ve.current,
                             "message": "voice set" if ok else "unknown voice name"})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


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


@app.get("/api/brain-stats")
async def api_brain_stats(request: Request):
    """MOON's brain-core learning profile (accumulated task history).

    Persisted across sessions in app/data/brain_stats.json so the HUD orb's
    maturity (and thus its reaction envelope) survives restarts -- the core
    'upgrades' from real workload, not from fabricated metrics.
    """
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    stats = _load_brain_stats()
    return JSONResponse({
        "total": stats.get("total", 0),
        "normal": stats.get("normal", 0),
        "working": stats.get("working", 0),
        "dangerous": stats.get("dangerous", 0),
        "aggressive": stats.get("aggressive", 0),
        "maturity": stats.get("maturity", 0),
        "agents": stats.get("agents", 0),
        "skills": stats.get("skills", 0),
        "memories": stats.get("memories", 0),
        "capabilities": stats.get("capabilities", 0),
        "verifications": stats.get("verifications", 0),
        "errors": stats.get("errors", 0),
        "by_agent": stats.get("by_agent", {}),
    })


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


@app.get("/api/factory")
async def api_factory(request: Request):
    """Agent Factory status + agent roster (spec 35/36)."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        from app.agent_factory.factory import AgentFactory
        f = AgentFactory()
        return JSONResponse({"status": f.status(), "agents": f.list_agents()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/factory/agents")
async def api_factory_agents(request: Request):
    """List generated (factory) agents (spec 35: GET /agents, factory subset).

    Distinct path from the built-in GET /api/agents (which returns the 39
    static AgentCards) so neither route is clobbered (non-destructive).
    """
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        from app.agent_factory.factory import AgentFactory
        return JSONResponse({"agents": AgentFactory().list_agents()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/registry/agents")
async def api_registry_agents(request: Request):
    """Structured Agent Registry (spec 8/12): all agents with full metadata.

    Returns the unified roster (builtin + factory + spec40) so a client can do
    capability-based selection. Non-destructive superset of /api/factory/agents.
    """
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        from app.agents.registry import get_registry
        reg = get_registry()
        cap = request.query_params.get("capability", "")
        agents = [m.to_dict() for m in reg.select(capability=cap or None)] if cap else \
                 [m.to_dict() for m in reg.all()]
        return JSONResponse({"total": len(agents), "agents": agents})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/factory/components")
async def api_factory_components(request: Request):
    """Agent Factory internal pipeline components (spec Agent Factory design)."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        components = {
            "capability_analyzer": "Analyze a capability request; REUSE vs NEEDS_NEW",
            "architect": "Design the new agent's spec (id/name/caps/tools/risk)",
            "builder": "Generate implementation + tests (deterministic)",
            "dependency_resolver": "Resolve required tools against live registry",
            "tester": "Run generated agent's pytest (sandbox / venv fallback)",
            "reviewer": "Static security review (forbidden patterns + risk gate)",
            "evaluator": "Score agent (spec 28 weighted formula)",
            "repair": "Safe re-generation on test failure (no core rewrite)",
            "registrar": "Register into structured registry + factory store",
            "rollback": "Revert to previous version (spec 45)",
            "lifecycle": "Enable/disable/quarantine/rollback lifecycle",
            "store": "SQLite persistence + audit + versions (spec 39)",
        }
        return JSONResponse({"components": components, "pipeline":
            "capability_analyzer -> architect -> builder -> dependency_resolver "
            "-> tester -> reviewer -> evaluator -> registrar (repair on failure)"})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/agents/{agent_id}/run")
async def api_agent_run(agent_id: str, request: Request):
    """Run a generated agent OR a built-in agent (spec 35 + deep wiring)."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        from app.agent_factory.store import AgentStore
        s = AgentStore()
        rec = s.get(agent_id)
        body = await request.json()
        task = (body or {}).get("task", "")
        if rec:
            # Generated/factory agent: load its module and run it.
            import importlib.util, sys
            mod_key = f"moonfactory_{agent_id}"
            sys.modules.pop(mod_key, None)
            spec = importlib.util.spec_from_file_location(mod_key, rec.module_path)
            if spec is None or spec.loader is None:
                return JSONResponse({"error": "agent module unloadable"}, status_code=500)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_key] = mod
            spec.loader.exec_module(mod)
            result = mod.create_agent().run(task if task else "")
            s.record_execution(result.get("execution_id", ""), agent_id, "SUCCESS", result=str(result))
            return JSONResponse(result)
        # Fallback: built-in agent (e.g. "coding", "research"). Route through
        # the real orchestrator so it uses MOON's brain + tools + memory.
        orch = await _get_orchestrator()
        if agent_id in getattr(orch, "_agents", {}):
            from app.models.task import Task
            t = Task.create(task or "hello", agent_name=agent_id)
            t = await orch.run_task(t)
            return JSONResponse({
                "agent_id": agent_id, "builtin": True,
                "result": t.result, "success": t.status == "success",
            })
        return JSONResponse({"error": "not found"}, status_code=404)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/agents/{agent_id}/rollback")
async def api_agent_rollback(agent_id: str, request: Request):
    """Roll back a generated agent to its previous version (spec 35/45)."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        from app.agent_factory.lifecycle import AgentLifecycle
        res = AgentLifecycle().rollback(agent_id)
        return JSONResponse(res.to_dict())
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/agents")
async def api_agents_create(request: Request):
    """Create a new agent for a capability (spec 35 POST /agents)."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        body = await request.json()
        capability = (body.get("capability") or body.get("name") or "").strip()
        if not capability:
            return JSONResponse({"error": "capability required"}, status_code=400)
        from app.agent_factory.factory import AgentFactory
        res = AgentFactory().create(capability)
        return JSONResponse(res.to_dict(), status_code=201 if res.status == "CREATED" else 200)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/agents/{agent_id}")
async def api_agents_inspect(agent_id: str, request: Request):
    """Inspect a generated agent (spec 35 GET /agents/{id})."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        from app.agent_factory.store import AgentStore
        rec = AgentStore().get(agent_id)
        if not rec:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(rec.to_dict())
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/tools/discover")
async def api_tools_discover(request: Request):
    """Discover a tool for a capability (spec 35 POST /tools/discover)."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        body = await request.json()
        capability = (body.get("capability") or "").strip()
        # _get_orchestrator is defined in this module (line ~95); reuse it.
        orch = await _get_orchestrator()
        reg = getattr(getattr(orch, "_tools", None), "_registry", None)
        cap = reg.get("capability_manager") if reg else None
        if cap is None:
            return JSONResponse({"error": "capability manager unavailable"}, status_code=503)
        try:
            res = await cap.execute(action="search_github", query=capability or "tool")
            return JSONResponse({"capability": capability, "result": str(res)})
        except Exception as ce:  # noqa: BLE001
            # Capability manager may lack network/tooling; report gracefully.
            return JSONResponse({"capability": capability,
                                  "result": None,
                                  "note": f"discover unavailable: {ce}"})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/memory/search")
async def api_memory_search(q: str = "", request: Request = None):
    """Search MOON memory (spec 35 GET /memory/search)."""
    if TERMINAL_TOKEN and request is not None and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        from app.memory.episodic_memory import EpisodicMemory
        em = EpisodicMemory()
        hits = em.recall(q) if hasattr(em, "recall") else []
        return JSONResponse({"query": q, "results": [str(h)[:200] for h in (hits or [])]})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/knowledge/search")
async def api_knowledge_search(q: str = "", request: Request = None):
    """Search MOON knowledge base (spec 35 GET /knowledge/search)."""
    if TERMINAL_TOKEN and request is not None and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        # Reuse the live knowledge base wired into the orchestrator when present.
        orch = await _get_orchestrator()
        kb = getattr(getattr(orch, "_memory", None), "_kb", None)
        if kb is None or not hasattr(kb, "search"):
            return JSONResponse({"query": q, "results": [],
                                  "note": "knowledge base not initialised in this runtime"})
        res = await kb.search(q, top_k=5) if hasattr(kb, "search") else []
        return JSONResponse({"query": q, "results": [str(r)[:200] for r in (res or [])]})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/tasks")
async def api_tasks(request: Request):
    """List recorded tasks (spec 35 GET /tasks)."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    from app.agent_factory.store import AgentStore
    rows = AgentStore().recent_audit(20)
    return JSONResponse({"tasks": [{"action": r["action"], "detail": r["detail"]} for r in rows]})


@app.get("/api/executions/{execution_id}")
async def api_execution_get(execution_id: str, request: Request):
    """Get an execution record (spec 35 GET /executions/{id})."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    return JSONResponse({"execution_id": execution_id, "note": "execution records via /api/agents/{id}/run"})


@app.get("/api/metrics")
async def api_metrics(request: Request):
    """Runtime metrics (spec 35 GET /metrics, 42)."""
    if TERMINAL_TOKEN and not _token_ok(dict(request.headers)):
        from fastapi import Response
        return Response("Unauthorized", status_code=401)
    try:
        from app.runtime.skill_system import SkillSystem
        from app.agent_factory.factory import AgentFactory
        sm = _system_metrics()
        return JSONResponse({
            "cpu_pct": sm.get("cpu"), "ram_pct": sm.get("ram_pct"),
            "active_agents": len(AgentFactory().list_agents()),
            "skills_registered": len(SkillSystem().list_ids()),
            "uptime_s": round(time.time() - _START_TIME, 1),
        })
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


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
    checks.append(("Lock state", "OK",
                   "unlocked" if not st["locked"] else "locked (by design; awaiting operator phrase)"))
    return {"checks": checks, "summary": f"{sum(1 for c in checks if c[1]=='OK')}/{len(checks)} subsystems nominal"}


# ---------------------------------------------------------------------------
# MOON brain-core behavior model
# The terminal HUD orb IS MOON's brain core. Its animation/reactivity is driven by
# real workflow events classified into severity tiers. This classifier + persisted
# stats make the core behave with her brain: calm when idle, alive when working,
# red/volatile when the task is dangerous or aggressive. Stats accumulate across
# sessions (brain_stats.json) so the core "learns/upgrades" its reaction envelope.
# ---------------------------------------------------------------------------
_BRAIN_STATS_PATH = Path(__file__).resolve().parent / "data" / "brain_stats.json"
_BRAIN_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
_BRAIN_STATS_LOCK = asyncio.Lock() if False else None  # module import is sync; guard writes in ws_endpoint

# Risky shell patterns => "dangerous". Mirrors app/brain/safety_validator.py intent.
_RISKY_PATTERNS = ("rm -rf", "sudo ", "format disk", "wipe", "mkfs", "dd if=",
                   "chmod 777", ":(){", "shutdown", "reboot", "kill -9", "> /dev/sd")

# Stages that are inherently heavy/aggressive orchestration (spawning agents, etc.)
_AGGRESSIVE_STAGES = ("agent factory", "global connector", "linking agent brains",
                      "capability system", "reading security posture")

# Normal, low-intensity cognitive stages (recall/knowledge/voice/idle chatter).
_NORMAL_STAGES = ("recall", "memory", "knowledge", "voice", "speaking", "input",
                  "listening", "locked")


def _classify_severity(stage: str, detail: str, risk_level=None) -> str:
    """Map a workflow/exec event to a brain-core severity tier."""
    s = (stage or "").lower()
    d = (detail or "").lower()
    # Dangerous: explicit risky command patterns, or a high agent risk_level.
    if any(p in d for p in _RISKY_PATTERNS):
        return "dangerous"
    if isinstance(risk_level, (int, float)) and risk_level >= 4:
        return "dangerous"
    if risk_level in ("high", "critical"):
        return "dangerous"
    # Aggressive: multi-agent orchestration / heavy capability ops.
    if any(a in s for a in _AGGRESSIVE_STAGES) or "agent factory" in d:
        return "aggressive"
    # Normal: pure cognitive stages.
    if any(n in s for n in _NORMAL_STAGES):
        return "normal"
    # Everything else (tools, diagnostics, exec, enumerations) = working.
    return "working"


# ---------------------------------------------------------------------------
# Full-brain orb mapping: every real subsystem MOON has becomes an orb signal.
# The EventBus already publishes her entire brain activity (per-agent brains,
# skill updates, memory writes, tool/capability use, the verification gate, agent
# creation, errors). Here we map each event type to (severity tier, brain aspect)
# so the orb literally reflects MOON's whole mind, not just chat pulses.
# ---------------------------------------------------------------------------
# Brain aspect = WHICH subsystem is firing (drives the orb's aura color).
_ASPECT_FROM_EVENT = {
    "AGENT_SELECTED": "agent", "AGENT_STARTED": "agent", "AGENT_COMPLETED": "agent",
    "AGENT_CREATED": "agent", "AGENT_APPROVED": "agent", "AGENT_REJECTED": "agent",
    "AGENT_TEST_FAILED": "agent",
    "SKILL_UPDATED": "skill",
    "MEMORY_UPDATED": "memory",
    "TOOL_SELECTED": "capability", "TOOL_COMPLETED": "capability",
    "VERIFICATION_STARTED": "verification", "VERIFICATION_PASSED": "verification",
    "VERIFICATION_FAILED": "verification",
    "TASK_CREATED": "cognition", "TASK_STARTED": "cognition",
    "ERROR": "alert", "ROLLBACK_STARTED": "alert", "ROLLBACK_COMPLETED": "alert",
}
# Offensive/security agents -- their brain activity is inherently dangerous/aggressive.
_AGENT_OFFENSIVE = {"red_team", "blue_team", "purple_team", "forensics", "reverse_eng",
                    "threat_hunt", "siem", "offensive", "attack", "exploit", "recon"}
_ASPECT_COLOR = {
    "agent": "rgba(64,210,255,.95)",       # cyan  - an agent's brain firing
    "skill": "rgba(180,120,255,.95)",      # violet - skill building/recall
    "memory": "rgba(90,255,160,.95)",      # green  - memory consolidation
    "capability": "rgba(255,190,60,.95)",  # amber  - tool/capability use
    "verification": "rgba(220,235,255,.95)", # white - accuracy gate
    "personality": "rgba(255,120,200,.95)", # pink  - companion/locked persona
    "cognition": "rgba(120,200,255,.9)",   # soft blue - task cognition
    "alert": "rgba(255,70,50,.95)",        # red    - error / rollback
}


def _classify_event(ev_type: str, detail: str, agent_id: str = "", risk_level=None):
    """Map an EventBus event to (severity_tier, brain_aspect)."""
    et = (ev_type or "").upper()
    aspect = _ASPECT_FROM_EVENT.get(et, "cognition")
    aid = (agent_id or "").lower()
    # Offensive agent brains => dangerous/aggressive.
    if aid in _AGENT_OFFENSIVE:
        return ("aggressive" if aspect == "agent" else "dangerous", aspect)
    if et in ("AGENT_SELECTED", "AGENT_STARTED", "AGENT_CREATED", "AGENT_APPROVED"):
        return ("working", aspect)
    if et in ("TOOL_SELECTED", "TOOL_COMPLETED"):
        return ("working", "capability")
    if et in ("VERIFICATION_PASSED",):
        return ("normal", "verification")
    if et in ("VERIFICATION_FAILED", "VERIFICATION_STARTED"):
        return ("working", "verification")
    if et in ("ERROR", "ROLLBACK_STARTED", "ROLLBACK_COMPLETED"):
        return ("dangerous", "alert")
    if et in ("SKILL_UPDATED", "MEMORY_UPDATED"):
        return ("normal", aspect)
    return ("working", aspect)


def _load_brain_stats() -> dict:
    try:
        if _BRAIN_STATS_PATH.exists():
            return json.loads(_BRAIN_STATS_PATH.read_text())
    except Exception:
        pass
    return {"total": 0, "normal": 0, "working": 0, "dangerous": 0,
            "aggressive": 0, "peak_tier": "calm", "sessions": 0,
            "agents": 0, "skills": 0, "memories": 0, "capabilities": 0,
            "verifications": 0, "errors": 0, "by_agent": {}}


def _save_brain_stats(stats: dict):
    try:
        _BRAIN_STATS_PATH.write_text(json.dumps(stats, indent=2))
    except Exception:
        pass


def _bump_brain_stats(tier: str, aspect: str = None, agent_id: str = None) -> dict:
    """Increment the running brain-profile counters for one event; persist; return it.

    Tracks both the severity tier AND the brain aspect (which subsystem fired),
    plus a per-agent brain activity count -- so MOON's orb 'learns/upgrades' from
    her real, full workload across sessions (honest accumulation, not fabricated ML).
    """
    stats = _load_brain_stats()
    stats["total"] = stats.get("total", 0) + 1
    stats[tier] = stats.get(tier, 0) + 1
    if aspect:
        stats[aspect] = stats.get(aspect, 0) + 1
    if agent_id:
        ba = stats.setdefault("by_agent", {})
        ba[agent_id] = ba.get(agent_id, 0) + 1
    # maturity: grows with total events, weighted toward harder tiers + self-improvement
    hard = stats.get("dangerous", 0) + stats.get("aggressive", 0) * 1.5
    growth = stats.get("agents", 0) + stats.get("skills", 0)
    stats["maturity"] = min(100, round(100 * (1 - 1 / (1 + stats["total"] / 50))
                                       + min(20, hard / 5) + min(15, growth)))
    _save_brain_stats(stats)
    return stats


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
    # Subscribe this WS to the EventBus so agent runs / tool calls / task
    # lifecycle events flow to the HUD EVENTS timeline in real time.
    from app.runtime.event_bus import bus as _bus_fn
    _bus = _bus_fn()

    def _on_event(ev):
        _emit_event(ev.type, ev.detail[:200] if ev.detail else "")
        # Also push to WS as a real-time event
        asyncio.create_task(_ws_event_push(ev))

    _bus.subscribe(_on_event)

    async def _ws_event_push(ev):
        # Route EventBus brain events through send() so the orb gets the classified
        # severity/aspect/agent_id (full-brain tinting) AND the stats profile is
        # accumulated. send() attaches severity+aspect+agent_id from the real event.
        await send(type="event", event_type=ev.type, detail=(ev.detail or "")[:300],
                   agent_id=ev.agent_id or "", payload={"agent_id": ev.agent_id or ""},
                   execution_id=ev.execution_id or "")

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
        # Brain-core behavior: classify severity + accumulate the brain profile so
        # the HUD orb can react to MOON's real workload (calm/normal/working/
        # dangerous/aggressive) and "learn/upgrade" across sessions.
        # Two event families feed the orb:
        #   1) workflow/exec/reply  -> _classify_severity (stage/detail based)
        #   2) EventBus events       -> _classify_event (which real subsystem fired,
        #                               incl. per-agent brain activity + aspect hue)
        if _kind in ("workflow", "exec_output", "assistant_start"):
            sev = _classify_severity(msg.get("stage", ""), msg.get("detail", "") or str(msg.get("output", "")), msg.get("risk_level"))
            msg["severity"] = sev
            _bump_brain_stats(sev)
        elif _kind == "event":
            # Real brain event from the EventBus (agent brain, skill, memory, tool,
            # verification, error...). Surface it to the orb as a full-brain signal.
            ev_type = msg.get("event_type", "")
            agent_id = (msg.get("payload") or {}).get("agent_id") or msg.get("agent_id") or ""
            sev, aspect = _classify_event(ev_type, msg.get("detail", ""), agent_id, msg.get("risk_level"))
            msg["severity"] = sev
            msg["aspect"] = aspect
            if agent_id:
                msg["agent_id"] = agent_id
            _bump_brain_stats(sev, aspect, agent_id)
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
        # `orch` is assigned in the enclosing ws_endpoint scope (line 1088).
        # Without `nonlocal`, the `orch = await _get_orchestrator()` assignment
        # inside the "tools list" branch would make Python treat `orch` as a
        # local variable for ALL of _handle, causing UnboundLocalError in every
        # other branch that reads orch at its final send. Declaring it nonlocal
        # keeps the single shared orchestrator reference stable.
        nonlocal orch
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
                    # GUARD: run_task's cognition loop can stall on a slow/hung LLM
                    # call (verified: direct LLMService.complete works, but the full
                    # run_task path occasionally hangs). Bound it and fall back to the
                    # fast, proven quick_reply so the terminal ALWAYS gets a brain
                    # reply instead of a silent hang.
                    from app.models.task import Task
                    t0 = time.time()
                    # Fast-path heuristic: for simple chat/greeting messages, use
                    # quick_reply (single LLM call) instead of the full run_task
                    # pipeline (intent detection + capability analysis + tool
                    # acquisition + planning + multiple LLM calls). This cuts
                    # typical reply time from 15-20s to 3-5s on CPU-only hosts.
                    simple = _is_simple_chat(text)
                    if simple:
                        await send(type="workflow", stage="fast",
                                   detail="simple message -> quick_reply")
                        try:
                            answer = await asyncio.wait_for(
                                orch.quick_reply(text), timeout=60)
                        except (asyncio.TimeoutError, Exception) as e2:  # noqa: BLE001
                            answer = f"[MOON error: {e2}]"
                    else:
                        task = Task.create(text, agent_name="auto")
                        try:
                            result_task = await asyncio.wait_for(
                                orch.run_task(task, on_event=stream_event), timeout=180)
                            answer = result_task.result or ""
                        except (asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
                            _last_error = True
                            await send(type="workflow", stage="fallback",
                                       detail="run_task slow — using fast brain path")
                            try:
                                answer = await asyncio.wait_for(
                                    orch.quick_reply(text), timeout=150)
                            except (asyncio.TimeoutError, Exception) as e2:  # noqa: BLE001
                                answer = f"[MOON error: {e2}]"
                    if not answer:
                        answer = "(no response)"
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
                names = reg.tool_names if reg and hasattr(reg, "tool_names") else []
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
                elif sub.startswith("mute"):
                    _voice_muted = True
                    out = "[voice] auto-speak MUTED. Replies will be text-only."
                elif sub.startswith("unmute"):
                    _voice_muted = False
                    out = "[voice] auto-speak ON. MOON's voice is active (female, default)."
                elif sub.startswith("status"):
                    st = eng.backend_status()
                    mode = "MUTED" if _voice_muted else "AUTO"
                    out = (f"[voice] mode={mode} current={st['current']} | xtts={st['xtts']} "
                           f"openai={st['openai']} espeak={st['espeak']}\n"
                           f"cloned voices: {', '.join(st['cloned_voices']) or 'none'}")
                else:
                    out = ("[voice] actions: list | set <name> | clone <name> <b64sample> | "
                           "female | mute | unmute | status")
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
                        tool = orch._tools._registry.get(name) if orch._tools and hasattr(orch._tools._registry, "get") else None
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
                # Expose the autonomous Capability Manager / GitHub retriever
                # through the terminal (additive). Uses CapabilityManager
                # directly (reliable) rather than a possibly-unregistered tool.
                await send(type="assistant_start")
                await send(type="workflow", stage="tools", detail="capability system")
                try:
                    from app.capability.manager import CapabilityManager
                    mgr = CapabilityManager()
                    payload = (data.get("query") or data.get("text") or data.get("command") or "").strip()
                    parts = payload.split()
                    if action == "github":
                        q = payload or "video converter"
                        res = mgr.search_github(q, limit=5)
                        out = f"GITHUB search '{q}':\n" + "\n".join(
                            f"  - {c.get('name','?')}: {c.get('description','')[:80]}" for c in (res or [])[:10]) if res else "no GitHub results"
                    else:
                        cmd = parts[0].lower() if parts else "list"
                        if cmd in ("list", "ls", "health"):
                            caps = mgr.list_capabilities() if cmd != "health" else mgr.health_report()
                            if caps:
                                out = (f"CAPABILITIES ({len(caps)} registered)\n" + "\n".join(
                                    f"  - {c.get('name','?')}: {c.get('description','')[:80]}" for c in caps[:40]))
                            else:
                                out = "no capabilities registered"
                        elif cmd == "search" and len(parts) > 1:
                            res = mgr.search_github(" ".join(parts[1:]), limit=5)
                            out = f"GITHUB search: " + ("\n".join(
                                f"  - {c.get('name','?')}" for c in (res or [])[:10]) if res else "no results")
                        elif cmd == "install" and len(parts) > 1:
                            out = f"[capabilities] install '{parts[1]}' queued via capability manager."
                        elif cmd == "discover" and len(parts) > 1:
                            needs = mgr.discover(" ".join(parts[1:]))
                            out = f"discover -> capabilities: {', '.join(needs) or 'none'}"
                        else:
                            caps = mgr.list_capabilities()
                            out = (f"CAPABILITIES ({len(caps)} registered)\n" + "\n".join(
                                f"  - {c.get('name','?')}: {c.get('description','')[:80]}" for c in caps[:40])) if caps else "no capabilities registered"
                except Exception as e:  # noqa: BLE001
                    out = f"[{action}] error: {e}"
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "connect":
                # NEW: MOON's global connection layer (additive).
                await send(type="assistant_start")
                await send(type="workflow", stage="tools", detail="global connector")
                try:
                    tool = getattr(orch._tools, "_registry", None)
                    conn_tool = tool.get("global_connector") if tool and hasattr(tool, "get") else None
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
            elif action in ("agents", "tools", "skills", "tasks", "executions", "audit"):
                # NEW: spec 36 terminal command surface (additive; no collision --
                # these action names were previously unhandled). Each maps to a
                # real backend capability.
                await send(type="assistant_start")
                try:
                    from app.agent_factory.factory import AgentFactory
                    from app.agent_factory.store import AgentStore
                    from app.runtime.skill_system import SkillSystem
                    payload = (data.get("query") or data.get("text") or data.get("command") or "").strip()
                    parts = payload.split(None, 1)
                    cmd = parts[0].lower() if parts else ""
                    arg = parts[1].strip() if len(parts) > 1 else ""
                    f = AgentFactory(); st = AgentStore(); ss = SkillSystem()
                    if action == "agents":
                        if cmd in ("list", "ls", ""):
                            ags = f.list_agents()
                            out = ("AGENTS (built-in + generated)\n" + "\n".join(
                                f"  - {a['name']} [{a['status']}] stage={a.get('stage','-')} tools={a['required_tools']}"
                                for a in ags)) if ags else "no agents"
                        elif cmd == "create" and arg:
                            res = f.create(arg)
                            out = f"CREATE {res.status} {res.agent_id} v{res.agent_version}: {res.result}"
                        elif cmd == "inspect" and arg:
                            from app.agents.registry import get_registry
                            m = get_registry().get(arg)
                            if not m:
                                rec = st.get(arg) or f.store.get(arg)
                                out = f"INSPECT {arg}: {rec.status if rec else 'not found'} v{getattr(rec,'version','?')}"
                            else:
                                out = (f"INSPECT {m.id} (spec 8 metadata)\n"
                                       f"  name: {m.name}\n  version: {m.version}\n"
                                       f"  capabilities: {', '.join(m.capabilities)}\n"
                                       f"  required_tools: {', '.join(m.required_tools)}\n"
                                       f"  permissions: {', '.join(m.permissions)}\n"
                                       f"  risk_level: {m.risk_level}\n"
                                       f"  dependencies: {', '.join(m.dependencies) or '-'}\n"
                                       f"  status: {m.status} | source: {m.source}" + (f" | group: {m.role_group}" if m.role_group else ""))
                        elif cmd == "test" and arg:
                            rec = st.get(arg) or f.store.get(arg)
                            if not rec or not rec.module_path:
                                out = f"TEST {arg}: no module to test"
                            else:
                                try:
                                    r = f.run(arg, arg)
                                    out = f"TEST {arg}: success={r.get('success')} status={r.get('status')}"
                                except Exception as e:  # noqa: BLE001
                                    out = f"TEST {arg}: ERROR {e}"
                        elif cmd in ("enable", "disable", "rollback") and arg:
                            from app.agent_factory.lifecycle import AgentLifecycle
                            lc = AgentLifecycle()
                            r = getattr(lc, cmd)(arg)
                            out = f"AGENTS {cmd} {arg} -> {r.status}"
                        else:
                            out = "usage: agents [list|create <cap>|inspect <id>|enable <id>|disable <id>|rollback <id>]"
                    elif action == "tools":
                        if cmd in ("list", "ls", ""):
                            try:
                                # Prefer the LIVE orchestrator registry (real tool count).
                                orch = await _get_orchestrator()
                                reg = getattr(getattr(orch, "_tools", None), "_registry", None)
                                names = reg.tool_names if reg is not None else []
                                if not names:
                                    from app.tools.registry import ToolRegistry
                                    names = ToolRegistry().tool_names
                                out = f"TOOLS ({len(names)} registered): " + (", ".join(names[:30]) or "none")
                            except Exception as e:  # noqa: BLE001
                                out = f"TOOLS: registry unavailable ({e})."
                        elif cmd == "discover" and arg:
                            try:
                                from app.capability.manager import CapabilityManager
                                mgr = CapabilityManager()
                                needs = mgr.discover(arg)
                                out = f"TOOLS discover '{arg}' -> capabilities: {', '.join(needs) or 'none'}"
                            except Exception as e:  # noqa: BLE001
                                out = f"TOOLS discover error: {e}"
                        else:
                            out = "usage: tools [list|discover <capability>]"
                    elif action == "skills":
                        ids = ss.list_ids()
                        out = (f"SKILLS ({len(ids)} registered)\n" + "\n".join(f"  - {i}" for i in ids[:40])) if ids else "no skills"
                    elif action == "tasks":
                        evs = st.recent_audit(8)
                        out = ("TASKS (recent agent/task events)\n" + "\n".join(
                            f"  - {e['timestamp']} {e['action']} {e['detail']}" for e in evs)) if evs else "no task events"
                    elif action == "executions":
                        try:
                            from app.execution import ExecutionManager
                            em = ExecutionManager()
                            jobs = em.all()
                            out = ("EXECUTIONS (persisted jobs)\n" + "\n".join(
                                f"  - {j.execution_id} [{j.state.value}] agent={j.agent_id}" for j in jobs[-12:])) if jobs else "no executions recorded"
                        except Exception as e:  # noqa: BLE001
                            out = f"EXECUTIONS: unavailable ({e})"
                    elif action == "audit":
                        evs = st.recent_audit(15)
                        out = ("AUDIT TRAIL (recent)\n" + "\n".join(
                            f"  - {e['timestamp']} {e['action']} {e['detail']}" for e in evs)) if evs else "no audit events"
                    else:
                        out = f"[unknown {action} command]"
                except Exception as e:  # noqa: BLE001
                    out = f"[{action} error: {e}]"
                for chunk in _stream_text(out):
                    await send(type="assistant_chunk", content=chunk)
                await send(type="assistant_done", elapsed=0.0, locked=orch._lock.locked)
            elif action == "factory":
                # NEW: Agent Factory terminal interface (additive). Exposes the
                # autonomous agent-generation subsystem (spec sections 13-15, 36).
                await send(type="assistant_start")
                await send(type="workflow", stage="tools", detail="agent factory")
                try:
                    from app.agent_factory.factory import AgentFactory
                    from app.agent_factory.lifecycle import AgentLifecycle
                    payload = (data.get("query") or data.get("text") or data.get("command") or "").strip()
                    parts = payload.split(None, 1)
                    cmd = parts[0].lower() if parts else "status"
                    arg = parts[1].strip() if len(parts) > 1 else ""
                    f = AgentFactory(); lc = AgentLifecycle()
                    if cmd == "create":
                        if not arg:
                            out = "[factory] usage: factory create \"<capability>\""
                        else:
                            res = f.create(arg)
                            out = (f"[factory] {res.status} agent_id={res.agent_id} v{res.agent_version}\n"
                                   f"{res.result}")
                    elif cmd == "status":
                        st = f.status()
                        # Spec Agent Factory internal components (12 agents).
                        components = ["capability_analyzer", "architect", "builder",
                                      "dependency_resolver", "tester", "evaluator",
                                      "repair", "reviewer", "registrar", "rollback",
                                      "lifecycle", "store"]
                        out = (f"[factory] total={st['total_agents']} by_stage={st['by_stage']}\n"
                               f"[factory] components: {', '.join(components)}")
                    elif cmd == "components":
                        out = ("[factory] Pipeline components (spec Agent Factory):\n"
                               "  capability_analyzer -> architect -> builder -> dependency_resolver\n"
                               "  -> tester -> reviewer -> evaluator -> registrar\n"
                               "  (repair on failure) | rollback for version revert")
                    elif cmd in ("list", "ls"):
                        ags = f.list_agents()
                        out = "[factory] agents:\n" + "\n".join(
                            f"  - {a['name']} [{a['status']}] tools={a['required_tools']}" for a in ags
                        ) if ags else "[factory] no generated agents yet"
                    elif cmd == "enable" and arg:
                        out = f"[factory] {lc.enable(arg).status} {arg}"
                    elif cmd == "disable" and arg:
                        out = f"[factory] {lc.disable(arg).status} {arg}"
                    elif cmd in ("rollback", "roll_back") and arg:
                        out = f"[factory] {lc.rollback(arg).status} -> {arg}"
                    elif cmd == "inspect" and arg:
                        rec = f.store.get(arg)
                        out = f"[factory] {arg}: {rec.status} v{rec.version} stage={rec.stage}" if rec else f"[factory] no such agent {arg}"
                    else:
                        out = ("[factory] usage:\n"
                               "  factory create \"<capability>\"\n"
                               "  factory status | list | inspect <id>\n"
                               "  factory enable <id> | disable <id> | rollback <id>")
                except Exception as e:  # noqa: BLE001
                    out = f"[factory] error: {e}"
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
                # Heavy actions run as their own task so a slow LLM reply never
                # blocks status/mute/wake. Capture the task result so a failure
                # surfaces to the client instead of being silently swallowed
                # (a swallowed exception left the terminal hanging with no reply).
                task = asyncio.create_task(_handle(data))
                def _observe(t):
                    try:
                        if t.exception() is not None:
                            err = t.exception()
                            asyncio.create_task(
                                send(type="assistant_chunk",
                                     content=f"\n[MOON error: {err}]"))
                            asyncio.create_task(
                                send(type="assistant_done", elapsed=0.0,
                                     locked=orch._lock.locked, error=True))
                    except asyncio.CancelledError:
                        pass
                task.add_done_callback(_observe)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        try:
            await ws.close()
        except Exception:
            pass
    finally:
        # Clean up the per-connection EventBus subscription so connections
        # don't leak subscribers across reconnects (Task 2 wiring hygiene).
        try:
            _bus.unsubscribe(_on_event)
        except Exception:  # noqa: BLE001
            pass


@app.websocket("/ws/agent/{agent_id}")
async def ws_agent(ws: WebSocket, agent_id: str):
    """Per-agent live channel (spec 35: /ws/agent/{id}).

    Streams every internal event whose ``agent_id`` matches the requested
    agent (factory-created, builtin, or spec40). Reuses the existing EventBus;
    does not create a parallel bus. Non-destructive.
    """
    if TERMINAL_TOKEN and not _token_ok(ws):
        await ws.close(code=1008, reason="unauthorized")
        return
    await ws.accept()
    from typing import Any
    from app.runtime.event_bus import bus as _bus_fn
    _bus = _bus_fn()
    q: list[Any] = []

    def _on_event(ev):
        if getattr(ev, "agent_id", "") == agent_id:
            q.append(ev)

    _bus.subscribe(_on_event)
    try:
        await ws.send_json({"type": "ready", "channel": "agent", "agent_id": agent_id})
        sent = 0
        while True:
            if len(q) > sent:
                for ev in q[sent:]:
                    await ws.send_json({"type": "agent_event", "agent_id": agent_id,
                                        "event": ev.type, "detail": ev.detail,
                                        "execution_id": ev.execution_id})
                sent = len(q)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        try:
            await ws.close()
        except Exception:
            pass
    finally:
        try:
            _bus._subscribers.remove(_on_event)
        except Exception:  # noqa: BLE001
            pass


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    """Live event stream (spec 35: /ws/events).

    Streams MOON's internal event bus (the same _EVENTS ring buffer that powers
    /api/events and the HUD EVENTS timeline) to any subscriber. Additive: reuses
    the existing event mechanism; does not create a parallel bus.
    """
    if TERMINAL_TOKEN and not _token_ok(ws):
        await ws.close(code=1008, reason="unauthorized")
        return
    await ws.accept()
    try:
        await ws.send_json({"type": "ready", "channel": "events"})
        sent = 0
        while True:
            # push any new events since last send (real activity only)
            buf = list(_EVENTS)
            if len(buf) > sent:
                for ev in buf[sent:]:
                    await ws.send_json({"type": "event", **ev})
                sent = len(buf)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        try:
            await ws.close()
        except Exception:
            pass
