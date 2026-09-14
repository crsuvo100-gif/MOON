#!/usr/bin/env python3
"""moonscope_tui.py — moonscope Textual TUI 독립 실행형 러너.

이 스크립트는 독립적으로 moonscope TUI를 부팅하며, 백엔드(8777) 연결 없이
로컬 LLM 직접 연결도 지원한다.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
sys.path.insert(0, ROOT)


def main() -> None:
    """moonscope Textual TUI 실행."""
    from app.tui import main as tui_main
    raise SystemExit(tui_main())


if __name__ == "__main__":
    main()
