"""MOON dashboard (Flask + SocketIO). Live command center for the neural core.

Usage:
    moon dashboard     # blocks until Ctrl-C; opens http://127.0.0.1:5000
"""

from __future__ import annotations

import asyncio
import json

from flask import Flask, render_template_string, jsonify
from flask_socketio import SocketIO

APP = Flask(__name__)
APP.config["SECRET_KEY"] = "moon-dashboard-internal"

SOCKETIO = SocketIO(APP, cors_allowed_origins="*", async_mode="threading")


def _html() -> str:
    return r"""
<!doctype html>
<html lang="en">
<head>
<title>MOON DASHBOARD</title>
<style>
  body { background:#040000; color:#ffcbcb; font-family: monospace;
         margin:0; padding:20px; }
  .panel { border:1px solid #7a1f1f; border-radius:6px; padding:12px;
           margin-bottom:14px; background:#0a0000; }
  h2 { color:#ff3b3b; margin:0 0 8px; font-size:14pt; }
  .row { display:flex; gap:12px; flex-wrap:wrap; }
  .col { flex:1 1 200px; }
  .val { color:#ff8a8a; font-size:18pt; font-weight:bold; }
  .lbl { color:#aa6060; font-size:10pt; }
  #events { height:220px; overflow:auto; font-size:11pt;
            background:#000; color:#ffd9d9; padding:8px;
            border:1px solid #5a1a1a; border-radius:4px; }
  .ev { margin-bottom:3px; }
  .ev .ts { color:#7a1f1f; }
  .ev.intake { color:#ff6b6b; }
  .ev.tool { color:#ffaaaa; }
  .ev.agent { color:#cc99ff; }
  .ev.done { color:#88dd88; }
  #log { font-size:10pt; color:#aa6060; max-height:80px; overflow:auto;
         background:#000; padding:6px; border:1px solid #3a1010;
         border-radius:4px; margin-top:6px; }
</style>
</head>
<body>
  <h2>🌙  MOON  ·  COMMAND CENTER</h2>
  <div id="events"></div>
  <div id="log"></div>

  <div class="row">
    <div class="col panel">
      <div class="lbl">LOCKED</div>
      <div class="val" id="locked">—</div>
    </div>
    <div class="col panel">
      <div class="lbl">AGENTS</div>
      <div class="val" id="agents">—</div>
    </div>
    <div class="col panel">
      <div class="lbl">TOOLS</div>
      <div class="val" id="tools">—</div>
    </div>
    <div class="col panel">
      <div class="lbl">MODEL</div>
      <div class="val" id="model">—</div>
    </div>
  </div>

  <div class="row">
    <div class="col panel">
      <h2>MEMORY</h2>
      <div class="val" id="mem-episodic">—</div>
      <div class="lbl">episodic</div>
      <div class="val" id="mem-ltm">—</div>
      <div class="lbl">long-term</div>
      <div class="val" id="mem-stm">—</div>
      <div class="lbl">short-term</div>
    </div>
    <div class="col panel">
      <h2>KNOWLEDGE</h2>
      <div class="val" id="kb-docs">—</div>
      <div class="lbl">kb docs</div>
      <div class="val" id="vec-items">—</div>
      <div class="lbl">vector items</div>
    </div>
    <div class="col panel">
      <h2>SYSTEM</h2>
      <div class="val" id="cpu">—</div>
      <div class="lbl">CPU %</div>
      <div class="val" id="ram">—</div>
      <div class="lbl">RAM %</div>
      <div class="val" id="uptime">—</div>
      <div class="lbl">uptime</div>
    </div>
    <div class="col panel">
      <h2>VOICE</h2>
      <div class="val" id="voice-mode">—</div>
      <div class="lbl">mode</div>
      <div class="val" id="voice-avail">—</div>
      <div class="lbl">available</div>
    </div>
  </div>

<script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
<script>
  var socket = io();

  function evEl(ts, cls, html) {
    return '<div class="ev ' + cls + '">' +
           '<span class="ts">' + ts + '</span> ' + html + '</div>';
  }

  socket.on('connect', function() {
    log('connected to MOON dashboard');
  });

  socket.on('event', function(data) {
    var ts = data.t || '';
    var kind = data.kind || 'info';
    var cls = 'info';
    if (kind === 'intake') cls = 'intake';
    else if (kind === 'tool') cls = 'tool';
    else if (kind === 'agent') cls = 'agent';
    else if (kind === 'done') cls = 'done';
    var el = document.getElementById('events');
    el.insertAdjacentHTML('afterbegin', evEl(ts, cls, data.html || data.detail || ''));
    while (el.children.length > 400) el.removeChild(el.lastChild);
  });

  socket.on('status', function(d) {
    $('#locked').textContent = d.locked ? 'YES' : 'NO';
    $('#agents').textContent = d.agents;
    $('#tools').textContent = d.n_tools;
    $('#model').textContent = d.model || '—';
    $('#mem-episodic').textContent = d.memory.episodic;
    $('#mem-ltm').textContent = d.memory.long_term;
    $('#mem-stm').textContent = d.memory.short_term;
    $('#kb-docs').textContent = d.knowledge.doc_store;
    $('#vec-items').textContent = d.knowledge.doc_store;
    $('#cpu').textContent = d.system.cpu + '%';
    $('#ram').textContent = d.system.ram_pct + '%';
    $('#uptime').textContent = d.uptime_fmt;
    $('#voice-mode').textContent = d.voice.mode;
    $('#voice-avail').textContent = d.voice.available ? 'YES' : 'NO';
  });

  socket.on('telemetry', function(d) {
    if (!d.series || !d.series.length) return;
    var last = d.series[d.series.length - 1];
    $('#cpu').textContent = (last.cpu || 0) + '%';
    $('#ram').textContent = (last.ram || 0) + '%';
  });

  function log(msg) {
    var el = document.getElementById('log');
    el.textContent = msg;
  }
</script>
</body>
</html>
"""


@APP.route("/")
def index() -> str:
    return render_template_string(_html())


@APP.route("/api/status")
def api_status():
    from app.terminal_interface import _get_orchestrator

    try:
        orch = asyncio.run(_get_orchestrator())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
    try:
        from app.terminal_interface import _moon_status
        return jsonify(asyncio.run(_moon_status(orch)))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@APP.route("/api/telemetry")
def api_telemetry():
    from app.terminal_interface import _get_orchestrator

    try:
        orch = asyncio.run(_get_orchestrator())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
    try:
        from app.terminal_interface import _telemetry_snapshot
        return jsonify(_telemetry_snapshot(orch))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


def run_dashboard(run_fn):
    """Block forever, serving the dashboard + a live brain-event stream."""
    import threading

    from app.terminal_interface import (_get_orchestrator, _moon_status,
                                        _telemetry_snapshot, _log)

    _log("dashboard starting on http://127.0.0.1:5000")

    orch = None
    try:
        orch = asyncio.run(_get_orchestrator())
    except Exception as exc:  # noqa: BLE001
        _log(f"dashboard orchestrator boot failed: {exc}")
        orch = None

    @SOCKETIO.on("connect")
    def _on_connect():
        if orch is not None:
            try:
                SOCKETIO.emit("status", _moon_status(orch))
            except Exception:  # noqa: BLE001
                pass

    @SOCKETIO.on("status_req")
    def _on_status_req():
        if orch is not None:
            try:
                SOCKETIO.emit("status", _moon_status(orch))
            except Exception:  # noqa: BLE001
                pass

    @SOCKETIO.on("chat")
    def _on_chat(data):
        if orch is None:
            SOCKETIO.emit("event", {
                "kind": "error",
                "t": "—",
                "html": "core not ready",
            })
            return
        try:
            from app.models.task import Task
            task = Task.create(data.get("text", ""), agent_name="auto")
            result = asyncio.run(orch.run_task(task))
            SOCKETIO.emit("event", {
                "kind": "done",
                "t": "—",
                "html": (result.result or "(no response)")[:300],
            })
        except Exception as exc:  # noqa: BLE001
            SOCKETIO.emit("event", {
                "kind": "error",
                "t": "—",
                "html": str(exc)[:160],
            })

    def _snapshot_loop():
        while True:
            try:
                import time
                time.sleep(2)
                if orch is not None:
                    try:
                        SOCKETIO.emit("telemetry",
                                         _telemetry_snapshot(orch))
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass

    t = threading.Thread(target=_snapshot_loop, daemon=True)
    t.start()

    SOCKETIO.run(APP, host="127.0.0.1", port=5000, debug=False,
                   allow_unsafe_werkzeug=True)
