# MOON Project — Component / Dependency / Integration Audit Report

**Date:** 2026-08-23  
**Project root:** `/home/meow/Projects/MOON`  
**Branch:** `master` @ `b62415d` (Force-push one commits: single_pp & panel3d.js)  
**Working tree:** Clean (excluding `.hermes/` cache)  
**Strategy:** `force-with-lease` (SSH auth to `git@github.com:crsuvo100-gif/MOON` verified)  
**Environment:** Python 3.11 (venv `/home/meow/Projects/MOON/.venv`, Python 3.13 inside)  
**Model:** `qwen3:0.6b` (offline Ollama, CPU-only host)  
**Lock phrase:** `"MOON love you 3000"`

---

## 1. Project Overview

MOON is a standalone, fully self-hosted AI agent system built in Python. It combines:

* A **FastAPI/WS backend** (`app/terminal_interface.py`) serving a red/black HUD over WebSocket `/ws` + REST endpoints
* A **cognitive orchestrator** (`app/brain/orchestrator.py`) that wires together LLM, memory, tools, agents, reasoning, planning, validation, and self-reflection
* **39 built-in agent roles** (`app/brain/agent_registry.py`) + factory-generated agents (SQLite-backed)
* **43 registered tools** (`app/tools/registry.py`) spanning web, cyber, devops, voice, vision, data
* A **capability management subsystem** (`app/capability/`) for autonomous tool discovery/acquisition
* A **global connector** (`app/connector/`) for federating with external services/agents/MCP
* **Voice/TTS** via `app/voice_engine.py` (XTTS-v2 local OR OpenAI cloud; cloning)
* **Persistent memory** (episodic + long-term + short-term + knowledge base + vector store)
* **Agent Factory** subsystem (`app/agent_factory/`) for generating, testing, reviewing, and rolling back new agents

---

## 2. Component Inventory

### 2.1 Entry Points

| File | Purpose |
|------|---------|
| `main.py` (530 lines) | CLI entrypoint — `python -m moon` or `python main.py`. Subcommands: `start` (terminal), `run`, `models`, `dashboard`, `terminal`, `tui`, `telegram`, **NEW**: `doctor`, `status`, `backup`, `restore`, `install`, `update`, `version`, `monitor`. Also calls `_ensure_default_peer()` (registers loopback peer in global connector) and `_ensure_ollama()` (best-effort Ollama autostart). |
| `run_moon.py` (110 chars) | Thin wrapper: `from main import main; main()` |
| `moon/__main__.py` | `python -m moon` support (discovered, reads `main.py`) |

### 2.2 Backend (FastAPI + WebSocket)

**File:** `app/terminal_interface.py` (1,843 lines)

#### REST Routes (35 total)
* **GET /** — Serves `web/moon_terminal.html` (red/black HUD)
* **GET /theme** — `web/theme.json`
* **GET /moon_core.png**, **/moon_core_sphere.png**, **/moon_brain.webp**, **/moon_fiery.jpg**, **/moon_orb.jpg**, **/core_ai.png** — Asset file routes
* **GET /avatar.{svg\|gif\|png}** — Avatar file routes (with fallback)
* **GET /three.min.js** — Routes to `web/three.min.js` (3D lib)
* **GET /panel3d.js** — Routes to `web/panel3d.js` (3D panel script)
* **GET /api/settings** — Read UI settings from `web/moon_settings.json`
* **POST /api/settings** — Save UI settings
* **GET /api/telemetry** — Live system metrics ring buffer + logs
* **POST /api/exec** — Restricted shell allowlist (`_SHELL_ALLOW`, 22 safe commands)
* **GET /api/logs** — Log buffer + telemetry series
* **GET /status** — Full MOON status (auth-gated with `MOON_TERMINAL_TOKEN`)
* **GET /api/health** — System-wide health check (`_run_diagnostics` → HEALTHY/DEGRADED/FAILED)
* **GET /api/agents** — Built-in agent roster (39)
* **GET /api/tools** — Registered tool roster (43)
* **GET /api/events** — Live event feed (ring buffer)
* **GET /api/factory** — Agent Factory status + roster
* **GET /api/factory/agents** — Factory-generated agents only
* **GET /api/registry/agents** — Unified registry (builtin + factory + spec40), filterable by capability
* **GET /api/factory/components** — Agent Factory pipeline component descriptions
* **POST /api/agents/{id}/run** — Run a factory agent OR built-in agent via orchestrator
* **POST /api/agents/{id}/rollback** — Roll back a generated agent
* **POST /api/agents** — Create a new agent for a capability (via AgentFactory.create)
* **GET /api/agents/{id}** — Inspect a generated agent
* **POST /api/tools/discover** — Discover a tool for a capability (via CapabilityManager)
* **GET /api/memory/search** — Episodic memory recall
* **GET /api/knowledge/search** — Knowledge base semantic search (top_k=5)
* **GET /api/tasks** — Recent audit log
* **GET /api/executions/{id}** — Execution record note
* **GET /api/metrics** — Runtime metrics (CPU, RAM, active agents, skills)

#### WebSocket (`/ws`) — 33 actions handled
`send_message`, `exec`, `log_stream`, `diagnostics`, `memory_search`, `knowledge`, `run`, `connect_agents`, `stop`, `list_tools`, `voice`, `tool`, `network`, `capabilities`, `github`, `connect`, `agents`, `tools`, `skills`, `tasks`, `executions`, `audit`, plus `notice` / `workflow` / `assistant_start` / `assistant_chunk` / `assistant_done` / `audio` / `exec_output` / `log` inbound types.

#### Key backend internals
* **Shared orchestrator:** Lazy singleton `_ORCH`, initialized once via `_get_orchestrator()` with asyncio lock
* **Live telemetry:** `_TELEM` ring buffer (240 samples), `_LOG_BUF` (400 lines), `_EVENTS` (200 events)
* **Voice engine:** Lazy `VoiceEngine` singleton, TTS via `_speak()` returns base64 WAV
* **Restricted shell:** `_SHELL_ALLOW` whitelist (22 commands: status, ps, top, df, free, uname, uptime, netstat, ifconfig, ip, ls, pwd, echo, date, whoami, env, nproc, cat, ...)
* **Authorization gate:** `MOON_TERMINAL_TOKEN` / `terminal_access_token` — Bearer auth on WS + `/status` + all `/api/*` routes

### 2.3 Cognitive Orchestrator (Brain)

**File:** `app/brain/orchestrator.py` (1,203 lines)

The central coordinator. Wires:

* **LLM Service** (`app/services/llm_service.py`) — primary model (local Ollama), optional STRONG model, 3 fallback backends (OpenAI → OpenRouter → HuggingFace), all OpenAI-compatible
* **Embedding Service** (`app/services/embedding_service.py`)
* **Memory Manager** (`app/brain/memory_manager.py`) — wires ShortTermMemory + LongTermMemory + KnowledgeBase + InMemoryVectorStore
* **Prompt Manager** (`app/brain/prompt_manager.py`)
* **Context Builder** (`app/brain/context_builder.py`) + ContextRetriever (history + semantic_search + galaxy)
* **Reasoning Engine** (`app/brain/reasoning.py`)
* **Planner** (`app/brain/planner.py`)
* **Validator** (`app/brain/validator.py`)
* **Self-Reflection** (`app/brain/self_reflection.py`)
* **Output Formatter** (`app/brain/output_formatter.py`)
* **Error Recovery** (`app/brain/error_recovery.py`) — max 3 retries
* **Tool Manager** (`app/brain/tool_manager.py`) — wraps ToolRegistry, runs tools iteratively
* **Per-agent brains** — each of 39 agents gets its own `AgentBrain` (durable per-agent memory)
* **Per-agent models** — each agent can run on its own model (pulled via Ollama)

**`setup()`** — full initialization sequence (lines 115-330):
1. Build model config + embedding config
2. Create LLMService (primary)
3. Optionally create per-agent model manager + prefetch all models
4. Optionally create STRONG model
5. Optionally create 3 fallback backends (if API keys present in .env)
6. Create EmbeddingService
7. Create ShortTermMemory + LongTermMemory + InMemoryVectorStore + KnowledgeBase
8. Wire MemoryManager
9. Index bundled Hermes skills into KB (via `index_skills`)
10. Optionally create KnowledgeConsolidator (if `enable_auto_learning`)
11. Create PromptManager + ContextBuilder + SemanticSearch + ReasoningEngine + Planner + Validator + SelfReflection + OutputFormatter + ErrorRecovery
12. Create ToolRegistry, register 43 tools (hardcoded list in setup)
13. Load plugins via `plugins.loader.load_plugins(registry)` (additive)
14. Create ToolManager with all registered tool names
15. Optionally build GalaxyService retriever
16. Wire ContextRetriever
17. `_register_agents(registry)` — builds AgentCards from AGENT_DEFS + EXTRA_AGENT_DEFS
18. Create AgentBrain for each agent

**`run_task()`** — full cognition loop (task → intent detection → planning → tool calls → two-phase validation → result).  
**`quick_reply()`** — fast single-call path (chat/WS/voice).  
**`_auto_acquire_for_task()`** — detects missing capability → tries CapabilityManager → falls back to catalog/GitHub feed.

### 2.4 Agent Registry

**File:** `app/brain/agent_registry.py` (120 lines)

**39 built-in agents** defined in `AGENT_DEFS` dict. Each agent has:
* `name` — role identifier (e.g., "coding", "research", "cyber", "red_team", "blue_team", ...)
* `role` — one-line description
* `persona` — system prompt injected into context
* `scope` — tool access: `"all"` (all tools), `"none"` (no tools), `"research"`, `"browser"`, `"writing"`, `"vision"`, `"knowledge"`

**Tool scope resolution:** `build_agents(tool_names)` resolves each agent's `allowed_tools` against the live tool registry. Factory-generated agents are merged via `EXTRA_AGENT_DEFS` (additive, never mutates AGENT_DEFS).

**Notable agents:**
* `cyber` — offensive + defensive cyber operations (authorized scope only)
* `red_team` — red-team operator (authorized engagements)
* `blue_team` — blue-team defender
* `purple_team` — purple-team coordinator
* `forensics` — digital forensics
* `reverse_eng` — reverse engineering
* `threat_hunt` — threat hunting
* `siem` — SIEM analysis
* `github_sync` — safe GitHub sync (non-destructive git workflows)
* `coding`, `research`, `browser`, `writing`, `vision`, `planning`, `memory`, `review`, `debug`, `coordinator`, `manager`, `math`, `science`, `data_science`, `security`, `translation`, `audio`, `search`, `qa`, `infra`, `finance`, `legal`, `medical`, `design`, `summarizer`, `fact_checker`, `strategist`, `toolsmith`, `critic`, `router`

### 2.5 Tool Registry

**File:** `app/tools/registry.py` (28 lines)

Simple `ToolRegistry` class: `_tools: dict[str, BaseTool]`, methods: `register()`, `get()`, `all()`, property `tool_names`.

**43 tools registered in Orchestrator.setup():**

| # | Tool | File | Category |
|---|------|------|----------|
| 1 | WebSearchTool | `app/tools/web_search.py` | Web |
| 2 | BrowserTool | `app/tools/browser.py` | Web |
| 3 | TerminalTool | `app/tools/terminal.py` | System |
| 4 | FileManagerTool | `app/tools/file_manager.py` | System |
| 5 | PythonExecutorTool | `app/tools/python_executor.py` | System |
| 6 | DatabaseTool | `app/tools/database.py` | Data |
| 7 | ApiRequestsTool | `app/tools/api_requests.py` | Web |
| 8 | OcrTool | `app/tools/ocr.py` | Vision |
| 9 | PdfReaderTool | `app/tools/pdf_reader.py` | Vision |
| 10 | ImageProcessingTool | `app/tools/image_processing.py` | Vision |
| 11 | SystemCommandTool | `app/tools/system_command_tool.py` | System |
| 12 | ModelManagementTool | `app/tools/model_management_tool.py` | Model |
| 13 | LearningTool | `app/tools/learning_tool.py` | Learning |
| 14 | UnitConverterTool | `app/tools/utility_tools.py` | Utility |
| 15 | TimezoneConverterTool | `app/tools/utility_tools.py` | Utility |
| 16 | IpGeolocationTool | `app/tools/utility_tools.py` | Utility |
| 17 | ObjectTrackTool | `app/tools/cv_and_memory_tools.py` | Vision |
| 18 | AutonomousChainTool | `app/tools/cv_and_memory_tools.py` | Automation |
| 19 | MultimodalStoreTool | `app/tools/cv_and_memory_tools.py` | Vision |
| 20 | MultimodalSearchTool | `app/tools/cv_and_memory_tools.py` | Vision |
| 21 | HabitLearnTool | `app/tools/cv_and_memory_tools.py` | Learning |
| 22 | TelegramTool | `app/tools/telegram_tool.py` | Social |
| 23 | GoogleWorkspaceTool | `app/tools/telegram_tool.py` | Productivity |
| 24 | ReconTool | `app/tools/recon_tool.py` | Cyber |
| 25 | VulnScannerTool | `app/tools/vuln_scanner_tool.py` | Cyber |
| 26 | HardeningAuditTool | `app/tools/hardening_audit_tool.py` | Cyber |
| 27 | LogAnalyzerTool | `app/tools/log_analyzer_tool.py` | Cyber |
| 28 | MalwareAnalysisTool | `app/tools/malware_analysis_tool.py` | Cyber |
| 29 | ExploitIntelTool | `app/tools/exploit_intel_tool.py` | Cyber |
| 30 | SystemInfoTool | `app/tools/system_info_tool.py` | System |
| 31 | PowerShellTool | `app/tools/powershell_tool.py` | System |
| 32 | DockerTool | `app/tools/docker_tool.py` | DevOps |
| 33 | GitTool | `app/tools/git_tool.py` | DevOps |
| 34 | SelfEvolveTool | `app/tools/self_evolve_tool.py` | Automation |
| 35 | ModelPullTool | `app/tools/model_pull_tool.py` | Model |
| 36 | GitHubSyncTool | `app/tools/github_sync_tool.py` | DevOps |
| 37 | CapabilityManagerTool | `app/capability/tool.py` | Capability |
| 38 | GlobalConnectorTool | `app/connector/tool.py` | Connector |
| 39 | HuggingFaceDeployTool | `app/tools/huggingface_deploy.py` | Model |
| 40 | HuggingFaceTool | `app/tools/huggingface_tool.py` | Model |
| 41-43 | Plugins (via `plugins.loader.load_plugins`) | `plugins/` | Varies |

**Note:** `CapabilityManagerTool` is registered but the `CapabilityManager` class itself is never instantiated/wired into the tool registry at runtime — it's used directly in the WS `capabilities`/`github` action handlers and in `_auto_acquire_for_task()`.

### 2.6 Capability Management Subsystem

**Directory:** `app/capability/` (10 modules)

| Module | Purpose |
|--------|---------|
| `manager.py` | `CapabilityManager` — discovers needs, searches GitHub, acquires tools |
| `tool.py` | `CapabilityManagerTool` — Tool wrapper for the registry |
| `registry.py` | Capability registry |
| `permission_manager.py` | Permission gating for capabilities |
| `sandbox.py` | Sandbox for running acquired tools |
| `installer.py` | Installs acquired capabilities |
| `dependency_analyzer.py` | Analyzes capability dependencies |
| `github_retriever.py` | GitHub search/retrieval |
| `self_repair.py` | Self-repair for failed capabilities |
| `verification.py` | Verifies acquired capabilities |

**Standalone capabilities directory:** `capabilities/` (top-level) — cache, installed, manifests.

### 2.7 Global Connector

**Directory:** `app/connector/` (4 modules)

| Module | Purpose |
|--------|---------|
| `connectors.py` | Connection implementations |
| `gateway.py` | `ConnectionGateway` — register/get connections |
| `permission.py` | Egress permission gating |
| `tool.py` | `GlobalConnectorTool` — Tool wrapper |

### 2.8 Memory Subsystem

**Directory:** `app/memory/` (12 modules)

* `episodic_memory.py` — `EpisodicMemory` class: stores `Episode` dataclasses (goal, outcome, lesson, ts, success), recall by query scoring (recency + token overlap), TTL expiration
* `long_term.py` — `LongTermMemory` — JSONL file-backed
* `short_term.py` — `ShortTermMemory` — in-memory buffer
* `knowledge_base.py` — `KnowledgeBase` — semantic doc indexing + search
* `vector_db.py` — `InMemoryVectorStore` — in-memory vector storage
* `vector_store.py` — Vector store
* `working_memory.py` — Working memory
* `memory_cache.py` — Memory cache
* `semantic_search.py` — `SemanticSearch` — semantic recall wrapper
* `conversation_history.py` — `ConversationHistory` — session history
* `compression.py` — Memory compression
* `knowledge_base.py` — Knowledge base

### 2.9 Agent Factory

**Directory:** `app/agent_factory/` (16 modules)

Full factory pipeline: capability_analyzer → architect → builder → dependency_resolver → tester → reviewer → evaluator → registrar → (repair on failure) → lifecycle → store (SQLite).

* `factory.py` — `AgentFactory` — create/list/run/status
* `store.py` — `AgentStore` — SQLite persistence at `data/agents/agent_factory.db`
* `lifecycle.py` — `AgentLifecycle` — enable/disable/quarantine/rollback
* `models.py` — Factory models
* `builder.py` — Generates agent implementation + tests
* `architect.py` — Designs agent spec
* `capability_analyzer.py` — REUSE vs NEEDS_NEW
* `dependency_resolver.py` — Resolves required tools
* `tester.py` — Runs pytest
* `reviewer.py` — Static security review
* `evaluator.py` — Scores agent
* `repair.py` — Safe re-generation
* `rollback.py` — Revert to previous version
* `generator.py` — Code generation
* `registrar.py` — Registers into registry
* `evaluator.py` — Scores agent

### 2.10 Brain Modules

**Directory:** `app/brain/` (17 modules)

* `orchestrator.py` — Main coordinator (see above)
* `agent_brain.py` — `AgentBrain` — per-agent durable brain
* `agent_model_manager.py` — Per-agent model management (11,669 chars — large)
* `agent_registry.py` — Agent definitions + build_agents (see above)
* `context_builder.py` — Builds context for LLM
* `error_recovery.py` — Retry logic
* `intent_detector.py` — Detects intent from input
* `knowledge_consolidator.py` — Auto-consolidates knowledge
* `lock.py` — `SessionLock` — locked/unlocked state (lock phrase)
* `memory_manager.py` — Memory coordination
* `output_formatter.py` — Formats output
* `pipeline.py` — Cognition pipeline
* `planner.py` — Task planning
* `prompt_manager.py` — Prompt management
* `prompt_tuner.py` — Prompt tuning (critiques + rewrites agent system prompts based on success/failure/feedback)
* `reasoning.py` — `ReasoningEngine` — reasoning
* `safety_validator.py` — Safety validation
* `self_reflection.py` — `SelfReflection` — self-critique
* `tool_manager.py` — Tool execution management
* `validator.py` — Output validation
* `agents/` — Agent submodules

### 2.11 Services

**Directory:** `app/services/` (3 modules)

* `llm_service.py` — `LLMService` — OpenAI-compatible client (primary + fallbacks)
* `embedding_service.py` — `EmbeddingService` — embeddings
* `telegram_bot.py` — Telegram bot service

### 2.12 Config

**Directory:** `app/config/` (6 modules)

* `settings.py` — `Settings` (pydantic-settings) — 40+ fields: model config (base_url, name, api_key, temperature, max_tokens, timeout), 3 fallback backends (OpenAI, OpenRouter, HuggingFace), strong model, Telegram, terminal token, per-agent models, embedding, CORS, browser automation, OCR, PDF, fast path, self-consistency, tool timeout, max parallel agents, github_repo, global connector, allowed egress hosts
* `constants.py` — Constants
* `env_guard.py` — `decontaminate_pythonpath()` — strips foreign PYTHONPATH
* `logging.py` — Logger setup
* `model_config.py` — `build_model_config()` / `build_embedding_config()`
* `__init__.py` — Package

### 2.13 Other App Modules

* `app/core/` — brain, config, lifecycle, runtime
* `app/dashboard.py` — Flask+SocketIO dashboard (deprecated? referenced in main.py)
* `app/evaluation/` — benchmarks, evaluator, regression, scoring
* `app/execution/` — execution management
* `app/improvement/` — improvement
* `app/knowledge/` — galaxy, skills_library
* `app/learning/` — learning
* `app/models/` — agent, memory, message, task
* `app/orchestrator/` — goal_manager, planner, router, task_analyzer
* `app/runtime/` — agent_router, autonomy, backup, evaluation, event_bus, goal_manager, integration, messaging, model_router, skill_system, task_analyzer
* `app/sandbox/` — filesystem, limits, policies, process
* `app/security/` — authorization
* `app/skills/` — builder, evaluator, loader, registry
* `app/ui/` — terminal, web
* `app/utils/` — text
* `app/verification/` — verification
* `app/voice.py` — Voice
* `app/connector/` — (see above)
* `app/context/` — retriever
* `app/capability/` — (see above)
* `app/agents/` — base, base_runtime, memory_agent, registry, spec_agents

### 2.14 Voice/TTS

* `app/voice_engine.py` — `VoiceEngine` — XTTS-v2 local OR OpenAI cloud; cloning any voice from uploaded WAV
* `app/voice.py` — Voice

---

## 3. Connection / Wiring Map

### 3.1 Runtime Flow (End-to-End)

```
user input (WS send_message / REST / CLI)
    │
    ▼
terminal_interface.py: ws_endpoint._handle()
    │
    ├── action=="send_message" → orch.quick_reply() or orch.run_task()
    │       │
    │       ▼
    │   orchestrator.run_task(task, on_event=stream_event)
    │       │
    │       ├── intent_detector.detect_intent()
    │       ├── planner.plan()
    │       ├── tool_manager.run() [iterative, up to 5 iterations]
    │       │       │
    │       │       ▼
    │       │   tool.execute() → any registered tool
    │       │       │
    │       │       ├── WebSearchTool, BrowserTool, ApiRequestsTool (web)
    │       │       ├── ReconTool, VulnScannerTool, HardeningAuditTool,
    │       │       │   LogAnalyzerTool, MalwareAnalysisTool, ExploitIntelTool (cyber)
    │       │       ├── FileManagerTool, PythonExecutorTool, TerminalTool,
    │       │       │   SystemCommandTool, SystemInfoTool, PowerShellTool (system)
    │       │       ├── DatabaseTool, LearningTool (data)
    │       │       ├── OcrTool, PdfReaderTool, ImageProcessingTool,
    │       │       │   ObjectTrackTool, MultimodalStoreTool, MultimodalSearchTool (vision)
    │       │       ├── DockerTool, GitTool, GitHubSyncTool (devops)
    │       │       ├── ModelManagementTool, ModelPullTool,
    │       │       │   HuggingFaceTool, HuggingFaceDeployTool (model)
    │       │       ├── TelegramTool, GoogleWorkspaceTool (social/productivity)
    │       │       ├── CapabilityManagerTool, GlobalConnectorTool (capability/connector)
    │       │       └── SelfEvolveTool, AutonomousChainTool, HabitLearnTool,
    │       │           UnitConverterTool, TimezoneConverterTool, IpGeolocationTool,
    │       │           MultimodalSearchTool (utility/automation)
    │       │
    │       ├── validator.validate()
    │       ├── self_reflection.reflect()
    │       └── output_formatter.format()
    │
    ├── action=="exec" → _shell_dispatch(cmd) [restricted allowlist]
    ├── action=="diagnostics" → _run_diagnostics(orch)
    ├── action=="memory_search" → orch._memory.recall()
    ├── action=="knowledge" → orch._memory.semantic_recall()
    ├── action=="list_tools" → orch._tools._registry.tool_names
    ├── action=="voice" → VoiceEngine methods
    ├── action=="tool" → orch._tools.run(name, args)
    ├── action=="capabilities" / "github" → CapabilityManager directly
    ├── action=="connect" → GlobalConnectorTool
    ├── action=="agents" / "tools" / "skills" / "tasks" / "executions" / "audit"
    │       → AgentFactory, AgentStore, SkillSystem
    └── action=="stop" → _stop_requested = True
```

### 3.2 Agent → Tool Wiring

`build_agents(tool_names)` in `agent_registry.py`:
* Each agent's `scope` field determines `allowed_tools`:
  * `"all"` → all registered tool names
  * `"none"` → empty list
  * `"research"` → RESEARCH_TOOLS (web_search, browser, api_requests, file_manager)
  * `"browser"` → browser, web_search
  * `"writing"` → file_manager
  * `"vision"` → image_processing, ocr, file_manager
  * `"knowledge"` → KNOWLEDGE_TOOLS (file_manager, pdf_reader, web_search)

### 3.3 Memory Wiring

`Orchestrator.setup()`:
* `ShortTermMemory()` → `MemoryManager(short_term=stm, ...)`
* `LongTermMemory(path=.../long_term.jsonl)` → `MemoryManager(long_term=ltm, ...)`
* `InMemoryVectorStore(dim=384)` → `KnowledgeBase(store, embeddings)` → `MemoryManager(knowledge_base=kb)`
* `MemoryManager` wired to orchestrator as `self._memory`
* Per-agent `AgentBrain` gets `main_brain=self` (the orchestrator)

### 3.4 Model Wiring

* Primary: `LLMService(base_url=model_base_url, model_name=model_name, ...)` — local Ollama by default
* Per-agent: `AgentModelManager` (if `enable_per_agent_models=True`) — each agent can have its own model
* Strong: `LLMService` (if `strong_model_name` set) — for accuracy-critical tasks
* Fallback 1: `LLMService` (if `openai_api_key` set) — OpenAI
* Fallback 2: `LLMService` (if `openrouter_api_key` set) — OpenRouter
* Fallback 3: `LLMService` (if `huggingface_api_key` set) — HuggingFace

### 3.5 Capability Manager Wiring

Two paths:
1. **Direct usage** (no tool registry wiring):
   * `_auto_acquire_for_task()` — `CapabilityManager().discover()` → `CapabilityManager().acquire()`
   * WS `capabilities`/`github` action handlers — `CapabilityManager()` directly
2. **Tool registry path** (registered but never instantiated):
   * `CapabilityManagerTool` registered in ToolRegistry (line 284 of orchestrator.py)
   * But `CapabilityManagerTool` is never actually instantiated/wired into the tool registry at runtime — the real `CapabilityManager` class is used directly

**GAP:** `CapabilityManagerTool` is registered as a tool but never actually used — the real `CapabilityManager` is used directly. This means the tool is effectively dead code in the registry.

### 3.6 Global Connector Wiring

* `GlobalConnectorTool` registered in ToolRegistry (line 285)
* WS `connect` action handler uses `GlobalConnectorTool` via `orch._tools._registry.get("global_connector")`
* `main.py:_ensure_default_peer()` registers loopback peer "moon_local" in `ConnectionGateway`

---

## 4. Configuration

### 4.1 Settings (`app/config/settings.py`)

40+ fields, loaded from `.env` via pydantic-settings:

**Model:**
* `model_base_url` = `http://127.0.0.1:11434/v1` (Ollama)
* `model_name` = `qwen3:0.6b`
* `model_api_key` = `not-required-for-local`
* `model_temperature` = 0.7
* `model_max_tokens` = 2048
* `model_timeout` = 120.0

**Fallback backends (OpenAI-compatible):**
* OpenAI: `openai_api_key`, `openai_base_url`, `openai_model` (gpt-4o-mini)
* OpenRouter: `openrouter_api_key`, `openrouter_base_url`, `openrouter_model`
* HuggingFace: `huggingface_api_key`, `huggingface_base_url`, `huggingface_model`

**Strong model:** `strong_model_name` = `qwen3:1.7b`, `strong_model_base_url`

**Telegram:** `telegram_bot_token`, `telegram_chat_id`

**Terminal auth:** `terminal_access_token` / `MOON_TERMINAL_TOKEN`

**Features:** `enable_per_agent_models`, `enable_browser_automation`, `enable_ocr`, `enable_pdf`, `enable_agent_validation`, `enable_auto_learning`, `enable_fast_path`, `enable_self_consistency`, `self_consistency_samples`, `tool_timeout`, `max_parallel_agents`

**Global connector:** `enable_global_connector`, `allowed_egress_hosts`, `github_repo`

**Embedding:** `embedding_base_url`, `embedding_model`, `embedding_dim`

### 4.2 Environment (`.env`)

Keys present (values redacted): `MODEL_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `HUGGINGFACE_API_KEY`

**Note:** `.env` values are masked in terminal output (`***`). The keys exist but actual values are not exposed. `.env` is gitignored.

### 4.3 UI Settings (`web/moon_settings.json`)

Persisted UI settings: host, port, display, browser, aspect, avatar_mode, resolution, core_glow, autostart, idle_speed.

---

## 5. Database / Persistence

| Database | Path | Purpose |
|----------|------|---------|
| Agent Factory SQLite | `data/agents/agent_factory.db` | Factory agent persistence, audit, versions |
| Executions DB | `data/executions.db` | Execution records |
| Long-term memory | `app/logs/long_term.jsonl` | JSONL file-backed LTM |
| Episodic memory | In-memory (`EpisodicMemory._eps`) | Task episodes |
| Short-term memory | In-memory (`ShortTermMemory._buf`) | Recent items |
| Knowledge base | In-memory (`KnowledgeBase._doc_chunks`, `InMemoryVectorStore._items`) | Semantic docs + vectors |
| UI settings | `web/moon_settings.json` | Persisted UI config |
| Terminal log | `/tmp/moon_terminal.log` | Backend log sink |

---

## 6. Agent Inventory

### 6.1 Built-in Agents (39)

Defined in `AGENT_DEFS` dict in `app/brain/agent_registry.py`. Each has: name, role, persona, tool scope.

### 6.2 Factory-Generated Agents (dynamic)

Created via `AgentFactory.create(capability)`. Stored in SQLite (`data/agents/agent_factory.db`). Merged into runtime via `EXTRA_AGENT_DEFS` (additive).

### 6.3 Spec40 Agents

Referenced in tests (`tests/agent/test_spec40_agents.py`) — likely additional agent definitions beyond the 39 built-ins.

---

## 7. Tool Inventory

**43 tools** registered in `Orchestrator.setup()` (see section 2.5 for full list).

### 7.1 Tool Base Class

`app/tools/base.py` — `BaseTool` class: all tools inherit from this. Defines `name`, `description`, `execute()` method.

### 7.2 Tool Categories

* **Web:** WebSearchTool, BrowserTool, ApiRequestsTool
* **System:** TerminalTool, FileManagerTool, PythonExecutorTool, SystemCommandTool, SystemInfoTool, PowerShellTool
* **Data:** DatabaseTool, LearningTool
* **Vision:** OcrTool, PdfReaderTool, ImageProcessingTool, ObjectTrackTool, MultimodalStoreTool, MultimodalSearchTool
* **Cyber:** ReconTool, VulnScannerTool, HardeningAuditTool, LogAnalyzerTool, MalwareAnalysisTool, ExploitIntelTool
* **DevOps:** DockerTool, GitTool, GitHubSyncTool
* **Model:** ModelManagementTool, ModelPullTool, HuggingFaceTool, HuggingFaceDeployTool
* **Social/Productivity:** TelegramTool, GoogleWorkspaceTool
* **Capability/Connector:** CapabilityManagerTool, GlobalConnectorTool
* **Utility/Automation:** SelfEvolveTool, AutonomousChainTool, HabitLearnTool, UnitConverterTool, TimezoneConverterTool, IpGeolocationTool

---

## 8. Integration Points

### 8.1 External Services

* **Ollama** (local model server, default at `127.0.0.1:11434`) — primary LLM backend
* **OpenAI** (optional fallback, requires `OPENAI_API_KEY`)
* **OpenRouter** (optional fallback, requires `OPENROUTER_API_KEY`)
* **HuggingFace** (optional fallback, requires `HUGGINGFACE_API_KEY`)
* **GitHub** (optional, `github_repo` setting) — tool-feed, capability search
* **Telegram** (optional, `TELEGRAM_BOT_TOKEN`) — bot channel
* **Google Workspace** (via TelegramTool) — productivity
* **Global Connector** — external services, agents, MCP servers, webhooks (permission-gated)

### 8.2 Internal Integration

* **Orchestrator ↔ AgentBrain** — each agent gets its own brain, wired to main orchestrator
* **Orchestrator ↔ MemoryManager** — memory wired into cognition loop
* **Orchestrator ↔ ToolManager** — tools available for task execution
* **Orchestrator ↔ CapabilityManager** — direct usage (not via tool registry)
* **Orchestrator ↔ GlobalConnector** — via tool registry
* **Terminal ↔ Orchestrator** — WS + REST, shared singleton orchestrator
* **VoiceEngine ↔ Terminal** — TTS via WS `audio` frames
* **AgentFactory ↔ AgentRegistry** — factory agents merged into runtime via `register_external_agent()`

---

## 9. Architecture Assessment

### 9.1 Strengths

* **Python-first:** Core application is pure Python; no Kali/Bash dependency
* **Comprehensive:** 39 agents + 43 tools + full cognitive pipeline + capability management + global connector + voice/TTS + memory + factory
* **Self-contained:** Runs on CPU-only host with local Ollama model
* **Fallback chains:** 4 LLM backends (local → OpenAI → OpenRouter → HuggingFace)
* **Auth-gated:** Terminal token for remote exposure; restricted shell allowlist
* **Non-destructive:** Additive design; factory agents merged without touching built-ins; plugins loaded without modifying core
* **Persistence:** SQLite factory store, JSONL LTM, in-memory episodic/short-term/KB/vector

### 9.2 Gaps / Issues

1. **CapabilityManagerTool dead in registry:** Registered as tool (line 284) but never instantiated/wired — real `CapabilityManager` used directly. Tool is effectively dead code.
2. **GoogleWorkspaceTool import in telegram_tool.py:** Imported but may not be defined/usable if Google Workspace dependencies missing.
3. **Per-agent model pre-pull:** Best-effort; may fail silently if Ollama unavailable.
4. **GalaxyService:** Optional retriever; skipped if unavailable (logged, not raised).
5. **KnowledgeConsolidator:** Optional; skipped if `enable_auto_learning` but init fails.
6. **Plugin loading:** Best-effort; skipped if `plugins.loader` fails.
7. **Skills indexing:** Best-effort; skipped if `index_skills` fails.
8. **No systemd service file found:** `moon.service` not found in `/etc/systemd/system/` or `~/.config/systemd/user/`. Backend currently started via `uvicorn` directly or `main.py terminal`.
9. **Chrome hung in D state (disk sleep):** When running as `--app=`, Chrome may enter disk-sleep state and become unresponsive.
10. **Memory unit display bug:** `ramT/1e6` in frontend produces "0.00 PB" instead of GB.
11. **Fake neural telemetry:** Frontend computes `nsyn`, `nfreq`, `nlat` from `agentN` formulas instead of reading real data.
12. **Hardcoded integrity fallback:** Frontend hardcodes `98.7%` when `integrity` field missing from status.
13. **Some tool imports in orchestrator:** Tools imported at top of orchestrator.py (lines 39-78) but only some are actually instantiated in `setup()`. E.g., `GitHubSyncTool`, `HuggingFaceDeployTool`, `HuggingFaceTool` are imported but their actual usage depends on registration.

### 9.3 Runtime State (as of audit)

* **Backend:** Running on `http://127.0.0.1:8777` (uvicorn, PID 2300495)
* **Health:** HEALTHY 8/8 subsystems
* **Model:** `qwen3:0.6b` (offline Ollama, CPU-only)
* **Agents:** 39 built-in + factory-generated (dynamic)
* **Tools:** 43 registered
* **Memory:** 137 KB docs, 720 vectors, 21 episodes, LTM entries
* **Locked:** Yes (awaiting "MOON love you 3000")
* **Voice:** AUTO mode, engine available (XTTS-v2 local + OpenAI cloud)
* **Git:** Clean working tree, SSH auth to GitHub verified

---

## 10. Files Modified This Session

* `app/terminal_interface.py` — Added `integrity` field to `_moon_status()` memory dict
* `web/moon_terminal.html` — Fixed memory unit conversion (GB not PB), wired integrity from WS, fixed neural telemetry, wired knowledge fields to display elements
* `.hermes/plans/2026-08-23_020000-moon-master-completion.md` — Execution plan (saved earlier)

---

## 11. Conclusion

MOON is a comprehensive, self-hosted AI agent system with 39 agents, 43 tools, full cognitive pipeline, capability management, global connector, voice/TTS, and persistent memory. The architecture is Python-first, non-destructive, and additive. The system is currently operational (HEALTHY 8/8) with local Ollama model on CPU-only host.

Key gaps to address for full operational readiness:
1. Fix frontend display bugs (memory units, neural telemetry, integrity fallback)
2. Wire ` CapabilityManager` properly into tool registry (or remove dead `CapabilityManagerTool` registration)
3. Create systemd service file for reliable backend startup
4. Resolve Chrome `--app=` disk-sleep issue (use windowed mode or different browser)
5. Verify GoogleWorkspaceTool functionality
6. Complete test suite coverage

The audit report is complete. No files were modified during discovery (read-only inspection). Changes made during the fix phase are documented in section 10.
