#!/usr/bin/env bash
# moon-launch.sh -- run MOON anywhere with one command.
#
# Portable launcher for MOON. It:
#   1. Ensures her model backend (Ollama) is reachable on OLLAMA_HOST, starting
#      the systemd service when possible (needs root/`sudo` for that step only).
#   2. Boots MOON's terminal interface (default) or dashboard.
#
# Works headless (servers/VMs) and on the desktop. No build step required beyond
# a ready Python venv (see `make install` / INSTALL notes).
#
# Usage:
#   ./moon-launch.sh                 # terminal UI on 127.0.0.1:8777
#   ./moon-launch.sh dashboard       # Flask+SocketIO dashboard on :5000
#   ./moon-launch.sh run "hi Moon"   # one-shot task via main.py
#   OLLAMA_HOST=127.0.0.1:11434 ./moon-launch.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
MODE="${1:-terminal}"

# --- 1. Ensure Ollama backend is up (best-effort, non-fatal) ---------------
ollama_up() { curl -s -o /dev/null -m 3 "http://$OLLAMA_HOST/api/tags" || return 1; }
if ollama_up; then
  echo "🌙 Ollama backend already reachable at $OLLAMA_HOST"
else
  echo "🌙 Ollama not reachable at $OLLAMA_HOST -- attempting to start service"
  if command -v systemctl >/dev/null 2>&1; then
    if [[ $EUID -eq 0 ]]; then
      systemctl start ollama || true
    elif command -v sudo >/dev/null 2>&1; then
      sudo systemctl start ollama || true
    fi
  fi
  # Give it a few seconds; MOON still launches even if this fails (operator can start it).
  for _ in $(seq 1 10); do ollama_up && break; sleep 1; done
  ollama_up && echo "🌙 Ollama backend is up" || echo "⚠️  Ollama still down -- start it manually (sudo systemctl start ollama)"
fi

# --- 2. Boot MOON ----------------------------------------------------------
export PYTHONPATH=""   # avoid foreign-venv contamination (see app/config/env_guard.py)
PY=./.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "⚠️  No .venv found at $PY -- create one: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

case "$MODE" in
  terminal|serve|start)
    echo "🌙 MOON Terminal starting at http://127.0.0.1:8777"
    exec "$PY" main.py start
    ;;
  dashboard)
    echo "🌙 MOON Dashboard starting at http://127.0.0.1:5000"
    exec "$PY" main.py dashboard
    ;;
  run)
    shift || true
    TASK="${*:-Say hello.}"
    echo "🌙 MOON running: $TASK"
    exec "$PY" main.py run "$TASK"
    ;;
  *)
    echo "Usage: $0 [terminal|dashboard|run <task>]"
    exit 1
    ;;
esac
