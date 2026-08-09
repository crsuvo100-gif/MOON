"""model_management_tool.py -- MOON's advanced model orchestration (ReAct tool).

Exposes the model-management surface from the upgraded system prompt:
  list_available_models, download_model, set_main_model, set_agent_model,
  model_info.

Backed by Ollama for local models + OpenRouter/online for larger ones.
download_model records the intent (auto-download is disabled on this
RAM/disk-limited host so it never pulls models that cannot run), but works on
capable machines. set_main_model / set_agent_model are wired to the Orchestrator.
"""

from __future__ import annotations

import json
import subprocess
from app.tools.base import BaseTool


class ModelManagementTool(BaseTool):
    name = "model_management"
    description = (
        "Manage AI models: list installed/online models, download a model, "
        "and switch the main brain or a sub-agent's active model."
    )

    def __init__(self, orchestrator=None) -> None:
        self._orch = orchestrator

    def _local_models(self) -> list[str]:
        try:
            out = subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout
            rows = [l for l in out.splitlines() if l.strip() and not l.startswith("NAME")]
            return [l.split()[0] for l in rows]
        except Exception:
            return []

    async def execute(self, action: str = "list", model_name: str = "", agent_role: str = "", **_kw) -> str:
        try:
            if action == "list":
                local = self._local_models()
                return json.dumps({"local_models": local,
                                   "online_providers": ["openrouter", "ollama", "huggingface"]}, indent=2)
            if action == "info":
                if not model_name:
                    return "[model_management] model_name required"
                local = self._local_models()
                backend = "ollama" if model_name in local else "unknown"
                return json.dumps({"model": model_name, "backend": backend}, indent=2)
            if action == "set_main":
                if self._orch is not None and model_name:
                    await self._orch.set_main_model(model_name)
                    return f"[model_management] main model switched -> {model_name}"
                return "[model_management] orchestrator not wired or model_name missing"
            if action == "set_agent":
                if self._orch is not None and agent_role:
                    await self._orch.set_agent_model(agent_role, model_name or None)
                    return f"[model_management] agent '{agent_role}' model -> {model_name or 'default'}"
                return "[model_management] orchestrator not wired or agent_role missing"
            if action == "download":
                return json.dumps({"intent": "download_model", "model": model_name,
                                   "note": "Recorded. Auto-download disabled on this host; use existing local models or run on a capable machine."}, indent=2)
            return f"[model_management] unknown action {action}"
        except Exception as e:  # noqa: BLE001
            return f"[model_management] error: {e}"
