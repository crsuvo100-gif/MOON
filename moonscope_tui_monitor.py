#!/usr/bin/env python3
"""
moonscope_tui_monitor.py - moonscope TUI 세션 + 백엔드 + LLM 종합 감시 데몬.
"""
import subprocess, json, time, logging, sys, os
from pathlib import Path

BACKEND_PORT = 8777
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
OLLAMA_PORT = 11434
OLLAMA_URL = f"http://127.0.0.1:{OLLAMA_PORT}"
LOG_DIR = Path("/tmp")
LOG_FILE = LOG_DIR / "moonscope-tui-monitor.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stderr), logging.FileHandler(LOG_FILE)]
)
logger = logging.getLogger("moonscope_tui_monitor")

def backend_healthy() -> bool:
    """moonscope 백엔드 /api/health 응답 확인."""
    import httpx
    try:
        r = httpx.get(f"{BACKEND_URL}/api/health", timeout=5)
        return r.status_code == 200 and str(r.json().get("status", "")).upper() == "HEALTHY"
    except Exception as e:
        logger.warning(f"Backend health check failed: {e}")
        return False

def tui_running() -> bool:
    """moonscope TUI 프로세스가 살아있는지 확인."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "moonscope_tui.py|app.tui"],
            capture_output=True, text=True, timeout=5
        )
        return bool(result.stdout.strip())
    except Exception as e:
        logger.warning(f"TUI running check failed: {e}")
        return False

def llm_responsive() -> bool:
    """Ollama LLM이 응답하는지 확인."""
    import httpx
    try:
        r = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": "qwen2.5:1.5b", "prompt": "x", "stream": False},
            timeout=10
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"LLM check failed: {e}")
        return False

def main_loop(interval=10):
    """무한 루프: 백엔드 TUI LLM 상태를 주기적으로 체크하고 로깅."""
    logger.info(f"moonscope_tui_monitor 시작 (백엔드:{BACKEND_PORT}, Ollama:{OLLAMA_PORT}, 주기:{interval}s)")
    while True:
        try:
            bh = backend_healthy()
            tr = tui_running()
            lr = llm_responsive()
            detail = f"백엔드:{'UP' if bh else 'DOWN'} TUI:{'1개' if tr else 'DEAD'} LLM:{'RESP' if lr else 'NO_RESP'}"
            if bh and tr and lr:
                logger.info(f"OK | {detail}")
            elif not bh:
                logger.warning(f"ALERT | 백엔드 DOWN | {detail}")
            elif not tr:
                logger.warning(f"ALERT | moonscope TUI 미실행 | {detail}")
            elif not lr:
                logger.warning(f"ALERT | LLM 무응답 | {detail}")
            else:
                logger.warning(f"ALERT | 복합 이상 | {detail}")
        except Exception as e:
            logger.error(f"체크 루프 오류: {e}")
        time.sleep(interval)

if __name__ == "__main__":
    main_loop()
