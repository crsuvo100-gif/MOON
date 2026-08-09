"""agent_model_manager.py -- every agent runs on its OWN AI model.

Per the system spec, each MOON agent should be able to pull/install and use a
model best suited to its function, then feed its result up to the main MOON
brain for accurate consolidation.

Design
------
- AGENT_MODELS maps each agent to a preferred model id. Most agents use the
  global default (CPU-friendly); specialists can request a stronger/coder/
  math model that Ollama will PULL on first use.
- When an agent runs, it gets its OWN LLMService instance pointed at its model
  (cached). The model is pulled/installed lazily via `ollama pull` if missing
  (best-effort -- falls back to the default model if offline / OOM).
- The agent's draft is still validated by the main MOON brain's two-phase gate,
  so the per-agent result is cross-checked before it reaches the operator.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


# Preferred model per agent. Values are Ollama model ids. `None` => use the
# global default (settings.model_name). On a CPU-only host, larger models are
# pulled only if Ollama can fetch + load them; otherwise we fall back.
AGENT_MODELS: dict[str, str | None] = {
    # General/default agents share the global model.
    "coding": "qwen2.5-coder:1.5b",
    "debug": "qwen2.5-coder:1.5b",
    "math": "qwen2.5:3b",
    "science": "qwen2.5:3b",
    "data_science": "qwen2.5:3b",
    "research": "qwen2.5:3b",
    "security": "qwen2.5:3b",
    "cyber": "qwen2.5:3b",
    "red_team": "qwen2.5:3b",
    "blue_team": "qwen2.5:3b",
    "purple_team": "qwen2.5:3b",
    "forensics": "qwen2.5:3b",
    "reverse_eng": "qwen2.5:3b",
    "threat_hunt": "qwen2.5:3b",
    "siem": "qwen2.5:3b",
    "translation": "qwen2.5:3b",
    "legal": "qwen2.5:3b",
    "medical": "qwen2.5:3b",
    "finance": "qwen2.5:3b",
    # Everyone else uses the global default.
}


class AgentModelManager:
    """Gives each agent its own model-backed LLMService (lazy pull + cache)."""

    def __init__(self, base_url: str, api_key: str, default_model: str,
                 temperature: float = 0.7, max_tokens: int = 2048, timeout: float = 120.0) -> None:
        self._base = base_url
        self._key = api_key
        self._default = default_model
        self._temp = temperature
        self._mtok = max_tokens
        self._to = timeout
        self._cache: dict[str, LLMService] = {}

    @staticmethod
    def _ollama_models() -> set[str]:
        if not shutil.which("ollama"):
            return set()
        try:
            out = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=15).stdout
            names = set()
            for line in out.splitlines()[1:]:
                line = line.strip()
                if line:
                    names.add(line.split()[0])
            return names
        except Exception:  # noqa: BLE001
            return set()

    def _preferred(self, agent: str) -> str:
        return AGENT_MODELS.get(agent) or self._default

    def ensure_model(self, model: str) -> bool:
        """Pull/install a model if missing. Returns True if available (best-effort)."""
        if model == self._default:
            return True  # default assumed available
        present = self._ollama_models()
        if model in present:
            return True
        if not shutil.which("ollama"):
            logger.info("ollama not found; cannot pull %s, using default", model)
            return False
        try:
            logger.info("Agent model '%s' not found locally; pulling...", model)
            r = subprocess.run(["ollama", "pull", model], capture_output=True, text=True, timeout=600)
            if r.returncode == 0:
                logger.info("Pulled agent model '%s'", model)
                return True
            logger.warning("Pull failed for '%s': %s", model, (r.stderr or r.stdout)[:200])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pull error for '%s': %s", model, exc)
        return False

    async def get_llm(self, agent: str) -> LLMService:
        """Return (creating+caching) the agent's dedicated LLMService."""
        if agent in self._cache:
            return self._cache[agent]
        preferred = self._preferred(agent)
        if not self.ensure_model(preferred):
            preferred = self._default  # graceful fallback
        svc = LLMService(
            base_url=self._base, model_name=preferred, api_key=self._key,
            temperature=self._temp, max_tokens=self._mtok, timeout=self._to,
        )
        await svc.setup()
        self._cache[agent] = svc
        logger.info("Agent '%s' bound to model '%s'", agent, preferred)
        return svc

    def status(self) -> dict[str, str]:
        return {a: (self._preferred(a)) for a in set(list(AGENT_MODELS) + [self._default])}

    async def prefetch_all(self, max_parallel: int = 2) -> dict[str, bool]:
        """Startup routine: pull every distinct preferred model so agents are
        ready instantly. Best-effort; reports per-model success and never
        raises. Runs a few pulls concurrently to stay fast."""
        import asyncio

        models = sorted({self._preferred(a) for a in AGENT_MODELS} | {self._default})
        sem = asyncio.Semaphore(max_parallel)
        results: dict[str, bool] = {}

        async def _one(m: str) -> None:
            async with sem:
                loop = asyncio.get_event_loop()
                # run the blocking pull in a thread so we don't block the loop
                ok = await loop.run_in_executor(None, self.ensure_model, m)
                results[m] = bool(ok)

        await asyncio.gather(*(_one(m) for m in models))
        return results

    async def teardown(self) -> None:
        for svc in self._cache.values():
            try:
                await svc.teardown()
            except Exception:  # noqa: BLE001
                pass
        self._cache.clear()
