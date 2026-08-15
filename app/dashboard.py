"""dashboard.py -- MOON's web dashboard (Flask + SocketIO).

Provides:
  - GET /                      : dashboard HTML
  - GET /video_feed            : MJPEG stream from the default camera (if opencv available)
  - SocketIO 'user_command'    : routes text through MOON's orchestrator (run_fn)
  - SocketIO 'stream_message'  : pushes MOON's streamed thoughts to the browser
  - stream_start/stop via socket

Auth: the dashboard is local-only by default. Set MOON_DASHBOARD_TOKEN to require
it; otherwise it binds to 127.0.0.1. No secrets are ever logged.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

DASHBOARD_TOKEN = os.environ.get("MOON_DASHBOARD_TOKEN", "")
BIND_HOST = os.environ.get("MOON_DASHBOARD_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("MOON_DASHBOARD_PORT", "5000"))


def create_dashboard(run_fn) -> Flask:
    """run_fn(prompt: str) -> str  (coroutine) is MOON's orchestrator entry."""
    try:
        from flask import Flask
        from flask_socketio import SocketIO, emit
    except Exception as e:
        raise RuntimeError("Flask/SocketIO not installed: pip install flask flask-socketio") from e
    app = Flask("moon_dashboard")
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

    streaming = {"active": False, "cap": None}

    @app.route("/")
    def index():
        from flask import Response, request
        token = request.args.get("token", "")
        if DASHBOARD_TOKEN and token != DASHBOARD_TOKEN:
            return Response("Unauthorized", status=401)
        return _HTML

    @app.route("/video_feed")
    def video_feed():
        from flask import Response, request
        token = request.args.get("token", "")
        if DASHBOARD_TOKEN and token != DASHBOARD_TOKEN:
            return Response("Unauthorized", status=401)
        try:
            import cv2
        except Exception:
            return Response("camera/unavailable", status=503)
        return Response(_gen_camera(cv2, streaming), mimetype="multipart/x-mixed-replace; boundary=frame")

    @socketio.on("user_command")
    def on_command(data):
        text = (data or {}).get("text", "")
        if not text:
            return
        try:
            result = asyncio.run_coroutine_threadsafe(_safe_run(run_fn, text), _loop()).result(timeout=180)
        except Exception as e:  # noqa: BLE001
            result = f"[dashboard] error: {e}"
        emit("assistant_response", {"text": result})

    @socketio.on("stream_start")
    def on_stream_start():
        streaming["active"] = True
        emit("stream_status", {"active": True})

    @socketio.on("stream_stop")
    def on_stream_stop():
        streaming["active"] = False
        emit("stream_status", {"active": False})

    # expose socketio so other modules can push stream updates
    app.config["socketio"] = socketio
    app._moon_socketio = socketio
    return app


def push_stream(text: str) -> None:
    sio = getattr(_dashboard_app, "_moon_socketio", None) if _dashboard_app else None
    if sio:
        try:
            sio.emit("stream_message", {"text": text})
        except Exception:  # noqa: BLE001
            pass


# ---- internal helpers ----
_dashboard_app = None
_loop_ref = None


def _loop():
    return _loop_ref


async def _safe_run(run_fn, text):
    return await run_fn(text)


def _gen_camera(cv2, streaming):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            _, jpeg = cv2.imencode(".jpg", frame)
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
            if not streaming["active"]:
                time.sleep(0.05)
    finally:
        cap.release()


_HTML = """<!DOCTYPE html>
<html><head><title>🌙 MOON Dashboard</title>
<style>body{font-family:system-ui;background:#0b0e14;color:#e6e6e6;margin:0;padding:20px}
h1{color:#ff8fce}#chat{height:60vh;overflow:auto;border:1px solid #333;border-radius:8px;padding:12px;background:#11151f}
.msg{margin:6px 0}.me{color:#7fd1ff}.moon{color:#ffd479}
input{width:70%;padding:8px;border-radius:6px;border:1px solid #333;background:#11151f;color:#fff}
button{padding:8px 14px;border:none;border-radius:6px;background:#ff8fce;color:#111}
img{width:100%;border-radius:8px;margin-top:10px}</style></head>
<body><h1>🌙 MOON — Neural Brain Command Center</h1>
<div id="chat"></div>
<input id="t" placeholder="Talk to MOON (unlock with passphrase)..." onkeydown="if(event.key==='Enter')send()">
<button onclick="send()">Send</button>
<img id="cam" src="/video_feed" style="display:none">
<button onclick="toggleCam()">Toggle Camera</button>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<script>
var s=io();var c=document.getElementById('chat');
function add(cls,t){var d=document.createElement('div');d.className='msg '+cls;d.textContent=cls+': '+t;c.appendChild(d);c.scrollTop=c.scrollHeight;}
s.on('assistant_response',d=>add('moon',d.text));
s.on('stream_message',d=>add('moon','(stream) '+d.text));
function send(){var t=document.getElementById('t').value;if(!t)return;add('me',t);
  s.emit('user_command',{text:t});document.getElementById('t').value='';}
function toggleCam(){var x=document.getElementById('cam');x.style.display=x.style.display==='none'?'block':'none';}
</script></body></html>"""


def run_dashboard(run_fn, app=None):
    """Start the dashboard in a daemon thread (non-blocking)."""
    global _dashboard_app, _loop_ref
    import asyncio as _a
    _loop_ref = _a.new_event_loop()
    threading.Thread(target=_loop_ref.run_forever, daemon=True).start()
    flask_app = app or create_dashboard(run_fn)
    _dashboard_app = flask_app
    socketio = flask_app.config.get("socketio")
    threading.Thread(target=lambda: socketio.run(flask_app, host=BIND_HOST, port=BIND_PORT,
                                                     debug=False, use_reloader=False,
                                                     allow_unsafe_werkzeug=True),
                     daemon=True).start()
    logger.info("MOON dashboard on http://%s:%s", BIND_HOST, BIND_PORT)
    return flask_app
