# MOON — Architecture

## Overview

MOON is a self-hosted autonomous AI agent with a modular, layered architecture. The system is organized around a central agent engine that routes requests through persona-based intent detection, a pluggable tool registry, and per-agent memory, all backed by a local Ollama LLM.

```
                    USER
                     │
                     ▼
              INTERFACE LAYER
          ┌──────────┼──────────┐
          │          │          │
         CLI        API        UI
          │          │          │
          └──────────┼──────────┘
                     ▼
               AI ASSISTANT
                     │
             ┌───────┴───────┐
             │               │
          PLANNER         MEMORY
             │               │
             ▼               ▼
       TASK EXECUTOR    RETRIEVAL
             │
       ┌─────┼─────┐
       ▼     ▼     ▼
     TOOLS SERVICES AGENTS
       │     │     │
       └─────┼─────┘
             ▼
        MODEL ROUTER
             │
      ┌──────┼──────┐
      ▼      ▼      ▼
    LOCAL   REMOTE  CUSTOM
    MODELS  MODELS  PROVIDERS
```

---

## Component Diagram

```
MOON/
├── main.py                  # Entry point — CLI, service bootstrap
├── engine.py                # Core agent engine (4,352 lines)
│   ├── Persona detection (13 personas)
│   ├── Intent routing (13 rules)
│   ├── Tool-calling loop
│   └── Response generation
├── app/                     # Core application package
│   ├── voice.py             # Female voice TTS (espeak + SoX)
│   ├── memory.py            # SQLite + semantic memory
│   └── ...
├── src/agents/              # 50+ specialist agents
│   ├── cyber/               # Red-team / offensive security
│   ├── research/            # Web research, OSINT
│   ├── coding/              # Code generation, review
│   ├── security/            # Defensive security
│   ├── voice/               # Voice interaction
│   ├── admin/               # System administration
│   ├── creative/            # ASCII art, image gen
│   ├── monitor/             # Health, watchdog
│   └── ...
├── src/tools/               # Tool registry + tool definitions
│   ├── tools_core.py        # 14 core tools
│   ├── tools_pro.py         # 52 professional tools (task_queue, workflow, etc.)
│   ├── tools_advanced.py    # Advanced tools (web, API, search)
│   └── ...
├── tests/                   # 130 tests (unit, integration, agent, tool, e2e)
├── deploy/                  # systemd service files
├── install.sh               # One-command installer
├── install_moon.py          # Python-stage bootstrap + verification
├── install_moon_full.py     # Full installer (deps, models, voice, smoke test)
├── setup_wizard.py          # Interactive configuration wizard
└── Makefile                 # Common targets: test, voice, models, install
```

---

## Agent Engine (`engine.py`)

The engine is the heart of MOON. On each request:

1. **Input Validation** — sanitize and validate the request
2. **Context Collection** — gather conversation history, memory, relevant tools
3. **Intent Understanding** — 13 personas, 13 intent routing rules
4. **Task Decomposition** — break complex requests into subtasks
5. **Planning** — create an execution plan
6. **Tool Selection** — choose appropriate tools from the registry
7. **Permission/Safety Check** — RUNLEVEL-based gating (SAFE → BLOCKED)
8. **Tool Execution** — execute selected tools
9. **Observation** — capture tool outputs
10. **Error Recovery** — retry, fallback, or escalate
11. **Result Verification** — confirm the result meets the request
12. **Memory Update** — store facts, lessons, outcomes
13. **Final Response** — return structured result to user

---

## Tool Registry

MOON has a three-tier tool architecture:

| Tier | File | Count | Description |
|------|------|-------|-------------|
| Core | `tools_core.py` | 14 | File ops, shell, git, HTTP, memory, search, eval |
| Professional | `tools_pro.py` | 52 | Task queue, workflow DAG, resources, chain, parallel, structured output, report, decision matrix |
| Advanced | `tools_advanced.py` | 22+ | Hermes bridge, web research, OSINT, code tools |

Each tool has: name, description, input schema, output schema, validation, permission level, timeout, error handling, logging.

---

## Memory System

Three layers:

1. **Conversation Memory** — in-memory, current session only
2. **Workspace Memory** — SQLite (`moon_memory.db`), persists across restarts
3. **Semantic Memory** — TF-IDF based retrieval over stored knowledge

Auto-learning is configurable: every interaction's facts, tool outcomes, and lessons can be consolidated into durable memory.

---

## Agent Architecture

MOON uses a main-agent + specialist-agents model:

- **Main Agent** — routes requests, chooses tools, coordinates
- **Planner** — decomposes complex tasks
- **Research Agent** — web research, OSINT
- **Coding Agent** — code generation, review, debugging
- **File Agent** — file operations, inspection
- **Automation Agent** — workflow execution, task queues
- **System Agent** — system info, service control
- **Web/API Agent** — HTTP, API interaction
- **Specialized Agents** — cyber, voice, creative, monitor, etc.

Specialist agents communicate through well-defined interfaces. The main agent coordinates rather than duplicating logic.

---

## Model Provider System

MOON uses Ollama as the primary local LLM provider:

- **OllamaClient** — speaks the Ollama REST API
- **Model selection** — per-agent model configuration
- **Fallback** — OpenAI-compatible API as secondary
- **No hard-coded keys** — all credentials via environment variables

---

## Interface Layer

| Interface | Entry Point | Description |
|-----------|-------------|-------------|
| CLI | `moon` or `python main.py` | Terminal-based interaction |
| REST API | `http://127.0.0.1:8777/api/...` | HTTP endpoints for integration |
| Web HUD | Browser → `http://127.0.0.1:8777` | Neural Brain Command Center (Three.js) |
| Voice | `make voice` | Typed/talked input → female voice output |

---

## Deployment

- **systemd user service** — auto-start, self-heal, deep monitoring every 15 min
- **Installer** — `install.sh` (bash) + `install_moon_full.py` (Python) handle everything
- **Port** — default `8777` (configurable via `MOON_PORT`)
