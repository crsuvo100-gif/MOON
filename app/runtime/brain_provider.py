"""Brain provider abstraction + model health + brain fallback (spec 17, 19, 37).

MOON's agents must not depend on one model vendor. A *Brain* is a configured,
health-checkable handle to a model endpoint; the *provider* is the thing that
knows how to talk to that kind of endpoint. Swapping the provider must never
require touching an Agent (spec 3: the Brain is replaceable, the Agent is
persistent).

    BrainProvider (ABC)
    ├── OllamaProvider            local Ollama / any OpenAI-compatible /v1
    ├── OpenAICompatibleProvider  OpenAI, OpenRouter, vLLM, llama.cpp server, LM Studio
    ├── HuggingFaceProvider       HF Inference API
    └── RemoteProvider            generic remote OpenAI-compatible endpoint

Only the providers the project actually needs are implemented (spec 17).

Every provider exposes a uniform :meth:`BrainProvider.health` returning the
spec-19 fields: availability, provider, model, context_limit, latency, error
state and resource requirement.

:class:`BrainRouter` (spec 18) selects a brain for a task and, when the primary
fails, walks a recorded fallback chain (spec 37) -- never silently pretending
the unavailable brain worked.
"""

from __future__ import annotations

import time
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------
# §19 Model health
# --------------------------------------------------------------------------
@dataclass
class BrainHealth:
    """Spec 19: everything a caller must know before trusting a brain."""

    available: bool = False
    provider: str = ""
    model: str = ""
    endpoint: str = ""
    context_limit: int = 0
    latency_ms: float | None = None
    error: str = ""
    # resource requirement (spec 19 / 32)
    is_remote: bool = False
    est_ram_mb: int = 0
    needs_gpu: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available, "provider": self.provider, "model": self.model,
            "endpoint": self.endpoint, "context_limit": self.context_limit,
            "latency_ms": self.latency_ms, "error": self.error,
            "is_remote": self.is_remote, "est_ram_mb": self.est_ram_mb,
            "needs_gpu": self.needs_gpu,
        }


@dataclass
class BrainSpec:
    """A configured brain: model + endpoint + generation settings (spec 16)."""

    model_id: str
    provider: str = "ollama"
    base_url: str = ""
    api_key: str = ""
    context_limit: int = 8192
    temperature: float = 0.7
    max_tokens: int = 1024
    timeout: float = 60.0
    supports_tools: bool = True
    is_remote: bool = False
    est_ram_mb: int = 0
    needs_gpu: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k != "api_key"}
        d["has_api_key"] = bool(self.api_key)
        return d


# --------------------------------------------------------------------------
# §17 Provider abstraction
# --------------------------------------------------------------------------
class BrainProvider(ABC):
    """Provider-independent interface (spec 17).

    A provider answers two questions: *is this brain alive?* and *what kind of
    endpoint is it?* Inference itself stays in ``LLMService`` so MOON keeps one
    generation path; the provider only owns identity + liveness.
    """

    name: str = "abstract"

    @abstractmethod
    def health(self, spec: BrainSpec) -> BrainHealth:
        """Probe availability and report spec-19 health fields."""

    def supports(self, spec: BrainSpec) -> bool:
        return spec.provider == self.name

    # -- shared helper ----------------------------------------------------
    @staticmethod
    def _http_ok(url: str, timeout: float = 3.0) -> tuple[bool, float | None, str]:
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                ok = 200 <= r.status < 300
            return ok, (time.perf_counter() - t0) * 1000.0, ""
        except Exception as exc:  # noqa: BLE001
            return False, None, f"{type(exc).__name__}: {exc}"


class OllamaProvider(BrainProvider):
    """Local Ollama (and any OpenAI-compatible local server)."""

    name = "ollama"

    def health(self, spec: BrainSpec) -> BrainHealth:
        base = (spec.base_url or "http://127.0.0.1:11434/v1").rstrip("/")
        root = base[:-3] if base.endswith("/v1") else base
        ok, ms, err = self._http_ok(f"{root}/api/tags")
        model_ready = False
        if ok:
            try:
                with urllib.request.urlopen(f"{root}/api/tags", timeout=3) as r:
                    import json
                    tags = json.loads(r.read().decode("utf-8", "replace"))
                names = {m.get("name", "") for m in tags.get("models", [])}
                model_ready = any(n == spec.model_id or n.startswith(spec.model_id + ":")
                                  for n in names)
            except Exception as exc:  # noqa: BLE001
                err = f"tag parse: {exc}"
        return BrainHealth(
            available=bool(ok and model_ready), provider=self.name, model=spec.model_id,
            endpoint=base, context_limit=spec.context_limit, latency_ms=ms,
            error=("" if model_ready else (err or f"model '{spec.model_id}' not pulled")),
            is_remote=spec.is_remote, est_ram_mb=spec.est_ram_mb, needs_gpu=spec.needs_gpu,
        )


class OpenAICompatibleProvider(BrainProvider):
    """OpenAI / OpenRouter / vLLM / llama.cpp-server / LM Studio."""

    name = "openai_compatible"

    def health(self, spec: BrainSpec) -> BrainHealth:
        base = (spec.base_url or "https://api.openai.com/v1").rstrip("/")
        ok, ms, err = self._http_ok(f"{base}/models")
        # An endpoint that requires auth may 401 -- that still proves reachability,
        # but we must not claim the brain is usable without a key.
        if not ok and spec.api_key and "401" in err:
            ok, err = True, ""
        if not ok and "HTTP Error 401" in err and spec.api_key:
            ok, err = True, ""
        usable = bool(ok and (spec.api_key or "127.0.0.1" in base or "localhost" in base))
        return BrainHealth(
            available=usable, provider=self.name, model=spec.model_id, endpoint=base,
            context_limit=spec.context_limit, latency_ms=ms,
            error="" if usable else (err or "missing api key"),
            is_remote=spec.is_remote, est_ram_mb=spec.est_ram_mb, needs_gpu=spec.needs_gpu,
        )


class HuggingFaceProvider(BrainProvider):
    """Hugging Face Inference API (hosted)."""

    name = "huggingface"

    def health(self, spec: BrainSpec) -> BrainHealth:
        base = (spec.base_url or "https://api-inference.huggingface.co").rstrip("/")
        if not spec.api_key:
            return BrainHealth(available=False, provider=self.name, model=spec.model_id,
                               endpoint=base, context_limit=spec.context_limit,
                               error="no HF token configured", is_remote=True,
                               est_ram_mb=0, needs_gpu=False)
        ok, ms, err = self._http_ok(f"{base}/models/{spec.model_id}")
        return BrainHealth(available=ok, provider=self.name, model=spec.model_id,
                           endpoint=base, context_limit=spec.context_limit, latency_ms=ms,
                           error=err, is_remote=True)


class RemoteProvider(OpenAICompatibleProvider):
    """Generic remote OpenAI-compatible endpoint (spec 17)."""

    name = "remote"

    def health(self, spec: BrainSpec) -> BrainHealth:
        h = super().health(spec)
        h.provider = self.name
        h.is_remote = True
        return h


_PROVIDERS: dict[str, BrainProvider] = {
    p.name: p for p in (OllamaProvider(), OpenAICompatibleProvider(),
                        HuggingFaceProvider(), RemoteProvider())
}


def provider_for(spec: BrainSpec) -> BrainProvider:
    """Resolve the provider for a brain spec.

    Endpoint shape wins over the *default* provider string: ``BrainSpec.provider``
    defaults to ``"ollama"``, so trusting it blindly would route a remote
    OpenAI/HF endpoint through the Ollama probe. An explicitly-declared
    non-default provider is still honoured.
    """
    url = (spec.base_url or "").lower()
    declared = (spec.provider or "").strip().lower()

    # Endpoint inference first for anything that is clearly not local.
    if url:
        is_local = "127.0.0.1" in url or "localhost" in url or "0.0.0.0" in url
        if "huggingface" in url:
            return _PROVIDERS["huggingface"]
        if not is_local:
            # an explicit non-default provider still wins over the generic guess
            if declared in ("remote", "openai_compatible", "huggingface"):
                return _PROVIDERS[declared]
            return _PROVIDERS["openai_compatible"]
        if is_local:
            return _PROVIDERS["ollama"]

    if declared in _PROVIDERS:
        return _PROVIDERS[declared]
    return _PROVIDERS["ollama"]


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)


# --------------------------------------------------------------------------
# §18 / §37 Brain router with recorded fallback
# --------------------------------------------------------------------------
@dataclass
class FallbackRecord:
    """Spec 37: a fallback must be RECORDED, never silent."""

    task_hint: str
    primary: str
    primary_error: str
    fallback: str
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"task_hint": self.task_hint, "primary": self.primary,
                "primary_error": self.primary_error, "fallback": self.fallback,
                "at": self.at}


class BrainRouter:
    """Selects a brain for a task and walks a recorded fallback chain (18/37)."""

    def __init__(self, specs: dict[str, BrainSpec] | None = None) -> None:
        self._specs: dict[str, BrainSpec] = specs or {}
        self._fallbacks: list[FallbackRecord] = []

    # -- registration -----------------------------------------------------
    def register(self, role: str, spec: BrainSpec) -> None:
        self._specs[role] = spec

    def specs(self) -> dict[str, BrainSpec]:
        return dict(self._specs)

    def fallback_history(self) -> list[dict[str, Any]]:
        return [f.to_dict() for f in self._fallbacks]

    # -- selection (spec 18) ---------------------------------------------
    def select(self, *, role: str = "default", complexity: str = "low",
               coding: bool = False, reasoning: bool = False,
               privacy: bool = False, low_resource: bool = False) -> BrainSpec | None:
        """Choose a brain: role first, then resource/complexity shaping.

        Deliberately NOT size-only (spec 18): a low-resource host prefers the
        smaller brain even for complex work, because a brain that cannot load is
        worth less than a smaller one that answers.
        """
        if privacy and any(s.is_remote is False for s in self._specs.values()):
            local = [s for s in self._specs.values() if not s.is_remote]
            if local:
                return min(local, key=lambda s: s.est_ram_mb or 10**9)
        if role in self._specs:
            spec = self._specs[role]
            if low_resource and spec.est_ram_mb > 4000:
                smaller = [s for s in self._specs.values()
                           if s.est_ram_mb and s.est_ram_mb <= 4000]
                if smaller:
                    return min(smaller, key=lambda s: s.est_ram_mb)
            return spec
        if coding and "coding" in self._specs:
            return self._specs["coding"]
        if reasoning and "strong" in self._specs:
            return self._specs["strong"]
        return self._specs.get("default")

    # -- health -----------------------------------------------------------
    def health(self, role: str) -> BrainHealth | None:
        spec = self._specs.get(role)
        if spec is None:
            return None
        return provider_for(spec).health(spec)

    def health_all(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for role, spec in self._specs.items():
            try:
                out[role] = provider_for(spec).health(spec).to_dict()
            except Exception as exc:  # noqa: BLE001
                out[role] = {"available": False, "provider": spec.provider,
                             "model": spec.model_id, "error": str(exc)}
        return out

    # -- fallback chain (spec 37) ----------------------------------------
    def resolve_with_fallback(self, *, role: str = "default", order: list[str] | None = None,
                              task_hint: str = "") -> tuple[BrainSpec | None, BrainHealth | None]:
        """Return the first HEALTHY brain, recording every failed attempt.

        Order defaults to [role, 'strong', 'default'] then any remaining specs.
        Returns ``(None, last_health)`` when nothing is available -- the caller
        must then report the failure rather than pretend (spec 19/37/38).
        """
        chain: list[str] = []
        for r in ([role] if role else []) + (order or ["strong", "default"]):
            if r in self._specs and r not in chain:
                chain.append(r)
        for r in self._specs:
            if r not in chain:
                chain.append(r)

        primary = chain[0] if chain else None
        last: BrainHealth | None = None
        for r in chain:
            spec = self._specs[r]
            try:
                h = provider_for(spec).health(spec)
            except Exception as exc:  # noqa: BLE001
                h = BrainHealth(available=False, provider=spec.provider,
                                model=spec.model_id, error=str(exc))
            last = h
            if h.available:
                if r != primary and primary is not None:
                    rec = FallbackRecord(
                        task_hint=task_hint, primary=primary,
                        primary_error=(last.error if last else ""), fallback=r)
                    self._fallbacks.append(rec)
                    logger.warning(
                        "Brain fallback RECORDED: %s -> %s (primary unavailable)",
                        primary, r)
                return spec, h
        return None, last


__all__ = [
    "BrainHealth", "BrainSpec", "BrainProvider", "OllamaProvider",
    "OpenAICompatibleProvider", "HuggingFaceProvider", "RemoteProvider",
    "BrainRouter", "FallbackRecord", "provider_for", "available_providers",
]
