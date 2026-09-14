# MOON — 운영 메시지 (MOTD)

## 시스템 상태 (2026-09-14)

### moonscope (FULL STACK)
- **백엔드 (port 8777)**: HEALTHY — 34 REST 라우트 + 3 WebSocket 엔드포인트 + 태스크 실행 API
- **프론트엔드**: Textual TUI — 뇌 대시보드(BrainCorePanel) + HUD(BrainHUD/StatusHUD) + 채팅(ChatPanel) + 입력
- **LLM**: qwen2.5:1.5b via Ollama (127.0.0.1:11434)
- **잠금 해제**: boot 시 unlocked (잠금 구절: `MOON love you 3000`)

### terminal_moon (STANDALONE TUI)
- **프론트엔드**: Textual TUI — StatusHUD + ChatPanel + 입력
- **LLM**: direct 연결 (백엔드 불필요, standalone)
- **잠금 해제**: boot 시 unlocked (잠금 구절: `MOON love you 3000`)

### 모니터링
- `run-monitor.sh` — 전체 MOON 상태 종합 체크 (백엔드 + TUI + LLM)
- `moon-tui-monitor.py` — 백엔드/TUI/LLM 자동 폴링 + 로깅 + 알림
- `moonscope_monitor.py` — moonscope 백엔드/TUI 전용 모니터
- systemd timer: 매 30초 자동 체크

## 실행 방법

```bash
# moonscope TUI
./moonscope_tui.py              # moonscope TUI (백엔드 연결 + 뇌 대시보드)
./tmux_start.sh both            # moonscope + terminal_moon tmux 세션

# terminal_moon TUI
cd terminal_moon && .venv/bin/python -m app.tui

# 모니터링
./run-monitor.sh                # 한 번 체크
./run-monitor.sh loop 30        # 30초 주기 모니터링
python moon-tui-monitor.py      # 자동 폴링 모니터 (백엔드/TUI/LLM)

# 시스템 서비스
systemctl --user status moon-terminal.service    # 백엔드
systemctl --user status moon-monitor.timer       # 모니터 타이머
systemctl --user status moonscope-tui-monitor.timer   # moonscope TUI 모니처 타이머

# 잠금 해제 구절 (공통)
# MOON love you 3000
```

## GitHub
- 원격: `git@github.com:crsuvo100-gif/MOON.git`
- branch: `master`
- local == remote: 확인 후 푸시
