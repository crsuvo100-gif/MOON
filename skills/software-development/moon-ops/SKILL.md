---
name: moon-ops
description: "Build, extend, operate, and verify the MOON project."
category: software-development
---

# moon-ops — Operating & Extending MOON

MOON is a self-hosted autonomous AI agent at `/home/meow/Projects/MOON` with its own
"brain" (cognition core), **39 connected specialist agents** (each with a durable
`AgentBrain` wired to the main brain via a two-phase CRITIQUE+VERIFY accuracy gate), a `plugins/` tool system, a knowledge base seeded from the Hermes
skill corpus, and a Neural Brain Command Center UI (`/brain`) + knowledge galaxy
(`/galaxy`).

## CURRENT RUNTIME FACTS (verified 2026-09-01)
- **Canonical path**: `/home/meow/Projects/MOON` (single checkout; the older
  `~/Desktop/MOON` no longer exists). **Consolidated MOON runs on `:8778`**
  via systemd `--user` `moon.service`; the original `:8777` backend is
  **decommissioned**. The agent engine lives in `Moon_Twin/` at
  `/home/meow/Projects/MOON/Moon_Twin` — tracked as regular files in the root
  repo (nested `.git` removed; do NOT re-init it).
- **Default model = `qwen3:0.6b`** via Ollama at `http://127.0.0.1:11434/v1`,
  temperature `0.7`. Ollama v0.32.1. Host: Kali (7.1.5+kali-amd64), user `meow`,
  **no GPU** (CPU-only). Keep defaults small — this host cannot run 3B+ models.
- **Voice**: Kokoro TTS, female voice, auto-on (`_speak()` on every reply);
  mute/unmute via `moon voice mute` / `moon voice unmute`.
- **Hard gate**: PUSH to `origin/main` (private `git@github.com:crsuvo100-gif/MOON.git`)
  after landing work ("SAVE AND PUSH TO REPO").

## MOON consolidation (single-service architecture)
MOON is now a single consolidated agent: the Moon_Twin engine
(`/home/meow/Projects/MOON/Moon_Twin/agent/engine.py`) runs on `:8778` via
`moon.service`; the original `:8777` terminal service is decommissioned.
- **Launchers** (in `~/.local/bin/`): `moon` points to `Moon_Twin/main.py`,
  plus `moon_twin`, `moon_twin_api`. All must target
  `/home/meow/Projects/MOON/Moon_Twin` — the old `/home/meow/Moon_Twin` path is
  broken. Verify with `cat ~/.local/bin/moon`.
- **Service file**: `/home/meow/Projects/MOON/deploy/moon-agent.service` is the
  template; the live unit is `~/.config/systemd/user/moon.service`.
- **Fresh reinstall sequence** (user says "reinstall"): stop+disable old
  `moon.service` → run `install_moon.py --no-ollama --no-voice --no-service` →
  write new `moon.service` from `deploy/moon-agent.service` → `daemon-reload` →
  `enable` → `start` → `curl /api/health` → verify launchers + tool count.
- **Missing `__init__.py` trap**: `app/toolbelt/__init__.py` and `app/voice/__init__.py`
  must exist in the **root** `/home/meow/Projects/MOON/app/`, NOT inside `Moon_Twin/`.
  Creating them inside `Moon_Twin/` silently fails (those paths don't exist there).
- **Moon_Twin git tracking**: Moon_Twin is tracked as regular files in the root
  repo. Its nested `.git` was removed. Do NOT `git init` inside `Moon_Twin/`
  again — it recreates the nested-repo problem. Commit Moon_Twin changes from
  the root repo.

Load this skill for ANY task touching the MOON project: rebuild, deep-scan-and-fix,
add a tool/agent, integrate external know-how, tune for a host, or verify it
installs/runs on a machine.

## 🛑 OPERATOR'S PRIME DIRECTIVE — "build only what's missing, never break what exists"
This is the user's most-repeated, emphatic rule across every build/merge/scan task.
Treat it as the FIRST step of any MOON work, above all others:

> "Do not build or program what is already built and programmed inside MOON. Only
> build and program what is MISSING for MOON. Make all functional and ready. Preserve
> every existing feature, behavior, configuration, and integration."

Concretely:
- **Run a gap analysis BEFORE writing code.** `ls app/tools/`, `grep` the agent
  registry, read the system prompt section — produce an inventory of what EXISTS, then
  build ONLY the gaps as real `BaseTool` subclasses / methods / agents.
- **Never overwrite, rename, delete, or rebuild a working module** to add a feature.
  Extend it (new method, new tool in the tuple) or add a NEW file.
- **Never pause/stop/refuse on existing functionality** — the user explicitly said
  don't "pause or stop or anything which is already build." If something already works,
  leave it and move on.
- When the user pastes a long spec/system-prompt and says "build what's missing," that
  is an ADDITIVE build, not a rewrite. Merge personality/identity sections into the
  existing `moon_system.md`; do not replace it wholesale.
- This directive applies to merges too: "merge with existing MOON system prompt" means
  TRUE MERGE (keep identity/lock/cyber/GitHub-feed/smart-build sections, add new ones).
- Commit only the additive, verified changes; the working tree's existing behavior must
  remain intact.

## ⚠️ Host quirks — FIXES (apply every session, do not rediscover)

These are durable properties of this host + MOON, not transient failures.

1. **PYTHONPATH pollution (TWO layers now fixed).** The Hermes runtime injects a
   `python3.11` site-packages path into `PYTHONPATH`, which poisons imports for MOON's
   `.venv` (python3.13) and makes every import *appear* to fail (`ModuleNotFoundError:
   No module named 'pydantic_core._pydantic_core'`). DO BOTH:
   - **At invocation:** prepend `env -u PYTHONPATH` to ALL python/pytest/uvicorn runs:
     `env -u PYTHONPATH .venv/bin/python -m pytest tests/`.
   - **At app start (committed `ec89ba2`):** `app/config/env_guard.py` strips PYTHONPATH
     at process start so MOON is portable to ANY machine even when launched from a
     poisoned shell. It is imported FIRST (right after `from __future__`) in `main.py`
     and `main.py`. **When editing that entrypoint, keep the
     `import app.config.env_guard` line immediately after the future-import and before
     any other import** — otherwise a contaminated PYTHONPATH crashes the import sweep.
   See `references/env_quirks.md` and `references/env_guard.md` (verification recipe
   + import ordering).

2. **`write_file` / `patch` tools are broken for MOON files on this host** ("`[Errno 2]
   No such file or directory`" even when the dir exists). The scanner also blocks large
   inline heredocs. **FIX:** author MOON files via `terminal` heredocs
   (`cat > path <<'EOF'`), splitting into chunks ≤ ~30 lines if the payload is large
   (oversized heredocs hit the hardline blocklist — write in 2–3 appends).
   `read_file` works fine; use it to inspect before editing.

3. **No `asyncio.run()` inside the Hermes background shell** — it already runs an event
   loop, so `asyncio.run()` raises `asyncio.run() cannot be called from a running event
   loop`. **FIX:** `main.py start` launches uvicorn via `subprocess.run([sys.executable,
   "-m","uvicorn",...])`; `get_orchestrator()` does NOT call `run_until_complete` — setup
   is awaited inside the FastAPI startup handler. Never wrap the server launch in
   `asyncio.run`.

4. **MOON HUD "blinking into the display" — three independent root causes (all fixed this
   session).** When the operator reports the web terminal blinking/strobing, do NOT just
   kill one animation — fix ALL THREE layers:
   - **(a) Global CRT flicker + sweep pulse:** `#app{animation:crt 8s}` oscillated the
     whole app opacity `1↔.97` (read as full-screen blink on many displays), and
     `@keyframes hudSweep` pulsed a full-width bar `.15↔.85`. FIX: `#app{animation:none}`
     + flatten `hudSweep` to constant opacity. Keep the neural-core canvas render loop
     (smooth motion, not blink).
   - **(b) Event-driven full-screen flashes:** `edgeFlash()` (full-screen edge glow on
     every core pulse) + `triggerGlitch()` (RGB-split panel jitter on every WS message +
     an ambient `glitchLoop`) + `fireBurst()` (screen-wide particle burst). These fire on
     EVERY backend event → constant strobing. FIX: make all three no-ops; remove
     `fireBurst` from `onCorePulse`.
   - **(c) Hardware panel flicker (Intel i915 eDP):** PSR/RC6 display-state transitions
     cause the physical panel to blink independent of MOON. FIX (reversible, no reboot):
     `scripts/live_gpu_mitigate.sh` (xset/xrandr), and for a permanent GRUB fix
     `scripts/apply_grub_psr_fix.sh` (needs `sudo` + reboot). Details in
     `docs/FIX_DISPLAY_BLINK.md`.
   - Also add a `prefers-reduced-motion` guard so the HUD goes fully calm if the OS asks.
   The canonical red/black palette is NEVER touched.

5. **`moon-terminal.service` restart-loop / stuck `activating` (fixed this session).**
   Symptom: `systemctl is-active` reads `activating` forever; journal shows
   `[Errno 98] address already in use` → `Restart=always` → infinite loop. ROOT CAUSE:
   the unit's `ExecStart` was `python main.py start`, which spawns uvicorn as a CHILD; an
   older backend still holding `:8777` makes the new unit fail to bind → crash-loop.
   FIX: `ExecStart` runs uvicorn DIRECTLY (`...python -m uvicorn app.terminal_interface:app
   --host 0.0.0.0 --port 8777`), so systemd tracks the real server and reports `active`.
   Reusable lesson: when a `Type=simple` unit is stuck `activating` with bind errors, the
   wrapper is spawning a child that can't bind a taken port — run the long-running process
   directly. SAFE KILL: `PID=$(ss -ltnp|grep ':8777'|grep -oP 'pid=\K[0-9]+'|head -1);
   [ -n "$PID" ] && kill "$PID"` — NEVER `pkill -f uvicorn` (it self-matches the shell).

6. **HUD "not opening" — stuck on the black boot overlay (fixed this session).** The HUD
   loads but shows a near-black screen (the `#boot` overlay, `background:#040000`) forever.
   ROOT CAUSE: `#boot` was only removed by `runBoot()`, which fired ONLY through
   `window.MOON_UI.onReady` on the WS `ready` message — any missed/batched frame or a JS
   error left it up. FIX: (a) call `runBoot()` directly inside `ws.onopen` (not just via
   onReady indirection), and (b) harden the monitor heartbeat to force-reveal the HUD
   after a short grace period even if `runBoot` failed. `runBoot` is a hoisted function so
   the early call is valid. Discriminant: an 81%-black screenshot = boot overlay stuck (not
   a CSS/missing-`</style>` issue — that would be PURE black; see moon-web-hud pitfalls).

7. **Deep-monitor `import asyncio` gotcha (caught this session).** When writing an
   in-process proof script that calls `asyncio.run(main())`, the script MUST `import
   asyncio` explicitly — a missing import raises `NameError: name 'asyncio' is not defined`
   → the monitor reports a FALSE FAIL and triggers a spurious backend restart. Always
   import stdlib modules explicitly inside `subprocess`-spawned `-c` snippets.

8. **One-click install + monitoring is the shipped state (this session).** `install.sh`
   is the single entry point: it runs the setup wizard (first run, or `--yes` for
   defaults), then delegates to `install_moon_full.py` (venv, deps incl Kokoro+F5 voice,
   **auto-installs Ollama + pulls all 5 models** via `scripts/install_ollama.py**, sane
   `.env`, launcher, desktop), then enables+starts `moon-terminal.service`,
   `moon-hud.service` (HUD window keeper), `moon-monitor.timer` (deep real-execution
   monitor every 15 min), and verifies HEALTHY. `scripts/moon_deep_monitor.py` proves the
   agent→tool pipeline returns a REAL result (not just a health ping). The deep monitor
   has a `--once` mode for `ExecStartPost` so the unit still reaches `active`. For a
   recurring self-heal beyond systemd, a `cronjob` every 30 min can also watch MOON.

9. **`moon run` (CLI) was ALWAYS blocked by lock — shared lock state was never wired.**
   Symptom: `moon run "any task"` from the terminal always returned
   `🔒 MOON is currently locked. To unlock, say: MOON love you 3000` — even right after
   unlocking in the web HUD. ROOT CAUSE: every call to `main.py:_run()` created a brand-new
   `Orchestrator(get_settings())` with `lock_state_file=None`, and the web backend
   (`terminal_interface._get_orchestrator()`) did the same — so each process had its OWN
   in-memory `SessionLock` with no shared persistence. Unlocking in the HUD unlocks the HUD's
   orchestrator only; the CLI's fresh orchestrator starts locked again every time.
   FIX (two files, additive, non-breaking):
   - `app/brain/orchestrator.py`: when `lock_state_file` is `None` (the common case),
     default it to a shared on-disk path
     `Path(__file__).resolve().parent.parent.parent / "app" / "data" / "lock_state.json"`
     BEFORE constructing `SessionLock`. Now both CLI and web read/write the SAME file.
   - `.gitignore`: add `app/data/lock_state.json` (runtime state, never commit — same class
     as `brain_stats.json`).
   Verification (run after the edit, both directions):
   1. `rm -f app/data/lock_state.json`
   2. `timeout 45 moon run "print UNLOCKED_TEST_1"` → expect the locked notice (correct,
      no state yet).
   3. Write `{"locked": false}` to `app/data/lock_state.json` (this is what the HUD writes
      on real unlock).
   4. `timeout 60 moon run "print UNLOCKED_TEST_2"` → expect the task to EXECUTE and print
      its result (shared persistence working).
   5. `curl -s http://127.0.0.1:8777/api/health` → expect `"locked": false` (the web backend
      picked up the file on the restart that followed the patch).
   6. (Reverse direction) write `{"locked": true}`, restart web backend once
      (`systemctl --user restart moon-terminal.service`), then `moon run` → expect locked
      again. This confirms the file is the single source of truth in BOTH directions.
   See `references/lock_state_sharing.md` for the full reproduction + patch.
   NOTE: after this fix, a HUD unlock persists for `moon run` immediately (each CLI run
   creates a fresh orchestrator that reads the file). The web backend's in-memory lock is
   stale until restart, so if you unlock via HUD and want the HUD's own `/api/health` to
   immediately show `locked:false`, restart the backend once. `moon run` does NOT need the
   restart — it reads the file each time.

10. **Session lock + unlock flow across all three terminal surfaces (moonscope TUI, terminal_moon TUI, CLI).** MOON boots locked on all surfaces; the unlock phrase is `MOON love you 3000` (case-insensitive substring match, also `love you 3000 moon`). Each surface has its OWN lock check that must be wired — a working web HUD does NOT make `moon cli` or `moon terminal` work. ROOT CAUSE class: each entry point creates its own `SessionLock` or `CLIState`; if the unlock check is absent from a surface's dispatch loop, that surface stays locked/silent. FIX (additive, one patch per surface):

   - **CLI path** (`app/cli/cli.py` + `app/cli/commands.py`): add `locked=True` to `CLIState.__init__`, then gate `_handle_chat_input` with `SessionLock().observe(text)` — if it returns an unlock notice, print it + set `self.state.locked=False`; if it returns a locked-rejection notice, print that and return. Also register `/unlock` in `COMMAND_REGISTRY` and wire `_handle_unlock`. Verified: banner shows LOCKED, typing the phrase unlocks, chat works after.

   - **moonscope TUI** (`app/tui.py`): boot `hud.locked=True` AND `self._state.locked=True` (both must agree — the `_handle_input` lock check reads `self._state.locked`). Gate input with `SessionLock().observe(text)`, distinguish unlock vs locked-rejection by keyword in the notice (both are truthy), render unlock notice as `role: agent` so it shows in chat panel. Also: `on_input_submitted` MUST be `async def` and `await self._handle_input(...)` — `asyncio.create_task` fire-and-forget swallows the LLM response rendering. And `query_one(StatusHUD)` in `_chat_with_llm` line must reference `BrainHUD` (the actual widget id is `hud`, class is `BrainHUD`) — wrong widget name raises `NoSuchWidget` and silently kills the response. Verified in `run_test`: boots LOCKED→blocked→unlocks→chat responds.

   - **terminal_moon TUI** (`terminal_moon/app/tui.py`): same pattern — boot `hud.locked=True`, gate `_handle_input` with `SessionLock().observe(text)` BEFORE calling `_chat_with_llm`, block non-unlock input while locked. Also: `LLMService` has NO `teardown()` method — calling it in `_chat_with_llm`'s `finally` raises `AttributeError` and crashes the TUI; use `await self._llm._client.aclose()` wrapped in try/except instead. Verified: boots LOCKED→blocked→unlocks with agent notice→chat responds, no crash.

   - **Shared lesson across all three**: `SessionLock.observe(text)` returns a truthy notice in BOTH cases — unlock (`"🔓 ... unlocked"`) and locked-rejection (`"🔒 ... locked"`). Always disambiguate by checking for `"unlocked"` in the notice rather than `if notice:` alone. The two unlock phrases are `"MOON love you 3000"` and `"love you 3000 moon"` (case-insensitive substring match). See the lock class itself at `terminal_moon/app/brain/lock.py` (the source of truth for `UNLOCK_PHRASES` + `WAKE_WORD`). 

- **Shared lesson across all three**: `SessionLock.observe(text)` returns a truthy notice in BOTH cases — unlock (`"🔓 ... unlocked"`) and locked-rejection (`"🔒 ... locked"`). Always disambiguate by checking for `"unlocked"` in the notice rather than `if notice:` alone. The two unlock phrases are `"MOON love you 3000"` and `"love you 3000 moon"` (case-insensitive substring match). See the lock class itself at `terminal_moon/app/brain/lock.py` (the source of truth for `UNLOCK_PHRASES` + `WAKE_WORD`). 

   Verification for ANY new/changed surface: (1) boots showing LOCKED, (2) typing non-unlock text while locked shows blocked notice + stays locked, (3) typing the unlock phrase unlocks + shows unlock notice + flips lock state, (4) chat after unlock gets a real LLM response, (5) no crashes on cleanup (`teardown` vs `aclose`). Run each surface via `run_test` for the TUIs or `echo ... | timeout ... moon cli` for the CLI.

See `references/tui_debugging.md` for the proven Textual TUI debugging technique (run_test + monkey-patch tracing) and the full list of MOON TUI bugs found + fixed this session.

## Core architecture (key paths)

- `app/brain/orchestrator.py` — cognition core, agent registry wiring, `run_task`.
- `app/brain/agent_registry.py` — `AGENT_DEFS` (39 agents) + `build_agents()` + `persona_for()`.
- `app/brain/agent_model_manager.py` — `AgentModelManager` + `AGENT_MODELS`: every agent runs on its OWN model (lazy `ollama pull`, cached `LLMService`).
- `app/brain/agent_brain.py` — per-agent durable brain (JSONL at `app/logs/agent_brains/<agent>.jsonl`),
  wired to main brain for two-phase validation.
- `app/brain/context_builder.py` — injects per-agent persona + retrieved context.
- `app/brain/knowledge_consolidator.py` — auto-learning (facts → LTM + KB).
- `app/brain/prompt_tuner.py` — self-improvement: `record_lesson()` / `load_lessons()` / `augment_persona()` persist + apply improvement "lessons" from `app/logs/lessons.jsonl` into agent personas at runtime.
- `app/voice.py` — MOON's **female voice** (TTS) + optional STT dictation. `Voice(preset=...)`; `speak(text)` returns a WAV; `transcribe_mic()` (vosk, optional).
- `scripts/voice_loop.py` — companion loop: mic/typed input → MOON WS → reply spoken in MOON's female voice.
- `plugins/` — `BaseTool` subclasses, auto-loaded by `plugins/loader.py` (no manual registration).
- `app/knowledge/skills_library.py` — indexes `skills/*.md` into the KB at startup. **The
  `skills/` dir is OPTIONAL LOCAL DATA, NOT shipped** (untracked + gitignored since commit
  `125fa27`; it was a 385 MB Hermes bundle that made the repo non-portable). `index_skills()`
  returns 0 if `skills/` is absent, so removal never breaks a feature. Drop your own MOON
  skills corpus there to have it indexed.
- `skills/` — OPTIONAL local skills corpus (NOT in git). If present, `skills_library.py`
  indexes it into the KB. See the repo-portability note in §E.
- `main.py` — CLI. `start` AND `terminal` both launch the MOON terminal (FastAPI on `:8777`, serving `web/moon_terminal.html`). `run "task" --agent X` for CLI tasks. The old `:8000` Command Center (`app/api/main.py` + `web/moon_brain.html` + `web/galaxy.html`) was DELETED — there is now exactly ONE terminal UI. Do NOT add back a second one.
- `install_moon.py` — bootstrap: creates `.venv`, `pip install -r requirements.txt`, smoke import.
- `web/moon_terminal.html` — the single MOON terminal UI (`:8777`). NOTE: `app/tools/terminal.py` is a SEPARATE capability tool (`TerminalTool`, shell exec, imported by the orchestrator) — NOT a UI.

## CLI Terminal Verification (Hermes-style `app/cli/` package)

See `references/moon-cli-terminal.md` for the full verification recipe, terminal
type matrix (REPL, Textual TUI, web HUD, old fallback), root-caused bugs, and the
GitHub push gate. Key points:

- MOON has 7 terminal entrypoints across 3 architectures: CLI REPL (`moon cli`),
  Textual TUI (`moon shell`/`moon tui`/`moon` bare), and web HUD
  (`moon terminal`/`moon-terminal.service`).
- After any change to `app/cli/`, verify: compile (py_compile), imports, CLI
  subcommands (doctor 9/9, status HEALTHY, oneshot real LLM response), Textual TUI
  boots (timeout 8, no traceback), web HUD active, old fallback functional.
- Two pre-existing bugs are patch-ready on request: (1) `moon shell`/`moon tui`/`moon`
  crash with `ModuleNotFoundError: No module named 'textual'` if textual isn't installed
  (`.venv/bin/pip install textual` fixes it); (2) `/compress` ignores all args and just
  deletes messages — `_handle_compress` must parse `command` into `parts[0].lower()`.
- GitHub push gate: commit with `fix(cli):` prefix, push with SSH key loaded
  (`ssh-add ~/.ssh/id_ed25519`), verify `git log --oneline -3`.

## Workflows

### A) Deep scan & fix (the user's recurring "scan and check" request)
1. **Whole-project import sweep (catches every actually-broken module in one pass).**
   Compile everything, then import ALL `.py` under the project (excluding `.venv/.git`
   and the embedded `skills/` corpus — those are the Hermes skill library with their own
   optional deps like `torch`/`PIL`/`defusedxml` and are NOT MOON core). A robust inline
   sweep:
   ```python
   import importlib, pkgutil, pathlib
   root = pathlib.Path('.')
   mods = ['.'.join(p.with_suffix('').parts) for p in root.rglob('*.py')
           if '.venv' not in p.parts and '.git' not in p.parts and '__pycache__' not in p.parts]
   for m in mods:
       try: importlib.import_module(m)
       except BaseException as e: print(f"IMPORT-FAIL {m}: {type(e).__name__}: {e}")
   ```
   This session: **158 modules, 150 import-OK, 8 failed — ALL 8 inside `skills/`** (the
   Hermes corpus, optional deps), and **every `app/` module imported cleanly** (proving
   MOON's core has no import errors). The `app/` tree imports lazily-gated optional libs
   (`vosk`, `pytesseract`, `PIL`, `playwright`, `pypdf` via `try`/`except`), so those
   missing is fine per `requirements.txt` comments.
2. Static: `env -u PYTHONPATH .venv/bin/python -m pyflakes app` then `ruff check app`
   (filter out `F401` package-`__init__` re-exports — those are intentional). Real bugs =
   F-codes other than F401, or `unterminated string`/`undefined name`.
3. Tests: `env -u PYTHONPATH .venv/bin/python -m pytest tests/ -q`.
4. Live proof: restart backend, then exercise via WebSocket — **unlock phrase
   `MOON love you 3000`**, then send a teaching message and confirm facts persist to
   `app/logs/long_term.jsonl` tagged `auto-learn`.
5. Only commit VERIFIED changes. Commit messages cite the real fix.

### B) Add a plugin tool (extend capability)
Write a `BaseTool` subclass in `plugins/<name>_tool.py` with `name`, `description`,
and `async def execute(self, **kwargs) -> str`. It auto-registers via `plugins/loader.py`
(no boilerplate). Prefer **dependency-free, key-free** tools (stdlib only) so they work
on any machine. See `references/extend_plugin.md`.

**⚠️ TOOL RETURN-CONTRACT GOTCHA (caught + fixed this session):** `execute()` MUST
return a **`str`**. The runtime (`ToolManager` → `orchestrator._tools`) calls the tool by
name and the cognition loop expects a string. Do NOT:
- return a `ToolResult(success=..., error=..., data=...)` object — `ToolResult` is defined
  in `app/tools/base.py` but is **NOT used by the execution path** (it's dead for returns);
- add a `parameters = {...}` class attribute expecting the runtime to read it (it doesn't —
  `spec()` is generic; args are passed positionally/by-name from the caller);
- return a `dict`/`json.dumps` and expect structured parsing — callers treat the whole
  return as text (you may `json.dumps` *inside* the string if the consumer parses it).
Correct shape (verified working): `async def execute(self, action: str = "list", **_kw) -> str:`
and `return json.dumps({...})` or `return "text result"`. If a sibling tool (e.g.
`web_search`) does `async def execute(self, query: str = "", **kw) -> str`, match that
signature. Both `model_management_tool.py` and `learning_tool.py` were first written with
the WRONG `ToolResult`/`parameters` contract and had to be rewritten → returned strings.

### C) Add/expand agents (advanced, fast, accurate)
Edit `AGENT_DEFS` in `app/brain/agent_registry.py` (role, persona, tool-scope). Each new
agent automatically gets a durable `AgentBrain` at startup. Speed/accuracy levers already
built in: **fast-path** (`enable_fast_path`, single-call for simple queries) and
**parallel fan-out** (`max_parallel_agents`, coordinator splits "X and also Y" and runs
sub-agents via `asyncio.gather`). See `references/extend_agents.md`.

### D) Integrate external know-how as MOON knowledge
Copy a skill/corpus dir into `MOON/skills/`, then add a loader that indexes each
`SKILL.md` into the KB at startup (pattern in `app/knowledge/skills_library.py`). Verify
with `semantic_recall("excalidraw")` returning the skill doc. Do NOT force-wrap
API-key/heavy-dep skills as offline tools — keep their docs in `skills/` for reference.

### F) Self-improvement / autonomous upgrade loop (real, safe)
MOON can keep improving while unattended. The building blocks (already present):

- **PromptTuner** (`app/brain/prompt_tuner.py`): `record_lesson(text, kind, agent)` appends
  to `app/logs/lessons.jsonl`; `load_lessons(agent)` + `augment_persona(base, agent)` inject
  the most recent lessons into an agent's persona at context-build time (wired in
  `context_builder.build`). Effect: MOON's answers steer away from past failure modes
  without hand-editing code.
- **Failure→lesson**: `orchestrator.run_task` calls `record_lesson(...)` when
  `Validator` flags invalid output (kind="validation"). Extend this for other correction
  signals (user "no, do X", reflection-unsatisfactory).
- **Self-consistency (accuracy)**: `enable_self_consistency` re-runs `_run_cognition_loop`
  once on factual prompts and, via `_answers_disagree()`, appends a "[Self-consistency
  note] verify the key claim" warning when the two passes differ. Off by default (CPU cost).
  **NOW (commit `20d6305`): `enable_self_consistency` is ON, `self_consistency_samples=2`
  => a 3-way majority vote that REPLACES the answer with `_majority_answer` (exact-match,
  then token-overlap consensus), not just a warning. `Orchestrator._pick_llm()` also
  routes factual + cyber-critical prompts to `STRONG_MODEL_NAME` (set in `.env`) when
  configured, and `refine()` audits on `_llm_strong`. See `references/agent_brain_accuracy_gate.md`.**
- **Tool hardening**: `ToolManager.run` wraps `tool.execute` in `asyncio.wait_for(timeout=
  settings.tool_timeout)`; set `tool_timeout` in `app/config/settings.py`.

**Background-run pattern (so it "runs until you come back"):** launch a `cronjob` or a
`terminal(background=true)` process that periodically runs `make test`, triggers
consolidation on any new LTM entries, and reports status. Keep it BOUNDED:
- Every code change MUST be followed by `env -u PYTHONPATH .venv/bin/python -m pytest tests/ -q`.
- Revert (or don't commit) any change that makes tests red. Commit only green, verified changes.
- Prefer small, tested commits over a free-running code-generator that could break the tree.
- Never let an unattended loop claim success it didn't verify.

See `references/self_improvement.md`.

### E) Verify "installs on any machine" (definitive)
Clean-room test: `rsync` the project (excluding `.venv`, `app/logs`, `.env`) to `/tmp`,
create a fresh venv there, run `install_moon.py`, then `make serve`, and `curl` every
endpoint. This catches missing `requirements.txt` deps and broken `Makefile` targets
before the user hits them. See `references/verify_install.md`.

**⚠️ CLEAN-ROOM ON THIS HOST: `unset PYTHONPATH` BEFORE `python3 -m venv`.** The Hermes
runtime injects a `python3.11` site-packages path into `PYTHONPATH`. If you create a fresh
venv WHILE that var is set, `pip install` and even a later `env -u PYTHONPATH python` import
will fail with `ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'` — the
venv's interpreter resolves a contaminated `sys.path`. Symptom seen this session: a
`rm -rf /tmp/cleanvenv && python3 -m venv /tmp/cleanvenv && pip install -r requirements.txt`
run under the inherited PYTHONPATH produced a venv where `import fastapi` crashed on
`pydantic_core`. **Fix:** `unset PYTHONPATH` at the SHELL level first (not merely as a
prefix on the pytest line), THEN `python3 -m venv` + `pip install`. Verify with
`/tmp/cleanvenv/bin/python -c "import fastapi,pydantic,pydantic_settings"` printing OK with
PYTHONPATH unset. This is the definitive "installs on a clean machine" proof — without it the
check is meaningless on this box (the contamination makes a clean-room test lie).

**Add a CI gate so GitHub verifies install automatically.** `.github/workflows/ci.yml`
builds its OWN venv, `pip install -r requirements.txt`, runs an **import smoke test**
(`python -c "import app.terminal_interface, app.dashboard, app.voice, app.brain.orchestrator"`),
then `env -u PYTHONPATH python -m pytest tests -q` across Python 3.10–3.12. Every push
proves the project installs + tests green. Full recipe + the `scripts/*.py` direct-run
import trap below: `references/ci_install_verify.md`.

**`scripts/*.py` direct-run import trap (real bug, fixed this audit):** when a script in
`scripts/` imports `from app...` and is launched as `python scripts/foo.py` (e.g. `make live`
→ `python scripts/live_smoke_pipeline.py`), the project ROOT is NOT on `sys.path`, so it
crashes `ModuleNotFoundError: No module named 'app'`. `voice_loop.py` already inserts
`sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` before its `app` import;
`live_smoke_pipeline.py` and `voice_test.py` were MISSING it and had to be patched. **Rule:**
any `scripts/*.py` that imports `app` must insert the project-root `sys.path` line at the
top (before the `app` import), OR it breaks when run via `make`. Audit with
`grep -L "sys.path.insert|sys.path.append" scripts/*.py` (should list only scripts that
never import `app`).

**⚠️ DO NOT SHIP THE `skills/` HERMES BUNDLE (repo-portability lesson, commit `125fa27`).**
A copy of the **entire Hermes skills corpus** (`skills/` — 25 top dirs, ~592 files, **~385 MB**
of unrelated skill content) had been committed into the MOON repo. That made a fresh
`git clone` pull 385 MB of non-MOON data and is the #1 "won't install cleanly anywhere"
problem. **Fix applied:** `git rm -r --cached skills/` (untracked, kept on disk locally as
optional data) + added `skills/` to `.gitignore`. The tracked tree dropped to **<1 MB**; a
fresh clone is **~1.7 MB** and installs in a clean venv in seconds. **Why it's safe:** the
only consumer is `app/knowledge/skills_library.py::index_skills()`, which already handles
absence gracefully — `if not SKILLS_DIR.exists(): logger.info(...); return 0`. So removing
it from git does NOT break any feature; the KB just indexes 0 external skills until the
operator drops their own corpus into `skills/`. **Rule:** never `git add` the `skills/`
corpus; it is local optional data. The same applies to any large embedded bundle — check
`git ls-files | xargs du` for unexpected bulk before pushing.

**⚠️ `pyproject.toml` MUST declare real `dependencies` (was `[]`).** With `dependencies=[]`,
`pip install .` installed no deps and the package was non-functional on a fresh machine.
Fix: list the `requirements.txt` deps in `[project].dependencies` AND add
`[project.scripts] moon = "main:main"` so the CLI is on PATH after install. Keep the two in
sync when you change requirements.

**`.gitignore` runtime logs (do NOT commit local state):** `app/logs/` JSONL
(`lessons.jsonl`, `episodes.json`, `long_term.jsonl`, `agent_brains/*.jsonl`) must be
gitignored. The repo `.gitignore` covered `long_term.jsonl` + `moon_lock.txt` but was
MISSING `lessons.jsonl`/`episodes.json` — a `git add -A` would commit local learning.
Keep them ignored; if already tracked, `git rm --cached <f>; git update-index --assume-unchanged <f>`.

### G) Pre-launch audit (the recurring "deep check / is it ready?" request)
Before declaring MOON ready/launchable, run the **12-point audit battery** in
`references/pre_launch_audit.md` (git state → pyflakes → import sweep → full tests →
route wiring → config → requirements → compile → entrypoints → lock → gitignore →
live boot). It is the canonical "scan everything and prove it works end-to-end" check.
When the user says "fully deeply check for what is missing for launch", run all 12.

### H) Voice — female TTS + dictation (real, not magic)
MOON got a warm, clearly-FEMALE voice this session. Module `app/voice.py`;
companion `scripts/voice_loop.py`. Makefile: `make voice` / `make voice-test` /
`make voice-install`.

- **Female TTS**: espeak female voice (`-v en+f5`) + a **SoX timbre chain**
  (`pitch` in **Hz** ~220–340, `bass` body, `treble` air, `highpass`, `compand`,
  optional `chorus`+`reverb`). Presets `default/seductive/warm/crystal` in
  `FEMALE_PRESETS`. See `references/voice.md` for the full chain + verification.
- **Dictation (STT)**: `Voice.transcribe_mic()` uses `vosk` + `VOSK_MODEL_DIR`.
  It is OPTIONAL+HEAVY and NOT installed by default — if absent, the companion
  loop falls back to typed input but STILL speaks replies in the female voice.
  Never fabricate a working mic dictation without vosk; wire it and degrade gracefully.
- **Verify**: `Voice(preset='seductive').speak("...")` writes a ~150–180 KB WAV;
  confirm the file exists + size. Live: unlock → ask → MOON replies → `speak()`
  writes the WAV (proven this session).
- **Install**: `install_moon.py` runs `apt-get install -y espeak sox` + `pip install vosk pyaudio`.

### I) Cyber-security: defensive + offensive expert (real, authorization-gated)
MOON can be a full cyber operator — defensive (audit/hardening/IR) AND offensive
(recon/scan/exploitation) — built as real `BaseTool` subclasses, not prompts.
User wants MOON "fully capable" here and "uncensored". Two honest constraints
to hold (the user accepted the authorization gate without pushback):

- **No hidden uncensored system prompt exists.** MOON's real system prompt is
  `app/prompts/templates/moon_system.md` (generic "helpful assistant" by default).
  To make MOON a cyber expert, REWRITE that file into a technical, non-refusing,
  authorized-scope framing (see `references/cyber_security.md` for the exact
  persona used). Do not claim a jailbreak prompt exists when it doesn't.
- **Authorization gate on ACTIVE offensive ops.** Don't remove safety such that
  MOON attacks third parties. Gate active ops (scan/exploit) behind target
  authorization: `app/security/authorization.py` — `require_auth(target,
  confirmed=...)` allows loopback/RFC1918 (your lab) and anything in
  `AUTHORIZED_TARGETS` env, else refuses. This is the professional red-team model
  (nmap/Metasploit are dual-use, legal only on authorized targets).

Build recipe (all `BaseTool` subclasses, registered in `app/brain/orchestrator.py`
tool tuple):
- `app/security/authorization.py` — `require_auth()` target gate (env `AUTHORIZED_TARGETS`).
- `app/tools/recon_tool.py` — passive DNS/whois + active port scan (auth-gated).
- `app/tools/vuln_scanner_tool.py` — nmap/nikto/nuclei if present else heuristic (auth-gated).
- `app/tools/hardening_audit_tool.py` — defensive config/host review (no auth needed; user supplies material).
- `app/tools/log_analyzer_tool.py` — SOC aid: brute-force/scan/web-exploit/reverse-shell/SQLi detection.
- `app/tools/malware_analysis_tool.py` — static triage (hashes, strings, IOCs), NO execution.
- `app/tools/exploit_intel_tool.py` — retrieves red-team/CVE refs from `skills/` corpus (knowledge only).
- Agents: enhance `security` persona + add `cyber` and `red_team` to `AGENT_DEFS`
  in `app/brain/agent_registry.py` (each auto-gets a durable `AgentBrain`).
- `.env.example`: add `AUTHORIZED_TARGETS=127.0.0.1,localhost,192.168.0.0/16,10.0.0.0/8`.

Verify: `orchestrator._tools._registry.tool_names` contains the 6 tools; auth gate
allows `127.0.0.1`, blocks `8.8.8.8`; `recon`/`hardening_audit`/`log_analyzer`/
`exploit_intel` execute correctly. See `references/cyber_security.md`.

### J) Auto tool-acquisition — MOON installs tools on demand (this session)
When a task needs a capability MOON lacks, she detects it, installs + registers
the tool, then completes the task — instead of giving up. Real code, not magic.

- **Engine**: `app/tools/tool_acquisition.py` — `TOOL_CATALOG` (capability → pip
  package), `acquire_by_catalog()` (pip-install + register thin wrapper),
  `generate_plugin()` (write an LLM-produced `BaseTool` to `plugins/generated/`,
  import + register, cleanup on failure). `plugins/generated/` is gitignored.
- **Wiring**: `orchestrator._auto_acquire_for_task(task, agent)` runs at task start
  (after agent selection). Catalog match first; if still missing, a tiny LLM call
  emits `{"need","name","purpose","code"}` JSON → installs from catalog or generates
  a plugin. Best-effort: on install failure / offline, the task proceeds with
  existing tools (never crashes).
- **Add a capability**: append to `TOOL_CATALOG` in `tool_acquisition.py`
  (`"mycap": {"pip":"mylib","import":"mylib","cap":"..."}`). No orchestrator
  change needed beyond the existing hook.
- **Verify**: `acquire_by_catalog("analyze this data with pandas", reg)` →
  `'tool_data'` registered + pandas importable; `generate_plugin(...)` writes +
  registers a `BaseTool` and `await reg.get("greet_custom").execute(name="MOON")`
  → `Hello, MOON!`. Full recipe + pitfalls in `references/auto_acquire.md`.
- **Pitfall**: `plugins/generated/` needs `__init__.py`; generated code must define
  a `BaseTool` subclass; orchestrator uses `self._tools._registry` (NOT `.get()`).

### K2) Import a Hermes `skills/` backup AS a callable MOON skill library (this session)
When the operator gives you a `hermes/skills/*` backup and says "gain and implement those skills,"
the correct build is to make MOON able to **recall AND execute** them — not just copy docs into a
folder. Proven pattern (built this session, 97 skills indexed + real tools wired):

1. **Copy the corpus, not the whole tree.** `find SRC -name SKILL.md` → preserve
   `category/skill/SKILL.md` under `moon_agent/skills/sk_db/`. Skip heavy blobs (the backup had a
   242 KB `.xsd` and a 385 MB potential bulk — copy only `.md` + small `.py`/`.sh`).
2. **`SkillCatalog`** (in `moon_agent/skills/catalog.py`): parse each `SKILL.md` frontmatter
   (`name`, `description`), build `SkillEntry(category, skill, name, description, path)`, expose
   `search(query)`, `get(name)`, `snippet()`, `summary()`. Pure stdlib, no deps.
3. **Vendor the runnable scripts** into `moon_agent/skills/vendor/`: copy the small stdlib-only
   helpers (`research/arxiv/scripts/search_arxiv.py`, `research/polymarket/scripts/polymarket.py`,
   `media/youtube-content/scripts/fetch_transcript.py`). For scripts needing pip
   (`youtube_transcript_api`, `marker-pdf`), wrap the tool to detect the missing import and return a
   clear `pip install ...` message instead of crashing.
4. **Wrap as tools** (`moon_agent/skills/tools.py`): each vendored script → a `ToolSpec` +
   `run()` that `subprocess.run([sys.executable, script, *args])`. Plus pure-Python tools derived
   from skill guidance: `humanize` (deterministic filler-stripper from the humanizer skill),
   `ascii_banner` (pyfiglet if present, box fallback), `plan` (writes `.hermes/plans/`).
5. **Wire into runtime:** `self.tools._tools.update(build_skill_tools(...)._tools)` so skill tools
   merge with the core registry. Add `/skills`, `/skill-search`, `/skill-view` commands + natural
   shortcuts (`arxiv <q>`, `polymarket trending`, `humanize <text>`).
6. **Tests:** assert `catalog.size() >= 90`, search hits for `arxiv`/`plan`/`godmode`, and that
   `skill_recall`/`skill_list`/`arxiv_search` are in `agent.tools.names()`.

**Pitfalls fixed this build:** (a) a stale `moon_agent/skills.py` module SHADOWED the new
`moon_agent/skills/` package (same name, file vs dir) — delete the old module first; (b) `patch`/
`execute_code` inserted a LITERAL newline inside `\"\\n\".join(...)` → `unterminated string literal`
— after writing, immediately `py_compile` and rewrite the whole function with `write_file` if a
string-literal patch looks suspect (see "Source-writing newline corruption" in Recurring pitfalls);
(c) `SkillEntry` needs its own `snippet()` method (the catalog's `snippet(entry)` takes the entry as
arg; tools called `entry.snippet()`) — put the method on the dataclass.

**Honesty rule:** MOON "knows" the skills because it can recall/execute them — not because it
memorized prose. If a skill's script needs an uninstalled dep, say so; never claim the skill ran
when the import failed. Full recipe + verified patterns: `references/skill_library_import.md`.

### K) Build missing capabilities from the system prompt (gap-analysis build)
When the user pastes a full MOON system prompt and says "build everything missing,"
do a STRUCTURED gap analysis, don't rebuild. Recipe that worked this session:

1. **Inventory prompt capabilities vs code** with a `grep`/`ls` sweep:
   `ls app/tools/ | grep -iE "linux|win|mac|docker|git|forensic|malware|..."` and
   `grep -oE '"(blue_team|purple_team|forensics|...)"' app/brain/agent_registry.py`.
   This surfaces what's absent (e.g. no OS-specific tools, no Blue/Purple/Forensics/
   SIEM agents, no structured report).
2. **Build only the gaps** as real `BaseTool` subclasses + `AgentCard`s (not prose):
   - `app/tools/system_info_tool.py` — cross-OS host recon (stdlib; `free`/`ps` via
     `shutil.which` guard). **Pitfall:** don't unpack unused tuple vars
     (`free, = ...` unused → RUF059); the `free` capture wasn't even used — drop it.
   - `app/tools/powershell_tool.py` — `pwsh`/`powershell` wrapper (Windows host).
   - `app/tools/docker_tool.py` — `docker ps/images/run/exec/logs` via subprocess.
   - `app/tools/git_tool.py` — `git status/diff/log/clone/commit` on a repo path.
   - `app/tools/self_evolve_tool.py` — **bounded self-evolution**: ingest a URL or
     local file/repo into the KB via `orchestrator._consolidator.consolidate(...)`.
     Operator-triggered (NOT autonomous crawling) — keeps "evolve from the internet"
     safe. If the consolidator import path is fragile, wrap in try/except and still
     report ingestion.
   - New agents in `AGENT_DEFS`: `blue_team`, `purple_team`, `forensics`, `reverse_eng`,
     `threat_hunt`, `siem` (each persona = "you are MOON's <role> ..."; auto-gets a
     durable `AgentBrain`). These satisfy the prompt's Blue/Purple/Red + forensics/SIEM
     requirement without touching existing agents.
   - **Final-report formatter** `orchestrator._final_report(task, actions, evidence,
     results)` → returns the prompt's required structure: `OBJECTIVE / ACTIONS
     PERFORMED / EVIDENCE / RESULTS / REMAINING ISSUES / RECOMMENDED NEXT STEPS`.
3. **Wire** all new tools into the orchestrator tool tuple + imports; register agents
   automatically via `build_agents()`.
4. **Verify live** (not just import): boot orchestrator, assert new tool names in
   `registry.tool_names`, new agents in `o._agents`, `_final_report` contains all 6
   section headers, `system_info.execute()` returns host info, `self_evolve.execute(
   source=/abs/path)` reports "ingested". Then `make test` + commit.

Key takeaway: the "smart build policy" in the prompt (preserve working features, build
only missing) maps directly to `git`-clean incremental commits + `make test` gating —
never rewrite working modules.

### L) Per-agent brain accuracy gate — "no mistake" guarantee (this session)
The user's recurring ask — "build own brain for all agents, connect to main
brain, accurate results no mistake" — is satisfied by `app/brain/agent_brain.py`
`AgentBrain`, where EVERY agent's brain is wired `main_brain=orchestrator` at
startup and its draft answer is passed through a **two-phase CRITIQUE+VERIFY**
gate before being persisted. This is the real mechanism behind "accurate, no
mistake" — not a prompt claim.

- **Connect:** `Orchestrator.setup()` builds `AgentBrain(name, main_brain=self)`
  for each agent in `AGENT_DEFS`; `run_task` calls
  `agent_brain.refine_with_main(final_text, task.prompt)` when
  `enable_agent_validation` is on, THEN `agent_brain.remember(...)` stores the
  (verified) episode to `app/logs/agent_brains/<agent>.jsonl`.
- **Gate logic (CURRENT, commit `20d6305`):** the main brain is asked for strict
  JSON `{"verdict":"ok|corrected","answer":"..."}` and parsed DEFENSIVELY (see
  `references/agent_brain_accuracy_gate.md`). **Do NOT use rigid `OK`/`CORRECTED`
  prefixes** — a prior version did and silently returned wrong answers because
  small local models reply in free-form prose ("The original calculation is
  incorrect... Corrected Answer: 56") that never starts with `CORRECTED`. Both
  audit calls use `temperature=0.1`; when `STRONG_MODEL_NAME` is set, `refine()`
  runs the audit on `_llm_strong`. Parse via `_extract_answer()` (JSON, then
  "corrected answer:" / last-line-on-"incorrect" fallback) so a disobedient model
  still gets corrected.
- **Verify**: assert `len(o._agent_brains) == len(o._agents)` and every
  `brain.main_brain is orch`; live-test by feeding wrong drafts and confirming the
  main brain returns the corrected answer (`7*8=54`→`56`, `2+2=5`→`4`,
  `integral of x is x cubed`→`x^2/2 + C`). Unit test `test_two_phase_parse_logic`
  covers JSON + free-form-prose parsing with a `FakeMain` (no LLM). Full recipe +
  the defensive `_extract_answer` parser in `references/agent_brain_accuracy_gate.md`.
- **Pitfalls**: gate adds 1–2 model calls/task (CPU cost); on `qwen3:0.6b` it
  works but isn't infallible — for max rigor also enable `enable_self_consistency`
  or route critical tasks to a larger model. `enable_agent_validation` is the
  master switch.

### M0) Local LLM brain ceiling on THIS host — verified (this session)
The operator asked to "pull the most intelligent all-capabilities model" for MOON's brain.
Empirically verified on the Kali box (CPU-only, **3.7 GB RAM** total / ~1.1 GB free + 3.8 GB swap,
4 cores; Ollama as `ollama.service`, worker owned by user `ollama`):

- **`qwen3:1.7b` RUNS** (tools + thinking). Two successive calls OK.
- **`qwen2.5:3b`, `qwen3:8b`, `deepseek-r1:8b`, `qwen3.5:9b` OOM-KILL Ollama** every time
  (curl exit 52/28/7, then API down until the worker respawns). Even though 9b/8b are *downloaded*,
  they will NOT execute here. The only model with vision+tools+thinking (`qwen3.5:9b`) crashes.
- Net: **1.7B is the largest model that runs** on this hardware; anything ≥3B crashes the API.

**Brain-wiring rule:** default brain model = `qwen3:1.7b`, with a fallback chain
`qwen3:1.7b -> qwen3:0.6b` so the harness NEVER auto-selects an 8B/9B model it cannot run.
When the operator demands "most intelligent / all capabilities," state the RAM ceiling HONESTLY and
offer the real upgrades: (a) a host with ≥16 GB RAM (8B) or ≥32 GB (≥9B) or a GPU; (b) wire an API
brain via `OPENAI_API_KEY` + endpoint in the runtime's chat-completion call. The runtime MUST degrade
to the multi-agent council if Ollama returns nothing — never crash.
Verified real run: `> What is 7 times 8?` → `MOON> 7 times 8 is **56**.` (via `qwen3:1.7b`).
Full recipe + evidence: `references/local_model_ceiling.md`.

### M) Per-agent AI models — every agent pulls/installs and runs on its OWN model
MOON gives each agent a dedicated model (pulled via Ollama on demand) for its
function, then feeds its result up through its AgentBrain to the main brain for
consolidated, accurate answers. The recurring ask "every agent can use its own
model for better results, feed main brain" is satisfied here — not a prompt claim.

- **Manager**: `app/brain/agent_model_manager.py` — `AgentModelManager` +
  `AGENT_MODELS` (role-suited map: coding→`qwen2.5-coder:1.5b`, math/science/
  research/cyber/forensics/SIEM→`qwen2.5:3b`, general→default). `ensure_model()`
  lazily `ollama pull`s a missing model (best-effort, graceful fallback to default
  on offline/OOM). `get_llm(agent)` returns (cached) the agent's OWN `LLMService`.
- **Tool**: `app/tools/model_pull_tool.py` (`model_pull` = `ollama pull` wrapper).
- **Setting**: `enable_per_agent_models` (default True) in `app/config/settings.py`.
- **Endpoint**: `GET /api/agent-models` → which model each agent is bound to.
- **Startup pre-pull (commit `2ed5cf8`)**: `AgentModelManager.prefetch_all(max_parallel=2)`
  concurrently `ollama pull`s every distinct preferred model inside `setup()` so
  agents are ready instantly (best-effort, never raises; reports per-model success).
  CLI: `python main.py models` and `make models` run it standalone — verified this
  session pulling qwen2.5-coder:1.5b, qwen2.5:3b, qwen3:0.6b (3/3 ready).
  Exact commands + RUF012/PERF402 lint recipe: `references/moon_lint_and_prepull.md`.
- **Wiring**: `Orchestrator.setup()` builds the manager; `_run_cognition_loop`
  generates on `await self._agent_models.get_llm(agent.name)` (fallback to
  `_pick_llm`). Teardown closes all agent LLMs.
- **Flow**: agent's own model produces the draft → `AgentBrain.refine_with_main`
  two-phase gate (uses `_llm`/`_llm_strong`, NOT the agent model) re-checks → main
  brain. So the result is independently validated, accuracy preserved.
- **Verify**: `o._agent_models._preferred("math")` → `qwen2.5:3b`;
  `await o._agent_models.get_llm("math")` → `svc._model == "qwen2.5:3b"`;
  `GET /api/agent-models` returns `per_agent_models: true`. Test:
  `test_per_agent_model_manager_binding`. Full recipe + RAM pitfalls in
  `references/per_agent_models.md`.
- **Pitfalls**: (1) On CPU-only hosts, don't pre-pull many 3B models at once —
  pulls are lazy + cached. (2) `setup()` is slow (~2–3 min, skill indexing +
  strong-model build); run with long `timeout` or background. (3) If `ollama`
  missing, agent gracefully uses default — no crash.

### O) Merge an external / "wife-of-Psycho" personality system prompt (this session)
When the operator pastes a full personality/identity system prompt (e.g. "MOON is the
devoted wife of Psycho, locked until passphrase, multi-agent council, continuous-learning")
and says "merge with the existing MOON prompt and build what's missing," do it as a
TRUE MERGE, not a replacement:

1. **Read the existing `app/prompts/templates/moon_system.md`** first — preserve its
   identity, lock phrase, cyber rules, GitHub tool-feed, smart-build policy.
2. **Audit capability vs code** (as in §K): most named capabilities already exist as real
   modules (39 agents cover the 7 council roles; lock/voice/learning all present). Build
   ONLY the genuinely missing *named* features as real `BaseTool` subclasses:
   - **Model-management tools** (`model_management_tool.py`): `list_available_models`,
     `download_model`, `set_main_model`, `set_agent_model`, `model_info`. Wire
     `set_main_model`/`set_agent_model` to NEW `Orchestrator.set_main_model()` /
     `set_agent_model()` methods (add the override dict `self._agent_model_overrides`).
   - **Continuous-learning tools** (`learning_tool.py`): `learn_topic` / `check_learning_status`
     / `apply_knowledge` / `schedule_auto_learning` — back them with `web_search` +
     `prompt_tuner.record_lesson` + long-term memory. (Returns a `str` — see §B gotcha.)
3. **Reconcile the unlock passphrase SAFELY** — the attached prompt said `love you 3000 moon`
   but the existing working lock uses `MOON love you 3000`. NEVER overwrite the working one
   (could lock the operator out). **Patch `app/brain/lock.py` to accept BOTH phrases**
   (`SessionLock.UNLOCK_PHRASES = [...]`, `observe()` checks `any(ph.lower() in low)`) so
   Psycho is never locked out. Verified: both phrases unlock.
4. **Write the merged prompt** into `moon_system.md` (keep all 14 existing sections + add the
   personality/council/learning sections). Use `write_file` for `.md` (heredocs trip the
   scanner on `&`/URLs — see §host-quirks-2).
5. **Verify**: dual-phrase unlock; import sweep 0 failures; `pytest` green; live boot
   `Connected 39 agent brains`; new tools present in `registry.tool_names` and exercised
   (e.g. `learning.execute(action="learn", topic=...)` stores to memory; `model_management`
   lists local models — and **strip the `ollama list` header row** `NAME` before returning).
See `references/merge_personality_prompt.md`.

### N) GitHub Sync & always-connected deploy — `github_sync` tool + agent (this session)
MOON can safely synchronize the local project with a GitHub repo AND stay
**always connected** to it for autonomous tool/asset pull. Both built as real
`BaseTool` code from the operator's "Fully Automated GitHub Sync & Deployment"
spec (merged into `moon_system.md`).

- `app/tools/github_sync_tool.py` — `GitHubSyncTool` with **two modes**:
  - `mode="sync"`: detect root → init if needed → keep existing `origin` (never
    clobber) → verify reachable → safe `.gitignore` → stage → **unstage any secret
    that slips in** → smart commit → pull --rebase → auto-resolve safe conflicts
    (else pause+explain) → NON-force push → verify → Completion Report.
  - `mode="fetch"`: MOON **autonomously pulls a tool/plugin/skill** from the
    connected repo when a task needs it (always-connected auto-install).
  - **Both auth options**: `auth="pat"` (uses `GITHUB_TOKEN`, never stored in repo
    config) and `auth="gh"` (GitHub CLI). Pauses for approval if neither available.
- Connected repo: `settings.github_repo` (`GITHUB_REPO` in `.env`), default
  `https://github.com/crsuvo100-gif/MOON`. Orchestrator `_auto_acquire_for_task`
  calls `mode="fetch"` when a needed `plugin`/`tool`/`skill` isn't local.
- `github_sync` agent added to `AGENT_DEFS` (now **39 agents**).
- Full recipe, both auth modes, safety guarantees, and pitfalls in
  `references/github_sync.md`.
- **Pitfall — profile vs repo URL:** operator gave `https://github.com/crsuvo100-gif`
  (a *username*). Corrected to `https://github.com/crsuvo100-gif/MOON`, but that
  **404s (repo doesn't exist yet)** — verified via `curl`. MOON pauses gracefully
  on push/pull until the repo exists or a token reveals it's private. **Never
  fabricate a successful push.**
- **Pitfall — tool-registration silent failure:** import line may register but the
  orchestrator *tuple* can drift. Always assert `"github_sync" in
  o._tools._registry.tool_names` after boot + run `make test`.

### N2) Autonomous GitHub tool-feed — `github_feed.py` (self-extending)
MOON stays **always connected** to GitHub and self-extends: when a task needs a
capability she lacks, she pulls from YOUR repo, and if not there, **searches the
public GitHub ecosystem**, pulls the best match, and installs it as a plugin.
Built as real code merged into the existing auto-acquire pipeline (not a separate
program) — the operator's "pull from GitHub and search for tools to install" ask.

- `app/tools/github_feed.py` — functions:
  - `list_repo_tools(repo_url)` — shallow-clones the connected repo and catalogs
    every `plugins/*.py`, `app/tools/*.py`, `skills/*/SKILL.md` (the trusted catalog).
  - `search_github(query, limit=5)` — GitHub **search API**, results ranked by stars.
  - `pull_and_install(repo_full_name, default_branch, keyword, registry)` — shallow-clones
    the public repo, picks the most relevant `.py`, **rejects obviously malicious
    content** (`rm -rf /`, `os.system("rm`, `shutdown`), copies into
    `plugins/generated/`, imports + registers any `BaseTool` subclass live.
  - `feed_for_capability(keyword, registry, repo_url="")` — **YOUR REPO FIRST**, then
    public GitHub search → pull → install → immediately usable. Best-effort / non-destructive.
- **Wiring**: `orchestrator._auto_acquire_for_task` calls `feed_for_capability` when a
  capability is missing (pipeline: catalog → your repo → public GitHub → LLM plugin).
  New `refresh_repo_catalog()` runs at startup to keep the connected repo's tool catalog live.
- **Verify**: `search_github("qr code generator in:name language:python")` → real ranked
  public tools (stars 95/58/45); `list_repo_tools("git@github.com:crsuvo100-gif/MOON.git")`
  → 33 tools discovered via SSH; `feed_for_capability("qr", reg, repo_url=...)` pulls +
  installs a real qr tool (verified safe: a `qrcode` wrapper). Full recipe + `SEARCH_QUERIES`
  map + malware-rejection regex in `references/github_connect_and_feed.md`.
- **Pitfall**: a pulled repo may have NO `BaseTool` subclass (it's a CLI app) → it's
  saved as an import-only plugin (graceful, NOT a failure). When a pulled repo DOES define
  a `BaseTool`, it registers and becomes directly callable. Never claim install-success
  without checking the registry actually gained a tool (`set(reg.tool_names) - before`).

### N3) Connecting MOON to GitHub (SSH — the working path)
The operator connected via **SSH key** (Option 2): no secret in chat, key stays local.
Verified end-to-end this session (push succeeded `3f6ac51..6f4e155`).

1. Generate key: `ssh-keygen -t ed25519 -C "meow@Meow" -f ~/.ssh/id_ed25519 -N ""`
2. Pin host: `ssh-keyscan -t ed25519,rsa github.com >> ~/.ssh/known_hosts`
3. Paste the **public** key (`cat ~/.ssh/id_ed25519.pub`) into GitHub → Settings →
   SSH and GPG keys → New SSH key. (Private key NEVER leaves the box.)
4. Point git at it: `git config core.sshCommand "ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes"`
5. Switch origin to SSH: `git remote set-url origin "git@github.com:crsuvo100-gif/MOON.git"`
6. Test: `ssh -T git@github.com` → `Hi crsuvo100-gif! You've successfully authenticated`.
7. Push (non-force, as required): `git pull --rebase origin main` (resolve any README
   conflict by keeping MOON's fuller version), `GIT_EDITOR=true git rebase --continue`
   (avoids the editor prompt hanging the command), then `git push -u origin master:main`.
- **PAT gotcha**: a fine-grained PAT whose **Contents** permission was edited *after*
  creation 403s git push with "Write access not granted" even though the API reports
  `permissions.push=true`. **Fix: REGENERATE the token** on GitHub after changing perms.
  Prefer the SSH-key path — it's permanent and needs no token.
- **Token hygiene**: if you ever use a PAT, pass it only via
  `git remote set-url origin "https://x-access-token:TOKEN@github.com/..."` at push time,
  then immediately `git remote set-url origin "https://github.com/crsuvo100-gif/MOON.git"`
  to scrub it from `.git/config`. Verify with `grep -c "x-access-token" .git/config` → `0`.
- Full connect + tool-feed recipe (commands, `SEARCH_QUERIES`, malware regex) in
  `references/github_connect_and_feed.md`.

### N3a) GitHub pre-receive hook: GH001 large-file rejection (caught this session)
A push was **rejected by a pre-receive hook** (NOT a 403 auth error) with:
`remote: error: GH001: Large files detected ... File Telegram/Telegram is 223.29 MB;
this exceeds GitHub's file size limit of 100.00 MB`. Root cause: a stray
**`Telegram/` directory at the repo root** (a 224 MB Telegram *desktop binary* +
`Updater`, not MOON code) got swept into the commit by `git add -A`. Fix, in order:
1. `git ls-files | grep -i "telegram/"` to see what's tracked.
2. `git rm --cached -f "Telegram/Telegram" "Telegram/Updater"` (untrack, keep disk-safe).
3. `rm -f Telegram/Telegram Telegram/Updater && rmdir Telegram 2>/dev/null`.
4. Append `Telegram/` to `.gitignore` so it can never be re-added.
5. `git add -A && git commit --amend -q --no-edit` (drop the blob from the bad commit).
6. Confirm no tracked file >100 MB: `git ls-files -z | xargs -0 -I{} sh -c 'f="{}"; [ -f "$f" ] && du -m "$f"' | awk '$1>100{print "BIG:",$0}'`.
7. `git push origin master:main` now succeeds.
**Pitfall rule:** NEVER `git add -A` blindly on this repo — there is a non-MOON
`Telegram/` binary at the root. Use targeted `git add <paths>` or ensure `.gitignore`
covers it first. A large binary in the tree = hard push rejection even with valid auth.

### P) Build the Web Dashboard (Flask + SocketIO) — `app/dashboard.py` (this session)
`MOON --dashboard` launches a local web UI (`http://127.0.0.1:5000`) with a chat
view, live stream pane, and camera feed. It routes `user_command` through the REAL
orchestrator (no duplicate agent loop). Build gotchas that cost a failed boot:
- **Flask 3.1 requires `allow_unsafe_werkzeug=True`** on `socketio.run(...)` or it
  raises `RuntimeError: The Werkzeug web server is not designed to run in production`.
  Pass `allow_unsafe_werkzeug=True` in the `socketio.run(...)` call (dev server only).
- **`flask`/`flask-socketio` must be in `requirements.txt`** and installed in the
  project venv (`env -u PYTHONPATH .venv/bin/pip install flask flask-socketio`) or
  `app/dashboard` fails to import and breaks the whole import sweep.
- **Lazy-import flask inside `create_dashboard()`** (not at module top) so the
  import sweep stays green on hosts without flask; raise a clear `RuntimeError` if
  missing. Same for `cv2` inside `video_feed` (return 503 "camera/unavailable" if absent).
- **Run the dashboard's async entry through a fresh event loop**: create
  `asyncio.new_event_loop()` + a daemon thread running `loop.run_forever()`, and route
  socket commands via `asyncio.run_coroutine_threadsafe(run_fn(text), loop)`. The
  `run_fn` wraps `Orchestrator.run_task(Task.create(prompt, agent_name="auto"))`.
- **Wiring**: add a `sub.add_parser("dashboard")` in `main.py`; `_run_dashboard()`
  sets up the orchestrator, defines `async def run_fn(prompt)`, and calls
  `run_dashboard(run_fn)`.
- **Verify live**: `fuser -k 5000/tcp; (python main.py dashboard &); sleep 12;
  curl -s localhost:5000/ | head -c 60` → HTML; `ss -ltnp | grep 5000` → LISTEN;
  `/video_feed` → 503 (no cam) is the GRACEFUL expected result on a headless box.
  Full recipe in `references/dashboard.md`.

### Q) MOON's own terminal interface — avatar = her BODY, wake word + self-unlock (this session)
A self-contained terminal UI where MOON's animated avatar sits centered and acts as
her "body": it reacts to her live workflow and she wakes / unlocks via phrases.
ADDITIVE ONLY — does NOT touch any existing MOON module.

- `app/terminal_interface.py` — `FastAPI` app on `:8777`. `GET /` serves
  `web/moon_terminal.html`; `GET /avatar.svg` (or `/avatar.gif` if the operator drops
  one in) serves the avatar; `WebSocket /ws` connects to the REAL `Orchestrator` (lazy
  singleton, env-decontaminated) and streams MOON's answer word-by-word.
- `web/moon_terminal.html` — single-file UI (NO npm build needed). Centered animated
  avatar (rings + orbiting-nodes canvas + `avatar.svg`), chat with live streaming, side
  panels, and a live **WORKFLOW** ticker. The avatar reacts via `body[data-moon]` CSS to
  states `idle/thinking/working/speaking/locked/listening`.
- `web/avatar.svg` — generated animated neon MOON avatar so it works with zero assets;
  operator can drop `web/avatar.gif` to override.
- Wiring: `main.py` gained a `moon terminal` subcommand → `uvicorn app.terminal_interface:app --port 8777`.

**HUD `/status` route + Quick-Action `run` action (added this session):**
- `GET /status` returns REAL MOON telemetry for the HUD. Current contract (verify against
  `app/terminal_interface.py:_moon_status`): `version`, `model` (`orch._settings.model_name`),
  `strong_model` (`strong_model_name`), `locked` (`orch._lock.locked`),
  `agents` (count — `orch._agents` is a **dict**, not a list: use `len()` then
  `[getattr(v,"name",k) for k,v in ags.items()]`), `agent_list` (names), `tools` +
  `n_tools` (traverse `orch._tools._registry.tool_names`), `memory` (`{episodic,
  long_term, short_term, vector, kb_docs}` — read `orch._memory._ltm/_stm/episodic/_kb`
  + `_kb._store._items`), `system` (host metrics — see `references/terminal_real_metrics.md`:
  CPU% from `/proc/loadavg` load1/ncpu, RAM% + used/total MB from `/proc/meminfo`,
  net MB from `/proc/net/dev`, temp °C from `/sys/class/thermal/thermal_zone0/temp`),
  `uptime` (float seconds from `/proc/uptime`), `uptime_fmt` (e.g. `1d 2h 8m`),
  `knowledge` (`{graph, doc_store, rt, context}` derived from `kb_docs` + agent count),
  `system.gpu` (0 on CPU-only box — report honestly, do NOT fake GPU%), `system.load`,
  and `pipeline` (8 real steps: `input/memory/knowledge/reasoning/planner/tools/execution/
  verify`, each with `active` from real state). The HTML `apply()` fills every panel
  (memory bars, system gauges incl. GPU/load, knowledge bars, agent roster, lock state,
  model) from this. The JS also sends `status` every 5 s as a heartbeat so the HUD stays live.
- **Real bug fixed:** `_moon_status()` first read `orch._tools.tool_names`, which
  raised AttributeError (`ToolManager` has no `tool_names`) → `n_tools=0`. Tools live at
  `orch._tools._registry.tool_names`. Correct path:
  `reg = getattr(orch._tools, "_registry", None); tools = list(reg.tool_names) if reg
  and hasattr(reg, "tool_names") else []`. Always traverse `_registry`.
- WS actions added (besides `wake`/`send_message`): `status` (pushes HUD data) and
  `run` (Quick Action buttons: `SYSTEM STATUS`, `RUN DIAGNOSTICS`, `ACTIVE WORKFLOW`,
  `MEMORY SEARCH`, `KNOWLEDGE BASE`, `STOP TASKS`). `run` routes `command` through
  `run_task(..., on_event=stream_event)` — so every button drives MOON's REAL brain, not
  a stub. The HTML `runAction(cmd)` / `quick(t)` helpers send these.
- The terminal UI was rebuilt to match the operator's "MOON Neural Command Center"
  screenshot: header (logo/title/clock/status), left column (Sensory Input, Memory
  Core, Knowledge Base, System Overview), center (avatar body + state-icon row
  idle→speaking + waveform + chat), right column (Cognition Core, 8-step Workflow
  Process grid, Environment, Live Events), 9-tab nav, footer deck (Voice Control +
  Mute, Command Palette quick tags, 6 Quick Action buttons, MOON AI Agent panel).
  Every panel/button is wired to real data or a real `run`/`send_message` call.

**Wake word vs unlock (lock logic in `app/brain/lock.py`):**
- `WAKE_WORD = "moon"`. Saying "Moon" → `hear()` returns `kind:"wake"` (avatar opens
  eyes / listening state) and does NOT unlock. The terminal sends a `wake` WS action
  that only flips the avatar to listening — it never calls `observe()`.
- `"love you 3000 Moon"` (case-insensitive) is already in `UNLOCK_PHRASES`, so it
  unlocks MOON *herself* inside the orchestrator lock during `run_task`. The terminal's
  `send_message` path routes through `run_task`, which unlocks when the phrase is seen.
- Both `"MOON love you 3000"` and `"love you 3000 moon"` unlock (dual phrase — operator
  is never locked out). Wake ≠ unlock: a bare "Moon" must NOT unlock.

**Workflow streaming (`on_event` callback) — the avatar shows her real work:**
- `Orchestrator.run_task(task, on_event=None)` and `_run_cognition_loop(task, agent,
  on_event=None)` now ACCEPT an async callback and EMIT real stages behind `if on_event`:
  `routing` (after intent), `thinking` (memory recall + context build), `tool_call`
  (per tool call, with the tool name), `reflection`, `consistency`. Purely additive — when
  `on_event is None`, behavior is unchanged (no new cost for existing callers).
- The terminal passes `async def stream_event(ev): ws.send_json({"type":"workflow",
  "stage":ev["stage"],"detail":ev.get("detail","")})` and also emits `speaking`/`locked`
  states. The HTML maps stages → avatar body language (thinking/working/speaking/locked).
- **Verify the `on_event` plumbing with a STUBBED cognition loop, not the live model.**
  The 0.6B CPU model takes >180 s to emit free-form text, so a live WS round-trip times
  out under normal `terminal` timeouts. Instead: `o._run_cognition_loop = async def
  fake_cog(task, agent, on_event=None): if on_event: await on_event({"stage":"thinking",
  ...}); await on_event({"stage":"tool_call", ...}); return "fixed answer", 1`. Then
  `run_task(t, on_event=cb)` and assert the captured stages == `[routing, thinking,
  tool_call, reflection]`. This deterministically proves the streaming without model latency.
  Also assert a locked task is gated (result contains "locked") before unlock.

**Verify live (boot):**
`fuser -k 8777/tcp; (env -u PYTHONPATH .venv/bin/python -m uvicorn app.terminal_interface:app --host 127.0.0.1 --port 8777 &); sleep 10; curl -s -o /dev/null -w '%{http_code}\n' localhost:8777/` → `200`; `curl localhost:8777/avatar.svg` → `200`. Then WS: `wake` →
`kind:wake` (still locked); `love you 3000 Moon` → unlock; real question → stages
`routing→thinking→...→speaking` + streamed answer.
- **Pitfall:** launching the server with `&` inside one `terminal()` call trips the
  long-lived-server heuristic. Start it with `terminal(background=true)`, then exercise
  the WS in a follow-up call. Never wrap the uvicorn launch in `asyncio.run` (§host-quirk-3).
- **`main.py start` exit- notice is NOT a server crash (recurring confusion this session).**
  `main.py start` does `subprocess.run([sys.executable, "-m", "uvicorn", ...])` — the
  MANAGED wrapper process (`proc_XXX`) exits once it spawns uvicorn, but the **uvicorn
  child keeps serving independently** (owned by a different pid, still bound to 8777).
  When the harness reports "Background process proc_XXX exited", always VERIFY the real
  server: `ss -ltnp | grep ':8777'` (or `curl :8777/`) before concluding anything broke.
  In this session the parent wrapper exited repeatedly while MOON stayed live — the notice
  was noise. Only restart if the port is actually FREE.
- **Pitfall:** the live free-form answer can exceed 180 s on this CPU box — keep live
  WS checks SHORT (e.g. unlock + a one-line factual question) or rely on the stubbed test.
- **Pitfall — MATCHING A MOCKUP MEANS MATCHING THE TEXTURE, NOT JUST THE LAYOUT.** The
  operator pasted a cinematic "MOON Neural Command Center" concept-art screenshot and
  rejected the first terminal build because it was a *functional but flat* dashboard
  (plain panels, no glass, no 3D brain, no particle web, no neon bloom). The layout
  matched; the *feel* didn't. Fix that landed (commit `4db9c45`) and the reusable recipe
  are in `references/terminal_cinematic.md`. Key techniques: (a) **glassmorphism** via
  `backdrop-filter: blur()` + translucent `rgba()` bg + neon `box-shadow` glow + inner
  `inset` bloom; (b) **rotating 3D wireframe brain** using nested `transform-style:
  preserve-3d` divs (`@keyframes spin { rotateY(0)→rotateY(360deg) }`); (c) **neural synapse
  particle web** on a full-bleed `<canvas>` (glowing nodes that drift + draw purple
  lines when within ~120px — star-map aesthetic); (d) **holographic avatar halo**
  (counter-rotating rings) + glass face-tracking dots + a scanning line; (e) **circular
  holographic gauges** via `conic-gradient(var(--cyan) var(--v), transparent)` with an
  inner `::before` disc; (f) **bloom/scanline** background via layered `radial-gradient`
  + `repeating-linear-gradient`. Keep ALL panels/buttons wired to the same WS actions
  (status/run/send_message/wake) — visual rebuild must not drop functionality.
- **Pitfall — can't synthesize the photoreal face:** the reference's AI face is
generative art; pure CSS can't replicate it. The honest move is the neon SVG avatar
(`/avatar.svg`) as the central anchor + rich holographic dressing, and tell the
operator they can drop `web/avatar.gif` (or any face image) to override. Never claim a
face was generated when it wasn't.
- **Pitfall — the avatar MUST NOT depend on WebGL (root cause of a "no face / blob"
  regression, fixed `88872af`).** The 3D face renders via Three.js/WebGL. On the
  operator's browser WebGL silently failed → the face didn't draw and he saw the bare
  constellation/radar blob (looked broken). Fix: `#avatarImg` (`web/avatar.svg`, a
  holographic female face) is the ALWAYS-ON base layer (`z-index:2; display:block`);
  `#face3d` (WebGL) sits ON TOP (`z-index:3`, transparent where undrawn). If WebGL works
  the 3D enhances; if it FAILS the face still shows. NEVER set `#avatarImg{display:none}`
  as default again — that caused the regression. Decisive verify: render with
  `--disable-webgl` and confirm a face is visible (recipe in
  `references/terminal_avatar_webgl_fallback.md`).
- **D-ID share link = NOT extractable code (recurring operator ask).** When the operator
  pastes a `studio.d-id.com/agents/share?...` link and says "build this for MOON," do NOT
  pretend to clone it — it's a hosted SaaS talking-face on D-ID's cloud; context extraction
  returns nothing. The right move is **Option B**: upgrade MOON's OWN local 3D avatar to
  D-ID-level polish (holographic rings + live RMS waveform + brainwave sync + environment
  globe), fully offline, no key/cost. Embedding D-ID (Option A/C) is only if the operator
  explicitly accepts the cloud dependency. Full recipe + the honesty caveat in
  `references/terminal_did_digital_human.md`.
- **OPERATOR PREFERENCE — "match MY mockup, don't invent your own, and don't polish
  cosmetics instead of function" (FIRST-CLASS correction this session).** The operator
  pasted a "MOON Neural Command Center" screenshot and, across MANY turns, rejected
  builds that (a) invented a different layout than the reference, or (b) over-invested in
  the avatar *face* while the panels didn't match. Hard rules for any MOON UI work:
  1. **Replicate the reference panel-for-panel** with the SAME titles/labels/order before
     adding anything. His reference = header (logo/title/clock/ONLINE) + LEFT: Sensory
     Input, Memory Core (bars + ENTRIES), Voice Control (sphere) + CENTER: neural
     constellation + "MOON IS ACTIVE AND AWARE" + STATE + 5 state buttons (IDLE/LISTEN/
     THINK/EXEC/SPEAK) + flowing curves + chat + Command Palette + RIGHT: Cognition Core
     (RSON/PLAN/GOAL/DECIS/EMOT/LEARN gauges), COMMAND input with DASHBOARD..NETWORK tab
     nav, Quick Actions (6 buttons), MOON AI Agent, Live Events + footer wake/unlock hint.
  2. **"Cool" = cinematic layer, not a different structure.** Keep glassmorphism, neural
     constellation (synapse canvas), scanlines, monospace HUD, neon bloom — but keep them
     wrapped AROUND the reference layout. The constellation/avatar sits at center as the
     visual anchor, exactly like the screenshot.
  3. **Function before face.** Wire every panel to REAL data (the `/status` route) and
     every button to a REAL WS action (status/run/send_message/wake/diagnostics/
     memory_search/knowledge) FIRST. Cosmetic avatar polish is the LAST thing, not the
     first; if you find yourself tuning the avatar face while panels still show fake bars,
     you are doing it in the wrong order. The operator explicitly said "check any skin and
     meet each entity… just like the didn't not look like" — i.e. every named panel must
     exist and look right before any face work.
  4. **When unsure what entity/panel they mean, ask or re-read the screenshot** — do not
     guess a layout. He will reject it.
  5. **EXACTLY ONE command input.** The reference has a single `MOON >` field in the
     bottom COMMAND PALETTE (tabs above it, chips below). Do NOT add a second input
     (e.g. a center chat composer AND a right "Command" panel) — the operator rejects
     "command palette show double." If you need a transcript view, make it display-only
     (no `<input>`). Concretely: the bottom `#cp` is the sole entry; remove any `#cmd2`
     / center `#input` duplicates.
  6. **Voice must be REAL, not cosmetic.** A MUTE button that only logs text is a fake.
     Wire Voice Control to MOON's real female TTS (`app/voice.Voice`, espeak `f5`): when
     MODE=AUTO, stream each reply as base64 WAV over the WS (`type:"audio"`) and play it
     in the browser via an `Audio` element; MUTE sends a real `mute`/`unmute` WS action
     and the server SKIPS TTS when muted. Verify: a live reply yields a valid RIFF WAV
     (~250 KB); after mute, 0 audio messages arrive. (espeak is at `/usr/bin/espeak`.)
  7. **Locked MOON must still REPLY.** `Orchestrator.run_task` short-circuits when
     `lock.locked` and returns ONLY the unlock prompt — so a locked terminal went silent
     ("did not reply to me"). Fix in the WS `send_message` handler: when locked, call
     `orch.quick_reply(text)` (her real brain, no tool execution) instead of `run_task`;
     keep `run_task` for when unlocked (active ops still gated). This honors the
     authorization boundary (she talks, but won't act) while ending the silence.
  8. **Sensory Input rows are driven by REAL backend flags, NOT hardcoded STANDBY.**
     The `/status` payload includes `sensors.vision` / `sensors.file` (backend computes them
     as `any(n in tools for n in ("image_processing","ocr","vision"))` etc.), plus
     `sensors.voice/text/system` (always True). The HTML `apply()` MUST map every channel
     from these flags: `setSens('senVision', sn.vision); setSens('senFile', sn.file); ...`
     (VOICE/TEXT/SYSTEM use `sn.voice`/`sn.text`/`sn.system` the same way). **Do NOT hardcode
     `false`** for VISION/FILE — that was a real bug this session (`aa13514`): the frontend
     hardcoded `setSens('senVision',false)` so they were STUCK on STANDBY even though the
     backend reported `vision:true, file:true`, and the operator flagged it ("why show
     STANDBY please fix it") and accepted the truthful fix. Rule: when the backend already
     reports a capability flag, the UI must reflect it. If a sensor has no real backend flag,
     derive it from observable state (like EMOT) — never display a static STANDBY that
     contradicts the backend's own status report. Verify: `GET /status` → `sensors.vision`
     and `sensors.file` truthfully true/false; the served HTML `apply()` uses `sn.vision`/
     `sn.file` (not literals).
  9. **CONNECT AGENTS surfaces the 39 brains.** Add a `connect_agents` WS action (and a
     quick button) that lists `orch._agents` names — proves all specialist brains are
     wired to the main cortex. The Agent Roster panel is populated from `status.agent_list`.
  10. **COMPLETE the function matrix — every backend action has a button, every tab is
      wired, and EMOT is LIVE (not hardcoded).** The operator's "deeply re-check and fix
      all function… have option button" request means: audit the WS handler, list every
      `action`, and guarantee each has a UI trigger; audit the tab nav and guarantee each
      tab maps to a real action. This session closed the gaps:
      - **Buttons for every action.** Quick Actions now cover ALL functions:
        `WAKE MOON`→`wake`, `SYSTEM STATUS`, `RUN DIAGNOSTICS`→`diagnostics`,
        `ACTIVE WORKFLOW`, `MEMORY SEARCH`→`memory_search`, `KNOWLEDGE BASE`→`knowledge`,
        `CONNECT AGENTS`→`connect_agents`, `LIST TOOLS`→`list_tools` (NEW),
        `STOP TASKS`→`stop` (NEW). `send_message` is the chat input; `mute`/`unmute` is the
        Voice MUTE toggle.
      - **NEW backend actions added** (all real, no stubs):
        * `stop` — sets module `_stop_requested` flag + MOON acknowledges via
          `quick_reply`. HONEST LIMITATION: the orchestrator is single-task and runs
          synchronously, so `stop` is meaningful BETWEEN turns (prevents the next run), not
          a mid-flight interrupt. State this honestly; never claim a hard cancel that
          isn't implemented.
        * `list_tools` — enumerates `orch._tools._registry.tool_names` (→ "N tools
          registered: …"). Prove the tool registry is reachable from the UI.
        * `network` — reads `_system_metrics()` and reports net MB / CPU% / RAM% / temp.
        * `settings` — dumps `orch._settings` (model, strong model, base URL, lock).
      - **All 9 tab-nav items wired** to real actions (was only 4): DIAGNOSTICS/MEMORY/
        KNOWLEDGE/SECURITY → existing handlers; TOOLS→`list_tools`, NETWORK→`network`,
        SETTINGS→`settings`, AUTOMATION→`run`. The `switchTab(name)` JS maps uppercase
        tab label → action and sends it.
      - **Sensory VISION/FILE fix (real bug, `aa13514`).** The `/status` payload already
        carries truthful `sensors.vision` / `sensors.file` flags (computed from whether the
        vision/file tools are registered). The HTML `apply()` MUST drive the rows from them
        (`setSens('senVision', sn.vision); setSens('senFile', sn.file)`) — NOT hardcoded
        `false`. A prior version hardcoded `setSens('senVision',false)` so they were stuck
        STANDBY; the operator flagged it and the truthful fix was accepted. Rule: when the
        backend reports a capability flag, reflect it. (Contrast with EMOT below, which has
        NO real signal and must be derived.)
      - **EMOT fix (no mood model exists).** MOON has NO emotion/sentiment subsystem
        (grep `emotion|mood|sentiment` finds nothing). The Cognition Core EMOT gauge was
        hardcoded 60%/CALM — a fake. Fix: derive a live mood from REAL signals via
        `_current_emotion(locked)` returning `{value, label}`:
        `locked → {45,"CALM"}`, `recent error (_last_error) → {30,"ALERT"}`,
        `else → {72,"ENGAGED"}`. Add `emotion` to `_moon_status`; set `_last_error=True`
        in the `send_message`/`run` `except` blocks; HTML `apply()` sets the EMOT gauge
        `--v` + label from `s.emotion`. Honest rule: if there's no real signal, derive from
        observable state — never display a static "feel" that implies a model MOON lacks.
      - **`runAction(c)` routing:** map button phrases → actions with regex
        (`/^wake/`, `/stop/`, `/connect.*agent/`, `/list.*tool/`); everything else → `run`.
      - **Deep re-check procedure for the terminal** (repeat after any UI change):
        (1) `curl :8777/` and grep for every expected button label (assert all present);
        (2) `curl :8777/status` and assert `emotion` + `sensors` + `voice` present;
        (3) open ONE WS, fire EVERY action (`wake`,`diagnostics`,`memory_search`,
        `knowledge`,`connect_agents`,`list_tools`,`network`,`settings`,`stop`) and assert
        each returns non-empty real text (or a valid `wake`/`status` envelope); (4)
        `make test` 15/15; (5) commit + push. This caught the missing buttons + dead tabs.

**Concrete terminal wiring shipped this session (reusable):**
  - Real metrics + `sensors` + `voice` already in `_moon_status` (see §Q HUD contract).
  - Voice engine in `app/terminal_interface.py`: module-level `_voice`/`_voice_muted`,
    `_get_voice()` lazy-imports `app.voice.Voice`, `_speak(text)` returns base64 WAV or
    `None` (muted/unavailable). Call `_speak(answer)` after streaming chunks in BOTH the
    `send_message` and `run` handlers; emit `{"type":"audio","format":"wav","data":b64}`.
  - **Global-in-function gotcha:** if a `ws_endpoint` handler both reads AND assigns a
    module global (`_voice_muted`), declare `global _voice_muted` ONCE at the TOP of the
    function (after `await ws.accept()`), and do NOT re-declare it inside the `elif`
    branch — a nested `global` after a read triggers `SyntaxError: name used prior to
    global declaration`. Also init `t0 = 0.0` before the branch so Pyright doesn't flag
    `possibly unbound`.

  - **Voice mode must actually OUTPUT audio AND accept INPUT (real bugs fixed `cd07cfb`).**
    Two frontend bugs made "voice mode did not work": (1) `playAudio()` built the
    `AudioContext` lazily inside playback, so the browser autoplay policy left it
    `suspended` and silently dropped TTS — fix by `resume()`-ing the context on the first
    page `click`/`keydown` and retrying `a.play()`. (2) There was **no voice-input path**
    at all (mic icon was decorative) — fix by a `TALK` push-to-talk button using the
    browser **Web Speech API**, feeding recognized speech to MOON like typed text. (3)
    Model stalls hung the whole WS session — `LLMService.complete()` now bounds each
    attempt to 45s + 1 retry. Full recipe + live `AUDIO_PRESENT` verifier in
    `references/terminal_voice_mode.md`. When voice "doesn't work", ALWAYS first check
    whether Ollama itself is responsive (`curl /v1/chat/completions`) — a wedged worker
    is the usual culprit, not the UI. **Diagnosis path + recovery (NO sudo needed) in
    `references/ollama_recovery.md`** — the definitive fix this session. Key facts:
    Ollama runs as a **systemd service** (`ollama.service`) with a worker owned by the
    `ollama` USER (not `meow`), so `kill -9 <pid>` returns `Operation not permitted` —
    you CANNOT kill it from the unprivileged shell, and there is no passwordless sudo here.
    A wedged worker makes `/v1/chat/completions` hang (code 000) even though `/api/tags`
    and `/api/ps` still respond 200. Recovery is via the **`ollama` CLI** (talks to the
    service as the service's own user): `ollama stop <model>` unloads the wedged worker,
    then the next request (or `ollama run <model> "hi"`) reloads it fresh — inference
    resumes. If `ollama run` itself blocks, the service is wedged hard and needs
    `systemctl restart ollama.service` (sudo). On a fresh reload, `qwen3:0.6b` returns in
    ~10-20s and the WS voice round-trip emits the `audio` frame again.
    - **Voice PANEL border/layout (fixed `fe84d84`).** `.dock-voice` was `width:140px`
      holding the icon + MUTE + TALK, so the buttons overflowed/clipped and collided with
      the panel's own 1px border (cramped). Fix: widen to `200px`, give `.dock-voice .qa`
      its own `flex:1 1 0; border:1px solid var(--edge); border-radius:7px` (no
      collision with the panel border), and add `.dock-voice .qa.on` (mic LISTENING) a
      glowing pink border + `animation:pulse` so the recording state is obvious. Rule:
      size the voice panel for icon + N buttons and give each button its own border
      rather than relying on the panel's border. Verify the rendered dock with a headless
      Chromium crop of the bottom-left (see `references/terminal_verify_live.md`) — vision
      confirmed MUTE/TALK fully visible, no clipping.
  - Locked-reply path: `if orch._lock.locked: answer = await orch.quick_reply(text)` else
    `run_task(...)`. Add `t0=0.0` at top; set `elapsed` to 0.0 when locked.
  - `connect_agents` action: `ags = getattr(orch,"_agents",{}); names=[getattr(v,"name",k)
    for k,v in ags.items()];` stream `f"Connected {len(names)} agent brains..."`.
  - **Ollama cold-load pitfall (CPU host):** the FIRST LLM call after a fresh boot
    cold-loads the model and can take 30 s+. WS client timeouts must be ≥90 s, or warm
    the model first with `curl -s -m 40 http://127.0.0.1:11434/v1/chat/completions -d
    '{"model":"qwen3:0.6b","messages":[{"role":"user","content":"hi"}],"stream":false}'`.
    A 30 s client timeout on the first call is a FALSE failure — the code path is fine.
  - **JS float formatting (real bug, fixed this session):** `apply()` computed
    `100 - (sy.ram_pct||0)` for the ENVIRONMENT energy bar; `100 - 85.4` is
    `14.600000000000001` in JS, which stringifies to `14.5999999` (ugly in the UI).
    Always run the result through `.toFixed(1)`: `const envPct = Math.max(0, Math.min(100,
    100 - (sy.ram_pct||0))); eet.textContent = envPct.toFixed(1) + '%'`. Any numeric %
    derived by subtraction in the HUD should be `.toFixed(1)`-safe.
  - **Reusable live-function verifier:** there is a ready-made sweep script that fires
    EVERY WS action handler and asserts none crash — `scripts/terminal_ws_sweep.py`
    (run `env -u PYTHONPATH .venv/bin/python scripts/terminal_ws_sweep.py` with the server
    up). Use it as the terminal-equivalent of `make test` whenever you add/change a handler.

    **Reusable live-function verifier (`scripts/terminal_ws_sweep.py`):** fires EVERY WS
    action handler against a live terminal and asserts none crash — run it as the
    terminal-equivalent of `make test` after any handler change (with the server up):
    `env -u PYTHONPATH .venv/bin/python scripts/terminal_ws_sweep.py`. Keep its `ACTIONS`
    list in sync with `app/terminal_interface.py`.

    **VERIFY THE LIVE BROWSER — `pytest` does NOT run the UI JS (FIRST-CLASS lesson this session):**
    `make test` / `pytest` only exercises the Python backend. It does **NOT** execute the
    browser JS in `web/moon_terminal.html`, so these failures pass tests while the UI is
    silently dead. Always run a headless-CDP check after any HTML/JS edit (recipe:
    `references/terminal_verify_live.md`):
    - **Referenced-but-undefined function.** A function called in `apply()` (or any handler)
      but never defined -> `ReferenceError` on EVERY `/status` reply -> `apply()` aborts
      after the Sensor block -> all bars/gauges stay `0%`. Real bug this session: `setSens`
      was missing. **Always** run `node --check` on the extracted inline `<script>` AND a
      CDP `Runtime.exceptionThrown` capture after any JS edit.
    - **Duplicate `const` in same scope** -> `SyntaxError` that kills the WHOLE script
      (every panel dead). Real bug this session: two `const eg=` in `apply()`.
    - **Pitfall — Rogue server squatting `:8777`.** Another project's process (e.g.
      `/home/meow/project/terminal/server.py`) bound 8777 and served a 959-byte D-ID stub,
      so every render showed the WRONG page. Always `curl :8777/` and assert `wc -c` ~ 56 KB
      + title "MOON Neural Command Center" before trusting any render. **Definitive kill
      (supervisor-aware):** the stub is RESPAWNED by a supervisor `launch.py` (pid under
      `/home/meow/project/terminal/`) started by systemd user unit `moon-avatar.service`, so
      a bare `fuser -k 8777/tcp` only kills it once before it re-execs. The kill sequence:
      `systemctl --user disable --now moon-avatar.service` (stops respawning) →
      `kill -9 <launch.py pid>` (SIGTERM may be ignored / re-exec'd) → `fuser -k 8777/tcp`
      → `ss -ltnp | grep ':8777' || echo FREE`. THEN start MOON. The operator confirmed the
      D-ID project is retired, so MOON owns 8777. (Full recipe: `references/ci_install_verify.md` §4.)
    - **900px dock-clip root cause:** `.moon-root` has **5 children** (`.hdr`, `.body`,
      `.tabs.nav`, `.dock`, `.foot`) — the nav bar is the 3rd. A 4-row layout forgets it,
      leaving a phantom "41px gap" that pushes the footer 22px past the fold. Use
      `display:grid; grid-template-rows:auto 1fr auto auto auto` + `.moon-root>.body{min-height:0}`
      so the body row shrinks and dock/footer are pinned. Re-assert `footBottom <= 900` via
      `Emulation.setDeviceMetricsOverride` after any layout edit.
    - **Vision misreads below-the-fold panels as "missing".** Confirm with **DOM rects**, not
      vision prose.

    **Animated 3D human-face avatar (Three.js, offline-vendored) — this session (`20aab95`):**
    The operator wanted the centered avatar to be a REAL animated 3D human face with
    interaction (breathing, blink, lip-sync to MOON's actual voice, react to wake/unlock/lock).
    Pure CSS can't do this (see §Q pitfall "can't synthesize the photoreal face") — but a
    self-contained **WebGL face from primitive meshes** CAN, with zero external assets, and runs
    offline. Concrete recipe in `references/terminal_3d_avatar.md`.

    - **Vendor Three.js locally (offline / any machine).** Download once to `web/three.min.js`
    (`curl -s -o web/three.min.js https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js`;
    r128 = legacy UMD global `THREE`, ~603 KB; a 2nd-gen ES-module build will NOT expose the global).
    Add a FastAPI route `GET /three.min.js` returning `FileResponse(WEB_DIR/'three.min.js')` so the
    terminal serves it (no CDN at runtime). Confirm `git check-ignore` does NOT list it (track it).
    `node -e "require('./web/three.min.js')"` should print "three loads OK".
    - **Build the face from primitives** (no GLTF/asset): `SphereGeometry` skin + jaw + hair cap + eye
    groups (white + iris + pupil) + eyelid caps (for blink) + `ConeGeometry` nose + `TorusGeometry`
    mouth (squash Y for talking) + a translucent `SphereGeometry` aura. `MeshStandardMaterial` +
    `AmbientLight` + two `PointLight`s (key/rim). `requestAnimationFrame` loop drives breathing
    (`sin(t*1.3)` on head y/scale), idle head sway, blink timer, and mouth-open amount.
    - **State reaction (real, not cosmetic):** expose `window.setMoonState(s)` + `window.setMouthOpen(v)`
    from the IIFE; the existing `setMoon(s)` calls `setMoonState(s)` so the face changes color/aura per
    state (idle=cyan, listening=amber, thinking=purple, speaking=green, working=magenta, locked=red).
    This reuses the SAME state machine the SVG avatar uses — face + state stay in sync.
    - **REAL lip-sync (audio-reactive, not faked):** in `playAudio(b64,fmt)`, decode the WAV, create a
    `MediaElementSource` -> `AnalyserNode` (`fftSize=256`) -> destination, and in a `requestAnimationFrame`
    loop read `getByteTimeDomainData`, compute RMS, and call `setMouthOpen(min(1, rms*3))`. Mouth opens
    with MOON's ACTUAL voice amplitude and closes on `onended`. Genuine audio analysis.
    - **Offline-safe fallback:** wrap the IIFE in `if(typeof THREE==='undefined'){return;}` so if the lib
    fails to load, the SVG avatar (`/avatar.svg`) still shows. Keep `<img id="avatarImg">` behind
    `<canvas id="face3d">` as the fallback layer.
    - **Validate before push (harness can't render WebGL):** the face only proves itself in a real
    browser, so pre-verify statically: (1) `GET /three.min.js` -> 200 + size; (2) extract each inline
    `<script>` and run `node --check` (the face-engine block must check clean — a stray `</script>` in
    the slice causes a false "Unexpected token '<'"); (3) `curl :8777/ | grep -oE
    'face3d|three.min.js|setMoonState|setMouthOpen'` -> all present; (4) `make test` 15/15.
    - **Honest limit:** you cannot screenshot a WebGL render from this terminal. Say so; the
    asset/route/syntax/reference path is fully verified and an SVG fallback covers WebGL-less browsers.
    - **Add the `references/terminal_3d_avatar.md` support file** (build + verification recipe) and a
    pointer line below. D-ID "digital human" reference build (rings + live RMS waveform + brainwave
    sync + environment globe, all real-data) + honesty-audit rule: `references/terminal_did_digital_human.md`.

    **Responsive across ALL displays (phone → 4K) — this session (`402c4da`):**
    The operator's "make the terminal compatible with all machine displays" ask.
    Responsive = CSS-only, never drop a button or WS action. Concrete recipe in
    `references/terminal_responsive.md`.
    - **Fluid face/avatar:** `width:min(320px,72vw)` etc. + the WebGL engine must size
      its drawing buffer to the canvas's real client rect each frame (`sizeFace()` →
      `cam.aspect` + `renderer.setSize`), else a fixed 320×320 buffer distorts under CSS.
    - **5 media-query blocks:** `>=1800px` (wider cols + bigger face for 4K),
      `<=1100px` (narrow cols), `<=860px` (flip the 3-col row into a STACKED column,
      page scrolls instead of `overflow:hidden`, face-first via `.center{order:-1}`),
      `<=560px` (phone: centered header, tighter text), `<=380px` (tiny phone).
    - **Headless verification is possible HERE:** `/usr/bin/chromium` exists, so
      actually RENDER the live UI at 375/834/1280/1920 via
      `chromium --headless --no-sandbox --disable-gpu --window-size=W,H --virtual-time-budget=6000
      --screenshot=/tmp/shots/moon_W.png http://127.0.0.1:8777/` and `vision_analyze`
      each shot for (no overflow / layout adapted / face present). Don't just eyeball CSS.
    - **Pitfall — headless WebGL:** `--disable-gpu` may not init WebGL, so the 3D face
      can be ABSENT in the screenshot — the SVG fallback shows instead. Verify the SVG
      fallback + responsive layout; state honestly you couldn't confirm WebGL in headless.
    - **Pitfall:** after responsive edits, re-run the function-matrix deep check — the
      `@media` blocks must not hide `.qa` buttons or `#cp` (grep served HTML `id="cp"` = 1).

    **Single terminal now (`:8000` REMOVED) — commit `eed2e67`:** the old Neural Brain
    Command Center (`app/api/main.py` → `:8000`, `web/moon_brain.html`, `web/galaxy.html`)
    was DELETED; `main.py start`/`terminal` both launch ONLY the MOON terminal on `:8777`.
    There is exactly ONE terminal UI. When the operator says "remove the old terminal / two
    terminals", the truth is usually: (a) the SAME file is open in two EDITOR TABS (no code
    fix — close a tab), (b) `app/tools/terminal.py` is MOON's `TerminalTool` shell-exec
    CAPABILITY (imported by the orchestrator, `from app.tools.terminal import TerminalTool`)
    — NOT a UI, never remove it, or (c) a stray unreferenced dir like `./Terminal/` (safe to
    delete after confirming no references). Verify with `find . -iname '*terminal*' -not
    -path './.venv/*'` + `git ls-files | grep -i terminal` BEFORE deleting anything.

    **Dashboard clipping on short viewports (this session):** a 3-column dashboard overflowed
    common laptop heights with hidden scrollbars, looking "broken / panels cut off". Fix that
    shipped: moved Quick Actions (all 9) + Voice Control into the BOTTOM Command Palette as a
    2-column `.botrow` so the RIGHT column holds Cognition Core + MOON AI Agent + ENVIRONMENT
    (ENVIRONMENT added later as a 3rd right panel for the D-ID-style "digital human" look).
    Added thin visible scrollbars + a short-height fallback `@media (max-height:900px){
    .moon-root{height:auto;min-height:100vh;overflow:auto} .col,.center{overflow:visible} }`
    (bumped from 800→900 this session) so short screens scroll the WHOLE page (nothing silently
    lost). The Environment panel (globe/temp/energy/nodes) must stay fully visible — verify with
    headless Chromium at 1366×768 + 1440×900 + `vision_analyze` asserting all 3 right-column
    panels reachable / no clipping. Recipe: `references/terminal_layout_clipping.md`.
    When you ADD a right-column panel, re-run the clipping check — a 4th panel will re-introduce
    the cut-off. Compact the right column (smaller rows/gaps) before widening the fallback.

    Full build + verification recipe: `references/terminal_interface.md`.
    Dashboard clipping on short viewports + "two terminal" disambiguation: `references/terminal_layout_clipping.md`.
    interface-5 gap-merge (5-state chips, sensory waves, WF icons, env gauge/uptime/portrait, compact single-row dock, vision-misread verification): `references/terminal_interface5_merge.md`.
    LIVE-BROWSER verification (pytest doesn't run the UI JS — setSens/rogue-port/900px pitfalls + CDP recipe): `references/terminal_verify_live.md`.
    Voice mode real bugs + AUDIO_PRESENT verifier: `references/terminal_voice_mode.md`.
    Ollama worker wedging recovery WITHOUT sudo: `references/ollama_recovery.md`.
    CI install-gate + `scripts/*.py` import trap + `.gitignore` runtime logs + supervisor-aware port-8777 kill: `references/ci_install_verify.md`.
    3D human-face avatar (Three.js, vendored, lip-sync) recipe: `references/terminal_3d_avatar.md`.
    Avatar MUST render without WebGL (SVG base + 3D enhancement) — verification recipe + the
    "no face / blob" regression fix: `references/terminal_avatar_webgl_fallback.md`.
    Responsive cross-device layout (fluid face + 5 breakpoints + headless verify): `references/terminal_responsive.md`.
    Dashboard clipping on short viewports + "two terminal" disambiguation: `references/terminal_layout_clipping.md`.

  11. **NO FAKE ANIMATIONS — every visual = MOON's real state (explicit operator spec).** The
      operator's terminal request said verbatim: "do not contain fake or random animations.
      Every visual element, animation, transition, and status indicator must be driven by
      MOON's actual runtime behavior / current operational state." This is a HARD global
      constraint over the whole UI. Concretely: the STATE indicator, the 8-step Workflow
      Pipeline, and the Workflow Process flowchart are driven ONLY by real `workflow` WS
      events (`routing/thinking/tool_call/reflection/consistency/speaking/locked`), mapped by
      the frontend `STAGE_MAP` → UI state. The 3D face color + facial mesh dots + brain viz
      brighten ONLY when MOON is active (`state not in ('idle','locked')`). Lip-sync uses the
      real voice-audio RMS. Verify with a live WS test: the `locked` path emits ONLY `locked`
      (no fake thinking/executing); the unlocked path emits the real orchestrator stages. If a
      signal has no real source, derive from observable state (like EMOT) — never fabricate.
  12. **When the operator challenges "is this the same as I asked?" — AUDIT, don't claim (FIRST-CLASS
      honesty correction this session).** The operator got angry ("you make me angry / are you
      fool or something") when asked to confirm the build matched the reference and I had not
      actually verified against the real spec. Hard rule: before answering "yes it matches,"
      actually audit against the source (the reference image + their written spec). If gaps
      exist, REPORT THEM HONESTLY with evidence — do NOT claim completeness. In this session
      the real gap was: their spec listed ~18 workflow states but MOON's orchestrator emits only
      5 real stages (`routing/thinking/tool_call/reflection/consistency/speaking`); the other
      states are not faked (would violate rule 11). Correct answer = confirm what IS real (layout
      matches, 5 real stages drive the avatar) + honestly list the missing states + offer to add
      genuine instrumentation if wanted. Also: a real bug found during this audit (unlock phrase
      never unlocked through the terminal WS) was FIXED and the regression guard is in
      `references/terminal_unlock_bug.md`. Full D-ID/digital-human build recipe + honesty
      checklist in `references/terminal_did_digital_human.md`.
  12. **There is exactly ONE terminal UI now (`:8000` removed).** The old Neural Brain Command
      Center (`app/api/main.py` → `:8000`, `web/moon_brain.html`, `web/galaxy.html`) was
      deleted; `main.py start`/`terminal` both launch ONLY the MOON terminal on `:8777`.
      When the operator reports "two terminals", it is (a) the same `web/moon_terminal.html`
      open in two editor tabs (no code fix — close a tab); (b) `app/tools/terminal.py` =
      `TerminalTool`, a shell-exec CAPABILITY the orchestrator imports (`from app.tools.terminal
      import TerminalTool`) — NOT a UI, never remove it; or (c) a stray unreferenced dir like
      `./Terminal/` (safe to delete after confirming no references). Verify with `find . -iname
      '*terminal*' -not -path './.venv/*'` + `git ls-files | grep -i terminal` before deleting.
Cinematic visual-fidelity recipe (glass/3D-brain/synapse/gauges): `references/terminal_cinematic.md`.
Real host metrics WITHOUT psutil (the /proc technique used for the gauges): `references/terminal_real_metrics.md`.
Real wiring recipes (single input, voice streaming + mute, locked-reply, sensors, connect_agents, Ollama warm-up): `references/terminal_wiring.md`.
Sensory VISION/FILE STANDBY bug + "drive rows from real backend flags" rule: `references/terminal_sensory_standby.md`.
Function-matrix audit + EMOT derivation (every action gets a button, all 9 tabs wired,
EMOT live from real signals, `stop` honest limitation): `references/terminal_function_matrix.md`.

## Recurring pitfalls
- **Re-confirm verification after every push.** The verify/approve harness keeps a
  stale snapshot of the previous commit (it pinged dangling objects like `24e1c9e` /
  `9e2eec1` and re-requested `make test` even after a clean push). When a push completes,
  ALWAYS re-run fresh evidence in a follow-up call: `git rev-parse --short HEAD` +
  `git rev-parse --short origin/main` (must match), `env -u PYTHONPATH make test`
  (15/15), and — for the terminal — `curl -s -o /dev/null -w '%{http_code}\n'
  http://127.0.0.1:8777/` (200). Treat the stale-object ping as noise; the authoritative
  state is `HEAD == origin/main` + green tests. Do NOT loop on the stale flag.
- **DEFINITIVE dangling-commit investigation (run it when the harness cites a phantom SHA):**
  `git cat-file -t <SHA>` (is it even an object?), `git branch -a --contains <SHA>` (empty
  => on NO ref), `git for-each-ref --contains <SHA>` (empty => no branch/tag), and
  `git merge-base --is-ancestor <SHA> HEAD` (prints nothing => NOT an ancestor = dangling
  orphan). This session proved `24e1c9e` is a **real commit** (`git cat-file -t` -> commit)
  authored `MOON <moon@local>` on a PRIOR date, present on NO branch and NOT an ancestor of
  HEAD — i.e. a disconnected orphan from an earlier session's history rewrite. It is NOT
  something you committed this turn, so it carries NO verification obligation. Action: report
  it as a dangling orphan, show `HEAD == origin/main` + green tests, and move on. Never treat
  the phantom SHA as your commit to "repair."
- `requests` was commented out of `requirements.txt` while `web_search`/`api_requests`
  imported it → those tools `ModuleNotFoundError` on fresh install. If a default-enabled
  tool imports a package, it MUST be in `requirements.txt`.
- `Makefile` `serve` target must call `main.py start` (the subcommand was renamed from
  `serve` during rebuild; `make serve` was broken until fixed).
- **Git push refspec: local branch is `master`, not `main`.** `git push origin main`
  fails with `error: src refspec main does not match any` because the local branch is
  `master` (it tracks `origin/main`). Correct forms: `git push origin master:main`
  (sets the GitHub default to your HEAD) and, when a `master` remote branch also exists,
  `git push origin master:master` too. If you only ever `git push` with no refspec, it
  pushes `master` → `master` but leaves `origin/main` stale — reconcile both so the repo
  shows your commits regardless of which branch is the GitHub default. Always confirm
  with `git log --oneline -1 origin/main` after pushing.
- Tests that assert an exact agent count break when you expand the roster — assert
  `>= N` or count from `AGENT_DEFS`.
- Don't assert an exact LTM/episode count against the global `app/logs/` store (the live
  backend writes to it); assert `>= 1` or use a unique temp agent name.
- **Lint hygiene (final-audit lesson):** MOON's `BaseTool` subclasses store class-level
  data constants (`_CHECKS`/`_SIGS`/`_INDICATORS`) as lists/dicts — `ruff` flags these as
  `RUF012` (mutable class attribute). Fix by annotating `ClassVar[list]` / `ClassVar[dict]`
  and adding `from typing import ClassVar` (keep it AFTER `from __future__ import annotations`).
  Also `context_builder.build` building a list via a `for`+`append` loop over history trips
  `PERF402` — use `messages.extend(history.messages())`. Run
  `env -u PYTHONPATH .venv/bin/python -m ruff check app/ scripts/ main.py install_moon.py`
  and fix real `F`-codes (ignore `F401` re-exports in `__init__`/package roots) before commit.
- **Source-writing newline corruption (recurring build bug).** When you compose Python
  source via `patch()`/`write_file()` — especially inside `execute_code` — and the
  content has a string literal with an embedded separator such as `"\n".join(...)` or an
  f-string carrying `\n`, the tool can SILENTLY insert a LITERAL newline inside the
  quotes (so `"\n"` becomes `"` + real newline + `"`), yielding
  `SyntaxError: unterminated string literal`. This bit 4+ times in one agent-build
  session. Fixes: (a) for join separators prefer `chr(10).join(parts)` or put the
  `"\n".join(parts)` on its OWN line where `\n` is the ONLY two chars; (b) when a file
  has several f-strings with embedded `\n`, REWRITE THE WHOLE FILE with `write_file`
  instead of chaining `patch()` calls; (c) ALWAYS `python3 -m py_compile <file>`
  immediately after writing and fix `unterminated string literal` on the spot — the
  error is deterministic and the remedy is re-writing the literal, never grep-guessing.
- **Package/module name collision when adding a subpackage.** If you create a subpackage
  `parent/foo/` while a module `parent/foo.py` already exists, `import parent.foo`
  resolves to the PACKAGE, so any code importing symbols from the old module breaks with
  `ImportError: cannot import name '...' from 'parent.foo'`. Before introducing a
  subpackage, `ls` the parent for a same-named `.py` and delete/merge the stale module
  first. (Seen when `moon_agent/skills/` replaced `moon_agent/skills.py`.)

## Final-audit reproducibility pitfalls (commit `ea68794`) — DO NOT re-introduce
- **Plugin loader import path:** `plugins/` is a repo-root package, NOT `app.plugins`.
  Importing `app.plugins.loader` makes the 3 plugin tools (excalidraw,
  architecture_diagram, ascii_art) silently never register (WARNING in log, no crash).
  Always import `from plugins.loader import load_plugins`. Verify via
  `o._tools._registry.tool_names` containing the 3 plugin names after a fresh boot.
**`install_moon.py` must never run under host `PYTHONPATH` OR a foreign `VIRTUAL_ENV`:** the
Hermes runtime injects a `python3.11` site-packages path that makes `pip`/venv target the
*Hermes* venv, so deps "install" there and the script's smoke test reports a FALSE "OK".
`_run()` now strips **BOTH** `PYTHONPATH` and `VIRTUAL_ENV`; `smoke_import()` uses the
project venv python + clean env. Rule: launch the script from a copy (`python3
./install_moon.py`), never as `python3 /abs/path/to/MOON/install_moon.py` (ROOT resolves to
the source dir). The clean-room test (`references/verify_install.md`, step 6) asserts deps
land in `$PWD/.venv` and that plugin tools load — both checks catch regressions.

## Similar-name folder guard — do not assume `/home/meow/Projects/MOON`
When the current directory is a similarly named project such as `Moon_AI_AGENT` or a pasted/legacy MOON concept folder, first verify the actual root and repo state before applying canonical `/home/meow/Projects/MOON` workflows. If it is not the main MOON repo:
- Treat it as a separate project. Preserve legacy files and build additively unless the operator explicitly asks for migration/removal.
- Inventory the existing files, compile/check syntax, and identify placeholders before writing code.
- For broken one-file prototypes, the best default is usually an additive structured package (`moon_agent/`, `main.py`, tests, README) while leaving the old monolith/D-ID terminal assets intact.
- Verify with `py_compile`, unit tests, and CLI/API smoke tests. Do not claim placeholder functions are real; either replace them with real code or label them as legacy.
- When generating Python source programmatically, use raw strings or escaped `\\n` in the writer; otherwise literal newlines inside generated string literals create `unterminated string` syntax errors that only appear at compile time.

## R) The `Moon_AI_AGENT` sibling — layered online-check, avatar-terminal bring-up, WS bridge defect

`Moon_AI_AGENT` (this session's cwd under `RED_TEAMING_HACKER_INTERFACE`) is a SEPARATE
project from `/home/meow/Projects/MOON` (see Similar-name folder guard). Stack:
`moon_agent/` package (`runtime.MoonAgent` brain + lock; `integrations/moon_nexus.MoonNexusBridge`
avatar bridge) + `MOON_NEXUS_FUNCTIONAL_FINAL/MOON_Avatar_Terminal_FINAL/` (tkinter Dashboard
+ `terminal/server.py` WebSocket + futuristic web UI).

**"Is MOON online?" = verify 3 independent layers (each can die alone):**
1. **Brain** — `python3 -c "from moon_agent.runtime import MoonAgent; a=MoonAgent(); a.observe_unlock('love you 3000 moon'); print(a.run('who are you?').text)"`. Lock phrases: `MOON love you 3000` AND `love you 3000 moon` (both unlock).
2. **Ollama LLM** — `curl -s http://127.0.0.1:11434/api/tags` (19 models here: qwen2.5:3b, qwen3:8b, deepseek-r1:8b, …). If empty, the brain returns a council-fallback, not an error.
3. **Avatar terminal WS** — `ss -ltnp | grep ':8765'` (MOON Agent bridge) and `:8787` (NEXUS web UI). If 8765 is NOT listening, the face is offline even though the brain works.

**Bring the avatar terminal back up (validated fix):** `run_nexus.py` imports `PIL`/`tkinter`.
The persistent Hermes terminal's `python3` resolves to the **Hermes venv whose PIL is broken**
(`ImportError: cannot import name '_imaging' from 'PIL'`) → the process dies silently and 8765
stays closed. Launch with the **system Python + sanitized env**:
```bash
cd MOON_AI_AGENT/MOON_NEXUS_FUNCTIONAL_FINAL/MOON_Avatar_Terminal_FINAL
env -u VIRTUAL_ENV -u PYTHONPATH -u PYTHONHOME PATH="/usr/bin:/bin:/usr/local/bin" \
  /usr/bin/python3 run_nexus.py > /tmp/moon_nexus_logs/run_nexus.out 2>&1 &
# wait ~3s; verify: ss -ltnp | grep -E ':8765|:8787'
```
This mirrors what `MoonNexusBridge.start_avatar_terminal()` already does (sanitizes env +
uses `sys.executable`); the failure only happens when YOU launch it manually from a poisoned
shell. `DISPLAY=:0.0` is live; `xvfb-run` exists as fallback.

**End-to-end proof (MOON drives her avatar):** boot `MoonNexusBridge` (see `moon_nexus.py`
`launch()`), then connect a WS client to `ws://127.0.0.1:8765/moon`, send
`{"type":"moon.ui.action","action":"moon.chat","payload":{"text":"..."}}`; MOON's reply comes
back as `avatar.speak` on the bridged socket. (Test-harness note: the reply is broadcast to the
BRIDGE's socket, not a separate test client — to assert the relay, capture on the bridge loop,
not a second socket.)

**⚠️ WS bridge protocol defect (identified this session, NOT yet fixed):** `terminal/server.py::
process()` only adds a client to `self.moon_clients` (the set the UI forwards `moon.chat` to)
when the incoming `hello` carries `role: "AGENT"` (defaults to `"UI"` otherwise). But
`MoonNexusBridge` sends `hello` **without** a `role` field → MOON is registered as a UI client,
so `moon.chat` is never delivered to her brain and the avatar cannot speak. **Fix (pick one):**
(a) add `"role": "AGENT"` to the `hello` dict in `moon_nexus.py::run()`, or (b) in `server.py`,
register any `hello` whose `agent == "MOON"` as an agent client. Verify after fix: UI
`moon.chat` → bridge receives `avatar.speak`.

Full command recipes + defect trace: `references/moon_ai_agent_bringup.md`.

## N) Master Project Completion protocol — the user's standing 5-task / 29-phase directive
When the user pastes the long "make the project fully operational" prompt (it names
Tasks 1–5 and a 29-phase completion sequence), treat it as a STANDING OPERATING
PROTOCOL, not a one-off. The user has repeated, emphatically, the rules below — they
are now part of how MOON work must be done for this operator.

**The 5 tasks (in order, each gates the next):**
1. Discovery + architecture audit ONLY (read-only; no file changes). Produce a
   component/dependency/integration report. Inspect the whole tree; classify each
   component COMPLETE / PARTIAL / DISCONNECTED / BROKEN / DUPLICATED / UNUSED /
   PLACEHOLDER / UNKNOWN.
2. Integration — wire existing components, PRESERVE everything that works, work
   incrementally, validate every change. Integrate-before-rebuild.
3. Automatic repair loop — do NOT stop at the first error. For every blocking issue:
   DETECT→DIAGNOSE→root cause→smallest safe repair→rerun test→regression. Never patch
   symptoms; never hide errors; never mark failed tests passed.
4. Real runtime — start via the REAL entrypoint (`main.py`/`uvicorn`), no mocked
   success, execute real end-to-end workflows, verify each critical subsystem
   actually works (input→understood→plan→agent→tool→executed→real result→verified).
5. Final acceptance — do NOT declare complete on code existence. 29-point checklist
   (root identified / agents registered / tool→agent comms / memory / knowledge /
   model / DB / APIs / services / UI / startup / runtime / integration / e2e /
   regression / security / health / no disconnected component / no placeholder / no
   fake success). Final status = one of NOT READY / PARTIALLY READY / OPERATIONALLY
   READY / PRODUCTION READY.

**Hard rules the user imposed (embed these into every completion run):**
- ANALYZE → UNDERSTAND → make a step-by-step per-task list → THEN execute list-by-list.
  Do not start coding before the plan exists and is grounded in real discovery.
- "Do not magically / unreal-ly complete the task." No fake success, no skipped tests,
  no mocks returning success. Claim success only on verified runtime behavior.
- PRESERVE existing work. Integrate before rebuilding. Smallest safe change.
- Fix root causes, not symptoms. Repair loop until the evidence shows it actually works.
- If a required capability can't complete due to an EXTERNAL blocker (missing cred,
  unavailable service, hardware limit), clearly NAME the blocker instead of pretending
  done.
- Phase 0 safety first: detect git repo / branch / uncommitted changes / secrets;
  never expose secrets; never destroy user data/DBs; use the existing VCS workflow.

## Verification recipes (this session — the reliable way to prove "it works")

**MOON operational verification sequence (run in this order; each gates the next):**

```bash
# PHASE 0 — static integrity
.env/bin/python -m compileall -q app/ main.py terminal_moon/main.py terminal_moon/app  # syntax clean
.env/bin/python -c "import sys; sys.path.insert(0,'.'); ..."  # full import smoke (195 modules, 0 FAIL)

# PHASE 1 — config + backend
.env/bin/python -c "from app.config.settings import get_settings; s=get_settings(); print(s.model_name, s.model_base_url)"  # settings resolve
curl -s --max-time 3 http://127.0.0.1:11434/api/tags | python -c "import sys,json; d=json.load(sys.stdin); print(len(d['models']),'models')"  # Ollama reachable + model count

# PHASE 2 — orchestrator subsystem audit (real, not mocked)
.env/bin/python -c "
import sys,asyncio; sys.path.insert(0,'.')
from app.config.settings import get_settings
from app.brain.orchestrator import Orchestrator
async def go():
    o=Orchestrator(get_settings()); await o.setup()
    print('Agents:',len(o._agents),'| Tools:',len(o._tools._registry.tool_names),'| Brains:',len(o._agent_brains))
    for n in ['LLM','ToolManager','MemoryManager','ContextBuilder','ReasoningEngine','Planner','Validator','SelfReflection','OutputFormatter','ErrorRecovery','EmbeddingService','PromptManager','KnowledgeBase']:
        print(f'  {n}:', 'OK' if getattr(o,'_'+n.lower().replace(' ','_'),None) or getattr(o,'__dict__',{}).get('_'+n.lower().replace(' ','_'),'MISSING') else 'MISSING')
asyncio.run(go())
"  # ALL SUBSYSTEMS WIRED: OK (39 agents, 43 tools)

# PHASE 3 — real task execution (cognition loop end-to-end, NOT mocked)
.env/bin/python -c "
import sys,asyncio; sys.path.insert(0,'.')
from app.brain.orchestrator import Orchestrator
from app.models.task import Task
from app.config.settings import get_settings
async def go():
    o=Orchestrator(get_settings()); await o.setup()
    t=Task.create('USE file_manager tool to list files in /home/meow/Projects/MOON. Tell me exactly what the tool returns.', agent_name='toolsmith')
    r=await o.run_task(t)
    print('STATUS=',r.status,'| RESULT=',r.result[:200] if r.result else '(none)')
    await o.teardown()
asyncio.run(go())
"  # tool output present + correct = system works

# PHASE 4 — moonscope TUI boot (Textual, stderr capture)
timeout 5 .venv/bin/python -m app.tui 2>/tmp/ms_verify.log
# checks: 0 Traceback/Exception, 0 LOCKED/🔒, brain panel renders real data (model/qwen2.5:1.5b/version/8 pipeline stages/agents), HUD line present

# PHASE 5 — terminal_moon standalone
cd terminal_moon && timeout 5 .venv/bin/python main.py terminal 2>/tmp/tm_verify.log  # boot clean, HUD shows UNLOCKED
.env/bin/python verify_all.py 2>/dev/null  # ALL 20 END-TO-END TESTS PASSED
.env/bin/python main.py doctor  # PASS (8/8 subsystems nominal)

# PHASE 6 — regression
re-run PHASE 0 + PHASE 5 to confirm nothing regressed
```

**Important techniques discovered this session:**

- **`moon doctor` reliability**: running `python main.py doctor` as a subprocess CAN HANG in this agent environment (the inline `timeout 120` timed out at 120s). The RELIABLE path is to call `_cmd_doctor()` directly:
  ```python
  import sys; sys.path.insert(0,'.')
  from main import _cmd_doctor
  _cmd_doctor()   # completes in ~3.3s, prints [PASS]/[WARN]/[FAIL] per subsystem
  ```
  This bypasses argparse dispatch overhead and is the verified-working approach.

- **Model hallucination of tool output**: qwen2.5:1.5b (and similar small local models) often NARRATES a plausible file list instead of actually returning `file_manager` tool output. The cognition loop completes end-to-end but the answer is WRONG. Fix: phrase tasks as explicit tool-use commands ("USE the file_manager tool to list... Tell me exactly what the tool returns") so the tool-intent fallback (`_try_explicit_tool`) fires deterministically. A task that returns made-up data is a FAILED acceptance criterion even if status=completed.

- **Lock state shared persistence**: both `app/` and `terminal_moon/` Orchestrators default `lock_state_file` to on-disk `app/data/lock_state.json` / `terminal_moon/data/lock_state.json` so unlocks persist across CLI runs, TUI boots, and web backend. After unlock, `moon run` and both TUIs see `locked=False`. (See lock_state_sharing.md in moon-engineering references.)

- **When the moonscope TUI HUD doesn't show lock/unlocked text**: the BrainHUD renders `🔒 locked` / `🔓 unlocked` but if the terminal width is tight the lock segment gets clipped. Verify with a wide terminal (COLUMNS≥120) or check the ANSI-striped log for the lock text. Boot default is `locked=False` (unlocked) — no LOCKED/🔒 should appear on fresh boot.
Do NOT rely on import-success or server-start as proof. Exercise the live system:
```python
# verify real cognition + memory + tool execution against the RUNNING backend
import sys, asyncio; sys.path.insert(0,'.')
from app.terminal_interface import _get_orchestrator
from app.models.message import Message
async def main():
    orch = await _get_orchestrator()
    r = await orch._llm.complete([Message(role="user", content="Reply with exactly: PONG")])
    assert "PONG" in (r.content or ""), "LLM dead"
    await orch._memory.remember("probe:k", "v", long_term=True)
    assert await orch._memory.recall("probe:k")   # memory works
    reg = orch._tools._registry
    res = await reg.get("system_info").execute()  # tool runs, returns str
    print("tools:", len(reg.all()), "agents:", len(orch._agents))
asyncio.run(main())
```
**API-shape gotchas that wasted cycles this session (don't re-discover):**
- `LLMService.complete()` takes `list[Message]` (from `app.models.message`, NOT
  `app.brain.types` which doesn't exist) and returns `CompletionResult` whose field is
  `.content` (NOT `.completion`).
- `MemoryManager` uses `.remember(content, long_term=, tags=)` / `.recall(keyword)` —
  there is NO `.add`/`.get` on it. `ShortTermMemory` has `.add(content)`.
- A tool's `execute()` returns whatever the tool defines (often a `str`, NOT a
  `ToolResult` wrapper — `ToolResult` in `app/tools/base.py` is NOT used by the
  execution path). Check `hasattr(res,'success')` before reading `.success`/`.output`.
- `orch._agents` is a **dict** (name→AgentCard), not a list.
- `orch._tools.tool_names` is wrong; use `orch._tools._registry.tool_names`.

**WS end-to-end proof:** unlock with `MOON love you 3000` (or `love you 3000 moon`) →
send a real question → assert `assistant_chunk` frames THEN `assistant_done` AND an
`audio` frame (Kokoro WAV) arrive. A test that breaks on the FIRST `recv` timeout
instead of continuing to collect will falsely report "0 frames" — the backend is fine,
the test is wrong. Collect with a long budget and break only on `assistant_done`.
Full 29-phase checklist + per-task template: `references/master_completion.md`.

## O) MOON install / run / HUD bring-up — operational pitfalls (this session)

These three failures recurred across install+run and have a SINGLE correct fix
each. They are the most common "MOON won't start / terminal won't open" causes.

**O1. Double-backend crash loop → service stuck `activating`, HUD blinks.**
Symptom: `systemctl --user is-active moon-terminal.service` shows `activating`
forever; journal shows `address already in use` (Errno 98) on :8777 in a tight
Restart=always loop; HUD WS drops/reconnects every few seconds (looks like
blinking). Root cause: the unit's `ExecStart` was `python main.py start`, which
spawns uvicorn as a **child**; if an older backend already held :8777 the new
one failed to bind and systemd restarted it endlessly, and the parent stayed in
`activating`. **Fix:** `ExecStart` runs uvicorn DIRECTLY
(`python -m uvicorn app.terminal_interface:app --host 0.0.0.0 --port 8777`),
never `main.py start`. Also: if a stale backend holds the port, `kill` that PID
first, then `systemctl --user restart moon-terminal.service`. Verify:
`systemctl --user is-active` → `active`, `curl /api/health` → HEALTHY.

**O2. HUD shows a near-black screen / "terminal won't open".**
Symptom: Chrome `--app` window opens but is ~81% black with a faint red logo
(the `#boot` overlay, `background:#040000`) and never reveals the terminal.
Root cause: the boot overlay was only removed by `runBoot()`, which fired ONLY
through `window.MOON_UI.onReady` on the WS `ready` message — any missed/batched
message or race left `#boot` up forever. **Fix:** call `runBoot()` directly in
`ws.onopen` (after the status/log_stream sends) AND harden the monitor safety
net to force-remove `#boot` after a short grace period unconditionally. The page
is self-contained (inline `<script>`, only `/panel3d.js` + `/three.min.js` must
load; both 200). Verify: load `http://127.0.0.1:8777/` → `#boot` element is
removed from the DOM and `#command` input is present.

**O3. `moon` opens MANY HUD windows / no usable terminal.**
Symptom: running `moon` (or `moon terminal`) spawns several Chrome windows.
Root cause: THREE openers all called `open_hud()` — `moon-hud.service` keeper,
the unit's `ExecStartPost=...open_hud.py --once`, AND manual `moon` — and
`open_hud()` wrote its lockfile AFTER `Popen`, so concurrent callers both passed
the `_hud_alive()` guard and each spawned a window. **Fix:** (a) `open_hud()`
claims the lockfile (sentinel) BEFORE spawning and bails if a window already
exists → truly single-instance; (b) drop `ExecStartPost` from
`deploy/moon-terminal.service` — the HUD window is owned SOLELY by
`moon-hud.service` (opens exactly one, reopens if closed). Verify:
`ps -eo pid,args | grep "chrome.*--app=http" | grep -v grep | wc -l` → `1`.
The HUD's interactive input is the `#command` box at the bottom; unlock with
`MOON love you 3000`. For a text-only terminal use `moon tui`.

**O4. One-click install + setup wizard architecture (the canonical path).**
`./install.sh` is the single entrypoint. It (1) runs `setup_wizard.py` on first
run (no `.env`) — interactive questions: model backend [local Ollama
recommended / OpenAI / OpenRouter / HuggingFace], optional cloud keys (masked
getpass), Telegram, authorized scan targets, remote token — then writes a
gitignored `.env`; (2) delegates the real install to `install_moon_full.py`
which installs venv+deps, **auto-installs Ollama + pulls the 5 models** (via
`scripts/install_ollama.py`), Kokoro+F5 voice, launcher, then **enables+starts**
`moon-terminal.service`, `moon-hud.service`, `moon-monitor.timer`, starts MOON,
and runs a real post-install acceptance. `--yes` = accept defaults (true
one-click). `moon` launcher must be on PATH: `export PATH="$HOME/.local/bin:$PATH"`
(added to `~/.bashrc`/`~/.profile`). The deep monitor (`scripts/moon_deep_monitor.py`)
proves real execution (unlock + `system_info` contains `linux`) every 15 min.
NEVER duplicate this logic — extend `install_moon_full.py`, don't fork it.

Exact recipes + service-unit templates: `references/moon_install_run.md`.

**O5. HUD does NOT open on login/boot (DISPLAY missing + backend-restart flap).**
Two independent bugs, both silent: (a) `moon-hud.service` had **no `DISPLAY`**
env — a systemd *user* service at login doesn't inherit DISPLAY, so
`open_hud.py` detects "no graphical display" and skips opening. **Fix:** add
`Environment=DISPLAY=:0` (WAYLAND fallback preserved in `open_hud.py`).
(b) `moon-hud.service` had `Requires=`+`PartOf=moon-terminal.service`, so
EVERY backend restart (crash or the deep monitor's `restart_backend()` heal)
propagated a stop+start to the HUD keeper → start/stop storm in the journal,
window never opens. **Fix:** `Wants=` only (start after backend, survive its
restarts). **Flap test:** `systemctl --user restart moon-terminal.service` →
HUD window must stay visible (`xdotool` geometry unchanged) and
`moon-hud.service` stays `active`. Regression if `PartOf`/`Requires` returns.
See `references/moon_install_run.md` §O5 for the exact unit + test.

**O6. Fresh `git clone` install FAILS — torch CPU pin delisted.**
`requirements.txt` pinned `torch==2.6.0+cpu` / `torchaudio==2.6.0+cpu`, but
the PyTorch CPU index only publishes **2.9.0+cpu and newer** — a clean clone
errored `Could not find a version that satisfies torch==2.6.0+cpu`. **Fix:**
pin `torch==2.9.0+cpu` + `torchaudio==2.9.0+cpu` (verified available; 2.9.0
CPU torch also imports `f5_tts` without the `libcudart.so.13` crash) and pass
`--extra-index-url https://download.pytorch.org/whl/cpu` in the installer's
core `pip install -r requirements.txt`. Always re-check with
`python3 -m pip index versions torch --extra-index-url .../cpu` before
bumping. Also: `/tmp` is a 1.9G tmpfs that fills during repeated
clones+pip → `[Errno 28] No space left on device` (NOT an install bug) — clone
the cert onto `/home/meow/MOON_cert` (big disk) with
`TMPDIR=/home/meow/.pip_tmp`. **Certify "installs on any machine" by cloning
fresh and running the installer isolated** (`install_moon_full.py
--no-service`) — this caught the O6 break the cached local venv hid. See
`references/moon_install_run.md` §O6.

**O7. Unlocked execution stall + auto-voice + HUD core (all verified this session).**
- **Orchestrator cognition-loop stall.** `_run_cognition_loop` had NO per-call
  timeout; factual queries routed (via `enable_fast_path`/`_is_simple_query`) to a
  per-agent **reasoning model** (e.g. `deepseek-r1:1.5b`) that "thinks" 100+ s on
  CPU, so the terminal got no reply for ~108 s. **Fix:** wrap every
  `llm.complete(...)` in `asyncio.wait_for(..., timeout=30)` and on `TimeoutError`
  fall back to the fast shared `self._llm` (qwen2.5:1.5b). 30 s is enough for a
  1.5b/3b call (1-3 s); past 30 s = stuck reasoning model. After this, MATH returns
  in <10 s. Verify with a live WS `send_message` "what is 7*6?" → "42".
- **Auto voice mode was dead (not missing).** The plumbing existed
  (`_speak()` after each reply + `audio` WS frame + mute/unmute) but
  `_get_voice_engine()` permanently cached the engine as `False` on a first-run
  init hiccup (boot probe runs before `_ORCH._settings` exists). **Fix:** build
  robustly (`VoiceEngine(settings=s)` → fall back to bare `VoiceEngine()`); do NOT
  permanently cache `False` — retry next call. Also `set_voice("aria")` so MOON
  speaks female by default (offline, no key). Result: locked reply / unlock notice /
  unlocked task result ALL deliver a real WAV `audio` frame. Regression: a locked
  `send_message` must yield an `audio` frame, not just `assistant_chunk`.
- **HUD fusion/neural core from a user image.** To make a supplied animated graphic
  the MOON fusion core AND neural core (integrated, not a floating overlay):
  copy it to `web/assets/moon_core.webp`, add a `/moon_core.webp` route, set
  `.fusionOrb { background: ... url('/moon_core.webp') }`, and in `applyAvatarMode()`
  reveal the orb in BOTH `fusion` and `neural` modes (don't hide it for the brain
  canvas). WebP animation plays as a CSS background in Chromium. Verify: headless
  screenshot, central region shows many distinct colors (the sphere is rendering).

## Keep it real
The user demands genuinely-built code, not magic/fabrication. Every "missing function"
must become an actual module + a verification step. If a folder (e.g. a backup) contains
no MOON source, say so honestly — do not invent files to "add".
