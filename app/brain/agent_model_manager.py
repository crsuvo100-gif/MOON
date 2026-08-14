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


# ---------------------------------------------------------------------------
# Per-agent AI model map  (THE core of "every agent runs on its own model").
#
# Each MOON agent is assigned a model best-suited to its FUNCTION. Model ids are
# Ollama tags. `None` => use the global default (settings.model_name).
#
# CPU-only host constraint: the active assignments below are restricted to the
# small models that actually load on this box (~0.6b-3b). The
# RECOMMENDED_FOR_CAPABLE_HW map lists the stronger models to use when MOON runs
# on a machine with a GPU / >16 GB RAM -- set them in .env / agent overrides to
# raise accuracy. The model manager pulls any tag lazily via `ollama pull`.
# ---------------------------------------------------------------------------

# Models that load comfortably on the current CPU-only host.
_M_CPU = "qwen2.5:3b"
_M_CPU_SMALL = "qwen2.5:1.5b"
_M_CODER = "qwen2.5-coder:1.5b"
_M_REASON = "deepseek-r1:1.5b"   # reasoning model for math/science/logic
_M_TINY = "qwen2.5:1.5b"

AGENT_MODELS: dict[str, str | None] = {
    # --- Code / engineering ------------------------------------------------
    "coding": _M_CODER,
    "debug": _M_CODER,
    "toolsmith": _M_CODER,
    "github_sync": _M_CODER,
    "qa": _M_CODER,
    "infra": _M_CPU,

    # --- Reasoning / math / science ----------------------------------------
    "math": _M_REASON,
    "science": _M_REASON,
    "data_science": _M_CPU,
    "strategist": _M_CPU,

    # --- Research / knowledge ----------------------------------------------
    "research": _M_CPU,
    "search": _M_CPU,
    "fact_checker": _M_CPU,
    "browser": _M_CPU,
    "summarizer": _M_CPU_SMALL,
    "memory": _M_CPU_SMALL,

    # --- Language / writing ------------------------------------------------
    "writing": _M_CPU_SMALL,
    "design": _M_CPU_SMALL,
    "translation": _M_CPU,
    "legal": _M_CPU,
    "medical": _M_CPU,
    "finance": _M_CPU,

    # --- Security / cyber (defensive + offensive, within authz gate) --------
    "security": _M_CPU,
    "cyber": _M_CPU,
    "red_team": _M_CPU,
    "blue_team": _M_CPU,
    "purple_team": _M_CPU,
    "forensics": _M_CPU,
    "reverse_eng": _M_CPU,
    "threat_hunt": _M_CPU,
    "siem": _M_CPU,

    # --- Coordination / meta -----------------------------------------------
    "planning": _M_CPU,
    "coordinator": _M_CPU,
    "manager": _M_CPU,
    "router": _M_TINY,          # pure classification -> smallest/fastest
    "review": _M_CPU,
    "critic": _M_CPU,
    "audio": _M_CPU_SMALL,      # text-side reasoning; STT handled separately

    # Agents NOT listed here (e.g. "vision", "voice") fall back to the global
    # default model for their text reasoning; their multimodal models are set
    # in AGENT_MULTIMODAL below.
}

# Multimodal models per agent. These are NOT pulled automatically on a CPU host
# (they need a GPU to be useful); set them via .env / overrides when hardware
# allows. The agent's text reasoning still uses AGENT_MODELS / the default.
AGENT_MULTIMODAL: dict[str, dict[str, str | None]] = {
    "vision": {"vision": "llava:7b", "fallback_text": _M_CPU},
    "voice":  {"audio": "qwen2-audio", "fallback_text": _M_CPU_SMALL},
    "audio":  {"audio": "qwen2-audio", "fallback_text": _M_CPU_SMALL},
}

# Stronger models recommended for capable hardware. Operators can copy these
# into AGENT_MODELS (or set STRONG_MODEL_NAME) when MOON runs on a GPU host.
RECOMMENDED_FOR_CAPABLE_HW: dict[str, str] = {
    "coding": "qwen2.5-coder:7b",
    "debug": "qwen2.5-coder:7b",
    "math": "deepseek-r1:8b",
    "science": "qwen3:8b",
    "data_science": "qwen3:8b",
    "research": "qwen3:8b",
    "security": "qwen3:8b",
    "cyber": "qwen3:8b",
    "red_team": "qwen3:8b",
    "blue_team": "qwen3:8b",
    "purple_team": "qwen3:8b",
    "forensics": "qwen3:8b",
    "reverse_eng": "qwen3:8b",
    "threat_hunt": "qwen3:8b",
    "siem": "qwen3:8b",
    "legal": "qwen3:8b",
    "medical": "qwen3:8b",
    "finance": "qwen3:8b",
    "vision": "llava:13b",
    "audio": "qwen2-audio:7b",
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
        """Resolve the text-reasoning model for an agent (covers ALL registered
        agents: listed ones use their mapped model, everything else inherits the
        global default)."""
        return AGENT_MODELS.get(agent) or self._default

    def multimodal_for(self, agent: str) -> dict[str, str | None]:
        """Return the multimodal model spec for an agent (may be empty)."""
        return dict(AGENT_MULTIMODAL.get(agent, {}))

    def recommended_for(self, agent: str) -> str | None:
        """Recommended stronger model when running on capable hardware."""
        return RECOMMENDED_FOR_CAPABLE_HW.get(agent)

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

    def all_preferred_models(self) -> set[str]:
        """Every model the agent roster needs (text + multimodal fallbacks)."""
        models: set[str] = {self._preferred(a) for a in AGENT_MODELS}
        models.add(self._default)
        for spec in AGENT_MULTIMODAL.values():
            fb = spec.get("fallback_text")
            if fb:
                models.add(fb)
        return {m for m in models if m}

    async def prefetch_all(self, max_parallel: int = 2) -> dict[str, bool]:
        """Startup routine: pull every distinct preferred model so agents are
        ready instantly. Best-effort; reports per-model success and never
        raises. Runs a few pulls concurrently to stay fast."""
        import asyncio

        models = sorted(self.all_preferred_models())
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
