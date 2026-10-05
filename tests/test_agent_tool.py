import pytest
import asyncio
from app.tools.terminal import TerminalTool

@pytest.mark.asyncio
async def test_terminal_tool():
    request = {
        "command": "echo hello",
        "cwd": ".",
        "backend": "local",
        "shell": False,
        "timeout": 10,
        "background": False,
        "interactive": False,
        "permission_mode": "auto",
    }
    result = await TerminalTool().execute(request=request)
    assert isinstance(result, dict)
    assert result.get("status") == "success"
    assert "hello" in (result.get("stdout") or "")

