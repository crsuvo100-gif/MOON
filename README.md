# MOON -- Neural Brain Command Center

A self-hosted autonomous AI agent with its own "brain", connected per-agent
brains, and continuous self-learning. The interface is the web-based Neural
Brain Command Center at `http://127.0.0.1:8777`.

## Features
- **Main brain (LongTermMemory + KnowledgeBase)** -- durable, survives restarts.
- **Per-agent brains** -- 39 specialist agents, each with its own isolated memory connected to the main brain.
- **Autonomous self-learning** -- every interaction's facts, tool outcomes, and lessons are consolidated into the durable brain (`enable_auto_learning`).
- **Neural Brain Command Center** -- Three.js visualization of the brain mesh, connected-agent mesh, and live cognition channel over WebSocket.
- **Always-connected GitHub** -- MOON autonomously pulls needed tools/plugins/skills from the connected repo on demand.

## Female Voice & Dictation

MOON speaks with a warm, clearly-FEMALE voice (espeak female voice `f5` + a SoX
timbre chain: pitch lift, body/bass, air/treble, subtle chorus + reverb for an
intimate, attractive tone). Presets: `default`, `seductive`, `warm`, `crystal`.

```bash
make voice-install          # install espeak + sox (+ optional vosk for mic)
make voice                  # companion loop: type/talk -> MOON -> female voice
make voice-test             # generate a sample female-voice WAV
```

With a microphone + vosk (`VOSK_MODEL_DIR` set), use `make voice -- --mic` for
true speech dictation. Without vosk it runs in typed mode but still replies in
MOON's female voice. The voice module is `app/voice.py`.

## Quick start
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
make serve          # MOON Neural Command Center at http://127.0.0.1:8777
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

---

## Python-First Architecture & Portability

MOON is a **Python-first** application. The core (orchestrator, agents, tools,
memory, model layer, services, terminal/UI, APIs) is implemented in Python and
runs on any machine with a compatible Python. Shell scripts (`install.sh`,
`start.sh`, `scripts/*.sh`, `Makefile`) are **optional convenience/bootstrap
wrappers only** — the real application is always launched through Python.

### Requirements
| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.10 | 3.11+ (3.13 tested) |
| OS | Linux, macOS, Windows | Linux (Debian/Ubuntu/Kali), macOS, Windows 10+ |
| CPU arch | x86_64, arm64 | x86_64 or arm64 |
| RAM | 4 GB | 8 GB+ |
| Storage | 2 GB (code + deps) | 10 GB+ (with models) |
| Network | localhost model endpoint OR cloud API | both |
| GPU | optional | optional (CPU works; GPU accelerates local models) |

MOON uses `pathlib`, `platform`, and `sys` for portable paths/OS detection;
there are **no hard-coded `/home/meow`, Kali, or Linux-only paths** in the core.
The only OS-specific code is `app/capability/installer.py`, which is a
**multi-platform package-manager abstraction** (apt/dnf/pacman/apk) — preserved
exactly as designed.

### Model dependencies
MOON talks to an **OpenAI-compatible** endpoint. Options:
- **Local** (default, CPU-friendly): [Ollama](https://ollama.com) serving
  `qwen3:0.6b`, `qwen2.5:3b`, `qwen2.5-coder:1.5b`, etc. Start Ollama, then
  `ollama pull qwen3:0.6b`.
- **Cloud**: set `OPENAI_API_KEY` / `OPENROUTER_API_KEY` / `HUGGINGFACE_API_KEY`
  in `.env` for the hosted fallback chain.

### Install (Python)
```bash
git clone git@github.com:crsuvo100-gif/MOON.git
cd MOON
python -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env          # then fill in secrets (NEVER commit .env)
python -m moon install        # bootstrap venv + deps + (best-effort) models
```

### Commands (all Python — `python -m moon <cmd>`)
| Command | Purpose |
|---------|---------|
| `python -m moon` | Launch the default Terminal/Neural Command Center UI |
| `python -m moon terminal` / `start` | Web Terminal / Neural Brain HUD at `http://127.0.0.1:8777` |
| `python -m moon run "task"` | Run a single task and exit |
| `python -m moon doctor` | Health check (Python/deps/config/DB/agents/tools/model/git) → PASS/WARN/FAIL |
| `python -m moon status` | Check the live backend `/api/health` |
| `python -m moon backup` | Snapshot runtime data into `backups/moon_<ts>/` (cross-platform) |
| `python -m moon restore <snapshot>` | Restore a backup over live data |
| `python -m moon install` | Python bootstrap installer (venv + deps + models) |
| `python -m moon update` | Safe update: `git pull --ff-only` + `pip install -e . --upgrade` |
| `python -m moon models` | Pre-pull per-agent preferred models |
| `python -m moon dashboard` | Flask+SocketIO web dashboard |
| `python -m moon tui` | Curses text-mode UI (headless/SSH) |
| `python -m moon telegram` | Telegram bot listener |
| `python -m moon version` | Print version |

> The installed `moon` console script (`pyproject.toml [project.scripts]`) also
> works after `pip install -e .`.

### Recovery workflow (clean compatible machine)
```bash
git clone git@github.com:crsuvo100-gif/MOON.git
cd MOON
python -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env            # supply real secrets
python -m moon install          # venv + dependencies (+ local models if Ollama present)
python -m moon doctor           # verify the machine is ready
python -m moon                  # launch -> complete MOON (agents, tools, services, UI)
```
Runtime data (`data/`, `capabilities/`, `connections/`, `*.db`) is **not**
committed to Git (see `.gitignore`); it is recreated on first run and can be
restored from a `python -m moon backup` snapshot. Secrets (`.env`) and model
files are never committed.

### Backup / Restore
```bash
python -m moon backup           # -> backups/moon_YYYYMMDD_HHMMSS/
python -m moon restore backups/moon_YYYYMMDD_HHMMSS
```
Backups capture agents, knowledge, memory, skills, evaluations, logs, the
`agent_factory.db` and `executions.db`. They **exclude** `.env` (secrets) by
design — back that up separately.
