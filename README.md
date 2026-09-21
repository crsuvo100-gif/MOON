# Moon_Twin — Standalone AI Agent System

A self-contained AI agent system. Runs on its own port (:8778), its own
virtualenv, and its own codebase. Fully independent — no connection to any
other project.

## What it is

- **8 agent personas**: general, code, security, research, voice, admin, creative, monitor
- **Per-prompt agent selection**: `agent:<name> <message>` prefix syntax
- **Intent→agent routing**: keyword-based automatic routing
- **Tool framework**: system_info, network_scan, security_tools, file_read, file_write, shell, memory_read, memory_write
- **SQLite-backed session memory**
- **Hermes-desktop-terminal replica TUI**: interactive REPL with command palette
- **REST + WebSocket API**: `/api/moon-agent` on port :8778

## Entry points

```bash
moon_twin                 # Interactive terminal REPL
moon_twin --list          # List all agents
moon_twin --route "query" # Show which agent handles a query
moon_twin "message"       # Process a single message (non-interactive)
moon_twin --json "msg"    # JSON output mode
moon_twin --agent code "write hello"  # Force a specific agent
moon_twin_api             # Start /api/moon-agent server on :8778
moon_twin_api --test      # Run API self-test
```

## API endpoints (port :8778)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/moon-agent` | List all agents |
| POST | `/api/moon-agent` | Process a message |
| GET | `/api/moon-agent/route?query=<q>` | Route a query |
| GET | `/api/moon-agent/agents` | List agents (alias) |
| GET | `/api/moon-agent/memory` | Get memory |
| POST | `/api/moon-agent/memory` | Set memory |
| WS | `/api/ws` | Real-time WebSocket |

## Layout

```
Moon_Twin/
├── main.py              # CLI entry point (moon_twin)
├── agent/
│   ├── engine.py        # Agent engine: personas, routing, tools, LLM hook
│   ├── api.py           # Starlette ASGI API server (/api/moon-agent)
│   └── memory.py        # SQLite session memory store
├── terminal/
│   └── app.py           # Hermes-desktop-terminal replica TUI
├── .venv/               # Python virtualenv (gitignored)
├── requirements.txt     # Dependencies
├── .env.example         # Example env config (gitignored)
└── README.md
```

## Dependencies

- Python 3.10+
- `rich` — terminal UI
- `starlette` + `uvicorn` — ASGI API server
- `websockets` — WebSocket client/server
- Python stdlib: `asyncio`, `socket`, `sqlite3`, `subprocess`, `platform`

## Separation

Moon_Twin's code imports **only from itself** (`agent.engine`, `terminal.app`).
It does not import from any external project.
Moon_Twin runs on `127.0.0.1:8778`.
