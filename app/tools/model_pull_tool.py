"""model_pull_tool.py -- let MOON (or an agent) pull/install an AI model.

Thin wrapper over `ollama pull` so any agent can fetch a model it needs for its
function. Best-effort; reports success/failure. This is the mechanism behind
"every agent pulls and installs its own model."
"""

from __future__ import annotations

import shutil
import subprocess

from app.tools.base import BaseTool


class ModelPullTool(BaseTool):
    name = "model_pull"
    description = "Pull/install an Ollama model by id (e.g. 'qwen2.5:3b'). Enables per-agent models."

    async def execute(self, model: str = "", **kwargs) -> str:
        if not model:
            return "[model_pull] supply a model id, e.g. 'qwen2.5:3b'"
        if not shutil.which("ollama"):
            return "[model_pull] ollama not found on this host."
        try:
            r = subprocess.run(["ollama", "pull", model], capture_output=True, text=True, timeout=600)
            if r.returncode == 0:
                return f"[model_pull] '{model}' installed successfully."
            return f"[model_pull] pull failed: {(r.stderr or r.stdout)[:300]}"
        except Exception as exc:  # noqa: BLE001
            return f"[model_pull] error: {exc}"
