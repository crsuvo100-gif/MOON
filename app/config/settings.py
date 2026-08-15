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

    # --- OpenAI-compatible FALLBACK backend ---------------------------------
    # When the primary local endpoint (Ollama) is unavailable OR a completion
    # fails, MOON falls back to a hosted OpenAI-compatible API (e.g. OpenAI).
    # The key is read from OPENAI_API_KEY (kept in the gitignored .env, never
    # committed). Leave blank to disable the fallback (local-only operation).
    openai_api_key: str = Field(
        default="",
        description="API key for the OpenAI-compatible fallback backend (OPENAI_API_KEY). Blank = no fallback.",
    )
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="Base URL of the OpenAI-compatible fallback endpoint.",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="Model id to request from the fallback backend.",
    )

    # --- OpenRouter FALLBACK backend (secondary) ---------------------------
    # A second hosted OpenAI-compatible API, tried after the local endpoint and
    # the primary OpenAI fallback. Useful when both local and OpenAI are down.
    # Key from OPENROUTER_API_KEY (gitignored .env, never committed). OpenRouter
    # is OpenAI-compatible, so it reuses the same LLMService client shape.
    openrouter_api_key: str = Field(
        default="",
        description="API key for the OpenRouter fallback backend (OPENROUTER_API_KEY). Blank = no secondary fallback.",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="Base URL of the OpenRouter endpoint (OpenAI-compatible).",
    )
    openrouter_model: str = Field(
        default="openai/gpt-4o-mini",
        description="Model id to request from OpenRouter (e.g. openai/gpt-4o-mini, anthropic/claude-3.5-sonnet).",
    )

    # --- OpenRouter ACCOUNT keys (NOT used for model serving) ---------------
    # These are auxiliary OpenRouter credentials, kept available for account
    # management / inbound-webhook verification. They are NEVER sent to the
    # chat-completions endpoint (that uses openrouter_api_key above).
    openrouter_management_key: str = Field(
        default="",
        description=(
            "OpenRouter MANAGEMENT key (sk-or-v1-...). Account/billing/admin only -- "
            "create keys, view usage. NOT a model-serving key; do not pass to /v1/chat/completions."
        ),
    )
    openrouter_webhook_secret: str = Field(
        default="",
        description=(
            "OpenRouter webhook signing secret (whsec_...). Used ONLY to verify inbound "
            "OpenRouter webhooks (e.g. usage events). No webhook ingestion is wired yet; "
            "stored for when that feature is added. Blank = disabled."
        ),
    )

    # Optional STRONG model for accuracy-critical work. When set, factual and
    # cyber-critical tasks (and the main-brain accuracy gate) are routed to it
    # for a higher-quality pass. Leave empty to use the default model only.
    # Unlocked: route accuracy-critical work to a larger local model on this host.
    strong_model_name: str = Field(
        default="qwen3:1.7b",
        description="Larger/more-capable model id for accuracy-critical tasks.",
    )
    strong_model_base_url: str = Field(
        default="",
        description="Endpoint for the strong model (defaults to model_base_url if blank).",
    )

    # Connected GitHub repository MOON always pulls tools/assets from on demand.
    github_repo: str = Field(
        default="",
        description='GitHub repo URL MOON is connected to for autonomous tool/asset pull (e.g. https://github.com/crsuvo100-gif/MOON).',
    )

    # Global Connector: MOON can connect to external services, other AI agents,
    # MCP servers, and webhooks. Egress is ALWAYS permission-gated (see
    # app.connector.permission). allowlisted/private hosts are SAFE (auto);
    # everything else requires operator confirmation. Disable the whole layer here.
    enable_global_connector: bool = True
    allowed_egress_hosts: str = Field(
        default="",
        description="Comma-separated hosts MOON may egress to WITHOUT confirmation "
                    "(e.g. api.github.com,my-agent.example.com). Everything else is CONFIRMATION.",
    )

    # Per-agent models: each agent can pull/install and run on its OWN model
    # (via Ollama) for domain-suited results, feeding its output up to the main
    # brain. Disable to force every agent to share the default model.
    enable_per_agent_models: bool = True

    embedding_base_url: str = ""
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    redis_url: str = ""
    task_queue_backend: Literal["memory", "redis"] = "memory"

    api_cors_origins: str = "*"

    enable_browser_automation: bool = True
    enable_ocr: bool = True
    enable_pdf: bool = True

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
