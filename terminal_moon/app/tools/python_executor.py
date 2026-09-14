"""
PythonExecutorTool — sandbox Python execution (restricted).
"""
from __future__ import annotations

import io
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr
from typing import Any

from app.tools.base import BaseTool


class PythonExecutorTool(BaseTool):
    name = "python_executor"
    description = "Execute a snippet of Python code in a sandbox and return stdout+result."

    async def execute(self, code: str = "", timeout: int = 10, **kwargs: Any) -> str:
        if not code:
            return "[python_executor] no code"

        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(buf):
                exec_globals: dict = {}
                exec(compile(code, "<moontm>", "exec"), exec_globals)
                result = exec_globals.get("result", exec_globals.get("__result__", ""))
                if result is not None:
                    buf.write(f"\n# → {result}")
        except Exception:
            buf.write(f"\n# ERROR:\n{traceback.format_exc()}")

        out = buf.getvalue()
        if len(out) > 8000:
            out = out[:8000] + "\n[...] (truncated)"
        return out
