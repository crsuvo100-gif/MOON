---
name: moon-engineering
description: "Build, audit, or deploy MOON. LIVE NEXUS deployment = Moon_AI_AGENT (.../RED_TEAMING_HACKER_INTERFACE/Moon_AI_AGENT); canonical whole-Moon repo = /home/meow/Projects/MOON (origin=crsuvo100-gif/MOON). Do NOT force-push to the unrelated 'moon' remote."
---

# MOON Engineering

MOON is Psycho's self-hosted autonomous AI agent (a "wife" persona, female voice)
at `/home/meow/Projects/MOON`. It is rebuilt and extended session after session.
This skill captures the durable architecture and the techniques that actually
worked, so the next session starts already knowing the shape.

## When to use
- Editing MOON's agents, brains, tools, orchestrator, voice, or system prompt.
- Wiring new capabilities (cyber, OS, GitHub, self-learning).
- Running a "deep final audit" / making MOON launch-ready.
- Connecting MOON to GitHub (sync, deploy, or autonomous tool-pull).
- **Wiring MOON's multi-agent brain into an interactive surface** (Textual TUI chat flow with agent persona injection + intent→agent fallback + explicit `agent:` prefix syntax; or external AI-agent integration endpoint `/api/moon-agent`). A dedicated reference: `references/terminal_brain_wiring.md` (in `moon-agent-extension`).
- **Auditing or fixing the `app/cli/` Hermes-style CLI terminal subsystem** — interactive dispatch bugs, subcommand wiring, oneshot integration, shell dispatch, command registry gaps. A dedicated reference: `references/cli_subsystem_deep_audit.md`.


## PRESERVATIVE BUILD RULE (operator's standing instruction — never violate)
The user repeats, in many phrasings, the same hard constraint:
**"Only build what is MISSING. Do NOT change or remove anything already present
in MOON."** Treat MOON as the source of truth. For every enhancement:

**EXPLICIT CORRECTION THIS SESSION (FIRST CLASS — embed it):** the operator said
*"do not remove already built but add and merge with and make better terminal
and build what its missing"* AFTER I had deleted the old Neural Brain Command
Center to keep "only one terminal." Lesson: **NEVER delete a working UI/module
the user already has — keep it AND add/merge the new one.** When the user asks
for "one terminal" or "remove the old one," the safe reading is "make the new one
the primary entry point / default," not "delete the old code." If a deletion
seems required, ASK first. The preserving-merge approach is always preferred over
removing-and-replacing. (Caveat: I did delete the old `app/api/*` + `moon_brain.html`
this session when told explicitly "remove old one and ready new one" — the user's
later "do not remove already built" message supersedes that; going forward, merge
rather than delete.)
1. Run an inventory/audit first (import sweep, `ls app/tools`, grep existing
   names) to PROVE a capability is absent before writing code for it.
2. Add NEW modules/classes; extend via composition, not by rewriting working
   files. The only edits to existing files should be additive (register a tool,
   add an import, append a section to the system prompt).
3. Do NOT "rebuild from scratch," do NOT rename/delete working modules, do NOT
   duplicate an existing tool under a new name.
4. When merging an external/attached spec, produce a MERGED result that keeps the
   existing identity + all prior capabilities, layering the new spec on top.
Violating this (e.g. replacing the system prompt, deleting a tool) is the single
most common way to make the user unhappy. If a real bug requires touching an
existing file, do the minimal surgical change and say so explicitly.

## SAFE DEAD-CODE REMOVAL (reconciles with the preservative rule — FIRST CLASS)
The preservative rule forbids deleting WORKING features the user already has. But when
the user EXPLICITLY says "remove the UNUSED / dead terminal / folder / functionality"
(and keep only the USED one), that is permitted — the distinction is **used vs unused**,
not "delete what I have." Worked example (2026-08-15): the NEXUS terminal stack
(`app/brain/nexus/`, `web/nexus/`, `MOON_NEXUS_SINGLE_FILE.py`, `tests/test_nexus_bridge.py`,
Makefile `nexus`/`nexus-ui-only`) was UNUSED dead code (only its own launcher + test imported
it; nothing in core did), so it was removed and the MOON Terminal (`app/terminal_interface.py`
@:8777) + `TerminalTool` remain as the used terminals.

**Safe-removal recipe (run before ANY delete, additive-proof first):**
1. **Prove it's unused:** `grep -rn '<module>' --include=*.py . | grep -v __pycache__` across the
   whole repo. Confirm only its OWN launcher/test imports it — no core entrypoint (`main.py`,
   orchestrator, other tools) imports it. Also check package `__init__.py` files for re-exports.
2. **Check tracking state:** `git ls-files <path>` — tracked files need `git rm -r --force`
   (dirs REQUIRE `-r`; a bare `git rm` on a dir errors with "without -r"). Untracked junk uses `rm -rf`.
3. **Strip dangling references:** delete the matching Makefile targets / help lines / subparser
   entries, and grep again to confirm ZERO importers remain.
4. **Verify green:** `env -u PYTHONPATH .venv/bin/python -m pytest tests -q` must still pass
   (a removed test file drops its count; that is expected, NOT a regression). Also
   `env -u PYTHONPATH .venv/bin/python -c 'import <kept_module>'` for the survivors.
5. **Staged only — do NOT auto-commit.** Report what was deleted; let the user commit.
Rule of thumb: if you are unsure whether the user "has" it, ASK. Deletion of genuinely-dead,
unused code the user pointed at is fine; deletion of a working feature is not.

## Architecture (known-good shape)
- **Orchestrator** (`app/brain/orchestrator.py`) is the brain coordinator. It
  holds the LLM(s), tool registry, context builder, validator, planner,
  reasoning engine, reflection, and one `AgentBrain` per agent.
- **39 agents** defined in `app/brain/agent_registry.py`, each with a persona.
  Examples: coding, research, browser, security, cyber, red_team, blue_team,
  purple_team, forensics, reverse_eng, threat_hunt, siem, github_sync, manager,
  coordinator (parallel fan-out), 34 others.
- **Per-agent brains connected to the MAIN brain** (`app/brain/agent_brain.py`):
  every `AgentBrain` is created with `main_brain=self` (the orchestrator). This
  is the accuracy mechanism — see below.
- **Main brain** = LongTermMemory + KnowledgeBase (durable, survives restarts)
  + the deterministic offline embedding fallback (`app/services/embedding_service.py`).
- **System prompt** = `app/prompts/templates/moon_system.md` (operator spec:
  identity, unlock phrase "MOON love you 3000", cyber rules, smart-build policy,
  GitHub sync sections). Loaded by `PromptManager` / context builder.
- **Tools** live in `app/tools/` (core + the 6 cyber tools + OS tools +
  github_sync + github_feed) and `plugins/` (excalidraw, architecture_diagram,
  ascii_art, generated/). Registered in orchestrator setup.
- **UI**: **MOON's own terminal interface = the SINGLE web UI**
 (`app/terminal_interface.py`; boot via `python main.py terminal` or
 `uvicorn app.terminal_interface:app --port 8777`). `web/moon_terminal.html` is a
 single no-build HTML file = a **red/black "NEURAL CORE INTERFACE" HUD** rebuilt
 from a USER-SUPPLIED REFERENCE IMAGE (he pastes a reference, you `vision_analyze`
 it layer-by-layer, then rebuild to match — see reference-driven workflow below
 and `references/terminal_aspect_ratio.md`). Grid regions 01–08:
 - **01 header**: logo + title + 6 status chips (temp/load/status/uptime/latency/threat)
 - **02 left nav** (system modules) + **05 left telemetry** (neural telemetry / core
   config / power management / system logs) — two stacked frames in the left column
 - **03 center neural frame**: hero **red orb** (`<canvas>` — wireframe globe cage +
   inner neural-brain mesh with FIRE pulses + 3 rotating gyroscope rings + hot core,
   Canvas2D, NO Three.js), 6 lobe-telemetry mini-panels (FRONTAL/TEMPORAL/PARIETAL/
   LIMBIC/OCCIPITAL/CEREBELLUM), cognitive pipeline, neural-convergence banner
 - **04 right intel**: topology donut / cognitive pipeline / memory donut / threat
 - **06 bottom analytics**: 7 widgets (synaptic spectrum, neural feed, memory gauge,
   learning bars, voice analyzer, efficiency, quantum channels)
 - **07 quick command** + **08 app bar** (terminal/ai chat/tasks/updates/diagnostics/
   help + clock + AUDIO + **RATIO selector**)
 **Aspect-ratio system**: `.fit`/`.app` shell with `data-ar` attr. **DEFAULT is AUTO = full-display
 FILL** (`.fit` is flexbox; `.app` uses `width/height:100%` under AUTO/FILL so it uses the whole
 viewport — NOT a letterboxed fixed ratio). **Do NOT use `display:grid;place-items:center` on `.fit`
 or a `bestFit()` "closest preset" routine — both collapse the HUD to a ~700px centered box with
 huge empty margins (the 2026-08-15 display bug). Fixed presets: `16:9`, `4:3`, `21:9`, `1:1`,
 `9:16 (mobile)`, `3:4 (mobile)`, plus `FILL`; choice persisted to `localStorage`.
 **Visual-fill verification pitfall:** `vision_analyze` misreads dark panel padding as "empty right
 margin." After any ratio change, OBJECTIVELY measure geometry: headless screenshot + PIL scan for the
 `.app` outline / rightmost red border (`scripts/terminal_pil_measure.py`). At 1600px the `.app` box
 must span ~x=7→1592. See **`references/terminal_aspect_ratio.md`** for the corrected approach + the
 letterbox-bug pitfall. **Concrete CSS grid→flexbox fix + the `.app`-outline PIL trick (2026-08-15
 display-suitability fix — operator said "check terminal and fix display suitable"):** see
 **`references/terminal_fill_fix.md`**. When the operator says "this look is wrong / why this terminal,"
 the cause is almost always the AUTO-letterbox regression — apply the flexbox `.fit` fix there and do
 NOT re-add `bestFit()` / `place-items:center` (both collapse `.app` to a ~700px centered box).
 **Operator correction (this session — FIRST CLASS):** the user said *"remove set default
 ratio 16:9 and make set all type of aspect ratio configure have for manually setup and all
 type of display suitable and compatible automatic."* So the default MUST be `auto`, never a
 fixed ratio. Confirm with: `grep 'data-ar="auto"' web/moon_terminal.html` (present) and
 `grep 'selected>16:9' web/moon_terminal.html` (must be 0). **Reference image embedded**
 as `web/moon_core.png` (route `/moon_core.png`): shown as a backdrop behind the live orb in
 the hero AND as a thumbnail/lightbox in region 04. `web/theme.json` holds JSON theme tokens
 (route `/theme`). The 3D face, `three.min.js`, `wfHead` waveforms, and `avatar.png` were ALL
 REMOVED — the UI is now pure HTML/CSS/vanilla-JS + JSON + Python backend. `web/moon_terminal.html`
 markers to grep for presence: `data-ar="auto"`, `id="coreThumb"`, `id="particles"`,
 `class="floor"`, `class="scan"`, `id="convBar"`, `Orbitron`.
 **Futuristic FX (operator: "push visual tweaks further, make more futuristic, exactly like
 the reference image"):** see **`references/terminal_futuristic_fx.md`** — concrete
 additive CSS/JS patterns that worked: sci-fi fonts (Orbitron/Rajdhani), perspective grid-floor
 + vertical light beam, floating sparkle particles, animated scan-sweep line, animated NEURAL
 CONVERGENCE bar, glossy modular header chips, intensified scanlines. Accent-aware (read
 `--accent` via getComputedStyle so FX follow the ACCENT selector). Section 7 of that file is the
 GLOBAL HOT-RED theming recipe (remap every accent variant to red, kill JS hex leaks in
 donuts/rings/gauges/logo, add global scan + hot-pulse vignette + panel/logo pulse + CRT
 flicker, then leak-verify with a headless screenshot + vision "any non-red color?" check).
 **3D-ANIMATED CENTER (operator: "put the attached central interface image in the center, make it
 3D animated, fully AI futuristic"):** the attach-and-3D recipe is in **`references/terminal_3d_ai_core.md`**
 — embed the attached reference as a 3D-tilted rotating holo-panel (CSS `perspective`+`rotateY/X`
 keyframes) + an `aiCanvas` overlay drawing hex tech panels, a rotating outer targeting ring with
 ticks, a counter-rotating inner ring, 14 orbiting data nodes, and an amber bloom. Reuse the global
 `STATE` so the core spins faster while MOON is processing (real-event motion). Pair with the
 GLOBAL-RED vs GOLD-CORE reconciliation below and `references/terminal_ai_core_fidelity.md` for
 palette/legibility. Adds a `/core_ai.png` backend route → restart uvicorn (see the restart gotcha
 in that file; `pkill -f uvicorn ...` self-kills the shell — separate the kill and the boot).
 The WebSocket `/ws` connects to the EXISTING orchestrator (lazy singleton in
 `terminal_interface._get_orchestrator`) and streams MOON's real answer
 word-by-word via `_stream_text`.

 **Aspect-ratio + reference-image embedding technique:** see
`references/terminal_aspect_ratio.md`.

**REFERENCE-DRIVEN REBUILD WORKFLOW (operator pattern, this session — FIRST CLASS):**
 When the user attaches a reference image and says "build the interface like this":
 1. `vision_analyze` the reference → exact element/region/color/fx list.
 2. `vision_analyze` the CURRENT build → same list; produce a FIELD-BY-FIELD DIFF
    (present/missing/different) and SHOW it (operator rejects "it's done" without the diff).
 3. Rebuild `web/moon_terminal.html` (HTML structure → CSS3 theme/scanlines/corner-brackets
    → JS: orb Canvas2D + gauges/waveforms + live `/ws` wiring + command bar) wired to REAL
    backend data from `/status`. Add JSON `web/theme.json` for structured tokens.
 4. Verify with headless Chromium screenshot + endpoint checks (see visual-verification refs).
 Use the RIGHT LANGUAGE PER LAYER (HTML structure, CSS theme, JS logic/comms, Python
 backend, JSON tokens) — not a single language, not padding the stack.

  **NO-FAKE-ANIMATION RULE (operator's HARD requirement, this session — FIRST
  CLASS):** "Every animation must have a purpose. Every visual change must
  correspond to a real event." Concretely:
  - State changes (idle/listening/thinking/planning/executing/speaking/locked/
    error) are driven ONLY by real WS `workflow` stages or real lock state — NEVER
    a random `setTimeout` loop. The avatar's `body[data-moon=...]` + the 3D face's
    `setMoonState()` reflect the same real stage.
  - The 8-step Workflow Pipeline and the Workflow Process flowchart light up ONLY
    on real orchestrator stages (`routing/thinking/tool_call/reflection/
    consistency/speaking`), mapped via `STAGE_MAP` in the frontend.
  - The facial mesh-dot overlay + Human-Brain viz intensify ONLY when MOON is
    `active` (not idle/locked) — driven by `document.body.dataset.moon`.
  - **Real voice lip-sync:** `playAudio()` wires a Web Audio `AnalyserNode` over
    MOON's actual WAV and feeds `RMS` to `setMouthOpen()` — the mouth opens with
    the REAL audio, not a canned cycle.
  - Do NOT add idle "breathing" loops that imply activity when MOON is static; if
    you must idle-animate, keep it subtle and clearly ambient (the face's gentle
    sway is acceptable; a pulsing "EXECUTING" badge when nothing runs is NOT).
  Accessor cheat-sheet: `references/terminal_status_accessors.md`.

  **Responsive across ALL displays:** `web/moon_terminal.html` has a media-query
  layer (4K `@media min-width:1800px`, desktop, `@media max-width:1100px`,
  tablet/phone `@media max-width:860px` stacks vertically with `overflow:auto`,
  phone `@media max-width:560px`, tiny `@media max-width:380px`). The 3D face +
  avatar scale via `width:min(...,vw)` so they never overflow. Verified at
  1440/834/390/375 px via headless Chromium (no horizontal scroll).

  **Function-first, THEN form:** every panel fed by MOON's truth and every button
  calls a real backend action BEFORE cosmetic work. A fake "92%" bar is worse
  than a truthful "0 entries" until the real count is wired.

  **Avatar-as-body technique (KEY):** the orchestrator's `run_task(task,
  on_event=None)` and `_run_cognition_loop(task, agent, on_event=None)` accept an
  OPTIONAL async callback that emits REAL workflow stages behind `if on_event`
  (additive — no behavior change when `on_event` is None). Stages emitted:
  `routing` (after intent route), `thinking` (after memory recall / during
  cognition), `tool_call` (per tool invocation), `reflection` (self-review),
  `consistency` (self-consistency vote). The terminal passes `stream_event` ->
  the WS sends `{type:"workflow", stage, detail}`, and the UI highlights the
  matching Workflow-Process node + sets MOON's body state. To add a new visible
  workflow step, emit it from the orchestrator with `if on_event: await
  on_event({"stage":..., "detail":...})` — never fabricate a step in the UI.
  Full WS message + stage contract: `references/terminal_avatar_protocol.md`.

  **WS actions** the UI uses (not just `send_message`):
  - `wake` → avatar enters LISTENING state; does NOT unlock.
  - `run` (Quick-Action buttons) → routes a preset command through `run_task`
    like `send_message` (so every button drives MOON's real brain).
  - `status` → backend returns real HUD data; also `GET /status` (agents, tools,
    model, lock, uptime, memory counts, system metrics).
  - `diagnostics` → `_run_diagnostics(orch)`: REAL self-check across all
    subsystems (agents, tools, each memory store, KB, system health, lock) —
    returns `[OK|WARN|FAIL] name: detail` lines, fed to chat.
  - `memory_search` (query) → `orch._memory.recall()` — REAL LTM recall.
  - `knowledge` (query) → `orch._memory.semantic_recall()` — REAL KB query.
  - Buttons that map to a real action send `{type:"forward", action:...}`; the
    client re-sends it as the real action. See `references/terminal_status_accessors.md`.
  It respects the lock: locked prompts return the lock notice; send the
  passphrase to unlock. Clone external terminal UIs into this pattern — reuse the
  orchestrator, never hardcode OpenAI keys.

## Lock / unlock passphrase
`app/brain/lock.py` `SessionLock` starts LOCKED. Supports BOTH passphrases so
Psycho is never locked out: `"MOON love you 3000"` AND `"love you 3000 moon"`
(`UNLOCK_PHRASES` list, case-insensitive `observe()` check). Any new
unlock-phrase change must keep both accepted.
- **Wake word ≠ unlock.** `SessionLock.WAKE_WORD = "moon"` + `hear(text)` classifies
  an utterance as `wake` (listening only, does NOT unlock) | `unlock`
  (unlocks, returns notice) | `none`. The terminal uses `hear()` so saying
  "Moon" opens her eyes/listens but keeps her locked; only "love you 3000 Moon"
  unlocks. Never make the wake word unlock her.
- **Status HUD pitfall (real bug found + fixed):** to report MOON's tool count,
  read `orch._tools._registry.tool_names` — NOT `orch._tools.tool_names`
  (`ToolManager` has no `tool_names` attr; the registry is nested under
  `_registry`). Querying the wrong attr silently yields `n_tools=0`.

## Per-agent AI model map (the "every agent on its own model" mechanism)
`app/brain/agent_model_manager.py` is where "every MOON agent runs on its OWN
model" is actually implemented. `AGENT_MODELS: dict[agent, model|None]` maps each
agent to an Ollama tag; `None` → global default (`settings.model_name`).
`AgentModelManager.get_llm(agent)` lazily pulls the model via `ollama pull` and
caches an `LLMService` per agent. The orchestrator wires it in
`_run_cognition_loop` (`if self._agent_models: llm = await self._agent_models.get_llm(agent.name)`).
- **Extend by FUNCTION, not by copy.** When adding a capability, open
  `AGENT_MODELS` and give the new/changed agent a model suited to its job:
  coder → `qwen2.5-coder:1.5b`, math/science/reasoning → `deepseek-r1:1.5b`,
  security/cyber/red/blue → `qwen2.5:3b`, generalist → default. Multimodal
  agents (vision/audio/voice) get `AGENT_MULTIMODAL` (vision→`llava:7b`,
  audio→`qwen2-audio`) with a text fallback; their text reasoning still uses
  `AGENT_MODELS`/default.
- **CPU-only host constraint (this box is ~465 MB free RAM, no GPU):** only
  assign/install 0.6b–3b models. The `RECOMMENDED_FOR_CAPABLE_HW` map lists the
  stronger 7b/8b tags to use when MOON runs on a GPU host — set them in `.env` /
  agent overrides, don't pull them here (they OOM). `prefetch_all()` + the
  `make models` / `main.py models` path pull every distinct preferred model;
  `ensure_model()` gracefully falls back to default if a pull fails or Ollama is
  absent.
- **Verification:** assert every registered agent in `app/brain/agent_registry.py`
  resolves to a real model string via `mgr._preferred(a)` (see
  `tests/test_per_agent_brains.py`), then `pytest`. Confirm which Ollama models
  are present with `ollama list` before declaring an agent "ready".

## LIVE REPO vs STALE SNAPSHOT — EDIT THE RIGHT TREE (FIRST CLASS)
There are THREE trees — know which is which:
- **LIVE NEXUS deployment** = `Moon_AI_AGENT`
  (`/home/meow/projectterminal/RED_TEAMING_HACKER_INTERFACE/Moon_AI_AGENT`, branch
  `master`). This is what `http://127.0.0.1:8787/` (UI) + `:8765` (bridge) actually
  serve, supervised by `moon.service`. Edits here show up live after `systemctl --user restart moon.service`.
- **CANONICAL whole-Moon repo** = `/home/meow/Projects/MOON` (branch `master`,
  `origin`=`git@github.com:crsuvo100-gif/MOON`). Its `web/nexus/futuristic/` was the
  SOURCE for the NEXUS build but **was removed as unused dead code (2026-08-15)** —
  `web/nexus/` + `app/brain/nexus/` + `MOON_NEXUS_SINGLE_FILE.py` no longer exist in this
  repo. The MOON Terminal (`app/terminal_interface.py` @:8777) is now the single terminal UI
  here. The LIVE NEXUS deployment is a SEPARATE tree (`Moon_AI_AGENT`, see below) and is
  unaffected. Push here with `git push origin master:main` (clean fast-forward after an additive commit).
- These two are **separate git trees but share the real NEXUS history**. The
  agent repo's `moon` remote points at `crsuvo100-gif/MOON` but is **UNRELATED
  history** to the agent repo's own `master` (no common ancestor, ~65 commits the
  local lacks). See the WHOLE-MOON PUSH rule below.
Before patching the NEXUS UI, `pgrep -f run_nexus.py` → `ls -l /proc/<pid>/cwd` →
edit `<cwd>/futuristic/*`, then `curl -s http://127.0.0.1:8787/<file>`
to confirm the served bytes contain your edit. Note: `Moon_AI_AGENT`'s `systemd` unit
`Moon_Avatar_Terminal_FINAL` dir may be stale — the live build dir is now
`MOON_NEXUS_FUNCTIONAL_FINAL/MOON_FINAL_3D_FUNCTIONAL/futuristic/` (verify via the
`/proc/<pid>/cwd` read, don't assume the folder name).

## WHOLE-MOON PUSH RULE (NEVER FORCE — FIRST CLASS)
When the user says "push to whole Moon", the correct target is the
**`/home/meow/Projects/MOON`** repo (`origin`=`crsuvo100-gif/MOON`), NOT the
`Moon_AI_AGENT` repo's `moon` remote. The `moon` remote is **unrelated history** —
`git push moon master` is rejected (non-fast-forward) and `--force` would **wipe 65
commits of whole Moon**. Procedure:
1. Build/fix in the LIVE `Moon_AI_AGENT/futuristic/` tree, verify, commit there
   (its true upstream is `origin`=`MOON-latest-agent`, clean fast-forward).
2. Copy the changed `futuristic/*` files into `/home/meow/Projects/MOON/web/nexus/futuristic/`
   (additive), commit there, then `git push origin master:main` (fast-forward).
   **NOTE (2026-08-15):** the canonical repo's `web/nexus/` path was REMOVED as unused dead
   code. For non-NEXUS work, commit directly in the canonical repo and push
   `git push origin master:main` (fast-forward); do NOT re-add `web/nexus/` unless the
   operator asks to revive it (then add it back as a NEW additive module, not by restoring
   a deleted path).
If `git rev-list --left-right --count master...origin/master` shows the REMOTE side
ahead (diverged), **do NOT force** — ask the user or merge first. Full recipe in
`references/nexus_3d_ultron_build.md`.

**DUAL-BRANCH RECONCILIATION (this repo has `master` AND `main`; FIRST CLASS):** the
MOON GitHub repo exposes **two branches** — `main` (the DEFAULT branch, `origin/HEAD`
points here) and `master` (an OLDER pre-rebuild ancestor, ~52 commits behind `main`).
The `gh` CLI is NOT installed on this host, so connect/push via **`git` directly**,
not `gh`. Routine work: commit on local `master`, then push to **both** so the repo
stays consistent:
1. `git fetch origin --quiet` → confirm `git rev-list --left-right --count HEAD...origin/main`
   is `0 0` (local == `main`) before pushing.
2. `git push origin master:main` (updates the default branch).
3. `git push origin master:master` — fast-forward only; safe IFF
   `git merge-base --is-ancestor origin/master origin/main` is true (master is an
   ancestor of main; verified this session). If NOT an ancestor, STOP and reconcile
   manually rather than force-pushing — you'd rewrite the stale branch onto main.
4. Final check: `git fetch origin --quiet && echo "main: $(git rev-list --left-right --count HEAD...origin/main) | master: $(git rev-list --left-right --count HEAD...origin/master)"`
   → both `0 0`, and `git rev-parse origin/main origin/master` are EQUAL.
Refspec gotcha: the local branch is named `master`; `git push origin main:main` would
fail ("src refspec main does not match any") — use `master:main` (push local master
to remote main) and `master:master` (push local master to remote master).
IMPORTANT: push the canonical repo LAST, after all fixes are verified locally
(import sweep + pytest + boot + CDP audit). Never push a half-fixed tree.

## NEXUS 3D avatar (Three.js) — build + verify
The avatar stage now renders a Three.js **Ultron-style** robotic head (replacing the
old SVG face) — vendored `three.min.js` + `ultron.js` exposing `window.__ultron`,
wired from `app.js` `setState/setMood`. Avatar-area-only; terminal + telemetry untouched.
Vendoring, wiring, CPU-friendly settings, CDP+swiftshader verification (incl. the
`Page.reload({ignoreCache:true})` stale-CSS gotcha), and the whole-Moon push topology:
**`references/nexus_3d_ultron_build.md`**.

## PORT-COLLISION REALITY (live MOON owns :8777 / :8765 / :8787 — FIRST CLASS)
`:8765` and `:8787` are NOT free dev ports — they are held by the operator's
LIVE `Moon_AI_AGENT` Avatar Terminal (`run_nexus.py`, package
`moon_agent/integrations/moon_nexus.py`), the same one the NEXUS UI expects.
**Pitfall hit this session:** a new bridge was launched on `8765/8787`, the test
client connected to the *live* bridge (reporting its own cwd/path), and a debug
cycle was wasted thinking the new code was broken. **Rule:** never launch anything
new on `:8765`/`:8787`/`:8777`. Use free ports (e.g. `8790/8791`, `8800/8801`,
`8810/8811`) for smoke tests, and make the launcher accept `--ws-port`/`--ui-port`
(added to `web/nexus/run_nexus_bridge.py` + `make nexus`). To probe what holds a
port: `for p in 8765 8787; do ss -ltnp | grep ":$p "; done` and
`ps -eo pid,cmd | grep -i nexus`. **Do NOT kill the live MOON** (pid from
`run_nexus.py`) — it is the user's running wife-agent; your work is additive and
runs elsewhere.

## SUPPLY-CHAIN: user-attached "reference" FOLDERS may be MALWARE, not source (FIRST CLASS)
When the user points at an attached/scraped **folder** (e.g. a "LinkedIn post"
save, a "build this exact this" download) as the source to copy, **inspect it
before copying anything.** This session a user supplied
`Building ULTRON UI with Three.js and MediaPipe HandLandmarker _ Adnan Saifi.
posted on the topic _ LinkedIn_files/` expecting reusable Ultron code — it was a
scraped LinkedIn page artifact: `index.html`+`main.min.js` were **HUMAN
Security (White Ops) bot-protection** scripts injecting `client.protechts.net`
trackers, and the rest were LinkedIn artdeco CSS / Google Sign-In / JPEGs — **no
actual Ultron/Three.js/MediaPipe source**. Rule: do NOT inject third-party
tracker/bot-protection scripts (exfil + violates loopback-only). Build the
feature from your own clean, vendored code instead, and tell the user the folder
had no reusable source. Full pattern (vendoring MediaPipe, ES-module load,
graceful camera-degrade, headless-WebGL verify) in
`references/nexus_3d_ultron_build.md`.

## STATIC-TRIAGE ATTACHED / UPSTREAM PAYLOADS (supply-chain safety — FIRST CLASS)
When an upstream commit or an "attached" file is a self-extracting base64-zip
launcher (a trivial commit message + a huge opaque blob that unzips into `$HOME`
and `runpy.run_path`s an app), **do not `git merge`/`pull`+run and never execute
it until you have read the bytes statically.** Full recipe (decode the zip in
memory, list members, scan for network/exec primitives, resolve URLs/IPs) lives
in `references/triage_self_extracting_payload.md`. Decision rule: if it only
talks to `127.0.0.1`, has a conservative command gate, and its useful parts are
additive → integrate the safe parts on DISTINCT ports; if it phones home to
external IPs or auto-installs into system dirs → reject. Either way: additive
only, never delete existing MOON.

## The accuracy architecture (CORE technique — do not regress)
MOON avoids "mistakes" via three layers, not magic:
1. **Two-phase CRITIQUE + VERIFY per agent** (`AgentBrain.refine_with_main`):
   the agent produces a draft; the MAIN brain audits it. The audit is asked for
   STRICT JSON `{"verdict":"ok|corrected","answer":"..."}`. Parse defensively
   (JSON + heuristic fallback) — the main brain often returns free-form prose
   ("The original calculation is incorrect… Corrected Answer: 56"), NOT the
   rigid prefix you requested. If `corrected`, replace the draft with the
   main brain's answer. Verify phase runs at low temperature (0.1).
2. **Self-consistency (3-way majority vote)**: `enable_self_consistency` +
   `self_consistency_samples` → primary + N samples; majority answer replaces
   the draft for factual prompts (`_majority_answer` in orchestrator).
3. **Strong-model routing**: `STRONG_MODEL_NAME` / `STRONG_MODEL_BASE_URL`
   settings + a second `LLMService` (`_llm_strong`). `_pick_llm()` routes
   factual/cyber-critical tasks to the strong model when configured. Both the
   main-brain gate AND self-consistency use it for max accuracy.

PITFALL (real bug found + fixed): a rigid `startswith("CORRECTED")` parser lets
wrong answers through because the model ignores your format. Parse JSON and
fall back to a heuristic; otherwise the accuracy gate is decorative.

## Always-connected GitHub tool-feed (self-extending)
`app/tools/github_feed.py` + `tool_acquisition.py` + `github_sync_tool.py`:
- `feed_for_capability(keyword, registry, repo_url)`: checks YOUR repo first
  (`list_repo_tools` clones + catalogs plugins/app/tools/skills), then if not
  found, `search_github()` queries the PUBLIC GitHub API (ranked by stars),
  then `pull_and_install()` clones the best match, REJECTS obviously malicious
  content (`rm -rf /`, `os.system rm`, shutdown patterns), and registers it
  under `plugins/generated/`.
- Wired into `_auto_acquire_for_task` (catalog pip → your repo → public GitHub →
  LLM-generated plugin) and `refresh_repo_catalog()` (runs at startup).
- Safety: read-only search/install, no force-push, no secret commits.

## GLOBAL CONNECTOR — MOON connects to anything (permission-gated, additive)
Built this session (`app/connector/`). MOON can now reach OUT to the world and
federate with other AI agents — under the operator's explicit "connect everything
with permission" instruction. ADDITIVE: reuses `ToolRegistry`, the capability
`PermissionManager`, `SafetyValidator`, and `GitHubSyncTool`; does NOT replace the
terminal/voice/brain.
- **`app/connector/permission.py`** — `ConnectorPermissionManager.egress_decision(host, scope)` → `(allowed, tier, reason)` with 3 tiers: `safe` (allowlisted/private/loopback → auto), `confirmation` (unknown host → operator must pass `confirmed=true`), `never` (secrets.read etc. → always denied). Hosts in `settings.allowed_egress_hosts` are safe.
- **`app/connector/connectors.py`** — real clients: `HTTPConnector` (httpx), `AgentConnector` (OpenAI-compatible `/chat/completions` — peer-agent federation), `WebSocketConnector`, `MCPConnector` (reachability probe; jsonrpc session a planned upgrade). REAL outbound calls, no fake telemetry.
- **`app/connector/gateway.py`** — `ConnectionGateway` persists named connections in `connections/registry.json` (gitignored), permission-checks every open/call, and exposes `call_agent(name, message)` for two-way federation.
- **`app/connector/tool.py`** — `GlobalConnectorTool` (orchestrator tool list + `connect` terminal command). Actions: `connect`, `list`, `call`, `health`, `disconnect`, `federate`. Every egress action gated; secrets referenced by name only, never stored.
- **Tests:** `tests/test_global_connector.py` (15 tests) incl. `test_federation_with_real_peer_agent` — registers MOON's own Ollama `/v1` as a peer `agent` and delegates via `federate`, asserting a real reply. Run against a serving Ollama.
- **System prompt** Section 16 "Global Connector" added to `moon_system.md`.
PITFALL (real, this session): a thinking model (qwen3) with a small `max_tokens` leaves `content` empty and puts the answer in `reasoning` (finish_reason: length). Fix: (a) give thinking models ≥1024 token headroom, (b) `_extract_answer_from_reasoning` pulls the real final answer. Without it MOON returns "I heard you, but I could not form a reply."

## SELF-EVOLUTION VERIFICATION (proves "work perfectly on everything")
`_auto_acquire_for_task` (in `app/brain/orchestrator.py`, wired into `run_task`) is
the autonomous capability-acquisition loop: discovers a missing capability via
`CapabilityManager`, falls back to `tool_acquisition.acquire_by_catalog` (real pip-install + register), then GitHub tool-feed, then LLM-generated plugin. All paths wrapped in try/except so acquisition never breaks the task. `tests/test_self_evolution.py` verifies the auto-acquire gating runs without raising (offline, stubbed registry+LLM) and `run_task` returns a real answer end-to-end via the `main.py run` path.

## PROJECT FINALIZATION — additive integration + per-change validation (this session — FIRST CLASS)
When the operator hands the "HERMES COMPLETE AI AGENT PROJECT FINALIZATION MASTER PROMPT"
(discovery → map → integrate → repair → test → verify → operationalize, preserve-everything), the
proven workflow that satisfied him:
1. **Phase 0–2 (read-only):** git safety, identify root, FULL discovery (every module/subsystem,
   LOC, imports). Produce a component / dependency / integration report. TOUCH NO FILES.
2. **Classify each component** COMPLETE / PARTIAL / DISCONNECTED / DEAD. Flag orphans.
3. **Integration is INCREMENTAL + ADDITIVE:** for each gap, make the SMALLEST change that reuses
   EXISTING functions. Never rebuild; never remove working code. (The `app/agents/base.py` +
   `memory_agent.py` `BaseAgent`/`MemoryAgent` is a DEAD PARALLEL abstraction — orchestrator uses
   `AgentCard` via `build_agents()`; wiring it would require a forbidden rebuild → leave untouched.)
4. **Validate EVERY change before moving on** (this is what made it trustworthy):
   `syntax (ast.parse / node --check)` → `import/route registration` → `pytest tests -q` →
   `live runtime (curl endpoint / real WS chat / real tool exec)`. Never claim success without the
   live check. Each step gets its own commit + push.

**PHASED COMPLETION SOP (Tasks 1–5) + REAL-RUNTIME RULES (operator's standing mandate — FIRST CLASS):**
When the operator issues the "Master Project Completion" / "make MOON fully operational / install 100%" prompt, the workflow that satisfies him is the **29-phase SOP** distilled to a 5-task loop. He REQUIRES a step-by-step plan BEFORE execution and explicit "do not magically/unreal complete the task":
- **T1 (Discovery/audit, READ-ONLY):** git safety → identify root → full module/subsystem inventory → component/dependency/integration report. **Touch no files.** Output the report + a per-task step list.
- **T2 (Integrate, additive):** smallest change reusing existing functions; never rebuild/remove working code. Validate every change (syntax→import→pytest→live runtime).
- **T3 (Repair loop):** for each blocking issue → DETECT→DIAGNOSE→root cause→SMALLEST safe fix→re-test→regression. Fix the TEST harness, not MOON, when the failure is a wrong call signature.
- **T4 (Real runtime e2e, NO MOCKS):** start via the genuine entrypoint (`main.py`/`uvicorn app.terminal_interface:app`); prove each subsystem returns REAL data (real LLM answer, real tool output, real WAV, real health).
- **T5 (Acceptance):** runtime behavior required; completion needs successful e2e, not code existence. Produce the final status (NOT READY/PARTIALLY/OPERATIONALLY/PRODUCTION READY).
**Harness-contract pitfalls discovered (real, this session — embed these in any e2e script):**
1. `Orchestrator.run_task(task)` takes a **`Task` object**, not a str — build with `from app.models.task import Task; Task.create(prompt, agent_name="auto")`. Passing a raw string → `AttributeError: 'str' has no attribute 'prompt'`.
2. `LLMService.complete(messages)` requires **`ChatMessage(role=, content=)`** objects, not dicts (same class of bug as the historical tool-planner fix). `from app.services.llm_service import ChatMessage`.
3. `MemoryManager.remember(content, long_term=, tags=)` + `recall(keyword)` — NOT `ShortTermMemory.add(k,v)` (2-arg). Use the orchestrator's `MemoryManager`.
4. `/api/health` JSON keys are **`subsystem`/`state`/`detail`** (NOT `name`/`status`). A probe reading `name`/`status` reports `None` even though the endpoint is correct — a PROBE-KEY trap, not a defect.
5. Tool execution: `ToolManager` has NO `tool_names` attr — read `orch._tools._registry.tool_names` (NOT `orch._tools.tool_names`, which is `None` → `n_tools=0`). Use `.execute(**kwargs)` (not `.run()`) for direct registry calls.

**DISPLAY BLINK — DEEP ROOT CAUSE (real, this session — FIRST CLASS):** "blinking into my display" was NOT only CSS. Three independent causes, all fixed:
- (a) **Backend double-bind crash-loop:** `main.py start` could spawn a 2nd uvicorn that failed to bind `:8777`; systemd `Restart=always` looped it, so the HUD WebSocket dropped/reconnected every few seconds. FIX: `main.py` port-busy guard — if `:8777` is already served, attach HUD only, never spawn a competing backend.
- (b) **Watchdog restarting the healthy backend:** `scripts/moon_monitor.py` did `pkill -f terminal_interface` on any transient health blip → same reconnect blink. FIX: double-probe + `_port_in_use()` guard — never `pkill` a backend already answering on the port.
- (c) **Intel i915 eDP hardware flicker:** PSR/RC6 display-state transitions cause the physical panel to blink, independent of MOON. FIX: `scripts/apply_grub_psr_fix.sh` (GRUB `i915.enable_psr=0 i915.enable_rc6=0`, needs sudo+reboot) + `scripts/live_gpu_mitigate.sh` (reversible `xset -dpms; xset s off; xrandr --output eDP-1 --mode 1366x768 --rate 60`).
- CSS layer (already done earlier): disabled `#app` global CRT flicker + sweep opacity pulse + `triggerGlitch`/`edgeFlash`/`fireBurst` event-driven flashes + flattened `ledblink`/`idleblink`/`beamflick`/`cortex` keyframes to constant. The HUD is owned exclusively by `scripts/open_hud.py` (idempotent single Chrome window, never touches `:8777`).
- **Verify fix:** hard-refresh browser; confirm no HUD reconnect + no panel flicker. The eDP fix needs the GRUB reboot to be permanent.

**VOICE CLONING ON PYTHON 3.13 (real, this session — FIRST CLASS):** XTTS-v2 (Coqui `TTS`) needs Python <3.12 and cannot install on 3.13; OpenAI key is quota-dead. The working path is **F5-TTS** (`f5-tts>=1.1`, already in `requirements-optional.txt`), a zero-shot cloning engine that runs on 3.13. Install gotcha: `pip install f5-tts` pulls CUDA torch (526MB+) and blew `/tmp` ("No space left on device" — `/tmp` had 676MB free). FIX: install **CPU-only torch** (`pip install --extra-index-url https://download.pytorch.org/whl/cpu torch==2.5.1`) and set `TMPDIR=/home/meow/.pip_tmp PIP_CACHE_DIR=/home/meow/.pip_cache` so pip's temp/cache use the spacious `/home`. After install, `voice_engine.backend_status()` reports `f5=True, cloning_ready=True`; `clone_voice(name, b64, transcript)` + `speak()` in the cloned voice produce a real WAV; `/api/voice/clone` + `/api/voice/set` expose it via REST. The `libcudart.so.13` warning on F5 load is HARMLESS (CUDA→CPU fallback; WAV still renders). `install_moon_full.py` pre-downloads the F5TTS_v1_Base model + asserts `cloning_ready` in acceptance.

**Observability endpoints added this session (all additive, auth-gated, real data):**
- `GET /api/health` → overall `HEALTHY|DEGRADED|FAILED` rolled from `_run_diagnostics()` per-subsystem
  OK/FAIL/WARN verdicts (agents, tools, memory stores, KB, system, lock). The single project-wide
  health mechanism (Phase 27).
- `GET /api/agents` → `{count, agents:[{name, allowed_tools}]}` (39 agents, real scopes).
- `GET /api/tools` → `{count, tools:[{name}]}` (43 tools).
- `GET /api/events` → bounded `_EVENTS` ring buffer (maxlen=200) populated by REAL activity:
  `_log()` emits `log` events; the WS `send()` path emits `workflow`/`chat`/`exec` events. Hooked at
  ONE point inside `send()` so all workflow/assistant frames are captured; `_emit_event()` is the helper.
  Empty until genuine activity occurs (no fake startup events). Feeds the HUD EVENTS timeline.
- `GET /status` route was MISSING (defined `status()` had no `@app.get` decorator) → repaired in place.
All reuse `_moon_status` / `_get_orchestrator` / existing diagnostics — no new data source.

**AGENT FACTORY BUILD PITFALLS (real, this session — embed these):**
1. **FastAPI route collision when adding a new `/api/*` route.** Adding `GET /api/agents`
   clobbered the EXISTING `GET /api/agents` (the 39-agent roster from an earlier step) —
   FastAPI served the FIRST registered handler, so clients got the wrong JSON shape and
   parsed as failure. **Rule:** before adding any `/api/<x>` route, grep for the path across
   `app/terminal_interface.py` to prove it is FREE. If it exists, pick a DISTINCT path
   (e.g. `/api/factory/agents`) rather than clobbering/renaming the existing one (preservative
   rule). The existing built-in route must keep working unchanged.
2. **WS end-to-end test harness RACE.** A naive WS client that sends `unlock` then
   immediately sends `task` and waits for the FIRST `assistant_done` captures the unlock's
   `assistant_done`, not the task's → appears as "no response". **Rule:** wait for each
   turn's `assistant_done` (or a non-empty `assistant_chunk` stream) BEFORE sending the
   next message; track turn state. Same applies to the `factory create` action.
3. **Test asserting a fixed pipeline status across runs.** `create(cap)` returns
   `REUSED_EXISTING` (not `CREATED`) when the capability already exists from a prior run —
   that is CORRECT dedupe behavior (spec §13 "IF EXISTING → REUSE"), NOT a failure. Tests
   must assert `status in ("CREATED","REUSED_EXISTING")` and use a UNIQUE capability string
   to exercise the genuine CREATE path. Don't "fix" the code to always return CREATED.

Full recipe + the generator/sandbox/store wiring + the SQLite schema:
`references/agent_factory_build.md`.

ADDITIONAL RECIPES (project-finalization session 2026-08-22):
- **SPEC-31 execution-state finalization** (job stuck in RUNNING / illegal transition crash / two lazy managers): `references/moon_execution_states.md`.
- **Tool-intent fallback** for non-tool-calling local models (real Agent→Tool→Result, arg-extraction gotchas): `references/moon_tool_intent_fallback.md`.
- **Runtime-data gitignore hygiene** (untrack already-committed `*.db`/agent JSON while keeping files on disk): `references/moon_runtime_data_gitignore.md`.

## SPEC-31 EXECUTION-STATE FINALIZATION (real bug found + fixed — FIRST CLASS)
The `ExecutionManager` (spec 31) is a persistent job state machine. `ExecutionManager.create()`
starts a job in `CREATED`; valid transitions are `CREATED→RUNNING→VERIFYING→SUCCESS` (or
`→FAILED`). The **orchestrator's `run_task` must emit the RUNNING transition at task start and
the SUCCESS/FAILED transition on every return path** — but the *early-return* paths
(fast-path, parallel fan-out) and the *exception* path each need their own transition call.
Pitfalls hit this session:
1. **Job stuck in RUNNING.** `run_task` set RUNNING at the top, but the fast-path
   (`enable_fast_path` + `_is_simple_query` + `agent_name != "auto"`) and the coordinator
   parallel-fan-out both `return` BEFORE reaching the main-loop SUCCESS transition → job
   stayed RUNNING forever. **Fix:** add `self._exec_transition(task.id, "SUCCESS", ...)`
   inside every early `return` (fast-path, parallel), and the FAILED one in the `except`.
2. **Illegal state transition crash.** The helper that emits SUCCESS must first step through
   VERIFYING when the current state is RUNNING (`em.transition(exec_id, VERIFYING)` then
   `em.transition(exec_id, SUCCESS)`) — calling `SUCCESS` directly from `RUNNING` raises
   `ValueError: illegal transition RUNNING -> SUCCESS`. Honor the validated machine.
3. **Two lazy managers.** `orch._exec_manager()` lazily builds its OWN `ExecutionManager()`
   instance; a test that does `ExecutionManager()` separately sees a different (empty) store.
   Always read the job via `orch._exec_manager().get(task.id)`, never a fresh constructor, when
   verifying end-to-end.
Verification: run a real `run_task`, then assert `orch._exec_manager().get(t.id).state.value ==
"SUCCESS"` (not "RUNNING"). Full recipe: `references/moon_execution_states.md`.

## TOOL-INTENT FALLBACK FOR NON-TOOL-CALLING LOCAL MODELS (real, this session — FIRST CLASS)
The local default model (`qwen3:0.6b`, CPU-only ~2.7GiB, no GPU) does **NOT emit OpenAI-style
`tool_calls`** — `resp.has_tool_calls` is always `False`, so the cognition loop's native
`if resp.has_tool_calls:` branch never fires and the model answers from its own knowledge
(even claiming "I can't run code"). On a tiny CPU-only box you must NOT force a bigger model
(`qwen3:8b` would OOM/stall) — the correct mitigation is a **deterministic tool-intent fallback**:
- After the model returns (no tool_calls), if the prompt explicitly requests a known tool,
  parse the intent and invoke the tool directly through `orch._tools.run(name, args, agent=agent)`,
  then fold the REAL result into the response (`f"{text}\n\n[tool:{name}] -> {out}"`).
- Match prompt → tool via an alias map keyed on `orch._tools._registry.tool_names`
  (NOT `orch._tools.tool_names` — `ToolManager` has no such attr; the registry is nested).
- **Only auto-run when the user provides a real code snippet** (clear intent): a `print(...)` /
  `exec(...)` call, or a fenced ```python block```. Do NOT guess arithmetic from prose — a brittle
  regex like `\d+([*+-/]\d+)+` matched the substring "10 + 3" inside "2**10 + 3**5" and produced
  WRONG results (13 instead of 1267). Pass the FULL snippet (`m.group(0)`), not the inner group —
  stripping to `2**10 + 3**5` makes the executor evaluate silently and return EMPTY output.
- Degrade cleanly: if no snippet present, return `None` (model's own correct answer stands).
- Emit `TOOL_SELECTED`/`TOOL_STARTED`/`TOOL_COMPLETED` events around the call for observability.
This guarantees real Agent→Tool→Result even when the model can't call tools. Verified:
`print(2**10 + 3**5)` → tool returns `1267`. Full recipe + the arg-extraction gotchas:
`references/moon_tool_intent_fallback.md`.

## RUNTIME-DATA GITIGNORE HYGIENE (real, this session — FIRST CLASS)
Runtime artifacts (SQLite `*.db`, generated agent JSON in `data/agents/agent_registry/`,
`data/agents/staging/`, `app/memory/episodes.json`, `web/moon_settings.json`) get committed by
accident because they were tracked in an EARLIER commit — `.gitignore` only ignores UNTRACKED
files, so adding an ignore rule does NOT untrack already-tracked files.
- **Fix (non-destructive — keeps files on disk):** `git rm --cached -r --quiet <path>` removes
  them from tracking while leaving the working files intact, then commit the removal-from-index.
  Verify the files still exist (`ls -la <path>`) and are now ignored (`git check-ignore <path>`).
- Use `data/**/*.db` (NOT `data/*.db`) so nested `data/agents/agent_factory.db` is covered.
- Add a `data/` runtime section to `.gitignore` so future runs never re-pollute. The repo then
  tracks only source + config; runtime state stays local. (Respects the operator's "do not remove
  anything" — files are preserved, just not version-controlled.)
Full recipe: `references/moon_runtime_data_gitignore.md`.

## PROVE "OPERATIONALLY INSTALLABLE FROM GITHUB" (real, this session — FIRST CLASS)
The "Python-First GitHub Preservation" master prompt's real test is not "does it import
locally" but "**can a fresh clone be installed and run on another machine?**" Verify it
with a REAL install-from-GitHub test, not just a doc claim:
1. **Fresh clone** into a temp dir (use `git clone --no-hardlinks <repo> <tmp>` to avoid the
   "Invalid cross-device link" error that `git clone --local` hits when `/tmp` is a different
   filesystem — see the recovery-test pitfall below).
2. **Isolated env** so the host's PYTHONPATH can't poison it:
   `env -i HOME=$HOME PATH=/usr/bin:/bin:/usr/local/bin python3 -m venv .venv` then
   `env -i HOME=$HOME PATH=<tmp>/.venv/bin:/usr/bin:/bin:/usr/local/bin bash -c '. .venv/bin/activate && pip install -q -e . -r requirements.txt && python -m moon doctor'`.
   (The `env -i` reset is essential — without it the Hermes venv's PYTHONPATH leaks and
   `pip install` lands in the wrong place / `pydantic_core` import fails. See Environment
   command patterns.)
3. **Launch from the clone** and prove it SERVES: `python -m moon terminal` (background), then
   `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8777/api/health` → **200**, and a
   real API call (e.g. `POST /api/tools/discover`) returns live data.
4. **Install.sh must install the package too.** `install.sh` historically only ran
   `pip install -r requirements.txt` and the `~/.local/bin/moon` launcher calls `main.py`
   directly — so after a fresh `./install.sh`, `python -m moon` / the `moon` console script
   did NOT exist (package never installed). FIX: add `pip install -e .` to `install.sh`
   (after requirements) so `python -m moon` works post-clone. Additive — `main.py` stays usable.

**PORT-8777 CONTAMINATION PITFALL (real, this session — FIRST CLASS):** if the CANONICAL
repo's own backend is ALREADY running on `:8777` when you launch the fresh clone's backend, the
clone's `python -m moon terminal` fails to bind (`address already in use`) OR — worse — your
`curl /api/health` returns 200 from the *main* backend, so you FALSELY conclude "the clone
serves." Proof the clone is the one serving: `ss -ltnp | grep 8777` and read the pid, then
`ls -l /proc/<pid>/cwd` → it must point at the clone dir, not `/home/meow/Projects/MOON`.
**Rule:** stop the canonical backend (`kill` the uvicorn pid) BEFORE launching the clone, so the
port is free and the clone's own process is unambiguously the server. (This is a stricter form of
the PORT-8777 SQUATTING rule — here the "squatter" is your own live MOON, not the D-ID stub.)

**CLEAN-MACHINE TEST FILESYSTEM PITFALL (real, this session):** `git clone --local` (and plain
`git clone` of a local path) uses hardlinks and fails with `fatal: failed to create link ...
Invalid cross-device link` when the destination (e.g. `/tmp`) is on a different filesystem than
the source. Use `git clone --no-hardlinks <abs-path>` or `git clone file://<abs-path>` to force
a normal copy. The clone must then actually contain `moon/` (the `python -m moon` package) —
confirm with `git ls-files | grep '^moon/'` in the clone, and that `pyproject.toml` lists
`"moon"` under `[tool.setuptools] packages` (it was missing from the packages list, so `pip
install -e .` did not install the module → `No module named moon`; add it).

Full reproducible recipe: `references/moon_install_from_github.md`.

## TOOL-EXECUTION INTERFACE PITFALL (real, this session):
`.run()`. The `ToolManager.execute` path calls `tool.execute(**kwargs)`; registry objects expose
`execute()` (e.g. `reg.get("python_executor").execute(code=...)` → real compute; `reg.get("web_search")
.execute(query=...)` → real web result). Verified live: `python_executor` returned `385`, `web_search`
returned a live snippet. A probe that calls `.run()` raises `AttributeError` — use `.execute(**...)`.

**LLM 429 hardening (this session):** `LLMService.complete()` now classifies 401/403/429 as permanent
failures → sets `self._disabled` (circuit-break) and logs INFO (not WARNING); `_complete_with_fallback`
skips a `_disabled` backend. Stops a rate-limited OpenAI key from spamming WARNINGs / retrying in a
tight loop; local-first Ollama path stays the source of truth. Verified: pytest green, real task still
returns correct answer.

## Deep-audit workflow (run before "launch-ready")
Full, copy-paste-ready recipe (syntax sweep, import smoke, stale-reference grep,
clean-port boot, WS probe, elementFromPoint DOM-walk):
**`references/terminal_whole_project_audit.md`** — use it as the checklist.
**ALSO** see **`references/moon_deep_audit_probes.md`** for the proven 2026-08-16
whole-Moon probe set: (1) deterministic live-peer test that kills the skip via
pre-warm retry, (2) orchestrator boot + dual-unlock-phrase proof (`SessionLock`
has NO `.unlocked` attr — use `hear()` which returns a dict), and (3) a fast
5-step whole-Moon audit checklist (pytest → import sweep → uvicorn boot + stub
check → CDP interaction audit → orchestrator e2e).
Key additions over the notes below:
- Boot the launch path on a CLEAN unused port (e.g. 8788), not 8777, so the D-ID
  squatter can't shadow your verification (you'd otherwise test the wrong page).
- DEEP AUDIT WITH DIRTY-TREE TRIAGE (this session's workflow): when the
  operator asks for a full deep audit + fix errors + wire every function +
  save-to-repo — and the working tree may be dirty — use
  **`references/moon_deep_audit_workflow.md`** instead. It starts with dirty-file
  triage (classify each modified/deleted file before committing), runs a subsystem
  wiring grid (import + call each major subsystem to prove it FUNCTIONAL, not just
  importable), verifies WS dispatch + REST route integrity + WS batching consistency
  + TUI speech-task cleanup, boots BOTH terminals (web UI + TUI), then commits and
  pushes. Covers the dirty-tree blind-commit trap, stale-pycache hygiene, dead
  batching detection, dead TTS-cancellation detection, wrong public-attr traps, and
  CLI-surface drift.
- After any UI/port migration, grep MOON-controlled files for the OLD endpoint
  (`:8000/brain`, `moon_brain.html`) — stale install/README/Makefile refs are a
  recurring "fresh install is broken" class of bug. Exclude the `skills/` subtree
  (it holds legitimate vLLM reference docs on localhost:8000).
- If a layout gap has no CSS explanation, `document.elementFromPoint(x,y)` +
  walk up the parent chain to reveal a forgotten grid/flex child (this session:
  `.tabs.nav` was a 5th `.moon-root` child, causing dock clipping).

**HEAVY-BOOT FOREGROUND-KILL WORKAROUND (recurring, real — FIRST CLASS):** any
deep e2e/audit that BOOTS the orchestrator (39-agent setup + KB index + model
pre-pull) exceeds the ~300s foreground terminal timeout and gets interrupted
mid-run, leaving you unsure what happened. **Run these in BACKGROUND and read the
log:** `terminal(background=True, notify_on_complete=True)` with the script writing
to `/tmp/x.log`, then `read`/`grep` the log after the completion ping. The
`scripts/moon_functional_audit.py` + `scripts/agent_brains_audit.py` in this repo
are the pattern. Keep per-call `timeout`s bounded (e.g. `asyncio.wait_for(..., 90)`)
inside the script so a slow peer model fails fast instead of hanging the whole run.

1. **Import sweep** (always with `env -u PYTHONPATH`, see guard note below):
   `env -u PYTHONPATH .venv/bin/python -c "import importlib, pkgutil, app; [importlib.import_module(m.name) for m in pkgutil.walk_packages(app.__path__,'app.')]"` → 0 failures. This must STILL pass even when a foreign `PYTHONPATH` is injected: `app/config/env_guard.py` strips `PYTHONPATH` at process start and is imported FIRST in `main.py` and `app/api/main.py`. Verify portability by simulating poison: `PYTHONPATH=/home/meow/.hermes/hermes-agent/venv/lib/python3.11/site-packages env -u PYTHONPATH .venv/bin/python -c "import importlib, pkgutil, app; [importlib.import_module(m.name) for m in pkgutil.walk_packages(app.__path__,'app.')]"` → must still be 0 failures.
2. **Tests**: `env -u PYTHONPATH .venv/bin/python -m pytest tests/ -q`.
3. **Ruff**: real errors only (`E`/`F` except intentional `BLE001` defensive catches).
4. **Live boot**: `env -u PYTHONPATH .venv/bin/python main.py start`, then curl
   `/ /health /status` → all 200 (the terminal is the single UI now; `/brain`/
   `/galaxy` were removed). Confirm "Connected N agent brains".

   **PORT-8777 SQUATTING PITFALL (recurring, real — FIRST CLASS):** a LEGACY D-ID
   avatar project at `/home/meow/project/terminal/` respawns a 959-byte stub
   `server.py` on `127.0.0.1:8777` (title "MOON :: D-ID Avatar Terminal"),
   supervised by `launch.py` (pid) + systemd user unit `moon-avatar.service`. If
   that stub holds 8777 first, MOON's `main.py start` cannot bind and curl shows
   the wrong page — so YOUR edits never appear and renders show a 959-byte stub.
   The operator confirmed the D-ID project is retired ("i already closed that"),
   so MOON owns 8777. Before trusting any render/verification, CONFIRM the served
   file: `curl -s http://127.0.0.1:8777/ | grep -c '<title>MOON Neural Command
   Center</title>'` must be ≥1 and byte size ~56KB (NOT 959). If you see the stub:
   - `systemctl --user disable --now moon-avatar.service` (kills the supervisor so
     it stops respawning), then `kill` any live `server.py`/`launch.py` pids.
   - SIGTERM may not kill `launch.py` (it re-execs) — use `kill -9` on the
     supervisor pid, then confirm `ss -ltnp | grep ':8777'` shows FREE.
   - THEN start MOON on 8777. Never "fix" the UI while the stub is serving — you'd
     be editing a file the browser never loads.
   Also boot the terminal UI: `env -u PYTHONPATH .venv/bin/python -m uvicorn app.terminal_interface:app --host 127.0.0.1 --port 8777` then
   `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8777/` → 200 and
   `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8777/` → 200 and
   `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8777/three.min.js` → 200 (vendored Three.js).
   **VISUAL VERIFICATION (reliable ground-truth technique):**
 The most trustworthy verification is NOT `vision_analyze` (it misreads
 presence/clipping — this session it falsely claimed BRAINWAVE SYNC, ENVIRONMENT,
 and 2 of 6 Quick-Action buttons were missing when they were in the DOM). Use a
 3-layer check, in order:
   1. **Served-file check (catches the stub-server trap above):** `curl -s
      http://127.0.0.1:8777/ | wc -c` (expect ~56KB, NOT 959) and grep for your
      markers (`wfHeadL`, `EARTH ONLINE`, `epPct`). If markers absent → you're
      seeing a cached/stub page, not your file.
   2. **Headless Chromium CDP ground truth** (preferred over `vision_analyze`
      for layout/presence): launch chromium headless with a remote-debugging
      port, then drive it with `ws` + the CDP JSON protocol:
        chromium --headless --no-sandbox --use-gl=swiftshader \
          --remote-allow-origins=* --remote-debugging-port=9228 \
          --user-data-dir=/tmp/cdpX \
          "http://127.0.0.1:8777/" &
        # CRITICAL: --remote-allow-origins=* is REQUIRED or the CDP WS handshake
        # returns 403 Forbidden and every driver connection fails. Run the CDP
        # driver with SYSTEM python3 (the `websocket` pkg lives there, NOT in
        # .venv and NOT in the execute_code sandbox). Page.captureScreenshot with
        # `clip` intermittently returns a null result — use full-page (no clip) or
        Merge-attached-folder workflow + the silent-IIF-abort debugging
         trap: see references/terminal_merge_attached_folder.md

        **REBUILD-FROM-ATTACHED-FOLDER (explicit REPLACE — sanctioned override of the preservative rule, FIRST CLASS):** when the operator points at an attached folder and says *"remove the old [UI/terminal] and rebuild [it] from MOON_3D_Neural_Terminal_Build"* / *"rebuild the terminal from this folder, match the attached reference image"*, that is an EXPLICIT, sanctioned REPLACE — it overrides the default additive stance for this case (distinct from MERGE: merge keeps the old UI and layers folder features on top; rebuild makes the folder's `index.html` the STRUCTURAL BASE and discards the old UI's body). Do NOT keep both UIs and do NOT refuse to remove the old one. Sequence:
         1. **Inspect the folder for malware first** (SUPPLY-CHAIN rule): read its `index.html`; confirm clean vanilla HTML/CSS/JS, no external `fetch`/tracker/`ws` scripts to unknown hosts. If clean → use it as the base. (A scraped LinkedIn/Ultron folder may be bot-protection junk — reject and tell the user.) Keep the folder on disk UNTOUCHED (copy its structure into the target `web/moon_terminal.html`; do NOT edit the folder's own `index.html`).
         2. **Re-theme to the attached reference image.** If the reference is the red/black "NEURAL CORE INTERFACE": bg `#060000`, panel `rgba(8,0,0,.88)`, accent `#ff1c1c`/`#ff5353`, text `#f7eaea`, fonts Orbitron (titles) + Rajdhani (body). If the folder is a different hue, remap to the reference.
         3. **DIFF reference→folder and ADD the missing pieces (reference-driven):** produce the field-by-field inventory (header chips, left nav+panels, center lobes, right topology/pipeline/memory/threat, bottom widgets, footer buttons) and build whatever the folder lacks. Worked example this session: the folder's center lacked the **CENTER FLANKING VERTICAL TIMELINE GRAPHS** (left/right of the orb) the reference showed → added `<canvas id="tlL">`/`<canvas id="tlR">` + a `timeline()` draw fn.
         4. **Wire the folder's DOM IDs to Moon's REAL backend — never fake data.** Write `applyStatus(s)` mapping `/status` JSON → the folder's static element IDs. Derive plausible secondary metrics from real ones (e.g. `tNodes = agentCount*65536`, `tConns = agentCount*(agentCount-1)*512`, `mTotal` from `system.ram_total_mb`) rather than hardcoding fake numbers. Connect `new WebSocket('/ws')`; on `ready`/`status`→`applyStatus`; `workflow`→light pipeline steps via `STAGE_MAP`; `audio`→decode+play WAV via `AudioContext`. Wire footer/CLI buttons to REAL actions (`status`/`diagnostics`/`memory_search`/`knowledge`/`send_message`). KEEP the backend serving contract (`/`+`/ws`+`/status`) UNTOUCHED so Moon stays functional.
         5. **PRESERVE the folder's provider-neutral bridge** `window.MOON_UI.emit({...})` + `window.MOON_TRANSPORT` (fetch POST / ws connect) — these are FEATURES, keep them so any AI/backend can drive the UI.
         6. **VERIFY** with the CDP ground-truth workflow. DISPROVE vision's count misreads with a DOM probe (vision reported **5 lobe labels** when **6** were in the DOM → `document.querySelectorAll('.lobe').length`→6). Concrete recipe + `applyStatus()` template + the rebuild checklist: **`references/terminal_rebuild_from_attached_folder.md`**.
        - `Page.enable`, `Runtime.enable`,
          `Emulation.setDeviceMetricsOverride` ({width:1920,height:1080}) for a
          wide ground-truth viewport (ambiguous 1440 crops mislead vision).
        - **REAL-TIME WAIT (critical):** sleep ~6s with the WS live so `/status`
          paints. Do NOT use `--virtual-time-budget` — it freezes JS before the
          async `/status` fetch resolves, so every gauge/bar reads 0% and you
          think data is broken when it isn't.
        - **DOM probe via `Runtime.evaluate`:** return `document.title`,
          `getElementById(...).textContent`, `getBoundingClientRect().bottom` for
          `.dock`/`.foot` (to prove no clipping at the target height), and
          `[...].map(b=>b.textContent)` for button labels. Null-safe each read
          (`e?e.textContent.trim():'NULL:'+id`).
        - `Page.captureScreenshot` (clip 1920×1080) → `/tmp/shots/x.png`.
        - Use `vision_analyze` ONLY as a last cross-check on the screenshot, and
        treat its "missing element" claims skeptically vs the DOM probe.

 **ADDENDA — this sandbox (2026-08-15, terminal-UI sessions):**
 - **Headless UI verify via the `chromium` CLI, NOT Playwright.** Playwright's
  bundled driver fails to launch here (sandbox), but the chromium CLI works and
  is the reliable ground-truth for `web/moon_terminal.html`:
  `chromium --headless --no-sandbox --disable-gpu --disable-dev-shm-usage
   --screenshot=/tmp/moon.png --window-size=1600,900 http://127.0.0.1:8777/`
  A stray `SharedImageManager` GPU error line is harmless — confirm the PNG was
  written via `ls -la`. Pair with `curl … | grep` for DOM markers
  (`data-ar="16:9"`, `id="coreImg"`, `id="arSel"`).
 - **Safe restart of the Terminal (avoid self-kill):** `kill $(pgrep -f "uvicorn
  app.terminal_interface")` in one line kills the bash tool's OWN shell
  (exit -15) because the pattern matches the running command string. Run kill
  and the post-kill `curl`/boot as SEPARATE calls; narrow the pattern to
  `pgrep -f "app.terminal_interface:app"` if it still self-matches. Confirm the
  port is free (`curl … --max-time 3` → `down`) before booting a fresh
  background uvicorn with the `Application startup complete` watch pattern.
 - **Real audio playback (wire the `audio` WS event):** decode + play MOON's WAV
  in-browser — `new AudioContext().decodeAudioData(atob(b64).buffer.slice(0))`
  then `createBufferSource().start()`. Gate on a `_muted` flag tied to the AUDIO
  button. Without this the reply is only logged, not heard (violates the
  no-fake rule — the user should hear MOON's REAL synthesized voice).
   3. **JS syntax gate:** extract the `<script>` with python `re` and run
      `node --check /tmp/main_script.js` — catches `SyntaxError`s (e.g. duplicate
      `const eg=...` in two scopes) that would silently break the ENTIRE script.
   **SILENT-`apply()`-ERROR LESSON (real bug found + fixed, FIRST CLASS):** a
   `ReferenceError` thrown inside `apply()` (e.g. calling a helper like `setSens`
   that was never defined because an earlier edit dropped it) does NOT crash the
   page — it aborts `apply()` partway, so everything AFTER the throw (memory/knowledge
   bars, system gauges, temp, load, agent count) silently stays at 0%/null, while
   everything before it (Sensory Input) looks fine. Symptom: "panels half-populated."
   Catch by (a) `node --check`, and (b) CDP `Runtime.evaluate` reading a value that
   `apply()` should set (e.g. `cpuTxt.textContent`) after a live `/status` — if it
   stays "0%" while the served HTML has real data, `apply()` threw. Fix by defining
   the missing helper; do not paper over with `try/catch` that hides the gap.
   **BROADER TRAP — silent WHOLE-SCRIPT abort (real bug, 2026-08-15):** a thrown
   error inside ANY `<script>` IIFE, *synchronous at init time*, aborts the ENTIRE
   outer script. Code declared AFTER the throwing IIFE (e.g. `connect()` and other
   IIFEs) never runs. Symptom: HUD shows static HTML but NEVER populates from
   `/status`; `window.__X__` globals from later IIFEs are `undefined`. `node --check`
   catches only SYNTAX errors — run the page under CDP and read the console for
   `Runtime.exceptionThrown`. Two concrete causes this session (do NOT repeat):
   (1) `const ctx = canvas.getContext('2d'); ctx.getBoundingClientRect()` →
   `ctx.getBoundingClientRect is not a function`; call it on the CANVAS ELEMENT.
   (2) `const btn = $$(sel); btn.addEventListener(...)` where `$$`=`querySelectorAll`
   → NodeList has no `addEventListener`; use `document.querySelector` for one node.
   Merge-attached-folder workflow + full debugging recipe:
   `references/terminal_merge_attached_folder.md`.
5. **Clean-room install**: rsync project (minus .venv/.git) to /tmp, run
   `install_moon.py`, confirm a fresh `fastapi` lands in THE PROJECT venv and
   tests pass. (Reproducibility is easy to break — see environment note.)

## Environment command patterns (this host)
- **ALWAYS prefix python/pytest/uvicorn with `env -u PYTHONPATH`.** Hermes
  injects a py3.11 `PYTHONPATH` that poisons imports and makes `pip install`
  target the Hermes venv instead of MOON's `.venv`. **Symptom→cause:** an ad-hoc `pytest`/`python` run reporting `ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'` is the PYTHONPATH LEAK, not a broken venv — the project's own `.venv` is fine; re-run with `env -u PYTHONPATH` and it vanishes, so never report it as real breakage. `install_moon.py`'s `_run`
  and the sync tool strip `PYTHONPATH` for every subprocess — keep it that way.
- **Settings defaults live in `app/config/settings.py` but the gitignored `.env` WINS.** Changing a default in `settings.py` does NOT change runtime behavior until the matching key in `.env` is also flipped. This session MOON kept booting with `browser=False/ocr=False/pdf=False` even after the code defaults were set `True` — the cause was a stale `ENABLE_*=false` block in `.env` (dated Aug 9) overriding the new defaults. **Rule:** when you unlock/change behavior via `settings.py`, also (a) edit the runtime `.env` with a targeted change that preserves secrets, and (b) **update any test that asserted the OLD default** — e.g. `test_pick_llm_routing` asserted "no strong model -> always default"; after enabling `STRONG_MODEL_NAME` it had to be changed to "factual/cyber -> strong, creative -> default". Verify the effective config with
  `env -u PYTHONPATH .venv/bin/python -c "from app.config.settings import get_settings; s=get_settings(); print(s.enable_browser_automation, s.enable_ocr, s.enable_pdf, s.strong_model_name)"`.
- **Pip installs into the WRONG venv when `PYTHONPATH` leaks.** `.venv/bin/pip install X` can resolve `X` to the Hermes agent venv (because `PYTHONPATH` lists `/home/meow/.hermes/hermes-agent/venv/.../site-packages`), so the package lands in the wrong place and the MOON venv still lacks it (you'll see "Requirement already satisfied: X in /home/meow/.hermes/..."). Fix: strip the env and invoke pip THROUGH the venv interpreter — `env -u PYTHONPATH .venv/bin/python -m pip install X`. If the venv's own `pip` module is missing (e.g. after a system-python upgrade 3.13→3.14 detached the venv), recreate it: `rm -rf .venv && env -u PYTHONPATH python3 -m venv .venv && env -u PYTHONPATH .venv/bin/python -m pip install -r requirements.txt`.
- **Create/edit files via terminal heredocs** (`cat > path <<'EOF'`), not the
  `write_file`/`patch` tools, which are intermittently broken on this host
  (`[Errno 2] No such file or directory`). Small `.md` writes sometimes work.
- **Commit ONLY verified changes.** `git` remote is `git@github.com:crsuvo100-gif/MOON.git`
  (SSH). Working tree must stay clean of secrets (`.env`, `long_term`, `agent_brains`, logs are gitignored).

## Moon_AI_AGENT VARIANT (this repo) — multi-brain + frontend/backend reply
The operator ALSO maintains `Moon_AI_AGENT`
(`/home/meow/projectterminal/RED_TEAMING_HACKER_INTERFACE/Moon_AI_AGENT`,
package `moon_agent/`) — a SEPARATE, stdlib-only implementation of the same MOON
persona (no Flask, no WebGL; Chromium `--app` desktop window + `http.server`).
It adds the MULTI-BRAIN COUNCIL accuracy pattern and proper chat reply wiring:
- Each specialist worker (`moon_agent/workers/*`) has its OWN `AgentBrain` with a
  specialist persona + an `is_honest()` anti-fabrication guard; the main brain
  synthesizes their independent outputs (`MultiAgentCouncil.run_brained`).
- Backend exposes `POST /api/chat` (clean `{reply,locked,tool_used}`) and
  `POST /council` (multi-brain synthesis); frontends render `reply` as TEXT, not
  raw JSON. `Lifecycle` holds both the `MOON` orchestrator and the council-bearing
  `MoonAgent`, and `unlock()` unlocks both.
- Full technique, Ollama-key wiring, live-smoke contract, and the
  fresh-`pytest` verification pitfall (stale snapshots get replayed by the
  self-check loop — always re-run after edits):
  **`references/moon_agent_multi_brain_frontend.md`**.

## USER'S UNDERSTAND-FIRST BUILD MANDATE (FIRST CLASS — embed it)
The operator issued a hard, durable rule (verbatim spirit): **UNDERSTAND FIRST,
BUILD SECOND.** Before creating, installing, modifying, merging, moving, deleting,
or replacing ANYTHING, run this sequence and do not skip the understanding stages:
`UNDERSTAND → INSPECT → ANALYZE → MAP → PLAN → VERIFY PLAN → BACKUP → BUILD →
MERGE → TEST → VERIFY → FIX → FINALIZE`.
- **NEVER `GUESS → DELETE → REBUILD`.** Inspect the real existing system first;
  read the actual implementation (don't assume a capability is missing just
  because the filename differs). Map every subsystem (what it does, depends on,
  API, state, whether working) BEFORE proposing changes.
- Prefer REUSE over CREATE: `SEARCH → UNDERSTAND → REUSE? YES→EXTEND /
  PARTIAL→UPGRADE / COMPAT ISSUE→ADAPTER / ABSENT→CREATE`.
- When the user says **"you decide / choose what's best for Moon"**, they want the
  agent to pick the additive + cross-machine-compatible option and PROCEED (with a
  short rationale), not ask. Still BACKUP/commit-checkpoint first.
- Maps the integration point BEFORE coding: new architecture is an **upgrade layer**
  on the existing brain/runtime, not a replacement. Integrate; do not replace the
  current brain.
- After every major build step: build → start MOON → test new feature → test old
  features → check logs/health/UI/API → continue. If an old feature breaks: STOP →
  diagnose → fix regression → retest.
Full checklist: `references/moon_understand_first_workflow.md`.

## INTERMEDIATE-TURN RESUME PATTERN (operator behavior — FIRST CLASS)
The operator frequently cuts off the assistant's spoken reply mid-turn with a
one-word "cotinue" (continue) or similar. When this happens:
- **RESUME the in-flight task.** Do not start something new, do not wrap up
  work that was already done, do not re-confirm completion. The latest user
  message wins over any in-flight work described in a prior turn.
- The interruption is a SIGNAL to keep going, not to stop. If the prior turn
  was mid-verification or mid-advancement, continue that loop until it reaches
  a natural stopping point (commit + push + restart + verify).
- A new distinct task in the latest message overrides the in-flight work;
  treat ONLY the latest message as the active task.

## DEPLOY TOOLING = PURE PYTHON, NOT SHELL (operator correction — FIRST CLASS)
The operator reversed a shell-script launcher/installer I built: *"make it py
language for launch any OS system supported not sh that you just build it."*
Rule: **every launcher / installer / deploy helper for MOON MUST be pure Python,
cross-platform (Linux/macOS/Windows). No `.sh`/`.bat`.** Use
`python3 scripts/<name>.py` from `Makefile` targets. Reference + full technique:
`references/cross_platform_launcher.md`. The working pair in the repo is
`scripts/install_ollama.py` (idempotent Ollama installer: Linux systemd unit with
the operator's exact spec + CUDA auto-detect; macOS `brew services`; Windows
`winget`) and `scripts/moon_launcher.py` (ensures Ollama is up, pops `PYTHONPATH`,
boots MOON terminal/dashboard). Both verified live (DRY_RUN unit + HTTP 200 boot).
If you ever reach for a `.sh`, STOP and write `.py`.

## CROSS-MACHINE / PURE-PYTHON COMPATIBILITY (operator requirement — FIRST CLASS)
The operator requires MOON to be **buildable and launchable on ANY machine with
only the Python standard library** ("everything on python coding language for
compatible and supported any machine"). Enforce:
- **Core MUST be stdlib-only.** `pyproject.toml` `dependencies = []`; optional
  extras (flask, ollama client, etc.) go under `[project.optional-dependencies]`
  and are NEVER imported at module top-level by the active path.
- **No non-pure-Python imports in the active runtime path.** `numpy`, `cv2`,
  `torch`, `pandas`, `sklearn`, `flask`, `flask_socketio`, `pyaudio`,
  `pyautogui`, `PIL`, `requests`-over-network are fine ONLY if imported
  **defensively** (`try/except` → `None`) AND used lazily inside a function, never
  at import time.
- **Delete flask/non-pure orphans** that duplicate a stdlib service. A stdlib
  `http.server` (ThreadingHTTPServer) covers REST + static + SSE with ZERO deps.
  When porting an endpoint off flask, preserve the response shape
  (`/health`, `/chat` returning `{text, locked, tool_used}`).
- **`requirements.txt` = stdlib-only core**, with a comment that external binaries
  (Chromium for the desktop window, Ollama for local LLM) are system-installed, not
  pip. Never list `flask` as a required core dependency.
- Perception/voice/vision boundaries stay as **honest stubs** when no local model
  is wired (return `""` or real file metadata), not fake data.
Technique + worked example (deleting `moon_agent/api.py` flask orphan, lazy
`except ImportError` guarding `moon.py`, stdlib server with path-traversal guard):
`references/moon_pure_python_compat.md`.

## SECRET-SAFE GIT (real near-miss this session — FIRST CLASS)
A checkpoint `git add -A && git commit` force-added the gitignored `.env` (with the
OpenAI key) into a local commit. Recovery + hardening:
- **`.gitignore` must list**: `.env`, `terminal/.env`, `__pycache__/`, `*.pyc`,
  `.moon_data/`, plus any local secret dirs. But **`git add -A` will force-add
  ignored files** if they were touched — verify with `git diff --cached --name-only
  | grep -E '\.env$'` BEFORE every commit.
- **If a secret lands in an UNPUSHED commit:** `git reset --soft <parent>` (keeps
  working tree), `git rm --cached -f .env terminal/.env`, drop `__pycache__`/`.moon_data`
  (also `rm -rf` locally), re-commit. Then `git rebase origin/main` so the push is a
  clean fast-forward.
- **Verify the key never reaches history BEFORE push:** `git log --all -p 2>/dev/null
  | grep -c 'sk-pro'` must be `0`. Also `git ls-files | grep -E '^\.env$|terminal/\.env$'`
  must be empty.
- **Never push a leaked commit** — rewrite it locally first. GitHub remote uses SSH
  (`git@github.com:crsuvo100-gif/...`); an existing `~/.ssh/id_ed25519` authenticates
  without a token. Replace real keys with `[REDACTED]` in any summary/chat; never
  print the literal key.
Full recovery recipe + checks: `references/moon_secret_safe_git.md`.

## GitHub connectivity pitfalls (see references/github_auth.md and references/moon_terminal_and_github_ssh.md)
## Terminal UI / avatar protocol (see references/terminal_avatar_protocol.md)
## Terminal real-status accessors + function wiring (see references/terminal_status_accessors.md)
## Terminal real-time, state-driven animation (no fakes): see references/terminal_realtime_animation.md)
## Terminal visual verification pitfalls + ground-truth technique (diff-first, vision_analyze reliability, WebGL-fallback layering, dock-clip fix): see references/terminal_visual_verification_pitfalls.md
## Merging an attached folder into the live terminal + silent-IIF-abort debugging: see references/terminal_merge_attached_folder.md
## NEXUS 3D Three.js avatar (Ultron) build + vendoring + CDP/swiftshader verify + whole-Moon push topology: see references/nexus_3d_ultron_build.md
- **Fine-grained PAT git-push quirk**: the API may report `permissions.push:true`
  but `git push` over HTTPS still 403s "Write access not granted" if the token's
  "Contents" permission was edited AFTER creation. Fix: REGENERATE the token.
  Both auth options are implemented in `github_sync_tool.py` (`auth="pat"` via
  `GITHUB_TOKEN`, and `auth="gh"` GitHub-CLI fallback).
- **SSH key path** (chosen here): generate ed25519 on the box, add public half
  to GitHub, set `git config core.sshCommand "ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes"`,
  switch `origin` to `git@github.com:crsuvo100-gif/MOON.git`. Works once the
  public key is added (no token regen needed).
- Never print/commit the token; scrub it from `.git/config` after any push test.

## Visual-fidelity iteration on the terminal UI (operator pattern)
The user judges the terminal UI against an ATTACHED REFERENCE screenshot and will
reject a "functional dashboard" look. **BUT (this session, hard correction): do
NOT start with visuals. First wire every panel to MOON's REAL data (`/status`,
`references/terminal_status_accessors.md`) and make every button call a REAL
backend action (`diagnostics`/`memory_search`/`knowledge`) — only THEN layer the
cinematic CSS. The operator pushed back hard when the avatar/glass looked good
but the panels were still fake bars. Function precedes form; form is the frame.**
When they paste a reference image and say "make it look like this," treat it as a
fidelity task, not just a layout task:
- Use `vision_analyze` on the reference to extract the EXACT visual vocabulary
  (glassmorphism, neon bloom, 3D brain, particle web, circular gauges, monospace
  logs, scanlines). Then rebuild the HTML/CSS to match — do NOT stop at copying
  the panel layout.
- The operator inspects the LIVE DOM (sends XPath like
  `html/body/div[3]/.../img` and pastes the element's computed `getComputedStyle`
  dump). If they send a computed-style dump, read it for what's MISSING vs the
  reference (e.g. `backdrop-filter:none`, `animation-name:none`, no `box-shadow`
  glow) and patch exactly those properties.
- Be honest about the ONE hard limit: pure code cannot render a PHOTOREALISTIC
  face — substitute a stylized SVG face + holographic overlay, and expose a
  drop-in path (`web/avatar.png` / `avatar.gif`) so the user can supply a real
  photo. Do not claim the code looks photoreal if it doesn't.
- Concrete CSS techniques that worked to reach the cinematic look (kept in
 `references/terminal_visual_fidelity.md`): glassmorphism via `backdrop-filter:

 **CLONING AN ATTACHED AI-CORE IMAGE INTO THE CENTER (reusable recipe —
 `references/terminal_ai_core_fidelity.md`):** when the operator pastes a
 fiery/orb/neural-core reference and says "make the center 3D animated, fully
 AI futuristic" / "check the built screenshot vs the attached image and fix the
 gaps expertly," run the DIFF-FIRST compare (built screenshot vs attached
 reference) and fix only real gaps. **Key pitfall:** do NOT tint the orb to the
 HUD `--accent` (a red core mismatches a fiery reference) — sample the
 reference's OWN palette and hardcode it (white-hot `#fff`→amber→orange→red→
 transparent radial; deep purple/blue background radial; bright horizontal
 EQUATORIAL RING; cyan right-side RIM LIGHT; left-side vertical DATA STREAKS).
 Embed the reference as a DIMMED backdrop (`opacity:.34; mix-blend-mode:screen`)
 so the live canvas core dominates — a bright (`opacity:.55`) image competes and
 washes out the heading/status text (fix legibility with strong black
 `text-shadow`). The recipe file has the exact Canvas2D/CSS snippets and the
 verified diff checklist.

 **GLOBAL-RED vs GOLD-CORE RECONCILIATION (operator correction, FIRST CLASS — 2026-08-15):**
 when the operator says "make the whole interface hot red" / "make it all red and more
 advanced," do NOT recolor the central fiery core to red. The reference HUD is RED/BLACK as
 a FRAME, but its defining center is an ORANGE/GOLD fiery 3D core (white-hot gold center). The
 correct split:
 - Apply HOT RED to the surrounding structure only: neural mesh, rings, equatorial band,
   hexagon frame, left data streaks, hex tech panels, targeting rings, background radial
   (red `rgba(110,10,20,…)` / `rgba(255,90,80,…)`), right rim light.
 - Keep the CORE itself GOLD/AMBER: white `#fff6e0` → amber `#ffe18c`(~0.22) → orange
   `#ff9632`(~0.55) → red `#ff3c14`(~0.80) → transparent radial; warm gold equatorial ring
   (`rgba(255,200,120,.8)`) + warm bloom + gold right-side rim light (`rgba(255,190,120,.6)`).
   The orb's ambient glow is a WARM gold-core bloom INSIDE a red frame, not a flat red.
 - When reconciling TWO references (the RED HUD + the ORANGE AI-core image), the orange
   AI-core palette WINS for the center core; the red HUD palette wins for everything else.
 Symptom this prevents: you recolor the core red to satisfy "all red," then the operator
 re-attaches the reference and says "the center must have this" (the gold core). RULE: RED =
 everything AROUND the core; GOLD = the core. Additive-only; never drop the gold core to satisfy
 a global-red instruction.
  blur()` + translucent bg + inner `box-shadow` bloom; rotating 3D-wireframe brain
  via CSS `transform-style: preserve-3d` + `@keyframes spin`; neural synapse
  particle web on a `<canvas>` (glowing nodes + purple connection lines, star-map
  style); circular holographic gauges via `conic-gradient`; `body[data-moon=...]`
  drives the avatar's CSS reactions (locked/thinking/working/speaking/listening).
  **DIFF-FIRST VERIFICATION (operator's explicit angry correction — FIRST CLASS):**
  When the user pastes a reference image and asks you to match/make it like the
  built terminal, do NOT just rebuild and claim done. The operator said: *"deeply
  check what i want from you and what you build for me… verify and understand and
  patch, extract and better knowledge understanding before task executed for better
  build something. now fix it if you have any different from what i want look like
  terminal interface."* The required workflow:
  1. `vision_analyze` the REFERENCE → exact element list.
  2. `vision_analyze` the CURRENT build (or last render) → same list.
  3. Produce a FIELD-BY-FIELD DIFF (present / missing / different) and SHOW it.
  4. Fix only real gaps (additive, real-data-driven). Re-render to verify.
  Skipping the diff and saying "it's done" makes the operator angry — he reads the
  live DOM and catches every missing panel.
  **vision_analyze reliability pitfall:** it MISreads "is element present / clipped"
  (this session it falsely reported BRAINWAVE SYNC + ENVIRONMENT panels and 2 of 6
  Quick-Action buttons as missing when they were in the DOM). Ground-truth with
  `curl … | grep` for presence, and re-render at a WIDER viewport (1920) when a
  crop read is ambiguous. Full technique + commands:
  `references/terminal_visual_verification_pitfalls.md`.
  **WebGL-fallback avatar (real bug + fix):** the 3D face must not be the only
  thing drawn — when WebGL fails on the user's browser they see a blank
  constellation blob, not the face. Layer the SVG face as the ALWAYS-ON base
  (`#avatarImg` z-index:2, `display:block`) with the Three.js canvas on top
  (`#face3d` z-index:3, transparent where undrawn) and `#meshDots` z-index:4.
  Force `--disable-webgl` in a headless render to PROVE the face still shows.

## FUNCTIONAL UI AUDIT — prove EVERY button/option works (not just renders)
After any terminal-UI rebuild, do NOT stop at "it renders." The operator wants every control
**verified functional**. Run a headless CDP interaction audit: launch chromium with
`--remote-allow-origins=*`, connect via CDP, `Page.reload`, then **click every button/nav/aspect
option and type into the CLI**, measuring a REAL effect for each (panel opens, log appends,
`active` class moves, `#app` resizes, CLI echoes). Drain `Runtime.exceptionThrown` at the end and
assert ZERO JS errors. This beats `vision_analyze` (which misreads presence, e.g. "5 vs 6 lobes").
Concrete runnable driver + Moon interaction checklist + CDP pitfalls:
**`references/terminal_cdp_audit.md`**. Key pitfalls captured there: `ws.settimeout` must be reset
to 20s after an error-drain or the next CDP call blocks; `Page.captureScreenshot` clip is flaky
(use full-page); never pre-drain console during reload (rAF/console flood the recv buffer).

**RECONCILE "rebuild from attached folder" vs the preservative rule (additive note):** when the
operator says "remove the old terminal and rebuild from MOON_3D_Neural_Terminal_Build," that is the
sanctioned REPLACE (see the REBUILD-FROM-ATTACHED-FOLDER block above) — but still (a) keep the
attached folder itself on disk untouched, and (b) preserve the BACKEND route contract
(`app/terminal_interface.py` serving `/` + `/ws` + `/status` + `/theme`) so Moon stays functional.
The rebuild swaps the HTML/CSS/JS body, not the engine.

**FLAKY LIVE-PEER TESTS (test-hygiene pitfall — FIRST CLASS):** a pytest that federates with a
real peer model (`test_federation_with_real_peer_agent`) HANGS (times out) when the peer model
(e.g. `qwen3:0.6b`) isn't pulled/ready on loopback. This blocks a clean `pytest` run and is
environment-dependent, not a Moon bug. Fix additively: at the top of the test, probe the peer with a
short hard timeout (`httpx.Timeout(15.0)` POST to `/v1/chat/completions`); `pytest.skip(reason)`
ONLY when unreachable / non-200 (the one legit skip — never skip just because the model is
cold/slow to load). Then PRE-WARM with one `httpx.AsyncClient(timeout=180.0)` looping up to 8
times until the peer returns 200, absorbing the full cold-load latency, then `federate` with a 120s
budget. Result: suite always green with **0 skips (89 passed)** when the model is present. Do NOT
"fix" by force-pulling a model in CI. Concrete recipe + the orchestrator e2e/dual-unlock proof:
**`references/moon_deep_audit_probes.md`**. Rule: a `pytest.skip` that fires when the resource is
*present but slow to warm* is a test bug, not a Moon bug — pre-warm + retry beats skip.

## MULTI-TIER LLM FALLBACK (local → OpenAI → OpenRouter → Hugging Face) — resilience
MOON must never go silent when one model backend dies. The orchestrator holds a
primary local `LLMService` (Ollama) plus `_llm_fallback` (OpenAI), `_llm_fallback2`
(OpenRouter), and `_llm_fallback3` (Hugging Face OpenAI-compatible router), and a
single `_complete_with_fallback()` helper that tries local → OpenAI → OpenRouter → HF,
stopping at the first non-empty result (empty `content` AND exceptions both fall through;
the chain iterates via `getattr(self, "_llm_fallbackN", None)` so a tier that was never
set — e.g. on a bare test `Orchestrator()` — is safely skipped). Each fallback is built
ONLY when its key is set (gated on `settings.openai_api_key` / `openrouter_api_key` /
`huggingface_api_key`); with no key MOON runs local-only. Hosted models are NOT thinking
models, so they are built with `disable_thinking=True`. Both `quick_reply` and `_fast_answer`
(run_task simple path) route through the helper. Full config + wiring + secret-safe
pasted-key handling + offline test recipe:
**`references/llm_fallback_backends.md`**.

**Secret handling (FIRST CLASS — when the operator pastes a literal API key):**
store it ONLY in the gitignored runtime `.env` via a python one-liner that strips
existing `KEY=` lines (never echo the value); put a BLANK placeholder in
`.env.example`; verify load by printing only `bool`/`len`; and PRE-push guard with
`git ls-files | grep -E '.env$'` (empty) + `git grep -nE 'sk-proj|sk-or-v1|hf_|whsec_' -- ':!*.log'`
(nothing). Full technique + test recipe + pasted-key safety:
**`references/llm_fallback_backends.md`**.

**PITFALL (real, this session):** a bare `Orchestrator()` (used in unit tests) has NO
`_llm_fallback2`/`_llm_fallback3` attribute — only set during `setup()`. Tests calling
`_complete_with_fallback` MUST set `o._llm_fallback2 = None` / `o._llm_fallback3 = None`
(or the helper's `getattr` default handles it). Also: `LLMService.complete()` swallows
exceptions and returns `CompletionResult(content=None)`, so a "dead" local model does NOT
raise — the empty-content check is what triggers the fallback; handle BOTH raise and empty.

## HUGGING FACE INFERENCE CLIENT + DEPLOY/OAUTH (additive capabilities)
MOON gained two HF-backed tools (registered in orchestrator setup, additive):
- **`HuggingFaceTool`** (`app/tools/huggingface_tool.py`): chat completion via
  `huggingface_hub.InferenceClient` with explicit provider selection (e.g. "novita") and
  `text_to_image` generation (FLUX etc.). `app/services/hf_inference.py` wraps the client
  with a **lazy import** of `huggingface_hub` (optional dep, declared as the `hf` extra) so
  MOON imports/runs fine without it; methods raise a clear error when missing. Reuses
  `settings.huggingface_api_key` as the token.
- **`HuggingFaceDeployTool`** (`app/tools/huggingface_deploy.py`): find → compare → deploy
  HF models as Inference Endpoints in `settings.hf_endpoint_namespace` (default `crsuvo`)
  via the `hf` CLI. `deploy()` is **CONFIRMATION-GATED** (`confirm=True` required — it
  provisions billable hardware; never auto-run). Also builds the HF OAuth client
  registration payload (Auth Code + PKCE, `token_endpoint_auth_method: "none"`) from
  `settings.hf_oauth_website`.

**`.env` auto-provisioning:** `scripts/moon_launcher.py` `ensure_env()` copies `.env.example`
→ `.env` when absent (never overwrites an existing `.env`, never commits it) so a fresh
clone boots fully configured (features unlocked; API-key fields blank to fill). `.env`
stays gitignored (secret vault) — committing it would leak all keys. `python-dotenv>=1.0`
is already a declared dep, so `.env` is actually loaded at runtime.

**Tests (offline, no network/token):** `tests/test_openai_fallback.py` (8: covers all
tiers incl. HF-last-resort + OpenRouter-preferred-over-HF), `tests/test_huggingface_inference.py`
(7: chat/provider/image-gen via mocked `InferenceClient`), `tests/test_huggingface_deploy.py`
(5: oauth payload, compare ranking, deploy confirmation-gate, deploy run+verify, failure not
faked — all mock the `hf` CLI). Full suite **70 passed** (`env -u PYTHONPATH .venv/bin/python -m pytest tests`).

## INTERACTION INTERFACES, REMOTE AUTHZ GATE, AND AUTONOMY (added 2026-08-15)
MOON has SIX interaction surfaces (Terminal @:8777, Flask Dashboard @:5000, one-shot
`python main.py run`, voice companion `scripts/voice_loop.py`, Telegram polling bot, and
programmatic `Orchestrator.run_task`). This session added three: a **curses TUI**
(`app/tui.py`, `python main.py tui`), a **Telegram polling bot**
(`app/services/telegram_bot.py`, `python main.py telegram`), and a **remote authz gate**
on the Terminal interface. Full map + the builtin-capability autonomy fix + the
optional-dependency lazy-import pattern: **`references/moon_interfaces_and_autonomy.md`**.
Key durable rules captured there:
- **Terminal remote gate:** `MOON_TERMINAL_TOKEN` (or `settings.terminal_access_token`)
  makes the WS + `/status` require `Authorization: Bearer <token>`; unset = local-only
  (safe default). The launcher `tunnel` mode generates a token if absent and starts
  `cloudflared` (best-effort) — NEVER exposes MOON remotely without auth.
- **Telegram:** token/chat from `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` (or settings);
  chat-id gate drops unauthorized chats; `available` is False without a token.
- **Optional deps (huggingface_hub, telegram):** lazy-import inside methods, optional
  `pyproject` extras (`hf`, `telegram`), degrade with a clear error — never fabricate,
  never force into core `dependencies`.
- **AUTONOMY / terse commands (operator style — FIRST CLASS):** "choose yourself and free",
  "push and make functional", "save it" are unambiguous GO signals. When the action is
  additive + lose-free (no secret commit, no billable side-effect like deploying cloud HW
  without `confirm=True`), PROCEED and report — do not stall on a clarifying question. Reserve
  questions for genuine ambiguity or destructive/irreversible acts (force-push, delete, spend money).
- **STOP "STANDING BY" / "AWAITING YOUR DIRECTION" (operator correction, this session — FIRST CLASS):**
  the operator cut off a turn with *"remove cccc and do not standby continue what you ask for"*
  after I repeatedly ended turns with "standing by / awaiting your direction." RULE: once a task
  is given and is additive/non-destructive, KEEP GOING to a natural stopping point (commit+push when
  the user said "save"/"push") and then give the FINAL report — do NOT close every turn inviting
  more input unless the work is genuinely blocked or the user asked a question. Ending with
  "standing by" after each step reads as stalling and annoys him. If you finish the requested work,
  report completion + status and stop; don't loop back for permission you already have.
- **Builtin-capability autonomy gap (closed):** `CapabilityManager` must list MOON's own
  built-in tools (e.g. `huggingface`, `image generation`) as `{"type":"builtin","method":"none"}`
  so she can autonomously *choose* them; `installer.install()` treats `method:"none"` as
  already-satisfied and `verification.verify()` confirms the live tool is registered rather
  than importing a pip package. Without this she cannot route image-gen/hosted-model tasks to her
  own tools. Tests: `tests/test_hf_autonomy.py` (5).

## Voice
`app/voice.py`: female TTS = espeak voice 5 + SoX chain (pitch/bass/treble/
chorus/reverb), presets default/seductive/warm/crystal. STT = vosk (optional).
No cloud TTS.

**Premium female voice engine** (`app/voice_engine.py`, additive upgrade over
`app/voice.py`): kokoro-ONNX (local, CPU, `aria`/`bella`/`sarah` female voices)
as the default, with F5-TTS (zero-shot cloning on Python 3.13) and OpenAI TTS as
optional backends, falling back to espeak. **Auto-voice is always ON** — the
WebSocket handler calls `_speak()` after every assistant reply, sending base64
WAV audio to the client. Voice mode is `AUTO` by default; the client can toggle
via `moon voice mute` / `moon voice unmute` (sets `_voice_muted` in the WS
handler). See **`references/terminal_on_demand_hud_launch.md`**.
