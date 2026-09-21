# MOON — Deep Discovery & Architecture Audit (T1, READ-ONLY)

Date: 2026-08-24. Method: full source + installer + runtime inspection. **No files modified.**

---

## 1. What is MOON?
Self-hosted autonomous AI-agent system (`moon-ai-agent` v0.1.0). Local-first:
FastAPI backend (`app.terminal_interface:app` on `0.0.0.0:8777`) serving a
Neural Brain Command Center HUD (pure HTML/Canvas2D), driven by an
`Orchestrator` brain, 39 spec agents (each with a connected AgentBrain), 43
tools, long/short/episodic memory, a knowledge base, and a Kokoro-ONNX
offline female voice. Model backend: local Ollama (qwen3:0.6b primary).

## 2. Major modules (31 app/ subdirs, ~15.4k LOC)
- **Entry/CLI:** `main.py` (`moon` console script) → uvicorn. `scripts/moon_launcher.py` is the cross-platform launcher (ensures Ollama, boots HUD). `run_moon.py` thin wrapper.
- **Backend/UI:** `app/terminal_interface.py` (43 routes: REST + 3 websockets; serves `web/moon_terminal.html`).
- **Brain:** `app/brain/orchestrator.py` (~1200 LOC) + planner, agent_registry, agent_brain, intent_detector, reasoning, validator, memory_manager, tool_manager, context_builder, knowledge_consolidator, lock, output_formatter, error_recovery, safety_validator, self_reflection, prompt_manager, prompt_tuner.
- **Agents:** `app/agents/` (base, base_runtime, memory_agent, registry, spec_agents — 40 spec agents idempotently registered; 39 live).
- **Tools:** `app/tools/` (36 files → 43 registered in Orchestrator.setup()).
- **Services:** `app/services/` (llm_service, hf_inference, embedding_service, telegram_bot).
- **Connector:** `app/connector/` (gateway — Global Connector, registers `moon_local` peer).
- **Capability:** `app/capability/` (manager, tool, permission_manager, installer, self_repair, verification, sandbox, registry).
- **Runtime:** `app/runtime/` (event_bus, autonomy, goal_manager, backup, skill_system, model_router, task_analyzer, agent_router, integration, messaging, evaluation).
- **Memory:** `app/memory/` (long_term, short_term, episodic, vector_db, knowledge_base, memory_manager).
- **Knowledge:** `app/knowledge/` (galaxy, skills_library — 85 skills indexed).
- **Agent Factory:** `app/agent_factory/` (builder, architect, generator, factory, repair, rollback, tester, …).
- **Execution/Verification/Security/Learning/Improvement/Evaluation/Sandbox/UI/API/Models/Prompts/Utils/Core.**
- **Frontend:** `web/moon_terminal.html` (connects to real backend via `WebSocket('/ws')` + `fetch('/api/...')`).
- **Other:** `capabilities/`, `connections/`, `data/` (SQLite), `models/`, `plugins/`, `skills/`, `tests/` (23 files), `voices/`.

## 3. Main entry point
`python -m uvicorn app.terminal_interface:app --host 0.0.0.0 --port 8777`
(via `main.py start` / `scripts/moon_launcher.py terminal`). `pyproject.toml`
exposes `moon = "main:main"`.

## 4. Agents (39 live / 40 spec)
Defined in `app/agents/spec_agents.py` → `register_spec_agents()` registers
into `app/agents/registry.py`. Built into `AgentCard`s by
`app/brain/agent_registry.build_agents(tool_names)` with per-agent allowed-tools
+ per-agent models (AgentModelManager binds qwen2.5:1.5b/3b, qwen2.5-coder:1.5b,
deepseek-r1:1.5b). Each gets a connected AgentBrain (episodic memory). Live
`/api/agents` → 39.

## 5. Tools (43 registered)
Explicitly instantiated in `Orchestrator.setup()` (orchestrator.py:268-289),
then `ToolManager(registry, enabled_tools=all, allow_dangerous=True)`. Plus
plugins via `plugins.loader.load_plugins`. Live `/api/tools` → 43. Includes
web_search, browser, terminal, file_manager, python_executor, system_info,
recon, vuln_scanner, malware_analysis, huggingface_*, telegram, github_sync,
model_pull, capability_manager, global_connector, etc.

## 6. Services
- **LLMService** (OpenAI-compatible → local Ollama qwen3:0.6b primary; fallbacks gpt-4o-mini/openrouter/llama-3.1/HF). Thinking kept ON, 300s client timeout (fixed this session).
- **EmbeddingService** (offline deterministic fallback dim=384).
- **HFInference** (optional HF hosted inference).
- **TelegramBot** (optional channel).
- **ConnectionGateway** (global connector; `moon_local` LIVE peer).
- **CapabilityManager** (1 capability: huggingface; extensible).
- **EventBus** (wired into WS `/ws` → HUD EVENTS).

## 7. Component connections (verified live)
```
USER → web/moon_terminal.html (WS /ws + REST /api/*)
     → app/terminal_interface.py (43 routes; serves HUD; bridges WS↔orchestrator)
     → Orchestrator (app/brain/orchestrator.py)
          ├─ LLMService → Ollama (qwen3:0.6b)        [VERIFIED real completion]
          ├─ MemoryManager → LTM/STM/episodic + vector_db [VERIFIED remember/recall]
          ├─ KnowledgeBase (137 docs / 720 vectors)   [HEALTHY]
          ├─ ToolManager → ToolRegistry (43 tools)    [VERIFIED system_info/python exec]
          ├─ Planner / IntentDetector / Reasoning / Validator / SelfReflection
          ├─ 39 AgentCards → per-agent AgentBrain (connected, model-bound)
          ├─ ContextBuilder + SemanticSearch + Galaxy retriever
          └─ EventBus → WS events stream
```
All connections present and exercised at runtime. No broken import chain.

---

## INSTALL COMPLETENESS AUDIT (critical for "100% install" task)
Two installers exist:
- **`install.sh`** (bash): Python≥3.10 check → venv → `requirements.txt` → `pip install -e .` → `requirements-optional.txt` → delegates to `install_moon.py --no-venv` → browser detect → `~/.local/bin/moon` launcher → `.desktop` → optional systemd.
- **`install_moon.py`** (Python): venv+deps (or `--no-venv`) → `.env` from `.env.example` → Ollama model pull (5 models) → voice stack (espeak-ng/sox + vosk/pyaudio + **TTS/XTTS** [FAILS on py3.13] + openai) → smoke import.

### GAPS (real, blocking "100% functional install"):
| # | Gap | Impact | Severity |
|---|-----|--------|----------|
| G1 | **Kokoro-ONNX + scipy NOT in `requirements.txt`/`requirements-optional.txt`** | Fresh install → no natural female voice; falls back to robotic espeak or silent. The spec'd "sexiest female voice" is MISSING after install. | **HIGH** |
| G2 | **Kokoro model files (kokoro-v1.0.onnx 311MB + voices-v1.0.bin 28MB) not downloaded by installer** | Voice fails on first use until manual download; not "works out of the box". | **HIGH** |
| G3 | `.env` created from `.env.example` with `<set>` literal placeholders | App has pydantic defaults so it RUNS, but `.env` contains junk values (`MODEL_BASE_URL=<set>`). Should use real sane defaults. | MEDIUM |
| G4 | `requirements-optional.txt` still lists `TTS>=0.21` (XTTS) which is uninstallable on py3.13 | Installer prints a noisy failure; benign but misleading. Should drop or guard. | LOW |
| G5 | No single "verify install actually works" step that asserts voice+agent+tool e2e | Install can "succeed" while a subsystem is broken. | MEDIUM |

### Non-gaps (already correct):
- Ollama model pull present (5 models). ✓
- Launcher + desktop entry. ✓
- Smoke import. ✓
- `scripts/moon_launcher.py` exists and ensures Ollama. ✓
- Systemd optional (intentionally default-no; avoids the restart-loop we killed). ✓

---

## Component classification
| Component | Status |
|---|---|
| Orchestrator setup | COMPLETE (verified) |
| LLM (local) | COMPLETE (timeout fixed) |
| 39/40 agents | COMPLETE |
| 43 tools | COMPLETE (execution verified) |
| Memory | COMPLETE |
| Knowledge | COMPLETE |
| REST API (43 routes) | COMPLETE |
| WebSocket /ws | COMPLETE |
| EventBus→HUD | COMPLETE |
| Voice — Kokoro (code) | COMPLETE (code present, works live) |
| Voice — install packaging | **GAP (G1/G2)** — not installed by installer |
| Global Connector | COMPLETE |
| Capability Manager | PARTIAL (1 capability; extensible) |
| HF/Telegram | OPTIONAL (key-gated) |
| Health check | COMPLETE (8/8) |
| Installers | PARTIAL (G1–G5) |
| Tests | COMPLETE (132/132) |

## Verdict
MOON's RUNTIME is fully operational (all critical subsystems verified at
runtime). The only real gaps are in **install packaging** (G1/G2: Kokoro voice
not installed/downloaded; G3: junk `.env`; G5: no post-install e2e). These are
exactly what the "100% installer" task must fix. No architectural rebuild
needed — integration is sound.
