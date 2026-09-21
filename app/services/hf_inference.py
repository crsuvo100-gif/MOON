"""Hugging Face InferenceClient service for MOON.

Wraps `huggingface_hub.InferenceClient` so MOON can use HF's hosted inference --
both chat completions (with explicit provider selection, e.g. "novita") and image
generation (text_to_image via FLUX and friends) -- in addition to the
OpenAI-compatible router already used by the fallback chain.

The `huggingface_hub` package is an OPTIONAL dependency: if it is not installed,
the service reports that clearly instead of crashing, and MOON keeps working via
its other backends. All network calls are real when the package + a token exist;
tests mock the client so no network/token is required to validate the logic.
"""

from __future__ import annotations

from typing import Any, Sequence

from app.config.logging import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)


def _inference_client_available() -> bool:
    try:
        import huggingface_hub  # noqa: F401

        return True
    except Exception:  # pragma: no cover - environment dependent
        return False


class HuggingFaceInference:
    """Thin async-friendly wrapper around huggingface_hub.InferenceClient."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        s = get_settings()
        self._api_key = (api_key or s.huggingface_api_key or "").strip()
        # The router is the OpenAI-compatible entrypoint used by InferenceClient
        # under the hood; exposed here for transparency / diagnostics.
        self._base_url = (base_url or s.huggingface_base_url or "https://router.huggingface.co").rstrip("/")
        self._available = _inference_client_available()

    @property
    def available(self) -> bool:
        return self._available and bool(self._api_key)

    # ------------------------------------------------------------------ #
    # Chat completion (OpenAI-compatible shape via InferenceClient)
    # ------------------------------------------------------------------ #
    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        model: str = "openai/gpt-oss-120b",
        provider: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Chat completion through HF's router.

        `provider` selects a specific provider (e.g. "novita"); omit for
        automatic selection. Returns the raw completion dict; raises on failure
        so callers (and the fallback chain) can react.
        """
        if not self._available:
            raise RuntimeError(
                "huggingface_hub is not installed (pip install 'huggingface_hub[cli]')"
            )
        if not self._api_key:
            raise RuntimeError("No HUGGINGFACE_API_KEY configured for Hugging Face inference")

        from huggingface_hub import InferenceClient

        client = InferenceClient(api_key=self._api_key)
        kwargs: dict[str, Any] = dict(
            model=model,
            messages=list(messages),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if provider:
            kwargs["provider"] = provider
        # InferenceClient.chat.completions.create is synchronous; run in thread.
        import asyncio

        result = await asyncio.to_thread(client.chat.completions.create, **kwargs)
        # Normalize to a plain dict for tool/serialization consumers.
        if hasattr(result, "model_dump"):
            return result.model_dump()
        return dict(result)

    # ------------------------------------------------------------------ #
    # Image generation (text_to_image)
    # ------------------------------------------------------------------ #
    async def text_to_image(
        self,
        prompt: str,
        *,
        model: str = "black-forest-labs/FLUX.1-dev",
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Generate an image from `prompt` via HF's text_to_image.

        Returns {"ok": True, "path": <saved file>} when a path is given, else
        {"ok": True, "image": <PIL.Image>}. Raises on failure.
        """
        if not self._available:
            raise RuntimeError(
                "huggingface_hub is not installed (pip install 'huggingface_hub[cli]')"
            )
        if not self._api_key:
            raise RuntimeError("No HUGGINGFACE_API_KEY configured for Hugging Face inference")

        from huggingface_hub import InferenceClient

        client = InferenceClient(api_key=self._api_key)
        import asyncio

        image = await asyncio.to_thread(client.text_to_image, prompt=prompt, model=model)
        if output_path:
            image.save(output_path)
            return {"ok": True, "path": output_path}
        return {"ok": True, "image": image}
