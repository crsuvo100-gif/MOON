---
name: agent-terminal-tui
description: Jarvis-style Textual TUI driving a real AI agent via tmux.
---

# Agent Terminal TUI (Textual + tmux + voice)

Build a gorgeous, fully-functional interactive terminal UI for an AI agent.
This is the class of work for "Jarvis-style" control rooms, neon skill walls,
and tmux-backed live agent consoles. Verified pattern from a real build where
the UI drove a local `llama3.2:3b` agent end-to-end (command -> agent runs ->
answer extracted -> spoken back via espeak).

## When to use
- User asks for a terminal/TUI for their AI agent, a "Jarvis" interface, an
  interactive agent console, or a cyberpunk/anime-styled agent front-end.
- You need to surface an agent's capabilities (agents/tools/workflows) as a
  clickable UI and let the user run them.

## Architecture (proven in this session)
- `terminal_app.py` — the Textual `App`. Layers: animated `Starfield` (background)
  + `CRT` scanline overlay + `TopBar` (clock/status) + main panels + `Input` chat bar.
- `starfield.py` — `Static` that renders twinkling glyphs + comets; `set_interval`
  to animate; pinned to `layer: background`.
- `boot.py` — `Screen` splash (ASCII banner + animated boot log) that `pop_screen()`s
  itself to reveal the main UI.
- `voice.py` — `espeak` TTS (offline) + optional mic STT.
- `tmux_controller.py` — launches the agent in a REAL tmux session, mirrors its
  pane, sends keystrokes, and pops out a GUI terminal attached to that session.
- `skills_loader.py` — introspects the agent package at runtime so the wall always
  reflects real capabilities (NEVER hardcode the list).

## Build steps
1. Create a venv (`python3 -m venv .venv`); `pip install textual` (+ the agent
   package's deps in the SAME venv so both import together — PEP 668 box).
2. Compose: background layers first, then Header/TopBar, main `Horizontal`,
   `Input` chat bar docked bottom, `Footer`.
3. Introspect capabilities via `skills_loader.load_skills()` -> render wall tiles.
4. Wire tiles/buttons to `run_skill()` which dispatches a real command into the
   tmux session (`bash -c "python3 main.py run ..."`).
5. Voice button: `voice.speak()` replies; if `voice.stt_available()`, start a
   listen -> execute -> speak-back loop.
6. GUI pop-out: `ctl.popout_gui()` opens gnome-terminal/xterm `tmux attach`.

## Verification (must actually run)
- `python -m py_compile $(find terminal -name '*.py')`
- Construct the app headlessly (no display needed): `AIOSApp()` then assert
  registry has expected agents/workflows.
- `pytest tests_terminal.py` — tmux create/capture/kill, espeak TTS, skills.
- Real GUI pop-out: launch tmux, call `popout_gui('gnome-terminal')`, confirm a
  window via `xdotool search --class gnome-terminal`.
- Live agent run: `python3 main.py run "..."` in tmux, poll pane for the result
  marker, then `voice.speak(result)`. Budget ~3 min for a 3B CPU model.

## Persona rebrand + Security Lock Mode pattern
- **Rebranding an existing terminal** (user: "rebuild it as MOON, same functions,
  match this video"): RESTYLE only — keep the verified dispatch glue
  (`bash -c "python3 main.py run ..."` in tmux), the skills_loader wall, the live
  console, voice, pop-out. Change colors/text/persona. Add a signature visual:
  for MOON it was a glowing cyan particle orb (see `templates/orb.py`, a pure-
  Textual glyph orb — no Three.js/browser needed). Replicate the VIDEO offline:
  extract frames with `ffmpeg -vf fps=1/2`, read them with `vision_analyze`
  (see `references/replicate-video-ui.md`). CRITICAL: the signature visual must be
  the CENTERPIECE, not a dim background layer — verify with `tmux capture-pane`
  (the user rejected a first pass where the orb was buried behind panels:
  "my terminal did not show same like that videos"). Also ship a one-command
  - Also ship a one-command `install_moon.py` that AUTO-OPENS the terminal on
    completion (see `references/installer_pattern.md` "Auto-open the terminal").
    Ship a `./moon` **pure-Python** launcher `moon.py` (see `templates/moon_launcher.py`)
    as the single entry point: `python3 moon.py` opens the UI directly,
    auto-installing first if the venv is missing. REUSE `install_moon.py`'s
    `launch_terminal()` so there is one source of truth. Do NOT leave a `./moon`
    bash script as the primary entry point — the user explicitly required
    "turn the project into .py; no bash needed" and the bash launcher was
    replaced for this reason. (`docker/entrypoint.sh` may stay shell — that is
    container infra, not app function, where Python adds deps for no benefit.)
- **Security Lock Mode as a real code gate** (not just a prompt): a `SessionLock`
  class (thread-safe) with `observe(text) -> notice | unlock_banner | None`,
  enforced at the TOP of the agent `run_task` AND the pipeline path that calls it.
  Persist state to a file (`app/logs/moon_lock.txt`) so the lock survives across
  separate `main.py run` invocations (CLI/TUI spawn a fresh process per message) —
  missing file = LOCKED (safe default). CRITICAL gate semantics: when the unlock
  phrase arrives, return the banner and DO NOT fall through to execute it as a
  task; only the NEXT message runs. Wire the same lock into the TUI: chat/voice
  checks the phrase, refuses tasks while locked, flips a top-bar lock chip.

## Pitfalls
- **C-library stderr (ALSA/Jack) bypasses `redirect_stderr`.** When suppressing
  mic noise, `contextlib.redirect_stderr` is NOT enough: ALSA/Jack write to the
  real file descriptor 2, not Python's `sys.stderr`. You MUST redirect fd 2 at
  the OS level around the probe — full recipe in `references/voice_mode_audit.md`
  D4: open `/dev/null`, `os.dup(2)`, `os.dup2(fd,2)` around the
  `sr.Microphone()` constructor, restore in `finally`. Symptom of getting this
  wrong: the terminal UI is flooded with `ALSA lib pcm_... unable to open slave`
  / `jack server is not running` even though `redirect_stderr` is already in
  place.
- **Pushed boot screen steals focus — chat input goes dead.** If you
  `push_screen(BootScreen())` on mount, after it `pop_screen()`s the underlying
  screen resumes but focus does NOT return to the chat `Input`. Result: the user
  types and "nothing happens" (keystrokes land nowhere, `run_prompt` never
  fires). FIX: add `def on_resume(self) -> None: self.query_one("chat",
  Input).focus()` to the main App — `on_resume` fires when the screen becomes
  active again after the boot splash. Diagnose with `tmux capture-pane`: the chat
  bar renders but sending keys produces no agent console / no log line. This was
  the real cause of a "my terminal does nothing / voice mode doesn't work" report
  on an otherwise-working build.
- **Live-monitor a TUI on a headless box — use tmux as the probe.** To prove the
  chat actually dispatched (not just rendered), watch for the spawned CHILD tmux
  session the terminal creates (e.g. `moon_terminal`): `tmux ls | grep
  moon_terminal` after a chat submit is unmistakable proof `run_prompt` fired.
  Also: KILL STALE SESSIONS. Multiple `moon_xxx` tmux sessions from earlier runs
  keep executing OLD code (pre-fix) and re-introduce the very bug you just fixed
  (e.g. the STT-error spin). Before diagnosing, `tmux kill-session -t moon_tui
  -t moon_terminal -t moon_monitor` and launch ONE fresh instance.
- **Plan mode before terminal changes.** When the user says "open in plan mode
  before changes" / "check X and fix it", INVESTIGATE FIRST (read code, probe
  env, run a pilot test), present a concrete fix plan, and WAIT for approval
  before editing. Do not silently apply fixes. This user tolerates autonomy for
  building, but wants a plan before mutating an existing working terminal.
- **Voice mode is easy to ship broken — verify it, don't assume.** Known defects
  (see `references/voice_mode_audit.md`): (a) the listen loop calls BLOCKING
  `rec.listen()` inside the async event loop → UI freezes and the loop hammers
  listen forever; run mic capture in a worker thread / `to_thread`. (b) On boxes
  with no configured capture device, `sr.Microphone()` raises ALSA/portaudio
  "unable to open slave" → `listen()` errors every call; catch it, set
  `stt_available=False`, and notify instead of spinning. (c) `recognize_google`
  needs network — falls back to a typed command line offline. (d) pyaudio/ALSA
  stderr floods logs — suppress it. Diagnose with a Textual `pilot`/`run_test`:
  toggle voice ON and assert the event loop still responds (e.g. a 0.1s sleep
  does not time out) — that catches the freeze bug.
- **Textual CSS rules (cost real debug cycles — see `references/textual-css-rules.md`):** (1) `border: bottom round #c` is INVALID → use `border-bottom: round #c`.
  (2) Widget `id` cannot contain `:` → use `wf_`, not `wf:`. (3) `self.log` and
  `self.name` are RESERVED Widget attrs → rename to `self._log`, `self.item_name`.
  (4) Layer model: `layers: background main overlay` drops unlayered content BELOW
  `background`; use `layers: background overlay` with all content in a wrapper on
  `layer: overlay`. Decorative full-screen widgets need `position:absolute; width:100%; height:100%`.
  (5) No element-type CSS selectors (`#panel h1` fails) → use `.class`.
- **Textual 8.2.8 import**: `from textual.worker import Worker, get_result`
  FAILS (no `get_result`). Import only what exists; drop unused `Worker`.
- **f-strings with backslashes/nested quotes** break (`SyntaxError`). Build
  shell-command strings with `+` concatenation, not f-strings.
- **Screen layering**: declare `Screen { layers: background main overlay; }`;
  give background widgets `layer: background` (starfield) and overlay widgets
  `layer: overlay` (CRT). Otherwise they stack in DOM order and block clicks.
- **Boot/modal screens**: use `push_screen(BootScreen())` on mount; a
  `ModalScreen` auto-dimmed overlay works for help/config. Call `self.pop_screen()`
  (boot) or `self.dismiss()` (modal) to close.
- **tmux result parsing**: the agent's `main.py` prints `Output :` (capital O,
  from `format_task_result`), NOT `OUTPUT :`. Anchor your regex on `Output\s*:`.
- **Local 3B model on CPU is SLOW** (~2-3 min per task — 3 model calls). Run
  live verification in the BACKGROUND with `notify_on_complete=true`; don't block.
- **Textual `_render()` override collisions (MOON moonscope lesson):**
  `Widget._render(self)` is called internally by Textual with **zero required args**
  (for layout/content-height calculation during `get_content_height`). If a custom
  widget defines `_render(self, extra_arg)` with any positional arg, Textual's
  internal call `self._render()` → `TypeError: missing 1 required positional
  argument`. Symptom: `run_test()` crashes at `_post_mount` / `_refresh_layout`
  with `TypeError` on the custom widget, NOT at your call site. Fix: rename the
  custom renderer to `_render_panel(self, ...)`, `_render_status(self, ...)`, etc.
  and call it from your own watcher/`on_mount` — never name a method `_render` if
  it takes extra args. **Construction smoke test + `py_compile` do NOT catch this;
  you must `run_test()` or actually mount the widget.** Proof: moonscope TUI crashed
  at `BrainCorePanel._render(new)` in `watch_brain_data` during mount because
  `_render(self, bs)` shadowed `Widget._render()` — renamed to `_render_panel` and
  boot succeeded.
- **Rich `Text()` nesting trap:** if a helper returns a `rich.text.Text` (e.g. a
  box-drawing status line) and you wrap it as `Text(helper(...))`, Rich's
  `__init__` runs `strip_control_codes(text)` which calls `text.translate(...)` —
  but `Text` has no `.translate`, so `AttributeError: 'Text' object has no
  attribute 'translate'`. Symptom: crash inside `_status_line_check` → `Text()` →
  `translate`. Fix: let the helper return `Text` and append it directly to the
  lines list; do NOT wrap a `Text` in another `Text()`. Proof: moonscope's
  `_status_line_check` was changed to return `Text` and the 3 voice/sensor
  `Text(_status_line_check(...))` calls were unwrapped.
- **Offline voice**: `espeak` is present on Kali and works with no network/mic.
  `pyaudio` will NOT build without `portaudio19-dev` (needs root); `speech_recognition`
  installs fine but can't use the mic without pyaudio. Fall back to the chat
  `Input` bar as the "voice command" entry — same code path the mic would feed.
- **Stray base classes in introspection**: exclude `BaseWorkflow`/`BaseTool` when
  scanning the package for the wall, or you get a useless `base` tile.

## User working style (this user)
- Wants MAXIMAL, complete, gorgeous deliverables — "do what is best, make it
  fully advanced." Don't ship a stub or ask many clarifying questions; build the
  whole thing and verify it runs.
- Dislikes long pre-amble narration; prefers you ACT and report verified results
  concisely. (Mirrors standing memory: direct, no-fluff, high-aggression execution.)
- Repeatedly interrupted spoken replies to say "yes, keep building" — so proceed
  without over-confirming.
- **Prefers the project to be ALL PYTHON — no bash launchers.** Explicitly: "if no
  need bash then all project turn into .py." Convert shell entry points (e.g. the
  `./moon` launcher) into pure-Python (`moon.py`) that reuses existing Python
  logic. Keep `shell=True`/bash out of the agent code entirely (tmux_controller
  uses `subprocess.run([...])` with no shell — that is fine). Only `docker/entrypoint.sh`
  stays shell (container infra).
- Wants a **plan before mutating an existing working terminal** ("open in plan
  mode before changes"): investigate + present fix plan + await approval.

## References
- `references/textual-gotchas.md` — Textual 8.2.8 API specifics & animation recipe.
- `references/textual-css-rules.md` — the 5 silent CSS crashers (border/id/reserved props/layers/selectors).
- `references/tmux-integration.md` — tmux controller code pattern.
- `references/replicate-video-ui.md` — ffmpeg+vision_analyze workflow to clone a reference video's UI offline (incl. the centerpiece-verification fix).
- `references/installer_pattern.md` — one-command idempotent `install_moon.py` (venv + deps + .env + model probe).
- `references/offline-voice.md` — espeak TTS + STT fallback details.
- `references/voice_mode_audit.md` — voice-mode defects + how to diagnose (blocking loop, mic device errors, ALSA noise) before fixing.
- `templates/moon_launcher.py` — drop-in pure-Python `moon.py` one-command launcher (auto-installs then opens the TUI; reuses install_moon.launch_terminal).
