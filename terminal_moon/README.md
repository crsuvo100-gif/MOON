# MOON Terminal — AI agent terminal interface

A three-layer terminal system (Textual TUI + CLI REPL + FastAPI/WS backend)
sharing a single brain core: orchestrator + LLM service + tool manager +
memory manager + session lock + event bus + voice engine.

## Quick start

```bash
cd terminal_moon
python -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pip install -r requirements.txt   # optional, for dev

# Ensure Ollama is running and a model is pulled:
ollama pull qwen2.5:1.5b

# Launch TUI:
.venv/bin/python main.py terminal

# Or bare (same as terminal):
.venv/bin/python main.py

# CLI REPL:
.venv/bin/python main.py cli

# REST + WS backend:
.venv/bin/uvicorn app.terminal_interface:app --port 8777

# Doctor check:
.venv/bin/python main.py doctor

# Status check:
.venv/bin/python main.py status
```

## Entry points

1. Browser: http://127.0.0.1:8777 (REST + WebSocket)
2. Terminal: `./venv/bin/python main.py terminal` (Textual TUI)
3. CLI: `./venv/bin/python main.py cli` (readline REPL)

## Unlock phrase

Default: `MOON love you 3000`  
Override: `MOON_TUI_UNLOCK=...` env var.

When locked, chat and knowledge queries still work. Active operations
(tool use, exec, agent runs) require unlocked state.

## Architecture

```
USER INPUT
   ├─► moonscope TUI  (app/tui.py)         ← Textual, in-terminal
   ├─► CLI REPL       (app/cli/cli.py)      ← readline fallback
   └─► REST + WS API  (app/terminal_interface.py)  ← headless backend
   ▼
SHARED BRAIN CORE
   ├─ Orchestrator      app/brain/orchestrator.py
   ├─ LLMService        app/services/llm_service.py
   ├─ ToolManager       app/brain/tool_manager.py
   ├─ MemoryManager     app/brain/memory_manager.py
   ├─ PromptManager     app/brain/prompt_manager.py
   ├─ Reasoning         app/brain/reasoning.py
   ├─ Planner           app/brain/planner.py
   ├─ Validator         app/brain/validator.py
   ├─ SelfReflection    app/brain/self_reflection.py
   ├─ IntentDetector    app/brain/intent_detector.py
   ├─ SessionLock       app/brain/lock.py
   ├─ EventBus          app/runtime/event_bus.py
   ├─ VoiceEngine       app/voice_engine.py
   └─ Agent brains      app/brain/agent_brain.py
```

## Config

Edit `.env` (copy from `.env.example`). All settings are pydantic-settings
and can be set via env vars with the `MOON_` prefix or directly.

## Dependencies

- Python ≥ 3.10
- Ollama (or any OpenAI-compatible local endpoint) + at least one model
- espeak-ng (optional, TTS fallback)
- Kokoro-ONNX (optional, premium female voice)
- F5-TTS / XTTS (optional, voice cloning)
