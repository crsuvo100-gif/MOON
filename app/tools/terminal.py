"""Shell command execution tool (hosted, guarded).

Provides a guard‑ed terminal execution that respects MOON's risk, permission, backend, and verification pipelines.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.tools.base import BaseTool
from app.terminal.execution_engine import ExecutionEngine
from app.terminal.models import ExecutionRequest, ExecutionResult

class TerminalTool(BaseTool):
    """Agent‑visible terminal tool.

    Accepts a ``request`` argument (dict or ExecutionRequest) and runs it via
    MOON's ``ExecutionEngine``. Returns the ``ExecutionResult`` as a plain dict.
    """

    name = "terminal"
    description = "Execute a command with full terminal model (risk, backend, verification)."

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        request_obj = kwargs.get("request")
        if request_obj is None:
            return {"error": "Missing 'request' argument"}
        if isinstance(request_obj, ExecutionRequest):
            exec_req = request_obj
        else:
            exec_req = ExecutionRequest.parse_obj(request_obj)
        engine = ExecutionEngine()
        result: ExecutionResult = engine.execute(exec_req)  # type: ignore[arg-type]
        return result.dict()
