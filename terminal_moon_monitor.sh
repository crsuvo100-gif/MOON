#!/bin/bash
# terminal_moon_monitor.sh — terminal_moon TUI 실행 + 헬스체크
# terminal_moon은 standalone TUI (직접 LLM 연결, 백엔드 불필요)
set -euo pipefail

MOON_HOME="${MOON_HOME:-/home/meow/Projects/MOON}"
TM_DIR="$MOON_HOME/terminal_moon"
LOG_DIR="$MOON_HOME/logs"
TM_LOG="$LOG_DIR/terminal_moon_monitor.log"
mkdir -p "$LOG_DIR"

export MOON_TUI_UNLOCK="${MOON_TUI_UNLOCK:-MOON love you 3000}"
export MODEL_BASE_URL="${MODEL_BASE_URL:-http://127.0.0.1:11434/v1}"
export MODEL_NAME="${MODEL_NAME:-qwen2.5:1.5b}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$TM_LOG"; }

log "terminal_moon TUI 시작"
cd "$TM_DIR"
nohup .venv/bin/python -m app.tui >> "$TM_LOG" 2>&1 &
TM_PID=$!
echo $TM_PID > "$LOG_DIR/terminal_moon.pid"
log "terminal_moon TUI PID: $TM_PID"

sleep 8
if kill -0 "$TM_PID" 2>/dev/null; then
    log "terminal_moon TUI 실행 중 (PID $TM_PID)"
else
    log "ERROR: terminal_moon TUI 실행 실패"
    exit 1
fi

if curl -s --max-time 5 http://127.0.0.1:8777/api/health >/dev/null 2>&1; then
    log "moonscope 백엔드(8777): 응답 중"
else
    log "WARN: moonscope 백엔드(8777) 응답 없음"
fi

log "terminal_moon 모니터링 완료"
wait "$TM_PID" 2>/dev/null || true
