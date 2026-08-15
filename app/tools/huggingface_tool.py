"""huggingface_tool.py -- Hugging Face inference via MOON's tool interface.

Exposes two actions:
  * chat         -> chat completion through HF router (provider-selectable)
  * text_to_image-> generate an image (FLUX etc.) from a prompt

Uses app.services.hf_inference.HuggingFaceInference, which lazily imports
huggingface_hub so MOON still runs if the package is absent. When the package or
token is missing, actions return a clear error instead of fabricating output.
"""

from __future__ import annotations

import json

from app.tools.base import BaseTool, ToolResult
from app.services.hf_inference import HuggingFaceInference


class HuggingFaceTool(BaseTool):
    name = "huggingface"
    description = (
        "Hugging Face hosted inference: chat completions (provider-selectable, e.g. "
        "openai/gpt-oss-120b, deepseek-ai/DeepSeek-R1) and text-to-image generation "
        "(e.g. black-forest-labs/FLUX.1-dev). Uses HUGGINGFACE_API_KEY."
    )

    def __init__(self) -> None:
        self._hf = HuggingFaceInference()

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "openai/gpt-oss-120b",
        provider: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> dict:
        try:
            return await self._hf.chat(
                messages, model=model, provider=provider,
                temperature=temperature, max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def text_to_image(
        self, prompt: str, *, model: str = "black-forest-labs/FLUX.1-dev", output_path: str | None = None
    ) -> dict:
        try:
            return await self._hf.text_to_image(prompt, model=model, output_path=output_path)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def execute(self, action: str = "chat", **kwargs) -> str:
        if action == "chat":
            msgs = kwargs.get("messages")
            if isinstance(msgs, str):
                msgs = [{"role": "user", "content": msgs}]
            if not msgs:
                msgs = [{"role": "user", "content": kwargs.get("prompt", "")}]
            result = await self.chat(
                msgs,
                model=kwargs.get("model", "openai/gpt-oss-120b"),
                provider=kwargs.get("provider"),
                temperature=float(kwargs.get("temperature", 0.7)),
                max_tokens=int(kwargs.get("max_tokens", 1024)),
            )
            return json.dumps(result, default=str, indent=2)
        if action == "text_to_image":
            result = await self.text_to_image(
                kwargs.get("prompt", ""),
                model=kwargs.get("model", "black-forest-labs/FLUX.1-dev"),
                output_path=kwargs.get("output_path"),
            )
            return json.dumps(result, default=str, indent=2)
        return "[huggingface] unknown action. Use chat|text_to_image."
