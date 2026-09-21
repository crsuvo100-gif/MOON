#!/usr/bin/env bash
# tmux_start.sh — moonscope + terminal_moon TUI를 tmux 세션으로 실행
# 사용법: ./tmux_start.sh [moonscope|terminal_moon|both]
set -euo pipefail

MOON_HOME="${MOON_HOME:-/home/meow/Projects/MOON}"
SESSION="${SESSION:-moon-tui}"
MODE="${1:-both}"  # moonscope | terminal_moon | both

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# tmux 설치 확인
if ! command -v tmux &>/dev/null; then
    echo "ERROR: tmux 설치 필요: sudo apt install tmux"
    exit 1
fi

# 기존 세션 정리
if tmux has-session -t "$SESSION" 2>/dev/null; then
    log "기존 tmux 세션 '$SESSION' 종료"
    tmux kill-session -t "$SESSION"
fi

log "tmux 세션 '$SESSION' 생성 (모드: $MODE)"

case "$MODE" in
    moonscope)
        tmux new-session -d -s "$SESSION" -n "moonscope"
        tmux send-keys -t "$SESSION" "cd $MOON_HOME && python moonscope_tui.py" Enter
        log "moonscope TUI tmux 세션에서 실행 중: tmux attach -t $SESSION"
        ;;
    terminal_moon)
        tmux new-session -d -s "$SESSION" -n "terminal_moon"
        tmux send-keys -t "$SESSION" "cd $MOON_HOME/terminal_moon && .venv/bin/python -m app.tui" Enter
        log "terminal_moon TUI tmux 세션에서 실행 중: tmux attach -t $SESSION"
        ;;
    both)
        tmux new-session -d -s "$SESSION" -n "moonscope"
        tmux send-keys -t "$SESSION" "cd $MOON_HOME && python moonscope_tui.py" Enter
        tmux split-window -h -t "$SESSION"
        tmux send-keys -t "$SESSION" "cd $MOON_HOME/terminal_moon && .venv/bin/python -m app.tui" Enter
        tmux select-layout -t "$SESSION" even-horizontal
        log "moonscope + terminal_moon tmux 세션에서 실행 중: tmux attach -t $SESSION"
        ;;
    *)
        echo "사용법: $0 [moonscope|terminal_moon|both]"
        exit 1
        ;;
esac

log "완료. tmux attach -t $SESSION 으로 접속"
