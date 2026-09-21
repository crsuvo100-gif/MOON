#!/usr/bin/env python3
"""
moonscope_monitor.py — moonscope 백엔드(8777) + TUI 프로세스 헬스체크.

백엔드 헬스: /api/health (HEALTHY 여부)
TUI 프로세스: moonscope_tui.py 또는 python -m app.tui 실행 중인지
트리거 시: moon-monitor.service/style로 로깅 또는 재시작 트리거
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("moonscope-monitor")


BACKEND_PORT = 8777
TUI_CMD = [str(ROOT / "moonscope_tui.py")]  # python moonscope_tui.py
# 대체: [sys.executable, "-m", "app.tui"]


def backend_healthy() -> bool:
    """moonscope 백엔드(8777)가 /api/health로 HEALTHY 응답하는지 확인."""
    import httpx
    try:
        r = httpx.get(f"http://127.0.0.1:{BACKEND_PORT}/api/health", timeout=5.0)
        d = r.json()
        return str(d.get("status", "")).upper() == "HEALTHY"
    except Exception:
        return False


def tui_running() -> bool:
    """moonscope TUI 프로세스가 실행 중인지 확인 (subprocess 조회)."""
    try:
        r = subprocess.run(
            ["pgrep", "-f", "moonscope_tui.py|app.tui|textual.app"],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def main_loop(interval: int = 30) -> None:
    """주기적 헬스체크. 백엔드 다운 시 재시작 권고 로그, TUI 다운 시 알림."""
    log.info("moonscope-monitor 시작 (백엔드:%d, 주기:%ds)", BACKEND_PORT, interval)
    while True:
        be_ok = backend_healthy()
        tui_ok = tui_running()
        status = "OK" if (be_ok and tui_ok) else "ISSUE"
        log.info("백엔드:%s TUI:%s [%s]",
                 "HEALTHY" if be_ok else "DOWN",
                 "RUNNING" if tui_ok else "DOWN",
                 status)
        if not be_ok:
            log.warning("moonscope 백엔드(%d) 응답 없음 — moon-terminal.service 재시작 고려", BACKEND_PORT)
        if not tui_ok:
            log.warning("moonscope TUI 프로세스 없음 — moonscope_tui.py 실행 필요")
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        log.info("moonscope-monitor 종료")
