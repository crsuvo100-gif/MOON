#!/usr/bin/env python3
"""
moon-tui-monitor.py — MOON moonscope TUI 세션 + 백엔드 + LLM 종합 감시 데몬.

TUI 프로세스는 살아있지만 LLM이 응답하지 않거나, 백엔드가 다운된 상황을
감지하여 로그를 남기고 알림을 발생시킨다. SSH 터미널에서 TUI가 떠 있으나
MOON이 응답하지 않는 시나리오 탐지가 주 목적.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import logging
import json as _json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("moon-tui-monitor")

BACKEND_PORT = 8777
OLLAMA_PORT = 11434
LLM_MODEL = os.environ.get("MODEL_NAME", "qwen2.5:1.5b")
TUI_PATTERNS = ["moonscope_tui.py", "app.tui", "textual.app"]
MON_LOG = ROOT / "logs" / "moon-tui-monitor.log"
MON_LOG.parent.mkdir(parents=True, exist_ok=True)
STATE_FILE = ROOT / "data" / "moon-tui-monitor.state.json"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _log_event(event: str = "", detail: str = "") -> None:
    """로그 이벤트 기록 (콘솔 + 파일)."""
    line = f"[{_now()}] {event}" + (f" — {detail}" if detail else "")
    log.info(detail)
    try:
        with open(MON_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def backend_healthy() -> bool:
    """moonscope 백엔드(8777)가 응답하는지 확인."""
    import httpx
    try:
        r = httpx.get(f"http://127.0.0.1:{BACKEND_PORT}/api/health", timeout=5.0)
        return r.json().get("status") == "healthy"
    except Exception:
        return False


def tui_sessions_alive() -> list[dict]:
    """실행 중인 moonscope/terminal_moon TUI 세션을 찾아 상태 반환."""
    sessions: list[dict] = []
    try:
        r = subprocess.run(
            ["pgrep", "-af", "|".join(TUI_PATTERNS)],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return sessions
        for line in r.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            pid = parts[0]
            cmd = " ".join(parts[1:])
            try:
                with open(f"/proc/{pid}/status") as f:
                    for l in f:
                        if l.startswith("State:"):
                            state = l.split()[1]
                            if state.startswith("Z"):
                                continue
                            break
            except FileNotFoundError:
                continue
            sessions.append({"pid": pid, "cmd": cmd, "state": "alive"})
    except Exception:
        pass
    return sessions


def llm_responsive() -> bool:
    """Ollama가 LLM 응답을 줄 수 있는지 빠른 체크 (경량 프롬프트)."""
    import httpx
    try:
        r = httpx.post(
            f"http://127.0.0.1:{OLLAMA_PORT}/v1/chat/completions",
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": "reply exactly: PING_OK"}],
                "max_tokens": 10,
                "temperature": 0.0,
            },
            timeout=15.0,
        )
        if r.status_code == 200:
            d = _json.loads(r.text)
            content = d.get("choices", [{}])[0].get("message", {}).get("content", "")
            return "PING_OK" in content
    except Exception:
        pass
    return False


def save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(
            _json.dumps(state, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        pass


def main_loop(interval: int = 15, max_alerts_per_minute: int = 3) -> None:
    """주기적 종합 감시 루프."""
    _log_event("moon-tui-monitor 시작",
               f"백엔드:{BACKEND_PORT} Ollama:{OLLAMA_PORT} LLM:{LLM_MODEL} 주기:{interval}s")
    alert_count = 0
    last_alert_minute = int(time.time() / 60)

    while True:
        be = backend_healthy()
        tuis = tui_sessions_alive()
        llm = llm_responsive()

        tui_count = len(tuis)
        tui_pids = [s["pid"] for s in tuis]

        status = "OK" if (be and tui_count > 0 and llm) else "ISSUE"
        detail = (
            f"백엔드:{'UP' if be else 'DOWN'} "
            f"TUI:{tui_count}개(pid={','.join(tui_pids) if tui_pids else '없음'}) "
            f"LLM:{'RESP' if llm else 'UNRESP'} "
            f"→ {status}"
        )

        if status == "OK":
            _log_event("OK", detail)
        else:
            alert_count += 1
            now_minute = int(time.time() / 60)
            if now_minute != last_alert_minute:
                alert_count = 1
                last_alert_minute = now_minute
            if alert_count <= max_alerts_per_minute:
                issues: list[str] = []
                if not be:
                    issues.append(f"백엔드({BACKEND_PORT}) DOWN")
                if tui_count == 0:
                    issues.append("TUI 세션 없음 (터미널에서 moonscope_tui.py 또는 terminal_moon TUI 실행 필요)")
                if not llm:
                    issues.append(f"LLM({LLM_MODEL}@127.0.0.1:{OLLAMA_PORT}) 무응답")
                _log_event("ALERT", "; ".join(issues))

        state = {
            "timestamp": _now(),
            "backend": "UP" if be else "DOWN",
            "tui_sessions": tui_count,
            "tui_pids": tui_pids,
            "llm": "RESP" if llm else "UNRESP",
            "overall": status,
        }
        save_state(state)

        if int(time.time() / 60) != last_alert_minute:
            alert_count = 0
            last_alert_minute = int(time.time() / 60)

        time.sleep(interval)


def print_status() -> None:
    """한 번 체크하고 결과를 출력 (cron/수작업 진단용)."""
    be = backend_healthy()
    tuis = tui_sessions_alive()
    llm = llm_responsive()
    print("MOON TUI Monitor — 상태 스냅샷")
    print("=" * 50)
    print(f"  백엔드(8777): {'UP' if be else 'DOWN'}")
    print(f"  TUI 세션: {len(tuis)}개")
    for s in tuis:
        print(f"    PID {s['pid']}: {s['cmd'][:60]}")
    print(f"  LLM({LLM_MODEL}): {'RESPONSIVE' if llm else 'UNRESPONSIVE'}")
    overall = "OK" if (be and len(tuis) > 0 and llm) else "ISSUE"
    print(f"  결과: {overall}")
    if overall == "ISSUE":
        if not be:
            print("    → moon-terminal.service 재시작: systemctl --user restart moon-terminal.service")
        if len(tuis) == 0:
            print("    → moonscope_tui.py 실행: cd /home/meow/Projects/MOON && python moonscope_tui.py")
            print("    → terminal_moon TUI: cd /home/meow/Projects/MOON/terminal_moon && .venv/bin/python -m app.tui")
        if not llm:
            print(f"    → Ollama 확인: curl http://127.0.0.1:{OLLAMA_PORT}/api/tags")
    print("=" * 50)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        print_status()
    else:
        try:
            main_loop()
        except KeyboardInterrupt:
            _log_event("종료")
