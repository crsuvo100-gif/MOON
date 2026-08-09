# MOON -- Neural Brain Command Center

A self-hosted autonomous AI agent with its own "brain", connected per-agent
brains, and continuous self-learning. The interface is the web-based Neural
Brain Command Center at `http://localhost:8000/brain`.

## Features
- **Main brain (LongTermMemory + KnowledgeBase)** -- durable, survives restarts.
- **Per-agent brains** -- 39 specialist agents, each with its own isolated memory connected to the main brain.
- **Autonomous self-learning** -- every interaction's facts, tool outcomes, and
  lessons are consolidated into the durable brain (`enable_auto_learning`).
- **Neural Brain Command Center** -- Three.js visualization of the brain mesh,
  connected-agent mesh, and live cognition channel over WebSocket.
- **Always-connected GitHub** -- MOON autonomously pulls needed tools/plugins/skills from the connected repo on demand.

## Quick start
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # point MODEL_BASE_URL at your local model (e.g. Ollama)
make serve                  # opens http://localhost:8000/brain
```

## Configuration (`.env`)
| Key | Default | Purpose |
|-----|---------|---------|
| `MODEL_BASE_URL` | `http://127.0.0.1:11434/v1` | OpenAI-compatible local endpoint |
| `MODEL_NAME` | `qwen3:0.6b` | model id |
| `ENABLE_AUTO_LEARNING` | `true` | MOON learns from every interaction |
| `ENABLE_AGENT_VALIDATION` | `true` | two-phase main-brain validation |
| `GITHUB_REPO` | `https://github.com/crsuvo100-gif/MOON` | connected repo for auto tool-pull |

## Tests
```bash
make test
```
