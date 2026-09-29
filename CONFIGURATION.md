# MOON — Configuration

All configuration lives in `.env` (created by `setup_wizard.py` on first run). Never edit `.env` by hand unless you know what you're doing — the wizard validates values.

---

## Environment Variables

### Model Backend

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OLLAMA_BASE_URL` | Yes | `http://127.0.0.1:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | Yes | `qwen2.5:0.5b` | Default model for the main brain |
| `OLLAMA_EMBEDDING_MODEL` | No | (same as above) | Model used for embeddings |

### API Keys (as needed)

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | No | OpenAI-compatible API key (fallback provider) |
| `HF_TOKEN` | No | Hugging Face token for model hub access |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token (if using Telegram interface) |

### Safety Boundary

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MOON_SAFETY boundary` | Yes | (wizard-prompted) | Target organization/domain MOON is authorized to operate on |
| `MOON_BLOCKED_DOMAINS` | No | — | Comma-separated list of domains MOON must never touch |

### Service

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MOON_PORT` | No | `8777` | HTTP API port |
| `MOON_WORKERS` | No | `4` | Concurrent worker threads |
| `MOON_LOG_LEVEL` | No | `INFO` | Python logging level |

### Voice

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TTS_ENGINE` | No | `espeak` | TTS engine: `espeak`, `kokoro`, `edge` |
| `VOICE_PRESET` | No | `default` | Voice preset: `default`, `seductive`, `warm`, `crystal` |

### Memory

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MOON_MEMORY_DB` | No | `moon_memory.db` | SQLite memory database path |

### Monitoring

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MOON_MONITOR_INTERVAL` | No | `900` | Deep monitor interval in seconds (15 min default) |

---

## .env.example

A template is provided at `.env.example`. Copy it and fill in your values:

```bash
cp .env.example .env
# Then run the wizard to validate:
python setup_wizard.py
```

---

## Configuration Validation

Run the wizard's validation standalone:

```bash
python setup_wizard.py --validate
```

This checks:
- Python version (≥ 3.10)
- Ollama reachable at `OLLAMA_BASE_URL`
- Model specified in `OLLAMA_MODEL` is pullable
- `.env` has all required fields
- Port `MOON_PORT` is free

---

## Changing Models

To switch the main brain model:

1. Edit `.env`: set `OLLAMA_MODEL` to the new model name
2. Pull the model: `ollama pull <new-model>`
3. Restart MOON: `systemctl --user restart moon-terminal.service`

Per-agent models can be set in the agent configuration (see `src/agents/`).
