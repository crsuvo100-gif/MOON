---
name: moon-agent-additive-build
description: Build/extend the MOON local AI agent non-destructively.
---

# MOON Agent — Additive Build Methodology

Project (CURRENT, verified 2026-08-15): MOON is a local, pure-Python AI agent at
`/home/meow/Projects/MOON` with package `app/` (NOT `moon_agent/` — that was an
earlier path; do not use it). Entrypoint `main.py`. Terminal UI served by
`app/terminal_interface.py` (uvicorn, `:8777`); CLI `main.py --help`.

## MANDATORY ENV RULE (under Hermes)
Every `python`/`pytest`/`ruff` invocation in this repo MUST be prefixed with
`env -u PYTHONPATH`. The Hermes venv exports a `PYTHONPATH` that loads a BROKEN
`pydantic_core`, which causes FALSE import failures (`No module named 'pydantic'`,
`ModuleNotFoundError: No module named 'app'`) unrelated to the code. The project venv
`.venv` is the healthy one to use. As of 2026-08-15 the venv was rebuilt on
**Python 3.13** (it had drifted to 3.14 with a broken pip that installed into the
Hermes venv instead — see VENV DRIFT below). So:
`env -u PYTHONPATH .venv/bin/python -m pytest tests -q`.
If you ever see a pydantic/pydantic_core import error, this is the cause — not a code bug.

## VENV DRIFT RECOVERY (learned 2026-08-15)
Symptom: `pytest` suddenly fails with `ModuleNotFoundError: No module named 'pygments'`
or similar, even though the suite passed minutes earlier. Cause: the MOON `.venv`
got re-pointed at a different Python (e.g. 3.14) whose `pip` is actually Hermes's pip,
so packages install into the wrong site-packages and the 3.14 site-packages ends up
missing deps. Recovery (non-destructive — preserves all installed packages):
1. `cp -r .venv/lib/python3.13/site-packages /tmp/moon_sp313_backup`
2. `rm -rf .venv`
3. `/usr/bin/python3.13 -m venv .venv`
4. `cp -r /tmp/moon_sp313_backup/* .venv/lib/python3.13/site-packages/`
5. `env -u PYTHONPATH .venv/bin/python -c "import pygments, pytest, pydantic, app.brain.orchestrator; print('ok')"`
Then re-run the suite. Always confirm the venv python with `.venv/bin/python --version`
before trusting a "missing dependency" error.

## USER'S STANDING RULE (honor above all)
1. UNDERSTAND, INSPECT, MAP, PLAN, VERIFY, BACKUP, BUILD, MERGE, TEST, FIX, FINALIZE.
2. Additive ONLY. Never remove/rename/replace working files or modules. EXTEND an existing component instead of creating a second one. (NEXUS terminal stack was removed only because the USER explicitly ordered "remove unused terminal" and it was already dead/isolated — that was an exception, not a precedent.)
3. Real output, never fabricated. Every verification must be a real tool run (pytest, live server curl, live brain call). No invented pass/fail.
4. Push to GitHub `origin/main` (`git@github.com:crsuvo100-gif/MOON.git`) after each coherent change, on a checkpoint branch, no force-push.
5. Keep `.env` (keys) gitignored; never print or commit secrets.

- **Deploy/launcher tooling MUST be pure Python, NOT shell.** The operator reversed
  a `.sh` launcher/installer I built: *"make it py language for launch any OS system
  supported not sh."* Use `scripts/install_ollama.py` + `scripts/moon_launcher.py`
  (cross-platform: Linux systemd / macOS brew / Windows winget). Full technique in
  `moon-engineering` → `references/cross_platform_launcher.md`.

## Adding a standalone CLI REPL surface (NEW — learned this session)

MOON already has TWO interactive surfaces that must NOT be clobbered:
- `moon terminal` / `moon ui` → web HUD via `app/terminal_interface.py` (uvicorn `:8777`, browser)
- `moon shell` / `moon tui` → Textual TUI via `app/tui.py` (rich visual terminal, mouse-aware)

When adding a THIRD surface that is a plain text CLI REPL (Hermes-style), follow this
pattern — additive, Moon-native, no Hermes imports:

1. Create `app/cli_terminal.py` (or similar) — a self-contained module, no Hermes deps.
   - Use `readline` for line editing + history (lighter than `prompt_toolkit`, sufficient for
     a REPL; Hermes uses prompt_toolkit but Moon doesn't need that weight).
   - Use `rich.console.Console` + `rich.panel.Panel` for colored output (already a Moon dep).
   - Slash commands via a module-level `@register(name)` decorator → dict dispatch, NOT a
     class-method decorator (a class-method `@register` breaks because `self` isn't bound at
     decoration time — the decorator runs at class-body exec, before any instance exists).
   - Dispatch must handle both sync and async handlers: check `inspect.iscoroutinefunction()`
     and `await` the async ones. Since the REPL loop runs inside `asyncio.run()`, sync handlers
     work directly; async handlers must be `await`ed, not wrapped in `asyncio.run()` (would
     crash with "event loop is already running").
   - One-shot mode (`-q`/`--query`) is a separate code path that calls `asyncio.run()` ONCE
     at the top level and exits — safe because no event loop is running yet.
2. Wire as `sub.add_parser("cli", ...)` in `main.py` argparse, dispatch to
   `from app.cli_terminal import main as cli_main; cli_main()` — mirrors how `shell`/`tui`
   subcommands already wire into `app/tui.py`.
3. Keep it additive: `moon cli` is a NEW subcommand; it does NOT replace `moon terminal` or
   `moon shell`. The other surfaces remain untouched.
4. Slash-command Hermes feature parity to aim for: `/help`, `/model [name] [--query <prompt>]`,
   `/agent`, `/status`, `/shell`, `/voice (on|off|tts|speak)`, `/reset`, `/save`, `/history`,
   `/clear`, `/quit|/exit|/q`, `/verbose`, `/goal`, `/personality`, `/busy`, `/indicator`,
   `/footer`, `/statusbar`, `/background`. The `/model --query <prompt>` backport is important
   — it switches the model AND immediately runs a one-shot on the new model (Hermes compat).
5. TTS: reuse Moon's own `VoiceEngine` via `_get_voice_engine()` from `app.terminal_interface`
   (the module-level singleton pattern Moon already uses). Do NOT import `app.tui`'s voice path.
6. Shell: reuse `_shell_dispatch` from `app.terminal_interface` (Moon's own allowlisted shell).
7. History: persist to `~/.moon/cli_history` via readline `write_history_file`/`read_history_file`.

### Rich `Console.print` gotcha (REAL runtime failure this session)
`rich.console.Console.print()` does NOT accept a `flush` parameter. Passing
`flush=True` raises `TypeError`. Rich controls flushing internally.
**Correct pattern** when streaming chunks: print the chunk with `end=""` and then
call `sys.stdout.flush()` explicitly as a separate statement. Two working forms:
- Lambda: `on_chunk=lambda chunk: (_console.print(chunk, end=""), sys.stdout.flush())`
- Named helper: define `def _stream_chunk(chunk): _console.print(chunk, end=""); sys.stdout.flush()`
  and pass `on_chunk=_stream_chunk` (cleaner, avoids lambda type warnings).

## Hermes CLI Architecture Mirroring (NEW — learned 2026-09-03)

When the user wants Moon's CLI to match Hermes CLI's command-line interface and
architecture EXACTLY (not just feature parity), build a class-level package
structured to mirror Hermes CLI's file layout, not a single flat file.

### When to use this pattern
User says things like "make Moon interface exactly hermes command line terminal
interface" or "do not change anything, just make it exactly hermes". This means
they want the ARCHITECTURE (file structure, dispatch pattern, REPL loop) to
mirror Hermes, with Moon-native code underneath.

### Hermes CLI file structure to replicate
Hermes CLI lives in `~/.hermes/hermes-agent/hermes_cli/`. Mirror this layout in
`app/cli/`:

```
app/cli/
├── __init__.py          # version + constants
├── main.py              # entry point: _set_process_title, argparse, _resolve_use_tui,
│                        #   _apply_safe_mode, _add_subcommands, cmd_* dispatch, main()
├── colors.py            # Colors(str, Enum) + color(text, color_name) — ANSI codes
├── cli_output.py        # print_info/success/warning/error/header
│                        #   + line_input() + prompt() + prompt_yes_no()
├── commands.py          # CommandDef dataclass + COMMAND_REGISTRY
│                        #   + SlashCommandCompleter + SlashCommandAutoSuggest
│                        #   + resolve_command() + cli_commands()
├── cli_commands_mixin.py  # CLICommandsMixin class with _handle_*_command methods
├── cli.py               # MoonCLI(HermesCLI) class: REPL loop, banner, history, dispatch
├── oneshot.py           # run_oneshot() for non-interactive -q mode
├── console_engine.py    # Rich-based: print_panel, print_table, print_divider, print_spinner
├── completion.py        # readline + prompt_toolkit completion + auto-suggest
└── subcommands/
    ├── __init__.py
    ├── model.py         # build() + cmd_model()
    ├── status.py        # build() + run_status()
    ├── doctor.py        # build() + run_doctor()
    └── setup.py         # build() + run_setup()
```

### Key architectural details (verified this session)

**main.py (mirrors hermes_cli/main.py):**
- `_set_process_title()` — sets ps title to `moon-cli` via `setproctitle` (if available)
  then `ctypes.prctl(PR_SET_NAME=15, ...)` Linux fallback. No-op on failure.
- `_ensure_project_root()` — adds project root to `sys.path` so `from app.*` works.
  Mirrors `hermes_cli/_ensure_project_root_on_path_fast`.
- `_resolve_use_tui(args)` — **always returns False** for Moon CLI. Hermes returns True
  when using prompt_toolkit TUI; Moon uses readline.
- `_apply_safe_mode(args)` — **no-op** for Moon. Hermes has a safe mode guard.
- `_add_subcommands(subparsers)` — imports `model`, `status`, `doctor`, `setup` from
  `app.cli.subcommands` and calls each `.build(subparsers)`. Mirrors Hermes' subcommand
  registration.
- `cmd_chat(args)`, `cmd_model(args)`, `cmd_status(args)`, `cmd_doctor(args)`, `cmd_setup(args)`,
  `cmd_oneshot(args)` — standalone dispatch functions (NOT class methods). Mirror Hermes
  `cmd_chat`/`cmd_model`/`cmd_status`/`cmd_doctor` functions.
- `_build_state(model, agent)` — returns a `CLIState` instance (defined in `commands.py`).
- `main()` — builds argparse with `chat`, `cli`, `oneshot` subparsers + calls
  `_add_subcommands()`. Default to `cmd_chat` if no subcommand given.

**colors.py (mirrors hermes_cli/colors.py):**
- `Colors(str, Enum)` with ANSI codes: RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE,
  BRIGHT_*, RESET, BOLD, DIM, UNDERLINE.
- `color(text, color_name)` — wraps text in ANSI code. Case-insensitive color name.
- Hermes uses `display_hermes_home`, `is_termux`, etc. — Moon doesn't need these.

**cli_output.py (mirrors hermes_cli/cli_output.py):**
- `print_info(text)` — dim informational (Colors.DIM)
- `print_success(text)` — green success with `✓` prefix
- `print_warning(text)` — yellow warning with `⚠` prefix
- `print_error(text)` — red error with `✗` prefix
- `print_header(text)` — bold yellow header with blank lines
- `line_input(prompt_text)` — TTY-aware: uses `prompt_toolkit` if available (arrow keys,
  history, editing), falls back to `input()` for non-TTY or missing prompt_toolkit.
- `prompt(question, default)` — formatted prompt with optional default
- `prompt_yes_no(question, default)` — yes/no prompt

**commands.py (mirrors hermes_cli/commands.py):**
- `CommandDef` dataclass (frozen): name, description, category, aliases, args_hint,
  subcommands, cli_only, gateway_only, busy_policy, busy_handler, execute,
  argument_mode, desktop. Mirrors Hermes EXACTLY.
- `COMMAND_REGISTRY` — list of CommandDef entries covering Session, Configuration,
  System, Voice, Exit categories.
- `resolve_command(name)` — lookup by name or alias (strips leading `/`).
- `cli_commands()` — filtered list (not gateway_only).
- `SlashCommandCompleter(Completer)` + `SlashCommandAutoSuggest(AutoSuggest)` —
  **conditionally defined** only when `prompt_toolkit` is importable. When prompt_toolkit
  is missing (common on constrained machines), these classes DON'T exist at module level.
  Import them with `hasattr()` checks or try/except — don't assume they're always present.

**cli_commands_mixin.py (mirrors hermes_cli/cli_commands_mixin.py):**
- `CLICommandsMixin` class with `_handle_*_command` methods. MoonCLI inherits this.
- All handlers use `self.state` (CLIState) + lazy imports from `cli` module.
- Rich `print_panel`/`print_divider`/`print_spinner` from `console_engine` for output.
- Commands implemented: help, new/rese`t`, clear, history, save, retry, undo, title,
  branch, compress, model, agent, verbose, voice, shell, status, doctor, quit,
  personality, goal, footer, indicator, statusbar, timestamps, focus, reload.
- Commands NOT implemented (Hermes-specific, not applicable to Moon): copy, paste,
  image, usage, version, update, debug, egress, context, snapshot, export, import,
  worktree, handoff, journey, moa, loop, plan, review, refine, queue, steer, btw,
  bg, heartbeat, tools, toolsets, skills, memory, bundles, pet, hatch, learn, init,
  cron, suggestions, blueprint, curator, kanban, reload-mcp, reload-skills, browser,
  plugins, stop, pause, resume, whoami, profile, sethome, sessions, config, codex-runtime,
  battery, diff, yolo, approvals, reasoning, fast, skin, wake, busy, approve, deny,
  start, topic, prompt, rollback, platforms, platform, insights, subscription, topup,
  agents, tasks, learning, memory-graph.

**cli.py (mirrors hermes_cli/cli.py):**
- `MoonCLI(CLICommandsMixin)` class with REPL loop, banner, history, prompt.
- `CLIState` dataclass: model_name, agent_name, session_id, voice_enabled, tts_enabled,
  verbose, messages, last_response, last_prompt. Also dynamic attrs: personality,
  goal, footer, statusbar, timestamps, focus (set via `__setattr__`).

**oneshot.py (mirrors hermes_cli/oneshot.py):**
- `run_oneshot(query, model, agent)` — async, calls LLM, returns response.
- `_exit_after_oneshot(rc)` — flush + `os._exit()` (Hermes uses this for clean exit).

**console_engine.py (Rich-based, mirrors Hermes prompt_toolkit console primitives):**
- `get_console()` — shared Rich Console singleton.
- `print_panel(title, body, border_style)` — Rich Panel.
- `print_table(headers, rows, title)` — Rich Table.
- `print_divider()` — horizontal rule.
- `print_spinner(text)` — Live spinner.
- `print_status(text, style)` — status line.
- `hprint(text, style)`, `hprint_info/success/warning/error(text)` — colored print helpers.

**subcommands/ (mirror hermes_cli/subcommands/):**
- Each subcommand is a thin module with `build(subparsers)` + `cmd_*`/`run_*` function.
- `model.py`: `build(subparsers)` registers `model` parser with `name` arg + `--query`.
  `cmd_model(args)` switches model and optionally runs one-shot.
- `status.py`: `build(subparsers)` registers `status` parser with `-H`/`-t` args.
  `run_status(args)` hits `/api/health` and prints results.
- `doctor.py`: `build(parser)` adds `--verbose`. `run_doctor(args)` checks Python, Rich,
  httpx, readline, asyncio, Settings, LLMService, VoiceEngine, Backend.
- `setup.py`: `build(parser)` adds `--branch`. `run_setup(args)` checks/creates `.env`.

### Critical differences from Hermes (must handle)
1. **No prompt_toolkit** — Moon CLI uses `readline` + `rich`. Hermes uses `prompt_toolkit`
   for its TUI. The completers (`SlashCommandCompleter`, `SlashCommandAutoSuggest`) are
   only defined when prompt_toolkit is available. Always guard imports of these.
2. **No `setproctitle`** — Moon CLI falls back to `ctypes.prctl` on Linux. Hermes prefers
   setproctitle.
3. **No Hermes config/env system** — Moon uses its own `app.config.settings.Settings`.
4. **No Hermes agent/brain system** — Moon uses its own `Orchestrator`, `LLMService`,
   `VoiceEngine`.
5. **CLIState defined in commands.py, imported by cli.py** — Hermes defines state differently.
   Make sure `CLIState` is importable from `app.cli.commands` so `main.py`'s
   `_build_state()` can use it.

### Verification recipe for Hermes-style CLI
1. AST parse every `.py`: `python -c "import ast; ast.parse(open('app/cli/foo.py').read())"`
2. Import chain test: `python -c "from app.cli.main import main"` (catches import errors).
3. `--help` smoke: `python -m app.cli.main --help`.
4. Subcommand help: `python -m app.cli.main chat --help`, `model --help`, `status --help`,
   `doctor --help`, `oneshot --help`.
5. One-shot test: `python -m app.cli.main oneshot -q "test"` (real LLM call).
6. Interactive REPL test: launch in a TTY, type `/help`, `/status`, `/quit`.
7. Pyright/linter on all `app/cli/*.py` files.

### Pitfalls
- Don't assume `SlashCommandCompleter`/`SlashCommandAutoSuggest` exist — guard imports.
- Don't call `asyncio.run()` inside the REPL's running event loop — use `await`.
- `CLIState` must be defined in `commands.py` (not just `cli.py`) so `main.py` can import it.
- Subcommand `build()` functions take `argparse._SubParsersAction`, not `ArgumentParser`.
- `cmd_*` functions in main.py are standalone (not methods) — they receive `argparse.Namespace`.
- `_resolve_use_tui` and `_apply_safe_mode` are no-ops for Moon — don't try to implement them.
- The `_add_subcommands()` in `_add_chat_args()` is a bug pattern — don't register subcommands
  on a parent parser's subparsers from within an argument-adding helper. Hermes does it at
  the top level in `main()`. Calling `_add_subcommands()` twice (once in `main()`, once inside
  `_add_chat_args()`) causes `argparse` to reject the second call with
  `AttributeError: '_SubParsersAction' object has no attribute 'add_argument'`.
- `console_engine.py` must provide a `ConsoleEngine` **class** (not just module-level functions)
  because `MoonCLI.__init__` does `self.engine = ConsoleEngine()`. Module-level functions alone
  will fail at import with `ImportError: cannot import name 'ConsoleEngine'`.
- `completion.py` must expose `setup_readline_completion()` (a function), not `MoonCLIReader`
  (a class), because `cli.py` does `from app.cli.completion import setup_readline_completion`.
  If `cli.py` imports a name that doesn't exist in `completion.py`, import fails.
- `cli_commands_mixin.py` handlers that reference `MoonCLI._query_llm_static(...)` will fail at
  runtime — that method doesn't exist. Use `from app.cli.oneshot import run_oneshot` and call
  `asyncio.run(run_oneshot(...))` instead. The dead `_query_llm_static` references are leftover
  from a class-method pattern that was never implemented.
- `status.py` subcommand must import `_panels` from where it actually lives
  (`app.cli.cli_commands_mixin`) — importing a non-existent `_panels` from
  `cli_commands_mixin` causes `ImportError`. The `_panels` function is defined in
  `cli_commands_mixin.py` as a module-level helper, not in `status.py`.
- The `_add_subcommands()` call must happen ONCE in `main()`, not inside `_add_chat_args()`.
- `CLIState.messages` type annotation: use `messages: list = None` with `self.messages = messages if messages is not None else []` in `__init__` to avoid Pyright `None` not assignable to `list` error.
- `SlashCommandAutoSuggest.get_suggestion()` signature must match the prompt_toolkit base class:
  `def get_suggestion(self, document, buffer)` — 3 params (self + 2), not 2. Mismatch causes
  `IncompatibleMethodOverride` from Pyright even though the class is never instantiated at runtime.

## Verification recipe — CLI REPL surfaces
Reuse existing pieces (do NOT duplicate):
- `app/tools/registry.py` `ToolRegistry` + `app/tools/base.py` `BaseTool` — add new tools
  as `class XTool(BaseTool)` and `reg.register(XTool())`; the Orchestrator's `setup()` builds
  the tool list — add your tool there (e.g. `CapabilityManagerTool()`).
- `app/brain/orchestrator.py` `Orchestrator` — central wiring. `_run_cognition_loop` already
  uses per-agent models; `_auto_acquire_for_task` is the hook for auto-capability.
- `app/brain/safety_validator.py` `SafetyValidator`, `app/brain/error_recovery.py` `ErrorRecovery`,
  `app/brain/planner.py` `Planner` — extend, don't fork.
- `app/tools/github_sync_tool.py` (auth + `_owner_repo`) and `app/tools/github_feed.py`
  (search) — reuse for any GitHub retrieval.
- `app/brain/agent_model_manager.py` `AgentModelManager` (`AGENT_MODELS` map) gives every agent
  its OWN model; `app/brain/agent_brain.py` `AgentBrain` is each agent's brain.
- `app/prompts/templates/moon_system.md` — merged system prompt; extend sections, never rewrite.

Additive subsystem recipe (used for the Capability Management subsystem):
1. Create a NEW package dir (e.g. `app/capability/`) with one module per component
   (`manager.py`, `registry.py`, `permission_manager.py`, `github_retriever.py`,
   `dependency_analyzer.py`, `installer.py`, `sandbox.py`, `verification.py`,
   `self_repair.py`, `tool.py`). `registry.py` must persist to `capabilities/` (gitignore it).
2. Expose a `CapabilityManagerTool(BaseTool)` and register it in the Orchestrator tool list +
   wire into `_auto_acquire_for_task` (prefer existing capability/installed CLI before network).
3. Add terminal commands (`capabilities`, `github`) in `app/terminal_interface.py` WITHOUT
   clobbering existing `action` branches.
4. Extend `moon_system.md` (new Section) to document the subsystem and map each documented
   behavior to a REAL backend call — no fake telemetry.
5. Branch `moon/<feature>`, commit, `make test` green, push `master:main`.

## Per-agent model wiring (real flow the user required)
- Default ON: `settings.enable_per_agent_models` -> `Orchestrator.setup()` builds
  `AgentModelManager` and injects it into every `AgentBrain(name, main_brain=self, agent_models=...)`.
- `AgentBrain.setup()` binds `self._llm = await agent_models.get_llm(agent_name)` (lazy Ollama pull).
  `AgentBrain.draft()` MUST call `self._llm.complete(...)` to produce the agent's real first-pass
  answer — a STUB that only returns a prompt template is a real bug (seen + fixed this session).
- The agent's draft is consolidated by the main brain via `refine_with_main()` (two-phase
  critique->verify gate). Graceful fallback: if no own model, return the template; main brain still validates.

## Verification recipe (MOON canonical — do not replace)
- Canonical: `env -u PYTHONPATH .venv/bin/python -m pytest tests -q` (the `Makefile` `test` target
  already prefixes `env -u PYTHONPATH`). 65 tests green as of 2026-08-15 (incl. 8 fallback-tier tests).
- Import-whole-package smoke: `python -c "import pkgutil,app; [importlib.import_module(m.name) for m in pkgutil.walk_packages(app.__path__,'app.')]"` (108 modules, 0 failures).
- Live terminal: `env -u PYTHONPATH .venv/bin/python -m uvicorn app.terminal_interface:app --host 127.0.0.1 --port 8777`, then `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8777/` (expect 200) + `/avatar.svg` (200).
- Re-run the relevant test file AFTER each edit; the harness flags stale verification.
- AST parse every new `.py` before trust: `python -c "import ast; ast.parse(open('path').read())"`.
- Always do a real `--help` smoke on any new CLI entrypoint: `python app/cli_terminal.py --help` (or
  equivalent). A file that AST-parses can still crash at import time due to a bad top-level import
  or decorator-ordering bug (e.g. a `@register` applied as an instance method before any instance
  exists — see the CLI REPL section above).
- For CLI REPLs specifically, test both code paths: interactive mode starts an event loop, one-shot
  mode (`-q`) calls `asyncio.run()` once at the top level. Never call `asyncio.run()` inside an
  already-running loop (the dispatch handler for async commands must `await`, not `asyncio.run()`).
- Pyright (or your linter) before commit: `pyright app/cli_terminal.py` — catches the `flush=True`
  Rich gotcha and undefined-name issues the AST won't.

## Pitfalls
- Hermes `PYTHONPATH` breaks imports — always `env -u PYTHONPATH` (see above).
- `AgentBrain.draft()` must generate a real answer on the agent's own model, not return a template.
- Don't `git add -A` without checking `.env` excluded; confirm `capabilities/` runtime state is gitignored.
- The MOON system prompt's lock/unlock phrase is `MOON love you 3000` (set by Psycho in system prompt).
- **Deploy/launcher tooling MUST be pure Python, NOT shell.** The operator reversed
  a `.sh` launcher/installer I built: *"make it py language for launch any OS system
  supported not sh."* Use `scripts/install_ollama.py` + `scripts/moon_launcher.py`
  (cross-platform: Linux systemd / macOS brew / Windows winget). Full technique in
  `moon-engineering` → `references/cross_platform_launcher.md`.
- **Multi-tier LLM fallback (local → OpenAI → OpenRouter → Hugging Face):** the
  orchestrator's `_complete_with_fallback()` walks a chain and tries each backend
  until one returns non-empty content. Tiers are gated on their key settings
  (`openai_api_key`, `openrouter_api_key`, `huggingface_api_key`) — each
  `LLMService` is built only when its key is set, with `disable_thinking=True`
  (hosted models are not thinking models). Hugging Face uses its OpenAI-compatible
  router `https://router.huggingface.co` with a model id like
  `meta-llama/Llama-3.1-8B-Instruct`. When the operator pastes a literal API key,
  store it ONLY in the gitignored `.env` (never source, never chat), put a blank
  placeholder in `.env.example`, and pre-push guard with
  `git grep -nE 'sk-proj|sk-or-v1|hf_'`. Full technique + test recipe in
  `references/llm_fallback_backends.md`.
- **OpenRouter has TWO key TYPES — never confuse them:** `OPENROUTER_API_KEY`
  (`sk-or-v1-...`) is the model-serving key used by the fallback chain. The
  operator also provided an OpenRouter *management* key (`sk-or-v1-...`, same
  prefix, different secret) and a `whsec_...` webhook signing secret. These are
  ACCOUNT/admin credentials: store them as `openrouter_management_key` /
  `openrouter_webhook_secret` settings, document them as NOT model-serving, and
  do NOT wire them into `_complete_with_fallback`. Same for any HF/OpenAI
  management keys. A management key will NOT work as a chat key and is a security
  risk if sent to `/v1/chat/completions`.
- **Billable / side-effecting external actions MUST be confirmation-gated.**
  `HuggingFaceDeployTool.deploy()` provisions HF Inference Endpoint hardware
  (real money). It returns the would-run command when `confirm=False` and only
  calls `hf endpoints create` when `confirm=True`, then verifies with
  `hf endpoints status`. NEVER auto-run a deploy/scan/spend; build the command,
  show it, require explicit `confirm=True`. Verify with mocks, not live billing.
  Full detail in `references/huggingface_deploy.md`.
- **HF OAuth client is a modeled config, not a pasted blob.** The operator's
  Authorization Code + PKCE registration (`client_id` = `<site>/.well-known/
  oauth-cimd`, `token_endpoint_auth_method: "none"`) is built from
  `hf_oauth_website`/`hf_endpoint_namespace` settings via
  `oauth_client_config()`; if the site is blank it returns `{"configured": False}`
  rather than a fake payload. See `references/huggingface_deploy.md`.
- **Test pitfall (RESOLVED):** a bare `Orchestrator()` had no `_llm_fallback2` /
  `_llm_fallback3` attrs (set only in `setup()`). Fixed by initializing all three
  to `None` at the top of the fallback block AND making the chain iterate with
  `getattr(self, "_llm_fallback3", None)` so any unset tier is safely skipped. New
  fallback tests should still set `o._llm_fallback2/_fallback3 = None` defensively,
  but the production code no longer `AttributeError`s.

## Deep-unlock scan (when the operator says "unlock everything / make it perform perfectly")
MOON's feature gates are the `enable_*` bools in `app/config/settings.py`. As of the
last full sweep **all 9 are `True`** (`enable_global_connector`, `enable_per_agent_models`,
`enable_browser_automation`, `enable_ocr`, `enable_pdf`, `enable_agent_validation`,
`enable_auto_learning`, `enable_fast_path`, `enable_self_consistency`). The tool
`enabled=` params (OcrTool/PdfReaderTool/BrowserTool/ImageProcessingTool) are wired to
these. So MOON is already fully unlocked — a "deep scan" CONFIRMS, it does not need
edits. Do NOT mistake the `locked` fields in `app/brain/lock.py` and
`app/terminal_interface.py` for disabled features: those are MOON's **intended unlock
phrase** (`MOON love you 3000`), a deliberate gate, not a feature flag.

## Integration workflow (operator's required sequence)
When the operator hands you a "make the project complete / finalize / integrate"
brief (e.g. the HERMES master finalization prompt), follow THIS order — verified
this session (2026-08-19):

1. **DISCOVERY + ARCHITECTURE AUDIT FIRST, READ-ONLY.** Inspect the whole repo
   (tree, LOC per submodule, every layer's entry points) and emit a
   component / dependency / integration report. **Do NOT modify any file during
   this phase.** The operator explicitly demanded this and will be annoyed if you
   start editing before reporting. Phrases like "first perform discovery and
   architecture audit only" / "do not modify any file" are hard gates.
2. **Report findings**, flagging dead/orphan/duplicate modules AND — critically —
   distinguishing "harmless dead code to leave alone" from "genuinely disconnected
   component worth integrating."
3. **Then integrate ADDITIVELY, one step at a time, validating each change:**
   syntax → import → existing tests (pytest) → live (restart backend, hit
   `/api/health`, run a real task). Commit+push each validated step atomically.
   Never batch unvalidated multi-file changes.

### Rebuild-trap detection (KEY pitfall)
Before "wiring up" a module, check whether its abstraction actually matches the
one the runtime uses. This session: `app/agents/base.py` (`BaseAgent`) and
`app/agents/memory_agent.py` (`MemoryAgent`) look like integrable components but
are a **parallel, incompatible abstraction** — the Orchestrator builds agents via
`app/brain/agent_registry.build_agents()` → `AgentCard`s and routes through its own
cognition loop. `MemoryAgent` is a `BaseAgent` wrapping a separate `AgentBrain`
with `.run()`, with NO hook in `build_agents` to inject it. "Wiring it in" would
require rewriting `build_agents`/the orchestrator = a forbidden rebuild. **Leave
`app/agents/*` untouched** (preservation rule wins over the appearance of a gap).
Same logic applies to any orphaned module that implies a second architecture:
verify the runtime path before integrating; if it conflicts, document and skip.

### Startup-readiness gap technique
If a launcher lacks what sibling launchers do, close it ADDITIVELY by mirroring the
existing working helper — do not rewrite. This session: `main.py terminal` (the
default `make serve`) did NOT auto-start Ollama, while `scripts/moon_launcher.py`
did, so a cold boot left the Orchestrator's `setup()` failing. Fix: added
`_ensure_ollama()` to `main.py` (probe `OLLAMA_HOST`, best-effort `systemctl
start ollama` on systemd Linux else `ollama serve` background) — a no-op when
Ollama is up, graceful when it can't start. Mirrors `moon_launcher.py`'s pattern.
Rule: reuse the proven helper's shape; keep it best-effort + non-destructive.

## .env / secrets handling (the operator WILL question the gitignore)
- `.env` is gitignored **by design** (it holds all API secrets: OpenAI / OpenRouter /
  HF keys + OpenRouter mgmt + webhook secret). Do NOT un-ignore it. The operator
  challenged this directly ("why .env gitignore? is it needed?") — the answer: it IS
  needed (only place the keys live) AND must stay ignored (only place the secrets live).
  Both true at once; no fix required.
- `.env` is only auto-loaded if `python-dotenv` is installed — pydantic-settings will
  NOT read `env_file` without it, and fails SILENTLY (keys default to `""`, MOON runs
  local-only, no error). Always confirm `python-dotenv>=1.0` is a declared dependency,
  and verify the load with a fresh-process test (no shell-env leakage). Full recipe +
  the `git grep` secret-scan false positive in `references/env_and_secret_handling.md`.
- Launcher `ensure_env()` auto-creates `.env` from `.env.example` on a fresh clone
  (never overwrites an existing one, never commits it) so cloud fallbacks aren't
  silently dead. That is the correct robustness fix — NOT committing `.env`.

## References (this skill)
- `references/brain-system-integration.md` — pattern for adding advanced brain modules (ReAct, DAG, metacognition) and integrating them into the main Orchestrator.
- `references/skill-system-integration.md` — additive advanced skill system pattern: `app/skills/advanced/` package, 4-point Orchestrator wiring (init/setup/cognition_loop/run_task/teardown), verification recipe.
- `references/cli_hermes_mirror.md` — Hermes-style CLI mirror: dead-reference traps,
  end-to-end verification recipe, output-never-empty rule, Pyright notes.
- `references/local-brain-wiring.md` — per-agent model / AgentBrain wiring detail.
- `references/build-verify-push.md` — commit/push checklist for MOON.
- `references/llm_fallback_backends.md` — full multi-tier fallback technique, settings
  table, secret-handling rules, and the 8-test recipe (local→OpenAI→OpenRouter→HF).
- `references/huggingface_deploy.md` — HF OAuth client config + Inference Endpoint
  deploy tool (`HuggingFaceDeployTool`), confirmation-gating rule, mock-based test recipe.
- `references/env_and_secret_handling.md` — `.env` gitignore rationale, dotenv-load
  verification, fresh-clone provisioning, and the `git grep` secret-scan false positive.

- `scripts/verify_api.py` — live 10-endpoint smoke test for the MOON API on :8778 (`/api/health`, `/api/tools`, `/api/tools/system_info`, `/api/tools/network_scan`, `/api/agents`, `/api/agents/general`, `POST /api/moon-agent`, `/api/moon-agent/agents`, `POST /api/moon-agent/agents/general`, `/api/moon-agent/clear`). Run after any engine or API change to confirm all endpoints respond before commit+push.
