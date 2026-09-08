# Hermes Agent Terminal Architecture — Reference for MOON Terminal Build
# Generated: 2026-09-08
# Source: /home/meow/.hermes/hermes-agent (v0.20.6, upstream b2aa855b)

## VERSION / IDENTITY
- Hermes Agent v0.20.6 (2026.8.27)
- Upstream commit: b2aa855b, 6409 commits behind latest
- Install: git checkout at /home/meow/.hermes/hermes-agent
- CLI entry: /home/meow/.local/bin/hermes (114-byte wrapper)
- Python runtime: 3.11.15
- Total install size: 4.1 GB on disk

## DISK WEIGHT
- venv (python deps): 993 MB
- node_modules (js deps): 1.1 GB
- .git (history): 1.1 GB
- apps/ (Electron desktop): 415 MB
- website/ (docusaurus docs): 28 MB
- tests/ (pytest suite): 41 MB
- hermes_cli/: 14 MB
- optional-skills/: 12 MB
- plugins/: 11 MB
- tools/: 7.2 MB
- agent/: 7.1 MB
- gateway/: 5.4 MB
- ui-tui/: 4.7 MB
- skills/: 4.1 MB
- web/ (dashboard frontend): 2.9 MB
- scripts/: 1.7 MB
- tui_gateway/: 1.5 MB
- Sans vendor (venv/node_modules/.git): 566 MB actual source/assets

## FILE / LINE COUNT (source, sans vendor)
- Total non-vendor files: ~10,157
- Python source lines: 351,024 lines
- All source lines (py/js/ts/md/yaml/json/css/html/rs/...): 330,222 lines
- By language: Python 4,776 files, TypeScript 1,935, Markdown 1,581, TSX 796, YAML 239, JSON 112, Rust 10, Shell 38, plus HTML/CSS/Stylus/Nix/LaTeX/PDF/icons

## ARCHITECTURE — TOP-LEVEL LAYOUT
/home/meow/.hermes/hermes-agent/
├── run_agent.py          # AIAgent core conversation loop (the "brain")
├── cli.py                # Interactive CLI — prompt_toolkit TUI, REPL, banner
├── cli-config.yaml.example
├── hermes_bootstrap.py   # Windows UTF-8 stdio init (no-op on POSIX)
├── hermes_constants.py   # Paths, env vars, defaults
├── hermes_logging.py     # Logging setup
├── hermes_state.py       # SQLite session store
├── model_tools.py        # Tool discovery + dispatch
├── toolsets.py           # Toolset definitions (TOOLSETS dict)
├── toolset_distributions.py
├── acp_adapter/          # ACP (IDE integration) server — 10 files
├── agent/                # 143 files — prompt builder, compression, memory,
│                         # credential pooling, skill dispatch, transports,
│                         # conversation loop, context engine, monitoring, LSP,
│                         # MoA, PET, learning graph, etc.
├── apps/                 # 746 files — Electron desktop app (392M unpacked)
├── assets/               # 1 file (20K)
├── cron/                 # 23 files — job scheduler (jobs.py, scheduler.py, lifecycle_guard, notepad, incidents, executions)
├── docker/               # 18 files — Docker + docker-compose
├── docs/                 # 20 files — 560K internal docs
├── evals/                # 38 files — evaluation harnesses
├── gateway/              # 151 files — messaging gateway: platforms/ (telegram, discord, slack, signal, webhook, api_server...), relay, slash_commands, session, browser_control_broker, kanban_watchers
├── hermes_cli/           # 563 files — all CLI subcommands: commands.py (slash registry), config.py, setup.py, doctor.py, gateway.py, cron.py, kanban.py, plugins.py, pty_session.py, pty_bridge.py, web_server.py, web_routers/, session_export_html.py, status.py, voice.py, hooks.py, etc.
├── locales/              # 17 files — i18n
├── mcp-research-data/    # 5 files
├── native/               # 5 files
├── nix/                  # 18 files
├── node_modules/         # 91,303 files — JS deps (1.1 GB)
├── optional-mcps/        # 65 files
├── optional-skills/      # 718 files
├── plugins/              # 498 files — browser, disk-cleanup, achievements, image_gen, kanban, memory/honcho, observability/langfuse, platforms (a2a, discord, email, feishu, google_chat, photon, slack, wecom, telegram), spotify, teams_pipeline, security-guidance
├── scripts/              # 82 files — release, test runners, smoke tests, keystroke diagnostic, profile-tui, toolperf, analyze_livetest
├── skills/               # 330 files — installed skills
├── tests/                # 3,522 files — ~3000 pytest tests
├── tests-js/             # 41 files — JS-side tests (6.6M)
├── tui_gateway/          # 55 files — TUI gateway server (ws, slash_worker, session, methods)
├── providers/            # 5 files
├── venv/                 # 23,502 files — Python virtualenv (993M)
├── web/                  # 460 files — dashboard web frontend (React/TS, 14M)
├── website/              # 812 files — Docusaurus docs site (28M)
├── .github/              # 42 files — CI workflows (30+), issue templates, PR template, actions
├── .git/                 # 1,969 files — full git history (1.1 GB)
├── Dockerfile, docker-compose.yml, flake.nix, constraints-termu.txt
└── .bak config snapshots, .env, .curator_backups, etc.

## TERMINAL MODULE — tools/terminal_tool.py (4,213 lines, 190 KB)
Core execution engine. Key facts:
- Executes commands in 6 backends: local, docker, modal (direct + managed), vercel_sandbox, ssh, singularity, daytona
- Background task support with process registry
- VM/container lifecycle management + automatic cleanup after inactivity
- Global interrupt event: polling during execution so user interrupts kill long-running subprocesses immediately
- Hard foreground timeout cap (override via TERMINAL_MAX_FOREGROUND_TIMEOUT env var)
- Shell heredoc support (strip_inert_heredoc_bodies)
- Error redaction via agent.redact before serializing error envelopes
- Environment selection via TERMINAL_ENV env var
- Cloud sandbox note: persistent filesystems exist but don't guarantee same live sandbox or long-running processes survive cleanup/idle reaping/Hermes exit

Terminal-adjacent tools:
- tools/environments/ — base, local, docker, modal, vercel_sandbox, singularity, daytona, managed_modal (8 env backends)
- tools/terminal_hints.py
- tools/read_terminal_tool.py
- tools/close_terminal_tool.py
- tools/process_registry.py
- tools/terminal_tool.py (main — 4,213 lines)

## CLI / TUI MODULE — cli.py + hermes_cli/
cli.py is the interactive terminal UI. Built on prompt_toolkit:
- FileHistory, PTStyle, patch_stdout, Application, Layout, HSplit, Window, FormattedTextControl, ConditionalContainer, CompletionsMenu, TextArea, KeyBindings, print_formatted_text
- Separate files: curses_ui.py, pt_input_extras.py, pty_session.py, pty_bridge.py, stdio.py, input_sanitize.py
- Slash command registry: hermes_cli/commands.py (CommandDef) — every consumer (autocomplete, Telegram menu, Slack mapping, /help) derives from it

TUI gateway (separate): tui_gateway/ — WebSocket server for web/TUI dashboard

## AGENT CORE — run_agent.py + agent/
run_agent.py: AIAgent class, conversation loop:
- "Automatic tool calling loop until completion"
- "Configurable model parameters"
- "Error handling and recovery"
- "Message history management"
- "Support for multiple model providers"
- Lazy-imports OpenAI SDK (~240ms saved on startup)

agent/ folder (154 Python files, 7.1M):
- conversation_loop.py — main loop
- context_engine.py, context_compressor.py, context_references.py, conversation_compression.py, native_compaction.py — context management
- prompt_builder.py — system prompt construction
- system_prompt.py — prompt content
- tool_executor.py, tool_dispatch_helpers.py, tool_guardrails.py, tool_result_classification.py — tool dispatch
- model routing: transports/ (anthropic.py, chat_completions.py, codex.py, codex_app_server_session.py, hermes_tools_mcp_server.py)
- credential pooling: credential_pool.py, credential_sources.py, credential_persistence.py, secret_scope.py
- memory: memory_manager.py, memory_provider.py
- skills: skill_commands.py, skill_utils.py, learn_prompt.py
- delegation: delegation_context.py, subagent_lifecycle.py
- monitoring: monitoring/ (emitter, events, cron_health, gateway_health, otlp_exporter, policy, redaction)
- LSP: lsp/ (client, server, manager, protocol, workspace, reporter, eventlog, install, cli, range_shift)
- MoA: moa_loop.py, moa_trace.py
- PET: pet/ (generate/, manifest, render, state, store, constants)
- learning_graph.py, learning_graph_render.py, learning_mutations.py
- coding_context.py, plan_prompt.py
- display.py, compaction_display.py
- error handling: error_classifier.py, error_surface.py, errors.py, empty_response_guard.py
- session: session_activity.py, title_generator.py

## CONFIG & STATE
~/.hermes/config.yaml — main config (9,298 bytes)
~/.hermes/.env — API keys and secrets (24,386 bytes)
~/.hermes/auth.json — OAuth tokens + credential pools (15,134 bytes)
~/.hermes/hermes_state.sqlite — session store (SQLite)
~/.hermes/sessions/ — session transcripts
~/.hermes/logs/ — gateway + error logs
~/.hermes/cron/ — scheduled jobs
~/.hermes/checkpoints/ — filesystem checkpoints for /rollback
~/.hermes/cache/ — runtime cache
~/.hermes/desktop/ — desktop integration
~/.hermes/attachments/ — pasted images
~/.hermes/audio_cache/ — TTS output
~/.hermes/skills/ — installed skills

Config sections: model, agent (max_turns=90, tool_use_enforcement), terminal (backend, cwd, timeout=180), compression (enabled, threshold=0.50, target_ratio=0.20), display (skin, tool_progress, show_reasoning, show_cost), stt, tts, memory, security (tirith_enabled, website_blocklist), delegation (max_iterations=50), checkpoints (max_snapshots=50)

## KEY DESIGN PRINCIPLES (from AGENTS.md)
1. Per-conversation prompt caching is sacred — nothing mutates past context or swaps toolsets mid-conversation except context compression
2. Core is a narrow waist — capability lives at the edges; new model tools are expensive (sent on every API call), so prefer CLI+skill > service-gated tool > plugin > MCP > new core tool
3. E2E validation over green unit mocks
4. Message role alternation must stay strict (never two same-role messages in a row)
5. System prompt must be byte-stable for the life of a conversation

## SLASH COMMANDS (in-session, from registry)
Session: /new, /clear, /retry, /undo, /title, /compress, /stop, /rollback, /snapshot, /background, /queue, /steer, /agents, /resume, /goal, /redraw
Config: /config, /model, /personality, /reasoning, /verbose, /voice, /yolo, /busy, /indicator, /footer, /skin, /statusbar
Tools/Skills: /tools, /toolsets, /skills, /skill, /reload-skills, /reload, /reload-mcp, /cron, /curator, /kanban, /plugins
Gateway: /approve, /deny, /restart, /sethome, /update, /topic, /platforms
Utility: /branch, /fast, /browser, /history, /save, /copy, /paste, /image
Info: /help, /commands, /usage, /insights, /gquota, /status, /profile, /debug
Exit: /quit, /exit, /q

## CLI SUBCOMMANDS (hermes <command>)
chat, setup, model, config, tools, skills, mcp, gateway, sessions, cron, webhooks, profile, auth, insights, update, pairing, plugins, honcho, memory, completion, acp, claw migrate, uninstall
Plus: --version, --resume, --continue, --worktree, --skills, --profile, --yolo, --pass-session-id, --quiet

## MESSAGING GATEWAY PLATFORMS SUPPORTED
Telegram, Discord, Slack, WhatsApp, Signal, Email, SMS, Matrix, Mattermost, Home Assistant, DingTalk, Feishu, WeCom, BlueBubbles (iMessage), Weixin (WeChat), API Server, Webhooks — ~20+ platforms total.

## HERMES WEB SERVER (hermes_cli/web_server.py)
- FastAPI backend serving Vite/React frontend + REST API
- Default port: 9119 (override --port)
- Key endpoints: /api/health, /api/status, /api/files, /api/fs/*, /api/media, /api/chat/image-upload, /api/ssh/ownership
- Auth: token-based (?token= query param or Authorization header), SSH-session tokens, dashboard auth gate, plugin API runtime gate
- Lifespan: _lifespan(app) — manages desktop cron ticker, gateway module warm-up, session DB reconcile
- Middleware: host_header_middleware, auth_middleware, _token_auth_seam, _dashboard_health_middleware, _plugin_api_runtime_gate, _dashboard_auth_gate
- Web routers: cron.py, git.py, mcp.py, profiles.py, sessions.py, skills.py, tools.py

## HERMES DESKTOP (Electron app, apps/)
- 746 files, 415 MB on disk
- Unpacked release: 392M at apps/desktop/release/linux-unpacked/
- Integrates: CLI REPL, TUI, gateway, web dashboard
- Desktop entry: ~/.local/share/applications/hermes.desktop

## WHAT "TERMINAL LENGTH / WEIGHT / BORDER" MEANS IN REAL TERMS
- "terminal length": terminal_tool.py alone is 4,213 lines; full terminal toolchain (terminal_tool + environments/ backends + read_terminal + close_terminal + process_registry + terminal_hints + pty_bridge + pty_session + curses_ui + stdio + input_sanitize + terminal_breadcrumbs + shell_heredoc + all env probe/bridge tests) spans several thousand more lines across a dozen files
- "weight" (disk + complexity): terminal subsystem is part of the 7.2M tools/ dir; whole agent is 351K Python lines across ~4,776 .py files; full install is 4.1GB (993MB venv + 1.1GB node_modules + 1.1GB .git + 566MB source/assets)
- "border" (boundaries/interfaces): tool registry (tools/registry.py) is border between tools and agent loop; run_agent.py AIAgent is border between model and tools; cli.py + hermes_cli/commands.py is border between user and agent; gateway/run.py + platforms/ is border between messaging apps and agent; config.yaml + .env is border between user config and internals

## HERMES TERMINAL TOOL — KEY INTERFACES FOR MOON TO MIMIC
1. Tool dispatch: tools/registry.py → tool_error helper → handler registration pattern
2. Environment abstraction: tools/environments/base.py → local/docker/modal/vercel_sandbox/singularity/daytona/managed_modal — each env is a class with execute(), cleanup(), lifecycle methods
3. Interrupt handling: tools/interrupt.py — _interrupt_event (threading.Event), is_interrupted() polling
4. Background tasks: process_registry.py — start/stop/poll/kill with session tracking
5. Shell heredoc: tools/shell_heredoc.py — strip_inert_heredoc_bodies()
6. Output redaction: agent/redact.py — redact_sensitive_text() with force flag
7. PTY bridge: hermes_cli/pty_bridge.py, pty_session.py — PTY management for interactive terminal sessions
8. CWD tracking: tools/file_tools.py session_cwd_store, terminal_cwd_echo — working directory persistence across tool calls
9. Approval gating: tools/approval.py — command approval prompts (manual/smart/off modes)
10. Timeout: FOREGROUND_MAX_TIMEOUT env var override, 180s default in config.yaml terminal.timeout

## LESSONS FOR MOON TERMINAL BUILD
1. Hermes separates the CLI REPL (cli.py, prompt_toolkit) from the agent core (run_agent.py) from the terminal execution engine (tools/terminal_tool.py) — MOON already does this (terminal_interface.py = backend, ui/terminal.py = frontend)
2. Hermes uses a tool registry pattern — MOON should adopt a similar registry for its tools
3. Hermes has environment backends (local/docker/modal/etc.) — MOON's sandbox module could mirror this
4. Hermes has interrupt polling — MOON should add interrupt event for long-running tasks
5. Hermes has shell heredoc support — MOON's exec tool should support heredoc
6. Hermes has CWD tracking across tool calls — MOON should track CWD in session state
7. Hermes has approval gating for destructive commands — MOON should add command safety gates
8. Hermes has context compression — MOON's context module should have compression
9. Hermes has skill system — MOON could adopt skills for extensibility
10. Hermes has slash command registry — MOON's CLI should have a command registry
