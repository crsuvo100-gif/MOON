"""
pydantic-settings for MOON Terminal — loads from .env + env vars.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM / model ────────────────────────────────────────────────────────
    model_base_url: str = "http://127.0.0.1:11434/v1"
    model_name: str = "qwen2.5:1.5b"
    model_temperature: float = 0.7
    model_max_tokens: int = 2048
    model_timeout: float = 120.0

    # strong / accuracy-critical model (optional)
    strong_model_name: str = ""
    strong_model_base_url: str = ""

    # ── fallback APIs (each gated on presence of key) ──────────────────────
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"

    huggingface_api_key: str = ""
    huggingface_base_url: str = "https://api.huggingface.co/v1"
    huggingface_model: str = "microsoft/DialoGPT-medium"

    # ── voice ──────────────────────────────────────────────────────────────
    terminal_access_token: str = ""
    voice_enabled: bool = True

    # ── embedding / semantic search ────────────────────────────────────────
    embedding_base_url: str = ""
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # ── feature flags ──────────────────────────────────────────────────────
    enable_browser_automation: bool = False
    enable_ocr: bool = False
    enable_pdf: bool = False
    enable_agent_validation: bool = False
    enable_auto_learning: bool = True
    enable_fast_path: bool = True
    enable_self_consistency: bool = True
    self_consistency_samples: int = 2
    tool_timeout: float = 30.0
    max_parallel_agents: int = 4
    allow_dangerous_tools: bool = True
    enable_per_agent_models: bool = True

    # ── runtime ────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_dir: str = "logs"
    app_name: str = "moontm"
    environment: str = "development"

    # ── telemetry / system ─────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8777
    autostart: bool = True
    auto_voice: bool = True
    idle_speed: float = 0.5

    # ── session lock ───────────────────────────────────────────────────────
    lock_state_file: Optional[str] = None  # auto-resolved relative to data/

    # ── derived paths (computed, not from env) ─────────────────────────────
    @property
    def data_dir(self) -> Path:
        return Path(self.log_dir).parent / "data" if self.log_dir else Path("data")

    @property
    def brain_stats_path(self) -> Path:
        return self.data_dir / "brain_stats.json"

    @property
    def episodes_path(self) -> Path:
        return Path("memory") / "episodes.json"

    @property
    def long_term_path(self) -> Path:
        return Path(self.log_dir) / "long_term.jsonl"

    @property
    def lock_state_path(self) -> Path:
        if self.lock_state_file:
            return Path(self.lock_state_file)
        return self.data_dir / "lock_state.json"

    @property
    def voices_dir(self) -> Path:
        return Path("voices")

    @property
    def log_file(self) -> Path:
        return Path(self.log_dir) / "moontm.log"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
