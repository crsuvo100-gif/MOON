"""example.py -- MOON project example settings (single self-contained file).

This is the canonical, copy-paste reference for configuring MOON.  It covers:

  (1) every API / model backend MOON is wired to (local Ollama, OpenAI,
      OpenRouter, Hugging Face, HF OAuth + Inference Endpoint), and
  (2) the build settings for every connected-app channel MOON can run WITHOUT a
      computer/laptop (telegram bot, whatsapp cloud API, slack, discord, signal,
      plus a mobile entry point), with all passwords/tokens/tokens marked
      [REDACTED] -- never commit real secrets.

MOON's real, live settings are loaded from `app/config/settings.py` (pydantic
with a `.env` file); this file is a STANDALONE reference and intentionally does
NOT touch the live settings so existing installs are never touched.  Copy the
values you need into `.env` (`cp .env.example .env`), then overwrite real
secrets by hand or via the `setup_wizard.py`.

Design rules
------------
* `KEY = "example value"`  -- every key shown, every credential = [REDACTED].
* Each section maps 1:1 to actual code constants in `app/config/settings.py`
  and to the connector / channel code, so nothing here is invented.
* `[REDACTED]` marks a secret.  Replace it with your real value before use.
* Values marked `""` (empty) mean "feature disabled / local-only" -- the safe
  default; the agent runs with a LOCAL model and no cloud keys until you fill
  this file in.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# (0) ANSI palette used by the HUD -- the three hard rules:
#     (1) female voice that CLONES any uploaded WAV
#     (2) red/black HUD canonical palette
#     (3) all functions open by default
# ---------------------------------------------------------------------------
_ansi = {
    "tx": "\033[38;5;220m",   # bright red  -- notification / danger
    "bk": "\033[40m",         # black bg    -- HUD surface
    "fw": "\033[1m",          # bold
    "cl": "\033[0m",          # reset
}

# ---------------------------------------------------------------------------
# (1) EVERY API / model backend config
# ---------------------------------------------------------------------------
API_CONFIG = {
    # --- Local model endpoint (primary brain). Ollama / LM Studio / Mew
    # --- speak the OpenAI-compatible shape /v1/chat/completions.
    #     Example for a local Ollama server:
    "MODEL_BASE_URL": "http://127.0.0.1:11434/v1",
    "MODEL_NAME": "qwen3:0.6b",         # safe default, small + fast on CPU
    "MODEL_API_KEY": "not-required-for-local",

    # --- Embeddings (offline fallback if EMBEDDING_BASE_URL is empty).
    "EMBEDDING_BASE_URL": "",
    "EMBEDDING_MODEL": "all-MiniLM-L6-v2",
    "EMBEDDING_DIM": 384,

    # --- Fast toggles (all functions open by default; keep True).
    "ENABLE_AGENT_VALIDATION": True,
    "ENABLE_AUTO_LEARNING": True,
    "ENABLE_BROWSER_AUTOMATION": True,
    "ENABLE_OCR": True,
    "ENABLE_PDF": True,
    "ENABLE_DANGEROUS_TOOLS": False,   # shell / python / docker: opt-in only
    "ENABLE_WEBCAM": True,
    "ENABLE_CAMERA": True,
    "ENABLE_MICROPHONE": True,

    # --- Cyber ops: hosts MOON may actively scan / exploit (authz-gated).
    "AUTHORIZED_TARGETS": "127.0.0.1,localhost,192.168.0.0/16,10.0.0.0/8",

    # --- Strong model for accuracy-critical / cyber tasks (optional unlock).
    "STRONG_MODEL_NAME": "qwen3:1.7b",
    "STRONG_MODEL_BASE_URL": "",

    # --- Connected GitHub repo (auto tool/pull). Public read OK, no token.
    "GITHUB_REPO": "https://github.com/crsuvo100-gif/MOON",
    "GITHUB_PAT": "[REDACTED]",        # optional Personal Access Token (keep blank)

    # --- Terminal remote access auth gate.
    "MOON_TERMINAL_TOKEN": "[REDACTED]",

    # --- Web UI / Node server.
    "NODE_ENV": "production",
    "WEBSOCKET_PORT": 8777,
    "SECRET_KEY": "[REDACTED]",
    "SESSION_COOKIE_SECURE": True,
    "SESSION_COOKIE_SAMESITE": "Lax",
    "CORS_ORIGINS": "*",
    "USE_WEBSERVER": True,
    "WEB_SERVER_HOST": "127.0.0.1",
    "WEB_SERVER_PORT": 8777,

    # --- HTTP / Web API (frontend Abra).
    "API_BASE_URL": "http://127.0.0.1:8777",
    "API_KEY": "[REDACTED]",
    "API_SUPERUSER_KEY": "[REDACTED]",
    "API_AUTH_MODE": "token",
    "ENABLE_API": True,
    "API_ORIGINS": ["http://127.0.0.1:8777"],
    "API_CORS_ORIGINS": ["http://127.0.0.1:8777"],
    "API_RATE_LIMIT": "100/minute",
    "API_TIMEOUT": 30,
    "API_MAX_BODY_BYTES": 2 * 1024 * 1024,   # 2 MB

    # --- OpenAI-compatible fallback backend (used when local endpoint is down).
    "OPENAI_API_KEY": "[REDACTED]",
    "OPENAI_BASE_URL": "https://api.openai.com/v1",
    "OPENAI_MODEL": "gpt-4o-mini",

    # --- OpenRouter fallback backend (secondary / many models incl. Claude, Llama).
    "OPENROUTER_API_KEY": "[REDACTED]",
    "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
    "OPENROUTER_MODEL": "openai/gpt-4o-mini",
    "OPENROUTER_MANAGEMENT_KEY": "[REDACTED]",   # account/billing/admin only
    "OPENROUTER_WEBHOOK_SECRET": "[REDACTED]",   # inbound webhook signing

    # --- Hugging Face fallback backend (tertiary).
    "HUGGINGFACE_API_KEY": "[REDACTED]",
    "HUGGINGFACE_BASE_URL": "https://router.huggingface.co",
    "HUGGINGFACE_MODEL": "meta-llama/Llama-3.1-8B-Instruct",

    # --- HF OAuth client (MOON registers as an HF OAuth app).
    "HF_OAUTH_WEBSITE": "",
    "HF_OAUTH_CLIENT_ID": "[REDACTED]",
    "HF_OAUTH_CLIENT_NAME": "MOON",
    "HF_OAUTH_CLIENT_SECRET": "[REDACTED]",
    "HF_OAUTH_REDIRECT_URI": "",
    "HF_OAUTH_SCOPES": "read:user,repo",
    "HF_ENDPOINT_NAMESPACE": "crsuvo",
    "HF_INFERENCE_API_KEY": "[REDACTED]",
    "HF_INFERENCE_ENDPOINT_URL": "",

    # --- Cognitive memory config.
    "MOON_MEMORY_PATH": "~/.moon/memory",
    "MOON_MEMORY_DB_URL": "",
    "MOON_MEMORY_SYNC_ENABLED": True,
    "MOON_MEMORY_SYNC_INTERVAL": 300,
    "MOON_MEMORY_MAX_RECORDS": 100_000,
    "MOON_MEMORY_CONTEXT_BUDGET": 2048,
    "MOON_MEMORY_BACKUP_PATH": "~/.moon/memory/backups",
    "MOON_MEMORY_CACHE_ENABLED": True,
    "MOON_MEMORY_CACHE_TTL": 60,
    "MOON_MEMORY_OFFLINE_MODE": False,
    "MOON_MEMORY_ENCRYPTION_KEY": "[REDACTED]",
    "MOON_MEMORY_SYNC_ENDPOINT": "https://api.moon.to/sync",
    "MOON_MEMORY_SYNC_TOKEN": "[REDACTED]",
}


# ---------------------------------------------------------------------------
# (2) CONNECTED APPLICATIONS + BUILD SETTINGS (run without a laptop)
# ---------------------------------------------------------------------------
CONNECTED_APPS_BUILD_SETTINGS = {
    # --- TELEGRAM (MOON as a Telegram BOT). Works on a phone, no laptop.
    #     Create a bot via @BotFather -> TELEGRAM_BOT_TOKEN; TELEGRAM_CHAT_ID is
    #     the numeric chat id MOON replies in (blank = accept any chat).
    #     Run: python main.py telegram
    "TELEGRAM_BOT_TOKEN": "[REDACTED]",
    "TELEGRAM_CHAT_ID": "[REDACTED]",
    "TELEGRAM_POLL_TIMEOUT": 30,
    "TELEGRAM_ALLOWED_CHATS": "",       # comma-list of allowed chat ids
    "TELEGRAM_WORKER_PLATFORM": "telegram",      # entry for mobile worker
    "TELEGRAM_ENCRYPTION_KEY": "[REDACTED]",

    # --- WHATSAPP (Meta WhatsApp Cloud API). App-only, no laptop needed.
    #     Create a Business Profile + phone number -> get WHATSAPP_TOKEN,
    #     WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_BUSINESS_ACCOUNT_ID from Meta.
    "WHATSAPP_TOKEN": "[REDACTED]",
    "WHATSAPP_PHONE_NUMBER_ID": "[REDACTED]",
    "WHATSAPP_BUSINESS_ACCOUNT_ID": "[REDACTED]",
    "WHATSAPP_BASE_URL": "https://graph.facebook.com/v19.0",
    "WHATSAPP_DESTINATION": "[REDACTED]",
    "WHATSAPP_ENCRYPTION_KEY": "[REDACTED]",
    "WHATSAPP_WORKER_PLATFORM": "whatsapp",
    "WHATSAPP_AUTH_MODE": "cloud_api",
    "WHATSAPP_MAX_ATTEMPTS": 3,

    # --- SIGNAL (Signal Messenger). Optional; uses signal-cli / HTTP API.
    "SIGNAL_ENABLED": False,
    "SIGNAL_API_URL": "http://localhost:8080",
    "SIGNAL_REST_API_KEY": "[REDACTED]",
    "SIGNAL_RECIPIENT": "[REDACTED]",
    "SIGNAL_ENCRYPTION_KEY": "[REDACTED]",
    "SIGNAL_WORKER_PLATFORM": "signal",

    # --- SLACK (Slack Web API + Socket Mode).
    "SLACK_ENABLED": False,
    "SLACK_BOT_TOKEN": "[REDACTED]",
    "SLACK_APP_TOKEN": "[REDACTED]",
    "SLACK_BOT_ID": "[REDACTED]",
    "SLACK_TEAM_ID": "[REDACTED]",
    "SLACK_ENCRYPTION_KEY": "[REDACTED]",
    "SLACK_WORKER_PLATFORM": "slack",

    # --- DISCORD (Discord API).
    "DISCORD_ENABLED": False,
    "DISCORD_TOKEN": "[REDACTED]",
    "DISCORD_GUILD_ID": "[REDACTED]",
    "DISCORD_CLIENT_ID": "[REDACTED]",
    "DISCORD_CLIENT_SECRET": "[REDACTED]",
    "DISCORD_ENCRYPTION_KEY": "[REDACTED]",
    "DISCORD_WORKER_PLATFORM": "discord",

    # --- Mattermost (self-hosted Slack alternative).
    "MATTERMOST_ENABLED": False,
    "MATTERMOST_URL": "http://localhost:8065",
    "MATTERMOST_TOKEN": "[REDACTED]",
    "MATTERMOST_TEAM": "[REDACTED]",
    "MATTERMOST_USER": "[REDACTED]",
    "MATTERMOST_ENCRYPTION_KEY": "[REDACTED]",
    "MATTERMOST_WORKER_PLATFORM": "mattermost",

    # --- IRC / IRC bridge (laptop-free public relay).
    "IRC_ENABLED": False,
    "IRC_SERVER": "chat.freenode.net",
    "IRC_PORT": 6697,
    "IRC_NICK": "MOON_Bot",
    "IRC_CHANNELS": "#moon",
    "IRC_ENCRYPTION_KEY": "[REDACTED]",
    "IRC_WORKER_PLATFORM": "irc",

    # --- Matrix (federated chat). Works on a phone without a laptop.
    "MATRIX_ENABLED": False,
    "MATRIX_HS_URL": "http://localhost:8008",
    "MATRIX_USER_ID": "[REDACTED]",
    "MATRIX_ACCESS_TOKEN": "[REDACTED]",
    "MATRIX_ROOM_ID": "[REDACTED]",
    "MATRIX_ENCRYPTION_KEY": "[REDACTED]",
    "MATRIX_WORKER_PLATFORM": "matrix",

    # --- Mail / SendGrid (email alerts + inbox).
    "MAIL_ENABLED": True,
    "MAIL_FROM": "MOON <noreply@example.com>",
    "MAIL_SENDGRID_API_KEY": "[REDACTED]",
    "MAIL_SENDGRID_TEMPLATE_ID": "[REDACTED]",
    "MAIL_SMTP_HOST": "smtp.gmail.com",
    "MAIL_SMTP_PORT": 587,
    "MAIL_SMTP_USER": "[REDACTED]",
    "MAIL_SMTP_PASSWORD": "[REDACTED]",
    "MAIL_ENCRYPTION_KEY": "[REDACTED]",
    "MAIL_WORKER_PLATFORM": "mail",

    # --- Push notifications (mobile banner when remote).
    "PUSH_ENABLED": True,
    "PUSH_FCM_SERVER_KEY": "[REDACTED]",
    "PUSH_FCM_CLIENT_KEY": "[REDACTED]",
    "PUSH_ENCRYPTION_KEY": "[REDACTED]",
    "PUSH_WORKER_PLATFORM": "push",

    # --- Voice / TTS (female voice that CLONES any uploaded WAV).
    "VOICE_TTS_ENABLED": True,
    "VOICE_TTS_SERVICE": "edge",       # edge | elevenlabs | gTTS
    "VOICE_TTS_ENGINE": "gpt-4o-mini-tts",
    "VOICE_TTS_CLONE_SAMPLE": "~/voice_samples/clone.wav",
    "VOICE_TTS_ENCRYPTION_KEY": "[REDACTED]",
    "VOICE_TTS_WORKER_PLATFORM": "voice",
    "VOICE_TTS_INPUT_WAV": "",

    # --- Camera / webcam input (local only).
    "WEBCAM_DEVICE": "/dev/video0",
    "CAMERA_DEVICE": "/dev/video0",
    "MICROPHONE_DEVICE": "/dev/alsa/pcm.default",
    "CAMERA_ENCRYPTION_KEY": "[REDACTED]",
    "CAMERA_WORKER_PLATFORM": "camera",

    # --- GitHub / Source control integration (remote build without laptop).
    "GITHUB_WORKFLOW_ENABLED": True,
    "GITHUB_REPO_TEMPLATE": "crsuvo100-gif/MOON",
    "GITHUB_TOKEN": "[REDACTED]",
    "GITHUB_SYNC_CI": True,
    "GITHUB_CI_INPUTS": {
        "task": "run_tests",
        "environment": "docker",
        "service": "moon",
    },
    "GITHUB_OAUTH_CLIENT_ID": "[REDACTED]",
    "GITHUB_OAUTH_CLIENT_SECRET": "[REDACTED]",
    "GITHUB_ENCRYPTION_KEY": "[REDACTED]",

    # --- Slack / Discord build (webhook-based, no long-lived bot needed).
    "SLACK_WEBHOOK_URL": "[REDACTED]",
    "DISCORD_WEBHOOK_URL": "[REDACTED]",
    "SLACK_ENCRYPTION_KEY": "[REDACTED]",
    "DISCORD_ENCRYPTION_KEY": "[REDACTED]",
}

# ---------------------------------------------------------------------------
# MOON source / build (git + deploy), non-secret only.
# ---------------------------------------------------------------------------
MOON_SOURCE_BUILD = {
    "GITHUB_REMOTE_NAME": "origin",
    "GITHUB_REMOTE_URL": "git@github.com:crsuvo100-gif/MOON.git",
    "GITHUB_BRANCH": "memory_checkpoint_2026_10_05",
    "MOON_PORT": 8777,
    "MOON_MAIN_ENTRY": "main.py",
    "MOON_MODULE_ENTRY": "app/__init__.py",
    "MOON_INSTALL_CMD": "python -m moon install",
    "MOON_REPO_URL": "https://github.com/crsuvo100-gif/MOON",
    "MOON_SERVICE_NAME": "moon-terminal.service",
    "MOON_SERVICE_OUTPUT": "journalctl -u moon-terminal -f",
    "MOON_SERVICE_ENABLED": True,
    "MOON_HUD_ENABLED": True,
    "MOON_WEBCAM_ENABLED": False,
    "MOON_CAMERA_ENABLED": False,
    "MOON_MICROPHONE_ENABLED": False,
    "MOON_LAUNCH_PHARSE": True,
    "MOON_BACKUP_SERVICE": True,
    "MOON_BACKUP_PATH": "backups/",
    "MOON_BACKUP_INTERVAL": 300,
    "MOON_BACKUP_KEEP": 7,
    "MOON_FIREWALL_POLICY": "allow",
    "MOON_FIREWALL_RULES": [
        "allow 127.0.0.1",
        "allow localhost",
        "allow 192.168.0.0/16",
        "allow 10.0.0.0/8",
    ],
}


# ---------------------------------------------------------------------------
# One-stop loader -- returns a plain-{}.dict view for docs / migration scripts.
# Does not touch the live `app.config.settings`.
# ---------------------------------------------------------------------------
def get_example_settings() -> dict:
    return {
        "api_config": API_CONFIG,
        "connected_apps_build_settings": CONNECTED_APPS_BUILD_SETTINGS,
        "moon_source_build": MOON_SOURCE_BUILD,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_example_settings(), indent=2, default=str))
