"""settings.py -- application settings via pydantic-settings.

Loads configuration from environment variables and/or a `.env` file.
All settings have safe local defaults so the agent runs out-of-the-box
against a local model endpoint.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration backed by the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="Standalone AI Agent", description="Human-readable app name.")
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    log_dir: str = "app/logs"

    model_base_url: str = Field(
        default="http://127.0.0.1:11434/v1",
        description="Base URL of an OpenAI-compatible model endpoint you operate.",
    )
    model_name: str = Field(default="qwen3:0.6b", description="Model id to request.")
    model_api_key: str = Field(
        default="not-required-for-local",
        description="API key; most local endpoints ignore this.",
    )
    model_temperature: float = 0.7
    model_max_tokens: int = 2048
    model_timeout: float = Field(default=120.0, description="Per-request timeout (seconds).")

    # Optional STRONG model for accuracy-critical work. When set, factual and
    # cyber-critical tasks (and the main-brain accuracy gate) are routed to it
    # for a higher-quality pass. Leave empty to use the default model only.
    strong_model_name: str = Field(
        default="",
        description="Optional larger/more-capable model id for accuracy-critical tasks.",
    )
    strong_model_base_url: str = Field(
        default="",
        description="Endpoint for the strong model (defaults to model_base_url if blank).",
    )

    embedding_base_url: str = ""
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    redis_url: str = ""
    task_queue_backend: Literal["memory", "redis"] = "memory"

    api_cors_origins: str = "*"

    enable_browser_automation: bool = False
    enable_ocr: bool = False
    enable_pdf: bool = False

    enable_agent_validation: bool = True
    enable_auto_learning: bool = True

    # --- Advanced workflow / speed / accuracy ------------------------------
    # Fast-path: for simple chat / single factual questions, skip the heavy
    # tool-call loop and two-phase validation and answer in one model call.
    # Dramatically reduces latency on CPU-only hosts for ordinary queries.
    enable_fast_path: bool = True
    # Self-consistency: sample multiple independent reasoning passes on
    # factual prompts; if the majority disagrees with the primary answer,
    # replace it with the majority answer. Strong accuracy boost.
    enable_self_consistency: bool = True
    # Number of EXTRA samples (primary + N = total passes). 2 -> 3-way vote.
    self_consistency_samples: int = 2
    # Tool execution timeout (seconds) -- hardens tools against hangs.
    tool_timeout: float = 30.0
    # Max sub-agents to run concurrently when a complex goal is fanned out.
    max_parallel_agents: int = 4

    @property
    def cors_origins_list(self) -> list[str]:
        if self.api_cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def use_embedding_service(self) -> bool:
        return bool(self.embedding_base_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


if __name__ == "__main__":
    import json
    print(json.dumps(get_settings().model_dump(), indent=2, default=str))
