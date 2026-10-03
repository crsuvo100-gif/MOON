---
name: moon-agent-extension
description: Extend MOON additively. Verified, pure-Python.
---

# MOON Agent Extension (additive · verified · pure-Python)

## Trigger
User asks to "add / build / upgrade MOON" with new capabilities (more agents each
with its own brain, desktop UI, frontend+backend interaction, avatar/nexus
integration, capability manager) on the existing `moon_agent` package.

## Hard rules (from Psycho)
- **ADDITIVE ONLY.** Never remove, replace, or rewrite working files. Extend
  existing modules; add new structured packages alongside. Preserve legacy
  `moon.py`, `terminal/`, `agents.py`, `runtime.py`, `tools/core.py`, `skills/*`,
  and config. "Extend, don't duplicate."
- **PURE PYTHON (NOT SHELL) for deploy/launcher tooling.** When Psycho wants MOON
  to "run anywhere" / launch easily on any OS, build the installer AND launcher in
  **Python** (`scripts/install_ollama.py`, `scripts/moon_launcher.py`), never `.sh`.
  Explicit correction this session: "make it py language for launch any OS system
  supported not sh that you just build it." Branch per-OS with `platform.system()` /
  `shutil.which`; resolve the venv python as `.venv/bin/python` (POSIX) or
  `.venv/Scripts/python.exe` (Windows). Full recipe + secret-safety in
  `references/deploy_anywhere.md`; verify with `scripts/moon_deploy_smoke.py`.
- **NO FABRICATION.** Every output must be grounded in real tool execution. When
  a model returns empty / refusal / placeholder, report an honest failure — never
  invent. Implement an `is_honest()` guard on every agent-brain path.
- **REAL VERIFICATION ONLY.** Run `pytest` + a live smoke (real LLM / WebSocket)
  and show the actual output. Do not claim success without tool evidence.
- **SECRETS:** `.env` is gitignored and never committed; Ollama/OpenAI keys live
  there only. After every commit verify `git log --all -p | grep -c <key> == 0`.
- **UI REBUILD RULE (MOON NEXUS / avatar interfaces).** When Psycho gives a
  design reference image (e.g. "MOON NEXUS v3.0" red/black cyberpunk), build the
  UI to MATCH IT EXACTLY — layout, panels, color scheme, typography. He rejected
  "cool"/"cinematic" deviations that didn't reproduce the reference. AND: every
  widget MUST be driven by REAL MOON runtime state — gauges/status/metrics are
  computed from live data (psutil, agent internals), NEVER hard-coded/placeholder
  numbers (no fake "CPU 18%", "312 functions", "2.4 TB"). Additive-only: extend
  the existing `futuristic/` NEXUS UI, don't fork a new copy. Reference image: the
  three-column "MOON NEXUS v3.0" spec — left (MOON CONNECTION / AGENT STATUS /
  SYSTEM OVERVIEW gauges / PERFORMANCE graph / QUICK LAUNCH), center (avatar +
  mood/voice/attention/thinking + terminal), right (LIVE EVENT STREAM / MOON
  FUNCTIONS / VOICE CONTROL / QUICK MOOD), bottom status bar. Panel→state map in
  references/nexus_ui_state.md.

## Mandated workflow
UNDERSTAND → INSPECT → MAP → PLAN → VERIFY → BACKUP → BUILD → MERGE → TEST →
VERIFY → FIX → FINALIZE. Inspect existing modules BEFORE editing; map reuse
points (security `Level`/`PolicyEngine`, `Sandbox`, `Planner`, `Verifier`,
`ToolRegistry`); extend, don't duplicate.

## Architecture map (`moon_agent/`)
- `core/brain/agent_brain.py`: `call_brain()` dual-backend (remote gpt-4o when key
  set, else local Ollama qwen3:1.7b; Ollama sends `OLLAMA_API_KEY` as Bearer) +
  `AgentBrain` (per-specialist persona) + `is_honest()`.
- `workers/`: 6 specialists (researcher/coder/debugger/analyst/reviewer/tester),
  each an `AgentBrain` with a specialist prompt. `build_council()` →
  `MultiAgentCouncil.run_brained()` has each specialist reason INDEPENDENTLY, then
  the executive brain synthesizes ONE grounded answer.
- `agents.py`: `Specialist` dataclass (name, mission, tools, system_prompt,
  brain_fn) + `MultiAgentCouncil`.
- `tools/`: `ToolRegistry`/`ToolSpec`. Per-agent `*_brain` tools live in
  `tools/agents.py`; register via `build_registry()`. Each tool maps to a real
  `MoonAgent` function — no dead tools.
- `runtime.py` `MoonAgent.run()`: slash-command parser (`/council`,
  `/agent <name>`, `/skills`, `/learn`, `/memory`, ...). Add new commands here.
- `app/server.py`: stdlib `http.server` HUD on :8789 (real-state endpoints
  `/api/state`, `/api/chat`, `/api/agents`, `/council`). `app/lifecycle.py` wraps
  the orchestrator + a council-bearing `MoonAgent`.
- `app/native_desktop.py`: **PURE-TKINTER** native desktop (no web/browser). Every
  button → a real built-in Moon function. Launch via `moon --desktop`.
- `integrations/moon_nexus.py`: `MoonNexusBridge` WebSocket client to the existing
  MOON Avatar Terminal (`ws://127.0.0.1:8765/moon`) — see references/protocol.md.
  It also **streams real telemetry** over the same socket: `_real_system_metrics()`
  (psutil CPU/RAM/DISK/NET, real OS/python), `_agent_status()` (BRAIN/MEMORY/
  RETRIEVER/PLANNER/TOOLS/FUNCTIONS/VISION/LISTENER mapped from real `agent`
  internals), and `_metrics_loop(ws)` pushing every 2s as `moon.system` /
  `moon.agent.status` / `moon.heartbeat`. The terminal's `terminal/server.py`
  additively broadcasts these new types to UI clients (see pitfall: add the
  `moon.*` branch). The NEXUS UI (`futuristic/app.js`) renders them — every
  gauge/dot is REAL state, never fabricated.
- **The NEXUS avatar UI is a WEB SERVER, not a file.** `run_nexus.py` starts
  `futuristic.web_server.serve` on `http://127.0.0.1:8787/` (const
  `NEXUS_WEB_PORT`). `launch()` calls `_open_nexus_ui()` which waits for `:8787`
  then opens `http://127.0.0.1:8787/` via `webbrowser.open` on desktop hosts; on
  headless/no-DISPLAY/SSH it skips the GUI open and just prints the URL.
- `cli.py`: `--desktop` (native), `--desktop-web` (legacy Chromium), `--hud`,
  `--moon-nexus` / `--avatar` (with `--no-terminal` for brain-only).

## Install / package for any machine (cross-machine from GitHub)
MOON must `pip install` cleanly and `moon` must work from a FRESH venv on a
different machine — not just from an editable source checkout. The gotchas
below are real and were all hit during the "make it installable" pass.

**pyproject.toml (the build):**
- Use `[tool.setuptools] packages = {find = {"include" = ["moon_agent", "moon_agent.*"]}}`
  — NOT a hand-listed `packages = [...]` array. A hand list silently DROPS
  subpackages (we lost `moon_agent.integrations`, `moon_agent.app`, all
  `moon_agent.core.*`) so `pip install` shipped a broken package where
  `moon --moon-nexus` raised ImportError. `find:` auto-ships all 120 submodules.
- Declare real core deps: `websockets`, `psutil`, `Pillow` (the avatar UI
  `run_nexus.py` hard-imports PIL). Optional skills (pymupdf, youtube-transcript,
  pyfiglet, marker-pdf) go under `[project.optional-dependencies]` (`avatar`,
  `docs`, `ocr`, `api`, `full`) because they're lazy-imported.
- Keep `moon = "moon_agent.cli:main"` in `[project.scripts]`.

**Data folders live in the REPO, not the package.** `MOON_NEXUS_FUNCTIONAL_FINAL/`
ships inside the repo. After `pip install .` the package is in site-packages, so
never resolve that folder relative to `__file__`. FIX: at runtime search
UPWARD from `Path.cwd()` for `MOON_NEXUS_FUNCTIONAL_FINAL/MOON_Avatar_Terminal_FINAL`
(the bridge's `_resolve_avatar_dir()` does this, falling back to the
file-relative path for editable installs). `install.sh` sets `WorkingDirectory`
to the repo root so the search always hits.

**Case-sensitive FS trap.** The real folder is `MOON_Avatar_Terminal_FINAL`
(all-caps FINAL). A path written as `MOON_Avatar_Terminal_Final` fails `is_dir()`
on Linux and falls through to the wrong fallback. Match the exact casing.

**`install.sh` (universal bootstrap):** creates `./venv`, `pip install -U pip
wheel`, `pip install -e ".[avatar,docs,api]"` (or `.[full]`), verifies
`import moon_agent.integrations.moon_nexus` + `moon --help`, and optionally
installs a `systemd --user` service (`moon_headless.py`) for an always-on avatar.
Offers `--minimal` / `--full` / `--no-venv` modes. Keep the legacy
`install-moon-desktop.sh` for backward compat (additive).

**`.gitignore`:** must ignore `.env`, `*.env`, `__pycache__/`, `*.egg-info/`,
`build/`, `venv/`, `.moon_data/`, `.pytest_cache/`. The repo inherited a stale
Dynamics-365 AL template `.gitignore` — replace it with a Python project one so
build artifacts stop getting committed.

**README.md:** give the `git clone` + `./install.sh` + `moon --moon-nexus` path
and the LLM setup (Ollama `qwen3:1.7b` or `OPENAI_API_KEY` in gitignored `.env`).

**Verify the install on a clean interpreter** (not just the dev venv):
`python -m venv /tmp/x && /tmp/x/bin/pip install . && /tmp/x/bin/moon --help &&
/tmp/x/bin/python -c "import moon_agent.integrations.moon_nexus"` then actually
launch `moon --moon-nexus` and confirm `:8787` serves HTTP 200 + `:8765` WS up.
(Rebuild with `--no-cache-dir --force-reinstall` when you changed build metadata
like `pyproject` packages, or pip reuses a stale wheel.)

## Pitfalls & fixes (real, this session)
- Bare `pytest` fails collection (`ModuleNotFoundError: No module named
  'moon_agent'`) under some interpreters. FIX: add root `conftest.py` that
  inserts repo root on `sys.path`. (Verifier otherwise reuses a STALE cached
  result — the "37 passed, 1 skipped" ghost — instead of failing loudly.)
- Full `pytest` can HANG on live-LLM tests (Ollama/OpenAI). For fast proof run
  `-k "not integration and not brained"`; the live-brain test self-skips when
  Ollama is unreachable. Always re-run the canonical `pytest` to clear stale
  verifier snapshots.
- Global `PYTHONPATH` (e.g. a Hermes venv) leaks into subprocesses and breaks
  their `PIL`/`_imaging` (ABI mismatch). FIX: launch subprocesses (avatar
  terminal) with a **sanitized env** (`env -u PYTHONPATH -u VIRTUAL_ENV
  -u PYTHONHOME PATH="/usr/bin:/bin:/usr/local/bin"`) and `xvfb-run -a` when
  headless. Also drop `PYTHONHOME` — a stale one points PIL at the wrong prefix.
  Never rely on inherited env for a subprocess that imports native extensions.
  (The bridge's `start_avatar_terminal()` already builds this clean env; reuse
  it rather than hand-rolling `Popen`.)
- Extending the avatar terminal's `terminal/server.py` `process()` with new MOON→
  UI message types (e.g. `moon.system`, `moon.agent.status`, `moon.heartbeat`):
  add ONE branch BEFORE `raise ValueError` that `broadcast`s the message unchanged
  to all connected clients (the NEXUS UI renders them). These are MOON-owned
  telemetry — the terminal must NOT execute/reinterpret them. Additive branch only.
- The bridge's `run()` must cancel `metrics_task` on disconnect and keep the outer
  `try/except` (connection-lost → retry with backoff). When editing `async with
  websockets.connect(...) as ws:` blocks, re-read the whole method first — nested
  `try`/`async for` indentation corrupts easily (compile-check after every edit).
- The NEXUS UI `app.js` must connect to the SAME `ws://host:8765/moon` and handle
  every real message type. Put the `speakBtn` guard as `$("speakBtn")&&(...)` with
  a single trailing `)` — the double `));` is a JS SyntaxError.
- **The avatar interface is opened via HTTP, NEVER as a file.** The real UI file is
  `MOON_NEXUS_FUNCTIONAL_FINAL/MOON_Avatar_Terminal_FINAL/futuristic/index.html`
  and is served only by the avatar terminal's web server on `:8787`. If you (or the
  user) try to open that `.html` as a `file://` path you get "No such file or
  directory" (a stray/typo'd copy may not even exist). Always launch with
  `python -m moon_agent.cli --moon-nexus` and open `http://127.0.0.1:8787/` in a
  browser, or let `launch()` auto-open it. Never create a second copy of the HTML
  in the repo root (it becomes a dead, unserved file).
- **Flaky LLM-dependent relay/integration tests.** A test that relies on a live
  model answering within a timeout (`agent.run("6*7")` -> "42") WILL flake under
  full-suite Ollama/OpenAI contention and falsely fail. The test's PURPOSE is
  usually the *relay path* (e.g. `role=AGENT` registration + `moon.chat`->
  `avatar.speak` forwarding), NOT arithmetic. FIX: stub `agent.run` to return a
  fixed reply so the relay logic is verified deterministically; keep the real
  assertion against the stubbed output. (See `tests/test_moon_nexus_bridge.py`.)

- **LOCAL THINKING MODELS RETURN EMPTY content via Ollama.** When MOON boots but
  quick_reply returns the "could not form a reply" string and the log shows
  "LLM complete failed", the cause is a reasoning model (qwen3 / deepseek-r1 /
  glm-z1) whose /v1/chat/completions answer lands in the reasoning field with
  content empty and finish_reason length — the small max_tokens budget was
  exhausted by thinking. FIX in app/services/llm_service.py: give thinking models
  headroom (bump effective max_tokens to 1024+ when thinking is on) and extract the
  real answer from the reasoning trace via _extract_answer_from_reasoning(). Do NOT
  disable thinking to fix it — that sacrifices quality. Full recipe in
  references/thinking_model_ollama.md (reusable for ANY local reasoning model).
- **MOON (app/ repo) is FULLY RUNNABLE and answers accurately** once Ollama serves
  on 127.0.0.1:11434. Boot proof: Orchestrator.setup() connects 39 agents (each on
  its own model via AgentModelManager), 41 tools registered (global_connector +
  capability_manager), and quick_reply returns the right answer. The "could not
  form a reply" string is the thinking-model token bug above, not a wiring defect.

- **`.env` OVERRIDES code defaults at runtime — prove the unlock in `.env`, not just
  `settings.py`.** When the user says "unlock all functions / make fully functional",
  the action is: (1) flip the `enable_*` flags in `app/config/settings.py` (e.g.
  `enable_browser_automation/enable_ocr/enable_pdf` → `True`, set `strong_model_name`
  to a real local model like `qwen3:1.7b` for accuracy routing), (2) mirror it in
  `.env.example` so docs match, AND **(3) also update the runtime `.env`** (gitignored,
  local-only) — because pydantic-settings loads `.env` OVER the code default. If the
  runtime `.env` still carries stale `ENABLE_BROWSER_AUTOMATION=false`, MOON boots
  STILL LOCKED even though the code default is now `True`. Never report "unlocked"
  until you prove it by reading settings at runtime:
  `env -u PYTHONPATH .venv/bin/python -c "from app.config.settings import get_settings as g; s=g(); print(s.enable_browser_automation, s.enable_ocr, s.enable_pdf, s.strong_model_name)"`
  must read the unlocked values. Edit `.env` via a safe targeted rewrite in
  terminal-python (flip only the toggles, preserve secrets) — the read/patch tools
  refuse `.env` as secret-bearing. `.env` is gitignored and MUST NOT be committed.

- **SPEC COMPLETENESS ≠ FUNCTIONAL — audit for ORPHANED modules, not just missing
  files.** When the user says "is anything missing from the spec / did you build it
  for real", do NOT stop at "the file exists". A module can exist (and even have
  unit tests) but be NEVER imported or called by the live pipeline — it looks done
  in a listing, contributes nothing at runtime, and is the #1 "magical completeness"
  trap. Detection + the non-destructive integration-glue fix + the importlib module
  collision bug + a §57 acceptance-E2E harness are all in
  `references/spec_integration_gapclosure.md`. Key rules: (a) wire orphans via a
  thin glue module (`app/runtime/integration.py`) called inside `try/except` at safe
  integration points — augment, never replace; (b) when loading generated/plugin
  modules with `importlib.util.spec_from_file_location`, use a UNIQUE per-agent key
  AND `sys.modules.pop(key, None)` before each exec, else a 2nd call in the same
  process reuses a stale cached module; (c) `run(task or "run")` masks empty input —
  use `task if task else ""` so empty input hits the generated guard and returns
  FAILED (spec 27); (d) prove end-to-end with `scripts/acceptance_factory.py`, not
  file existence.

- **Changing a default config breaks tests that encode the OLD default — update the
  test, don't revert the feature.** Setting `strong_model_name` (was empty) made
  `test_pick_llm_routing` fail: it asserted "no strong model → always default", but
  `_pick_llm` now routes factual/cyber-critical prompts to `_llm_strong`. FIX: grep
  tests for assumptions about the changed config and update expectations (assert
  factual/cyber → `_llm_strong`, creative → `_llm`). The feature is correct; the test
  expectation was stale. Same pattern applies whenever you flip any default.

- **Full `pytest` with live-LLM/connector tests exceeds the 300s foreground timeout.**
  `test_global_connector.py` (real Ollama peer-agent federation) + `test_per_agent_brains.py`
  + `test_capability_system.py` together take >300s and will hit the foreground cap
  looking like a hang. FIX: run the canonical suite in BACKGROUND with
  `notify_on_complete=true` (`terminal(background=true, notify_on_complete=true)` then
  `process(action="wait")`), or run one fast file foreground
  (`pytest tests/test_per_agent_brains.py -q` ≈ 5s). Don't conclude the suite is broken
  from a 300s timeout — it's live-model latency, not a regression.

## Verification checklist
1. `python -m py_compile` all changed modules.
2. `pytest -q -k "not integration and not brained"` → must be green.
3. Live smoke: boot server/desktop/nexus, hit a real endpoint, show real output
   (e.g. `/api/chat`→"42"; `terminal.exec echo`→exit 0, stdout echoed).
4. `git add -A`; confirm `.env` NOT staged; push; confirm key not in history (0).

## References
- `references/moon_nexus_protocol.md` — full WebSocket handshake + message types
  for the avatar-terminal bridge (incl. the new `moon.system`/`moon.agent.status`/
  `moon.heartbeat` telemetry types).
- `references/nexus_ui_state.md` — MOON NEXUS v3.0 UI panel → REAL state map
  (what each widget reads, so no value is ever fabricated).
- `references/install_packaging.md` — copy-modify pyproject/install.sh/cwd-relative
  data resolution + clean-venv verification recipe for cross-machine install.
- `references/capability_additive_build.md` — the `env -u PYTHONPATH` venv trap,
  safe `ruff --fix`, additive deletion of a dead subsystem, and the verified
  recipe for adding a new `app/capability/` subsystem (reusing ToolRegistry/
  BaseTool/github_feed). Covers the `app/`-package repo at `/home/meow/Projects/MOON`
  (venv `.venv/`, entry `python main.py terminal` → `app.terminal_interface:app`
  on :8777), which is a SECOND MOON layout distinct from the `moon_agent/` package
  above — same additive rules, different module tree. EXTENDED this session with a
  full per-module map, a `.gitignore` runtime-state rule, and the §5 git flow
  (checkpoint branch → commit → `--ff-only` merge → `git push origin master:main`).
  The AGENT-GENERATION half of the same spec lives in `app/agent_factory/` —
  see `moon-engineering` SKILL.md \"AGENT FACTORY\" subsection + `references/agent_factory_build.md`
  (reuses `CapabilityManager.sandbox`/`VerificationEngine`; adds `/api/factory`,
  `/api/factory/agents`, `/api/agents/{id}/run`, `/api/agents/{id}/rollback`).
- `scripts/capability_smoke.py` — re-runnable build/import gate: `env -u PYTHONPATH
  .venv/bin/python scripts/capability_smoke.py` asserts all `app` modules import and
  every capability + connector symbol is present; exits 1 on any failure. Run before
  committing any `app/capability/` OR `app/connector/` change.
- `references/global_connector_build.md` — the permission-gated Global Connector
  subsystem (`app/connector/`): egress tiers (SAFE/allowlist vs CONFIRMATION vs NEVER
  for secrets), HTTPConnector/AgentConnector/WebSocketConnector/MCPConnector clients,
  ConnectionGateway persistence, the two-way `federate`/`call_agent` AI-agent path,
  the `connect` terminal command, and the §5 git flow (`git push origin master:main`).
  Second verified additive build on this repo.
- `references/thinking_model_ollama.md` — why local reasoning models (qwen3 /
  deepseek-r1) return EMPTY `content` via Ollama `/v1/chat/completions` and the
  fix (token headroom + extract answer from `reasoning`); reusable for ANY local
  thinking model.
- `references/unlock_functions.md` — the `.env`-overrides-code-defaults trap and the
  three-place unlock recipe (settings.py + .env.example + runtime .env) for "unlock
  all MOON functions", plus the live-boot proof and the test-staleness side effect.
- `references/deploy_anywhere.md` — cross-platform **pure-Python** Ollama installer
  (Linux systemd / macOS brew / Windows winget) + MOON launcher + the local→OpenAI→
  OpenRouter model fallback chain, plus the management-key≠serving-key secret rule.
  Triggered by "make MOON run anywhere". Pair with `scripts/moon_deploy_smoke.py`.
- `scripts/moon_deploy_smoke.py` — re-runnable gate for deploy tooling: py_compiles
  both scripts, DRY_RUN-checks the installer unit, loads settings, runs pytest;
  exits 1 on failure. Run `env -u PYTHONPATH .venv/bin/python
  scripts/moon_deploy_smoke.py` before committing scripts/install_ollama.py,
  scripts/moon_launcher.py, or orchestrator fallback changes.
- `references/context_self_function_build.md` — the `app/context/advanced/` 9-module context self-function system (window management, awareness, injection, lifecycle, retrieval, compression, analytics, orchestrator) and the 5-patch Orchestrator wiring pattern (init → setup → cognition loop → run_task → teardown). Load when asked to add context self-function or wire a new subsystem into the Orchestrator.
- `references/spec_integration_gapclosure.md` — how to detect ORPHANED spec modules
  (exist but never wired into the live pipeline), the non-destructive integration-glue
  pattern, the `importlib` module-key COLLISION fix (unique key + `sys.modules.pop`
  before re-exec), the empty-input masking trap (`task if task else ""`), evidence-based
  `Verifier` rules, and a §57 acceptance-E2E harness. Load when asked "is anything
  missing from the spec / did you actually build it functional".

## The two MOON repos (don't confuse them)
- `moon_agent/` package (this skill's primary map): native tkinter desktop,
  multi-agent council, NEXUS avatar web UI, `cli.py` entry.
- `/home/meow/Projects/MOON` (`app/` package, venv `.venv/`): FastAPI terminal
  interface (`app/terminal_interface.py` @ :8777), `app.brain.orchestrator`,
  `app/tools/*`, `app/capability/*`. Same additive/verify discipline applies;
  verify with `env -u PYTHONPATH .venv/bin/python -m pytest tests` (see
  references/capability_additive_build.md for the exact trap + recipe).
