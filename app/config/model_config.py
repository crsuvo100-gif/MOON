"""Model/embedding configuration derived from :class:`Settings`."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelConfig:
    base_url: str
    model_name: str
    api_key: str
    temperature: float
    max_tokens: int
    timeout: float


@dataclass
class EmbeddingConfig:
    base_url: str
    model_name: str
    dim: int
    enabled: bool


def build_model_config(settings) -> ModelConfig:
    return ModelConfig(
        base_url=settings.model_base_url,
        model_name=settings.model_name,
        api_key=settings.model_api_key,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        timeout=settings.model_timeout,
    )


def build_embedding_config(settings) -> EmbeddingConfig:
    return EmbeddingConfig(
        base_url=settings.embedding_base_url,
        model_name=settings.embedding_model,
        dim=settings.embedding_dim,
        enabled=bool(settings.embedding_base_url),
    )
