---
name: textual-agent-terminal
description: Build a Textual agent terminal with a real tmux backend.
---

# Textual Agent Terminal

Build a rich terminal UI for an AI agent: a neon "skill wall" of live capability
tiles, workflow panel, config overlay, an integrated REAL agent terminal (tmux),
a Jarvis-style voice button, and a GUI pop-out — not a simulation.

## Trigger
User asks for an "advanced terminal", "control room", "Jarvis terminal", "rich
agent UI", "neon/anime wall of skills", or wants the agent's functions presented
as clickable tiles with voice + a real interactive shell.

## Architecture
- **TUI — Textual** (`pip install textual`; use a venv, PEP 668 blocks system
  pip). Compose widgets: Header/Footer, Horizontal/Vertical containers, Static
  tiles, RichLog, Input, Button, Switch. CSS is inline strings — neon palette
  (`#05060a` bg, `#36e0ff` / `#ff4fd8` accents, `#2bd96b` for the terminal).
  Bindings: `q` quit, `v` voice, `g` GUI pop-out, `r` reload skills.
- **Real backend (NOT a mock):** wrap `tmux`:
  - `tmux new-session -d -s <name> -n agent -c <cwd>` then `tmux send-keys` to run
    the agent command.
  - Mirror the pane with `tmux capture-pane -t <name> -p -S -<N>` on a
    `set_interval` timer into a `RichLog`.
  - Accept keystrokes: forward the Input value to `tmux send-keys`.
  - **GUI pop-out:** `gnome-terminal -- tmux attach -t <name>` (or
    `xterm -e "tmux attach -t <name>"`). Detect emulator via `shutil.which`.
    Requires `DISPLAY` set.
- **Skill wall is REAL:** introspect the agent package (agents / tools /
  workflows) with `importlib` so tiles match actual capabilities — never hard-code
  a list. A `SkillRegistry` with `.all()` → `(kind, name)` pairs feeds the tiles.
- **Voice (Jarvis):** TTS via `espeak` (present on Kali, offline, no mic/network):
  run `espeak -s 150 -p 50 "<text>"` in a daemon thread so the UI never blocks.
  Mic STT is OPTIONAL: probe `import speech_recognition, pyaudio`; if present,
  record + `recognize_google`; else fall back to a typed command. Auto-detect so
  the button always works.
  - **"Clean like you talk" = use Piper neural TTS, not espeak.** espeak sounds
    robotic. Install `piper-tts` + download a voice `.onnx`+`.onnx.json` from HF
    `rhasspy/piper-voices` into `tts_voices/`. Wrap `from piper import PiperVoice;
    PiperVoice.load(onnx, json); v.synthesize_wav(text, wav)`, then play with
    `play`/`ffplay`. Multi-voice: discover all `*.onnx` in `tts_voices/`, expose
    `list_voices()`/`set_voice(name)`. Tone-clone: post-process the WAV with SoX
    `pitch <cents>` (cents = 1200*log2(target_hz/base_hz) from the sample's median
    pitch via `sox ... stat` → "Rough frequency" line; that label has IRREGULAR
    spacing, so match on `"frequency" in low and "rough" in low`, NOT the exact
    phrase, or parsing silently fails). Persist `MOON_TONE` to `.env`.

## Pitfalls
- **Textual API drift:** in 8.x, `from textual.worker import get_result` does NOT
  exist and `Worker` is unused — don't import them. Construct `App()` then `.run()`.
  Verify construction headlessly with `python -c "from x import AIOSApp; AIOSApp()"`
  before relying on a display.
- **f-string shell commands:** build tmux/bash command strings by concatenation;
  escaped quotes inside f-strings fail (`SyntaxError`). Shell-quote args for
  `send-keys`.
- **GUI needs DISPLAY:** check `os.environ.get("DISPLAY")`; if unset, the pop-out
  can't open a window — notify instead of crashing.
- **Never block the event loop:** speech, tmux capture, subprocesses → thread or
  worker. Don't `time.sleep` long in `compose`/`on_mount`.
- **Install deps into the SAME venv** the TUI uses, or the agent package's imports
  (pydantic, fastapi, …) will fail when the wall introspects it. One unified venv
  (textual + agent runtime deps) keeps both importable.
- **Dead chat input after a BootScreen.** `push_screen(BootScreen())` on mount
  leaves focus on the splash; when it `pop_screen()`s, the underlying screen
  resumes with focus NOT on the chat `Input` — typed keystrokes land nowhere and
  the UI looks frozen/"nothing happens". Fix: override `on_resume(self)` on the
  `App` and `self.query_one("chat", Input).focus()` there (it fires when the
  screen becomes active again after a screen pops). This was the real root cause
  of a "chat bar does nothing" report that was NOT a brain/model bug.
- **C-library stderr (ALSA/Jack) is NOT caught by `redirect_stderr`.**
  `contextlib.redirect_stderr` only captures Python-level writes; ALSA/Jack/Pulse
  C libraries write device errors straight to **fd 2**, flooding the terminal UI
  on headless boxes with no capture device. Fix: redirect the real fd around the
  mic probe — `fd=os.open(os.devnull,os.O_WRONLY); old=os.dup(2);
  os.dup2(fd,2); try: ...; finally: os.dup2(old,2); os.close(fd);
  os.close(old)`. Apply in `stt_available()` AND the listen loop. Without this,
  `sr.Microphone()` constructs fine but the noise buries the UI.
- **Mic listen loop must not spin on headless.** `sr.Microphone()` may construct
  successfully (so `stt_available()` returns True) while `rec.listen()` always
  fails → an infinite `while` logging "STT error" forever. In the voice loop,
  `if not cmd: mark_stt_unavailable(); notify(...); break` (don't `continue`).
- **Voice mode must reply even with no mic.** If `stt_available()` is True but the
  loop fails, the orb goes silent — "voice mode can't reply". Fix pattern: when
  voice mode is ON, route typed chat through an **in-process** pipeline
  (`BrainPipeline.from_orchestrator(orch).run(prompt)`) instead of only the tmux
  dispatch, then `write_moon(answer)` + `speak(answer)`. Run the async pipeline in
  a worker thread (`asyncio.new_event_loop()` + `loop.run_until_complete`) and
  `await asyncio.to_thread(...)` so the Textual loop stays responsive; the orb
  keeps animating. This makes TTS replies work regardless of mic availability.
- **One-command launcher for the WHOLE system.** Users want `python3 one_file.py`
  to start API/WS + terminal UI + browser orb together. Build a pure-Python
  `run_moon.py` (PEP 668 → no bash): `subprocess.Popen([sys.executable, "-m",
  "uvicorn", "app.api.main:app", "--host", "127.0.0.1", "--port", port])`, poll
  `/health` to know it's up, optionally `webbrowser.open(web/moon_orb.html)`, then
  launch the TUI as a foreground subprocess and `signal.signal(SIGINT, cleanup)`
  to tear the API down on exit. A home-dir `~/moon` shim (`cd project; . venv/bin/activate;
  exec python3 run_moon.py "$@"`) lets it run from anywhere.
- **Stale tmux sessions mask fixes.** An earlier session running OLD code can keep
  running while you debug the new one, so the user reports "still broken". Before
  diagnosing "nothing works", run `tmux ls`, kill ALL `moon*` sessions, launch ONE
  clean instance, and prove the fix by checking it spawns its agent console
  (e.g. `moon_terminal`) — that is unmistakable proof the chat `run_prompt` fired.
- **Verify every `patch()` result by re-reading the region.** A fuzzy
  `old_string` that accidentally includes the NEXT method's signature can merge
  two methods into one (e.g. `on_resume` swallowed `_build_wall`), leaving a
  public method gone while tests stay green (the doctored method still exists,
  just misnamed). After any multi-method edit, `read_file` the boundaries and run
  the targeted test before declaring success.
- **Don't shadow Textual `Widget` internal attributes.** Naming a custom instance
  attr after a Textual internal (notably `self._nodes` — Textual uses it as a
  render-node cache) crashes at **mount** with the misleading
  `AttributeError: 'tuple' object has no attribute '_closing'`. `py_compile` AND a
  construction smoke test (`App()`) do NOT catch it; the pretty traceback even
  prints your own data tuples as `widget_list = ((-0.255, -1.02), ...)` and hides
  the real cause. Prefix ALL custom attrs (`_bnodes`, `_badj`, `_bact`, `_bsig`)
  and never reuse names like `_nodes`, `_closing`, `_styles`, `_pending_*`. If a
  mounting widget throws `'tuple'/'NoneType' has no attribute '_closing'`, grep
  the widget for internal-name collisions first — see `references/textual_neural_orb.md`.

## Textual CSS & layout gotchas (learned the hard way — real render failures)
These crash the app at launch or silently hide the whole UI. Apply ALL of them:

1. **`border` shorthand is invalid.** `border: bottom round #1b6cff;` raises a
   CSS parse error and kills the app. Use the side-specific property:
   `border-bottom: round #1b6cff;`. Same for `border-top/left/right`.
2. **Widget `id` must be a valid CSS identifier — NO colon.** `id="wf:" + w`
   is illegal; every widget with that id fails to mount/style. Use `wf_` + w
   and update the handler (`startswith("wf_")`, `split("wf_", 1)`).
3. **`self.log` / `self.name` are RESERVED `Widget` attributes.** Assigning
   `self.log = RichLog(...)` or `self.name = name` in a custom widget clobbers
   the base class and errors/oddly-behaves. Rename to `self._log` /
   `self.item_name` and update `render()` / `on_click()` accordingly.
4. **The `layers` model is NOT what you'd guess.** If you declare
   `layers: background main overlay`, unlayered content goes BELOW `background`
   (hidden), NOT on top. Correct options:
   - `layers: background base overlay` and put most content in `base` (default
     for unlayered widgets), decorative behind, `overlay` on top; OR
   - `layers: background overlay` and wrap content in a container with
     `layer: overlay`, while decorative full-screen widgets use
     `layer: background` + `position: absolute; width:100%; height:100%;`.
5. **Don't bury a centerpiece behind panels.** A full-screen decorative widget
   (starfield/orb) must sit on `background`; functional panels on `overlay`
   (or `main` above `background`). If the centerpiece is invisible, panels are
   painting over it. This is the #1 "my orb doesn't show" bug.
6. **Empty placeholder containers don't show through reliably.** A bare
   `Container(id="leftorb")` with no children is transparent but can collapse
   to 0 width. Put the decorative widget INSIDE the container as a real child
   (`Container(Orb(id="orb"), id="leftorb")`) and give it `width:1fr;
   height:1fr` so it lays out in normal flow and fills the area. Absolute
   positioning + show-through is fragile; normal flow is reliable.
7. **Headless render verification:** `App().run_test()` is an async context
   manager. `Pilot` is NOT — use `async with app.run_test()` then
   `await pilot.pause()`. Typing into chat: call the real handler
   (`app.run_prompt(...)`), not `Input.action_submit(value)` (takes no arg).
   To spy on side effects without relying on `RichLog.lines` (often empty in
   `run_test`), monkeypatch the downstream call (e.g. `app.ctl.launch = spy`).

## Centerpiece "orb" pattern (MOON look)
**PREFERRED / reference-matching: an irregular 3D POINT-CLOUD NETWORK** — the
look the user actually asked for (matches the @tec.timmy "Three.js particle
orb" from the attached MP4). It is NOT a regular lat/long grid globe. Geometry:
Fibonacci-spiral node distribution over the sphere (~150 nodes), each wired to
its ≤4 **nearest neighbours** (network mesh), plus a few nodes floating **just
outside** the shell for volumetric depth; front nodes render brighter (depth =
`(rz+1)/2`). Signals hop node→node across the network. Full working
`Orb(Widget)` in `references/textual_point_cloud_orb.md`. **Matching a reference
orb from an attachment:** don't guess — `ffmpeg -i vid.mp4 -vf fps=1 frames/%02d.png`
then `vision_analyze` 2-3 frames asking "regular grid globe vs irregular
point-cloud network vs brain?". The user's reference was the **point-cloud
network**; the lat/long wireframe globe is only a simpler approximation.

**Simpler alternative:** a rotating 3D **wireframe globe** (lat/long lattice
`NLAT×NLON`, ~15×26, edges = longitude+latitude neighbours). Same projection
(Y-spin + X-tilt 22° + perspective `f=dist/(dist+rz2)`, Y compressed ×0.55),
front nodes brighter, signals along a longitude band. Code in
`references/textual_wireframe_globe.md`.

**CRITICAL attribute rule (both):** never name an instance attr `self._nodes` —
Textual's `Widget._nodes` is its render cache; clobbering it crashes at mount
with the misleading `AttributeError: 'tuple' object has no attribute
'_closing'`. Prefix custom attrs (`_sph_pts`/`_sph_edges`/`_sph_sig`).
Construction smoke test + `py_compile` do NOT catch it — mount the widget (or
run the TUI) to confirm.

**`set_working(False)` MUST reset to `0.0`, NOT `max(self._working, 0.0)`.**
The orb's busy glow is driven by `self._working` (1.0 = working, eased down by
the `_tick` decay). A common typo is
`self._working = 1.0 if on else max(self._working, 0.0)` — the `else` branch
keeps it pinned at 1.0 forever, so the orb **never returns to idle** (user
reports "orb not idle / stuck working"). Correct form:
`self._working = 1.0 if on else 0.0`. The `_tick` decay then handles smooth
idle↔working transitions; the explicit off is what guarantees return to idle.
Same rule for any `pulse`/`set_listening` busy-flag API you expose.

**Alternative (if the user wants a "brain" specifically):** a **neural-brain
orb** — brain-shaped node network with signals that fire/flow along synapses.
Define two hemispheres + cerebellum as ellipses (`_in_brain` carves a central
fissure), lattice nodes with organic dropout, wire ≤4 nearest neighbours,
animate `[i,j,t,speed]` signals hopping node→neighbour. Same `_nodes`-collision
rule (`_bnodes`/`_badj`/`_bact`/`_bsig`). Code in `references/textual_neural_orb.md`.

Both: `set_interval(0.06, self._tick)`, compose as
`Container(Orb(id="orb"), id="leftorb")` in normal flow (`width:1fr; height:1fr`),
and DON'T shadow Textual internals (see Pitfalls).

## Completion / production-readiness patterns
These turn a working prototype into a "fully completed" terminal the user can
actually live in. All proven in the MOON build.

1. **Right rail MUST be scrollable.** Stacking SKILL WALL + WORKFLOWS + console +
   equalizer + 6 buttons in a plain `Vertical` overflows on short terminals and
   the bottom buttons (GUI/RELOAD/CONFIG/HELP/KILL) get cut off. Fix: wrap the
   rail in `ScrollableContainer(Vertical(...))`, or set `#right { overflow-y: auto; }`.
   Verify by launching at a small tmux pane and confirming every button is
   reachable/visible.
2. **Dedicated ChatPanel (you↔MOON transcript).** Don't dump chat into the raw
   tmux `RichLog`. Add a separate `Static` holding a `RichLog` (`ChatPanel`) and
   write `write_user(prompt)` / `write_moon(reply)` from `run_prompt`, the voice
   loop, and `_maybe_unlock`. Keeps the conversation legible separate from agent
   stdout. Proven via pilot: `[you] ...` / `[MOON] ...` lines appear.
3. **BootScreen rebrand + auto-dismiss.** Show an ASCII banner + animated boot log
   on `on_mount` via `push_screen(BootScreen())`, then `pop_screen()` after the
   last line (small `set_timer` pause). Rebrand it to the agent's name (don't
   leave a stale "J.A.R.V.I.S." splash on a MOON terminal).
4. **Catch import/runtime gaps the suite misses.** `py_compile` only checks
   syntax — a missing `import os` then `os.environ.get(...)` in `__init__`
   compiles fine but crashes at launch (`NameError`), and a test suite that never
   constructs `App()` won't catch it. Add a construction smoke test
   (`def test_app_constructs(): AIOSApp()`) so App `__init__` (and its `os`,
   `math`, etc. imports) is actually executed. This caught a real launch crash.
5. **Auto-open the terminal as the front-end.** The agent shouldn't need a
   separate install step for the UI. Make `install_moon.py` spawn the TUI (force
   `tmux new-session -d -s moon_tui ... run_terminal.py` so the installer
   returns) and add a `moon.py` entrypoint that auto-installs-if-missing then
   opens the TUI. Keep the installer in pure Python (no bash launcher) so the
   whole project is Python-driven.
6. **Lock Mode is a real gate, not a prompt.** The Orchestrator refuses tasks
   while locked; the TUI mirrors it (TopBar 🔒/🔓, chat refuses with the lock
   message). Unlock phrase persisted to a state file so it survives separate
   `main.py run` processes. Verify: locked→refuse (no model call), exact
   phrase→unlock+persist, next msg executes.

## Health-check / audit harnesses (run them, don't trust the suite alone)
A green `pytest` run only proves tests — it does NOT execute every code path.
Add `scripts/_audit_agents.py` + `scripts/_audit_tools.py` (proven in MOON) that
**actually instantiate all agents** and **execute all tools** end-to-end, and
**RUN them** after any deep change. Two gotchas that bit the MOON build:
- **`ToolResult.ok()` requires positional args `tool` and `output`** in this
  codebase (signature `ok(self, tool, output)`). Calling `r.ok()` with no args
  raises `TypeError: missing 2 required positional arguments` and aborts the
  whole audit, hiding real tool results. Call `r.ok(tool=None, output=r.output)`.
- **Audit harness with an in-process pipeline** can itself hit the live model;
  if the local model endpoint blips, the harness "fails" transiently — retry
  once before concluding a regression. The harness is the proof the
  skill-wall tiles + tools actually work, independent of the unit tests.

## File / folder attachment modal (Textual `DirectoryTree`)
To let the operator attach files/folders as context to a prompt, use Textual's
`DirectoryTree` inside a `ModalScreen` — it renders a real, navigable filesystem
picker with zero custom path logic. Proven in MOON `terminal/terminal_app.py`
(`AttachScreen`, `action_attach`, `build_attachment_block`):

- `class AttachScreen(ModalScreen[Path | None])` with `compose()` yielding
  `DirectoryTree(str(start_path), id="tree")` + `Button("📎 ATTACH", id="attach_ok")`
  + `Button("✗ CANCEL", id="attach_cancel")`. `esc` dismisses (returns `None`) for free.
- Capture the selection: `on_directory_tree_file_selected` /
  `on_directory_tree_directory_selected` both set `self._selected = Path(event.path)`
  (so either a file OR a folder attaches — one modal covers both).
- On ATTACH: `self.dismiss(self._selected)`. Wire the result via
  `self.push_screen(AttachScreen(...), callback)` where the callback appends the path
  to `self._attachments` and re-renders a tray (`remove_children()` + `mount(Label)`).
- Build the context block to append to the prompt: folders → bounded `rglob("*")` tree
  (cap ~60 entries); **small (<20KB) text files** → inline contents; large/binary →
  path-only (`(binary/large file, N bytes — path only)`) so context stays sane. Clear
  `self._attachments` after each send so it doesn't leak into the next prompt.
- Add a tray in `compose()`: `Button("📎 ATTACH FILE / FOLDER")` + `Label("📎 ATTACHMENTS")`
  + `ScrollableContainer(id="attach_list")` + `Button("🧹 CLEAR ATTACHMENTS")`, plus a
  `"a"` keybinding → `action_attach`. CSS: give `#attach_list` a fixed `max-height` and
  `overflow` so a long list scrolls instead of pushing the layout.
- **Testability:** refactor the block-builder into a module-level
  `build_attachment_block(attachments: list[Path]) -> str` (not a method) so it's
  unit-testable without an `App` instance — cover empty / small-file-inline /
  large-by-path / folder-tree / missing-file. Verify the modal headlessly with
  `async with app.run_test(): tree = app.screen.query_one(DirectoryTree); await
  pilot.click("#attach_ok")` → `type(app.screen).__name__ == "Screen"` (dismissed).
- **Pitfall:** `DirectoryTree` needs a real filesystem path string (not a `Path`
  object passed positionally is fine, but `str()` it to be safe). On a headless box
  with no `$DISPLAY` the modal still works (it's a TUI widget, not a GUI dialog).

## References
- `references/tmux_voice_snippets.md` — ready-to-copy `TmuxController` + `Voice`
  snippets and the GUI pop-out argv shapes.
- `references/textual_point_cloud_orb.md` — the **preferred** reference-matching
  orb: irregular 3D point-cloud network (Fibonacci nodes + nearest-neighbour
  edges + floating outer nodes), full working `Orb(Widget)` code, the
  ffmpeg+vision_analyze workflow for matching a reference attachment, and the
  browser-canvas mirror.
- `references/textual_wireframe_globe.md` — the simpler rotating 3D wireframe
  globe (lat/long lattice) alternative.
- `references/textual_neural_orb.md` — the **neural-brain** orb alternative
  (brain-shaped node network + flowing signals), full working
  `NeuralBrain(Widget)` code, and the `_nodes`-collision mount-crash gotcha.
- `references/textual_orb_snippet.md` — older particle-sphere variant (sphere
  without the lat/long wireframe), kept for reference only.
- `references/moon_terminal_patterns.md` — completion patterns: scrollable right
  rail, ChatPanel transcript wiring, BootScreen rebrand, Piper voice selection +
  SoX tone-clone, lock-mode integration, and the auto-open installer entrypoint.
- `references/textual_focus_and_stderr.md` — fixing dead chat input after a
  BootScreen (`on_resume` focus), silencing ALSA/Jack C-lib stderr via fd-2
  redirect, and stopping the mic loop from spinning on headless boxes.
- `references/browser_orb.md` — self-contained offline browser orb (canvas
  wireframe globe, no CDN) opened via an `o` keybinding / button; mirrors the
  Three.js reference look without a web framework.
- `references/orb_and_audit_pitfalls.md` — the "orb not idle" `set_working`
  reset bug, the Textual `Widget._nodes` mount-crash, and the audit-harness
  + `ToolResult.ok(tool, output)` pitfalls.
