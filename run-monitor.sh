#!/bin/bash
# run-monitor.sh — MOON 전체 운영 상태 모니터링 + 자동 복구
# moonscope 백엔드 + moonscope TUI + terminal_moon TUI + LLM 종합 점검
set -euo pipefail

MOON_HOME="${MOON_HOME:-/home/meow/Projects/MOON}"
LOG_DIR="$MOON_HOME/logs"
mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_DIR/run-monitor.log"; }

check_backend() {
    curl -s --max-time 5 http://127.0.0.1:8777/api/health >/dev/null 2>&1
}

check_moonscope_tui() {
    pgrep -af "moonscope_tui.py|app.tui|textual.app" >/dev/null 2>&1
}

check_terminal_moon() {
    pgrep -af "terminal_moon.*app.tui|terminal_moon.*main.py.*terminal" >/dev/null 2>&1
}

check_llm() {
    curl -s --max-time 15 -X POST http://127.0.0.1:11434/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"qwen2.5:1.5b\",\"messages\":[{\"role\":\"user\",\"content\":\"reply exactly: PING_OK\"}],\"max_tokens\":10,\"temperature\":0}" 2>/dev/null | grep -q "PING_OK"
}

heal_backend() {
    log "ACTION: moonscope 백엔드(8777) 응답 없음 — 재시작"
    systemctl --user restart moon-terminal.service 2>/dev/null || true
    sleep 3
    if check_backend; then
        log "OK: moon-terminal.service 재시작 완료, 백엔드 응답 중"
    else
        log "FAIL: 재시작 후에도 백엔드 응답 없음"
    fi
}

heal_moonscope_tui() {
    log "ACTION: moonscope TUI 프로세스 없음 — 실행"
    cd "$MOON_HOME"
    nohup .venv/bin/python moonscope_tui.py >> "$LOG_DIR/moonscope_tui.log" 2>&1 &
    log "OK: moonscope_tui.py 백그라운드 실행 (PID $!)"
}

heal_terminal_moon() {
    log "ACTION: terminal_moon TUI 프로세스 없음 — 실행"
    cd "$MOON_HOME/terminal_moon"
    nohup .venv/bin/python -m app.tui >> "$LOG_DIR/terminal_moon.log" 2>&1 &
    log "OK: terminal_moon TUI 백그라운드 실행 (PID $!)"
}

heal_llm() {
    log "ACTION: LLM(Ollama) 무응답 — 확인"
    if curl -s --max-time 5 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        log "OK: Ollama 응답 중 (LLM 무응답은 일시적일 수 있음)"
    else
        log "FAIL: Ollama 응답 불가 — ollama serve 확인 필요"
    fi
}

run_check() {
    log "=== MOON 모니터링 체크 ==="
    local be_ok=0 tm_ok=0 mt_ok=0 llm_ok=0
    
    check_backend && { be_ok=1; log "  백엔드(8777): OK"; } || log "  백엔드(8777): DOWN"
    check_moonscope_tui && { mt_ok=1; log "  moonscope TUI: RUNNING"; } || log "  moonscope TUI: DOWN"
    check_terminal_moon && { tm_ok=1; log "  terminal_moon TUI: RUNNING"; } || log "  terminal_moon TUI: DOWN"
    check_llm && { llm_ok=1; log "  LLM(Ollama): RESPONSIVE"; } || log "  LLM(Ollama): UNRESPONSIVE"
    
    # 자동 복구
    if [[ $be_ok -eq 0 ]]; then heal_backend; fi
    if [[ $mt_ok -eq 0 ]]; then heal_moonscope_tui; fi
    if [[ $tm_ok -eq 0 ]]; then heal_terminal_moon; fi
    if [[ $llm_ok -eq 0 ]]; then heal_llm; fi
    
    log "=== 체크 완료 ==="
}

case "${1:-all}" in
    once)
        run_check
        ;;
    loop)
        INTERVAL="${2:-60}"
        log "모니터링 루프 시작 (주기: ${INTERVAL}s)"
        while true; do
            run_check
            sleep "$INTERVAL"
        done
        ;;
    all)
        run_check
        log "반복 모니터링: $0 loop [초]"
        ;;
    *)
        echo "사용법: $0 [once|loop [초]|all]"
        exit 1
        ;;
esac
