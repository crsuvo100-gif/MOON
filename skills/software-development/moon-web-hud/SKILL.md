---
name: moon-web-hud
description: Build and verify MOON's NEURAL CORE web HUD.
---

# MOON Web HUD — NEURAL CORE INTERFACE

This skill governs the **front-end terminal HUD** of MOON (`web/moon_terminal.html`,
served at `GET /` by `app/terminal_interface.py`). It is independent of the backend
agent/orchestrator skills — this is HTML5 + CSS3 + vanilla JS (Canvas2D) + a FastAPI
backend that only serves `/status`, `/ws`, `/theme`, `/moon_core.png`, `/avatar.svg`.

## When to use
- User supplies a reference image/spec and wants the HUD built or reconciled to it.
- Editing layout, panels, the central orb, theming, or aspect ratio.
- Verifying the UI actually renders (no JS error / blank / overlap) before claiming done.

## Hard constraints (MOON project)
- **NON-DESTRUCTIVE / additive only**: extend `web/`; never disable the backend engine
  (`/ws`, `/status`, authz gate). Keep the reference image held in the interface (hero
  backdrop `<img src="/moon_core.png">` + right-column thumbnail + click-to-expand lightbox).
- **Dep-free, no build step**: vanilla JS + Canvas2D. No Three.js, no framework, no TS.
- **Real data only**: wire panels to `/status` + `/ws`; don't hardcode fake live numbers
  (placeholders `--` OK). Language: HTML5 · CSS3 (`:root` props, scanlines, brackets, glow)
  · vanilla JS + Canvas2D + WebSocket · JSON `web/theme.json`.

## Frame structure (canonical 8-region wireframe)
01 HEADER (logo + title + 7 chips: CORE TEMP+OPTIMAL, QUANTUM LOAD, CORE STATUS,
 SYSTEM UPTIME `d h m s`, NET LATENCY+LINK STABLE, NEURAL SYNC 100%, THREAT LEVEL).
02 LEFT NAV (icon + label + sublabel per module).
03 CENTER: 03.01 orb (6 lobe labels FRONTAL/PARIETAL/TEMPORAL/OCCIPITAL/LIMBIC/CEREBELLUM
 + QUANTUM NEURAL MATRIX / ENTANGLEMENT VISUALIZATION inner label), 03.02 lobe telemetry,
 03.04 NEURAL CONVERGENCE, 03.05 banner.
04 RIGHT INTEL: Topology (Plasticity/Learning Rate/Network Type), Memory (Integrity/
 Redundancy), Threat (wireframe WORLD MAP + Monitored Regions), MOON CORE IMAGE thumbnail.
05 LEFT TELEMETRY (density/synaptic/latency bars + config + power mgmt + logs).
06 BOTTOM (7 widgets: logs, synaptic spectrum, neural feed, memory gauge, learning %bars,
 voice MOON-SYNTH v5.2, quantum channels + stability).
07 QUICK COMMAND. 08 APP BAR (Terminal/AI Chat/Tasks/Updates/Diagnostics/Help + RATIO +
 ACCENT + clock + AUDIO).

## Central avatar orb (Canvas2D clone)
Reference avatar = brain-shaped neural network in a wireframe cage, 12–16 center beams,
3 rotating rings, surrounding lobe labels, glowing core.
- Nodes = two **bilateral hemispheres** with a central fissure: `hem=i%2?1:-1; fx=cos*0.82+hem*0.20`,
  NOT a uniform sphere. ~120 nodes, link if dist < 0.28.
- Cage: latitude bands (la=-3..3) + longitude bands (lo=0..9) projected.
- Beams: 14 spokes from center, white→accent fade, flicker via per-beam phase.
- Rings: 3 ellipses (RR*0.42 on one axis for tilt) + drifting light-node dots.
- Accent-aware: read `--accent`/`--accent-soft` from computed style; core glow = radial
  white→accent→transparent. `requestAnimationFrame` loop; faster spin when STATE != idle.
- Lobe labels: absolutely-positioned DOM spans in `.lobe-ring` (crisp, not canvas text);
  FRONTAL top-left, PARIETAL top-right, TEMPORAL mid-left, OCCIPITAL mid-right, LIMBIC/
  CEREBELLUM bottom.

## Aspect-ratio + auto-fit
- `.app` has `--ar` var + `aspect-ratio:var(--ar)`; presets `[data-ar="16:9|4:3|21:9|1:1|
  9:16|3:4|fill"]`.
- **DEFAULT = `auto`** (user removed 16:9 default). AUTO computes best-fit ratio for
  current `innerWidth/innerHeight` on load AND resize → compatible with any display incl.
  portrait. Manual presets incl. 9:16 / 3:4 (mobile). Persist `localStorage('moon_ar')`.

## Accent-color theming
Colors flow from `--accent`/`--accent-soft`/`--accent-dim`/`--accent-line`;
`[data-accent="red|cyan|violet|amber|emerald"]` overrides on `.app`. ACCENT select in app
bar; persist `localStorage('moon_ac')`. Orb + waveforms read the live var → recolor instantly.

## Real wired function: audio playback
Voice arrives as WAV base64 in the `audio` WS event. Play it:
`new AudioContext().decodeAudioData(Uint8Array.from(atob(b64)).buffer)` then buffer source →
destination. AUDIO button toggles `_muted`. (Gap fixed this session: audio was only logged.)

## Verification (REQUIRED before "done")
See `references/visual_verify.md` for the headless-Chromium recipe. **Pitfall**: a prior
screenshot's ratio/accent choice persists in localStorage and makes AUTO look unapplied — always
verify with a FRESH `--user-data-dir`.
- **WORKING headless screenshot (2026-08-19 — supersedes the old "screenshot always hangs" note).**
  Screenshots do NOT hang when the virtual-time budget is large enough. The OLD "hang / 0-byte PNG"
  reports were actually the **boot-overlay timing artifact**: with a small `--virtual-time-budget`
  the capture fires before the WS `ready` frame clears the boot overlay → you get an ~18KB "INITIALIZING"
  boot frame that *looks* broken but isn't. Use `--virtual-time-budget=6000` (≥ boot+WS+1.8s) → a
  fully-rendered HUD PNG of ~470-700 KB. Command:
  `chromium --headless --no-sandbox --disable-gpu --hide-scrollbars --virtual-time-budget=6000 --window-size=1920,1080 --screenshot=/tmp/hud.png "http://127.0.0.1:8777/"`.
  If the PNG is <~200 KB, the capture was too early — raise the budget, don't "fix" the code.
- **URL-hash deep-link (PRIMARY way to verify INNER panels).** Blind coordinate-clicks on the
  app-mode Chrome window MISS inner buttons (cua-driver SOM only exposes the top-level `<frame>`,
  not SETTINGS/WORKSPACE/footer-tab buttons), and a `--remote-debugging-port=9222` CDP port does
  NOT bind in the nested agent session, so `cdp_hud_audit.py` can't drive the page here. The
  reliable path: add a `location.hash` deep-link to the HUD (opens a panel on load) AND capture it
  headless. Full recipe + the exact JS + command in `references/headless_deeplink_verify.md`.
  Concretely: hit `http://127.0.0.1:8777/#agents` (or `/#tools` `/#events` `/#shell`) headless →
  the workspace auto-opens after WS status arrives → screenshot proves the inner grid/matrix renders
  with real counts. This is also a useful shareable feature, not just a test hook.
- **CDP audit** (`scripts/cdp_hud_audit.py`) is the authoritative no-screenshot audit IF the CDP
  port is reachable (it is NOT in the nested agent session here — don't rely on it in this env).
- **Reusable audit script**: `scripts/cdp_hud_audit.py` — launches nothing itself, drives a
  running chromium (`CHROME_PORT`, `HUD_URL` env) via CDP: clicks every button + 3D core,
  checks real effects, drains JS errors, prints PASS/FAIL. Run `python3 scripts/cdp_hud_audit.py`
  after starting chromium with `--remote-debugging-port=9222` and the HUD URL.
- **Theme/color check WITHOUT screenshot** (use when only CSS colors changed): CDP
  `Runtime.evaluate` → `getComputedStyle(document.body).color`. A hot-red pass yields
  `rgb(255, 90, 90)`. This avoids the screenshot hang entirely for color-only edits.
- **LIVE-DATA verification (WS-driven HUD) — READ THIS before chasing a "monitoring broken" report.**
  The HUD's panels are populated ONLY by WebSocket frames (`onmessage` → `handle` → `applyStatus`),
  so headless `chromium --screenshot`/`--dump-dom` show the **STATIC HTML DEFAULTS**
  (`smCpu="--%"`, `mTotal="1.02 PB"`, `gActive="17"`) because headless Chrome **throttles
  `WebSocket.onmessage` in background/non-focused tabs**. The DOM is NOT broken — the data
  path is unproven by those tools. To prove the HUD will be live, run a **raw WS client**
  (no browser): see `references/ws_live_data_verification.md` + `scripts/ws_status_probe.py`.
  It asserts the backend pushes `type:"status"` with a real `system` object on connect and on
  `action:"status"`. If that passes and a prior full-HUD screenshot rendered, the HUD IS
  functional — do NOT "fix" the code to satisfy a headless `--%` artifact.
- **Whole-Moon deep-scan probe** (import-all / boot brain / count tools / unlock→real
  task / endpoints / pytest, incl. the live-federation test fix): see
  `references/whole_moon_deep_scan.md`. Reuse verbatim for "scan + make Moon ready/launch".
- **Pitfall — do NOT reuse a CDP `--user-data-dir`**: launching `--screenshot` against a
  profile dir that an already-running chromium (CDP) instance owns fails with exit 21 / 0-byte
  PNG. Always use a FRESH, unique `--user-data-dir` for screenshot attempts; better, just use
  the CDP audit script above.

## Live behavioral verification + WebP-core + systemd lessons (2026-08-29)
- **Proving a feature REACTS (not just renders)**: a headless screenshot proves paint, not
  behavior. To prove a DOM change happens during a LIVE WS reply (e.g. an avatar face gets
  `.speaking`, a panel updates), use headless Chrome CDP: launch with
  `--remote-debugging-port=9222 --remote-allow-origins=*` (the origins flag is MANDATORY or the
  WS handshake 403s), attach to the `type:"page"` target from `/json/list` (NOT `/json/new`,
  which 405s on modern Chrome), and `Runtime.evaluate` an async fn that calls the page's `wsSend`,
  polls `el(id).classList.contains('x')` for ~35s, and returns the bool. Full recipe +
  worked example in `references/cdp_live_verify.md`. This is the authoritative "did it actually
  toggle" proof when vision is down (401 this session).
- **Animated WebP AS the core (no artificial orb)**: when the operator attaches an animated WebP
  and says "make it the fusion/neural core, not a separate floating image", render it as a real
  `<img>` inside `.fusionCore` (`<img class="fusionOrb" id="fusionOrb" src="/moon_core.webp">`),
  NOT a `background-image` div. Pitfalls that "build an orb around it": `border-radius:50%` clips
  the WebP to a circle (kills its own shape/alpha), `mix-blend-mode:screen` washes it out, and a
  heavy `box-shadow` adds a fake halo. Drop those — keep only a soft `drop-shadow` (follows the
  image's natural alpha) + a `--core-e` scale pulse tied to `onCorePulse`. To make it BOTH fusion
  and neural core, `applyAvatarMode()` should reveal the same `#fusionOrb` in both `fusion` and
  neural modes (the brain canvas becomes a layered accent, never a separate overlay).
- **Adjustable core background + living orb (NEW, 2026-08-29, recurring operator ask):**
  When the operator attaches a 3D animated sphere whose FILE has an opaque violet/blue
  background and says "remove the background / make it transparent + invisible + matched",
  do NOT destructively re-key the active `moon_core.webp` — they REVERT keying changes.
  Instead add a **`core_bg` Settings control** (auto / transparent / solid) that is
  non-destructive: keep the full-bg asset, plus a SEPARATE keyed `moon_core_transparent.webp`
  used only when `core_bg=transparent`. `auto` (default) = `mix-blend-mode:screen` on the
  orb so the violet bg dissolves into the dark HUD (invisible/matched); `transparent` = swap
  to the keyed orb-only file (true alpha); `solid` = file as-is. Full recipe (asset gen via
  PIL red-blue separation across 33 frames, backend route, Settings HTML/JS wiring, CDP
  verification) in `references/core_bg_and_living_orb.md`.
  **Default-imposition correction (2026-08-29):** if the operator has EXPLICITLY said they do
  NOT want the background, set the `core_bg` DEFAULT to `transparent` (not `auto`/`solid`) — a
  `auto`/`solid` default re-imposes the background they rejected. AND bump the `localStorage`
  key (`moon-ui-corebg` → `moon-ui-corebg-vN`) whenever you change that default: `core_bg` is
  frontend-only (the server does not persist it), so a stale stored value silently overrides the
  new default. See the "DEFAULT MUST NOT RE-IMPOSE A BACKGROUND" section in that reference file.
  For "make it exactly functional/animated" (Option B), ADD: idle breathing (`.fusionOrb.idle`
  runs a 6s `moonCoreBreath` scale loop, applied whenever NOT `.thinking`, started on load
  so the orb is alive from first paint), a `#coreState` label under the orb (IDLE / SPEAKING /
  THINKING / EXECUTING, color-coded), `.thinking` glow on reply+workflow (cleared on done),
  and a stronger exec pulse (`onCorePulse(0.6)` + 700ms EXECUTING flash). Verified via CDP:
  `IDLE_ON_LOAD {idle:True,...anim:'moonCoreBreath'}`, reply `{thinking:True, state:'SPEAKING'}`,
  after `{idle:True, state:'IDLE'}`. The idle keyframe MUST keep `translate(-50%,-50%)` or the
  orb jumps off-center. Same reference file has the copy-ready recipe.
- **systemd `start-limit-hit` from rapid restarts**: `systemctl --user restart` fired in a tight
  loop (or overlapping restarts) can trip `start-limit-hit` and leave the service FAILED even though
  the code is fine. Symptom: `curl /api/health` = DOWN but `py_compile` + `import` + launching
  uvicorn on an alt port (e.g. 8779) succeeds ("Application startup complete"). Fix:
  `systemctl --user reset-failed moon-terminal.service` then `start` (not `restart`), and verify
  by launching on an alt port first. Don't "fix" working code to satisfy the DOWN check.
- **Vision API 401 fallback**: when `vision_analyze` returns 401, you cannot SEE the screenshot.
  Verify structurally instead: headless `--screenshot` + PIL pixel analysis — `non-black px ~100%`
  proves it renders (not black); count DISTINCT colors in the central region (hundreds = the WebP/
  core is showing its varied content; a flat/black area is low). Pair with `curl /`=200 and
  `node --check` on the inlined script. See `references/cdp_live_verify.md` (vision-API-401 fallback).

## Operator's recurring HUD polish requests (additive patterns — start here)
These three requests recur; implement additively (no feature removal):
- **"make fonts medium and bold"**: `html,body{font-weight:500}` (medium body) + bump
  titles/labels/buttons to `font-weight:700` (titles 900) via
  `h3,.nav,.metric strong,.btn,.title,.bcell h4,.logo,.aspectTitle,.ratio{font-weight:700}`.
  Keep sublabels/muted text at 500. Orbitron (titles) + Rajdhani (body) load via Google Fonts.
- **"every function button gets its own handler / runs its function"**: one named `doX()` per
  control, bind `el("xBtn").onclick=doX;` (not inline arrow IIFEs). Each `doX` does a REAL
  action (toggle panel, `wsSend({action:"diagnostics"})`, `command("help")`, focus input, append
  log). Expose important ones on `window.MOON_UI` (`doDiagnostics`, `coreSync`) for the
  provider-neutral bridge.
- **"replace the central neural brain with THIS attached image, make it idle animated 3D"** (NEW, 2026-08-16, ESCALATES): this request recurs and the operator iterates it. The arc seen this session:
  (1) attach image → put in core, idle-spin 3D; (2) "replace with THIS circle orbit like Ultron brain, remove old one, make 3D animated, interact with Moon brain workflow" → Ultron energy-core image + 3 orbital rings;
  (3) "weaken orbit speed/colors" → slower/softer; (4) "make it more live and HD and more intelligent brain core type making Moon core" → a LIVING CANVAS 3D NEURAL NETWORK with the attached image as a pulsing nucleus at center (intermediate; recipe in `references/living_neural_brain.md`).
 (5) **FINAL (2026-08-16): "fully remove Moon neural core and put in there as a Moon brain avatar THIS [attached animated webp]"** → the operator SUPERSEDED the canvas brain with the **attached animated WebP as the literal central brain avatar**, fully removing `#coreBrain`/rings/nucleus. Recipe below. So the durable lesson: this recurring request's TRUE target is **an animated image/webp avatar of the brain**, not a procedurally-drawn one — prefer swapping in the attached asset over building canvas neural nets (unless the operator explicitly asks for "more live/intelligent" specifically, which is the canvas path).
  So: start with the attached image, but the operator's TRUE target is a *living, intelligent* core, not a static picture. Concrete recipe for the final state:
  * Asset: copy the image into `web/assets/<name>.png` and add a `FileResponse` route
    `@app.get("/<name>.png")` in `app/terminal_interface.py` (mirrors the existing
    `/moon_core.png` route — `f = WEB_DIR / "assets" / "<name>.png"`). Do NOT inline base64
    (bloats the HTML and breaks future edits); do NOT rely on an external URL.
  * HTML: keep the `.avatar`/`#coreSphere` element (so `querySelector(".avatar").onclick=doCoreSync`
    and the `.core-active` pulse still work) but put a **`<canvas id="coreBrain">` + a `.nucleus` img**
    inside it: `<div class="avatar coreSphere" id="coreSphere"><span class="coreGlow"></span>
    <span class="orbit o1"></span><span class="orbit o2"></span><span class="orbit o3"></span>
    <canvas id="coreBrain"></canvas><img class="nucleus" src="/<name>.png"></div>`.
  * CSS: `.coreSphere{width:46%;top:47%;perspective:900px}`; `#coreBrain{position:absolute;inset:0;
    width:100%;height:100%;z-index:2}`; `.nucleus{position:relative;z-index:4;width:62%;height:62%;
    left:19%;top:19%;border-radius:50%;animation:coreSpin 40s ...,coreBreathe 4.5s ...}`; the 3
    `.orbit` rings (o1/o2/o3) get `border` + `animation:orbitX/Y/Z` at different speeds/tilts for
    parallax depth; `.coreGlow` radial-gradient pulse. Scale all durations by `calc(Xs / var(--idle-speed,1))`.
  * JS — the LIVING BRAIN (`coreBrain(t)`, called from `loop()`): on init build **150 nodes** on a
    Fibonacci sphere, precompute synapse `bLinks` (link if squared-dist < 0.34), and `setInterval`
    ~320ms to spawn a **firing signal** (travels along a link, lights its endpoint node). Each
    frame: rotate nodes (rotateY+rotateX by `t * speed*(1+bActivity*1.4)`), depth-shade links
    (`strokeStyle rgba(255,70+act*120,90+act*60, 0.05+dg*0.12)`), draw traveling cyan pulses
    (`rgba(120,220,255)`) along `bLinks`, draw nodes with depth-based size/alpha and a HOT flare
    (`rgba(150,230,255)`) when `lit>0.25`. Decay `bActivity*=0.97` so it calms. **Reactive**:
    `window.MOON_UI.onCorePulse=(amt)=>{ bActivity=Math.min(1.4,(bActivity||0)+(amt||0.6)); ... add
    "core-active energized" ...}` — so every backend event (assistant_start/workflow/audio/status)
    spins faster + flares brighter, then decays. (This REPLACED the old dead `core3d()` no-op and
    its `coreActivity` var — renamed to `bActivity`.) Keep `#brain{opacity:0}` (old canvas hidden).
  * SAFE JS: removing `#core3d` is fine because `core3d()` guarded on its canvas; but now `loop()`
    must call `coreBrain(t)`, not `core3d(t)`. `node --check` the inlined script after the swap.
  * Tuning lever the operator used: "weaken" = multiply orbit/spin durations ~2× (o1 11→24s, o2 15→34s,
    o3 19→44s, core spin 24→44s) and lower glow alphas. Keep the parallax + reactivity.
  * Verify by VISION on a headless `--screenshot`: center shows a sphere of glowing nodes with
    synapse lines + a brighter central nucleus + orbital rings (NOT a flat radial core); rest intact.
    This operator request recurs — treat the attached image as THE neural core, keep lobes/radar/idleTag framing.
    Exact `coreBrain()` DOM+CSS+JS to copy is in `references/living_neural_brain.md`.
- **LATEST ITERATION (2026-08-16, SUPERSEDES the neural-net above): "fully remove the central
  interface and adjust it to THIS 2nd reference image"** → the operator attached a *different* target
  (a **fusion-reactor core**: white→orange→red sphere in a faint geodesic lattice, 3 tilted
  cyan/orange orbital rings with tick marks, vertical energy conduits, starfield) and wanted the
  OLD central composition (brain-avatar webp + reticle + 6 lobes) **fully removed**. Final build =
  a canvas-drawn **fusion-reactor core** (`coreFx(t)`) + **two flanking data panels** (left cyan
  QUANTUM FLUX / ENTROPY LEVEL / COHERENCE; right orange NEURAL SYNAPSES / FIRING RATE / SIGNAL
  STRENGTH, each with a sparkline). Title `MOON FUSION CORE`, idle `MOON IDLE — NEURAL CORE
  STANDBY`, convergence bar kept. `onCorePulse` spikes a `coreEnergy` var → core brightens + spins
  faster + rings glow on MOON's brain events. So the durable lesson is refined: **the operator
  iterates the central core AGGRESSIVELY across attached references — when they attach a NEW
  reference and say "rebuild THIS area / remove that, use this", treat it as a CLEAN REPLACEMENT,
  not an add-on.** Exact `coreFx()` DOM+CSS+JS recipe is in `references/fusion_core.md`.
- **"make the frame richer / more advanced"**: add rotating `.energy` ring around `#app`, ornate
  `.appframe` corner brackets (4 thick red L-brackets w/ glow), pulsing `.led` chip style,
  stronger avatar `core-active` glow, brighter 2px frame border — on top of existing grid-floor /
  light-beam / sparkle-particles / scan-sweep / CRT-flicker FX. See `moon-engineering`
  `references/terminal_futuristic_fx.md` for the full FX library.
- **"make fonts deep hot red + frame brighter/richer"** (NEW, 2026-08-15): shift the palette to
  SATURATED red and add stronger red glows:
  * root vars: `--text:#ff5a5a; --muted:#ff8a8a; --line:#e21b1b; --line2:#ff3a3a`.
  * text elements get hot-red + glow: `h3{text-shadow:0 0 10px rgba(255,30,30,.8)}`,
    `.title{text-shadow:0 0 18px rgba(255,0,0,.6),0 0 30px rgba(255,30,30,.4)}`,
    `.logo{color:var(--red);text-shadow:0 0 14px var(--red),0 0 26px rgba(255,30,30,.6)}`,
    `.stats{color:#ff7a7a} .stats b{color:#ff5a5a;text-shadow:...}`, `.nav{color:#ff8a8a}`,
    `.metric strong{color:#ff4a4a;text-shadow:0 0 14px rgba(255,0,0,.85)}`,
    `.bcell h4{color:#ffb0b0;text-shadow:0 0 8px rgba(255,30,30,.6)}`.
  * brighter frame: `#app{border:2px solid var(--red);box-shadow:0 0 70px rgba(255,0,0,.35)...,inset 0 0 90px...}`,
    `.energy{box-shadow:inset 0 0 80px rgba(255,0,0,.18),0 0 50px rgba(255,0,0,.30)}`,
    `.energy:before{border-top:2px solid rgba(255,120,120,.95)...}`,
    `.appframe i{border-width:4px;filter:drop-shadow(0 0 14px #ff2a2a)}`,
    `.frame-tr,.frame-bl,#app:before,#app:after{border-width:3px;box-shadow:0 0 22px rgba(255,0,0,.8)}`,
    `.panel{box-shadow:inset 0 0 22px rgba(255,0,0,.10),0 0 18px rgba(255,0,0,.18)}`.
  * Verify the theme WITHOUT a screenshot: CDP `getComputedStyle(document.body).color` should
    return `rgb(255, 90, 90)` for the hottest setting; the **balanced** default the operator
    approved this session is `--text:#ff6e6e` → `rgb(255, 110, 110)` (saturated but readable,
    not eye-searing). See `scripts/cdp_hud_audit.py`.
- **"make this the DEFAULT Moon terminal"** (NEW, 2026-08-15): when the operator promotes the
  HUD to Moon's canonical default, NO new UI work is needed — it is already served:
  * Backend already serves `web/moon_terminal.html` at `GET /` via `terminal_page()` in
    `app/terminal_interface.py` (reads the file per-request, so HTML/CSS/JS edits need NO restart).
    `main.py terminal` / `main.py start` and `scripts/moon_launcher.py` (default `mode="terminal"`)
    all launch it on `127.0.0.1:8777`.
  * To make `python main.py` (no subcommand) also launch the terminal instead of printing help,
    change `main.py`'s final `else: ap.print_help()` to `_run_terminal()`. Purely additive.
  * Verify: hit `/` and confirm `/status` + `/theme` = 200.
- **"make the terminal interface colour like dangerous/offensive hacker" -> "more gorgeous" -> "more deep"** (NEW, 2026-08-29): this is a 3-step COLOR-ONLY escalation the operator runs in order. Layout/grid is untouched (see the no-overlap layout below). Consolidated recipe + bulk-recolor regex (with the 4-vs-5 group gotcha) in `references/hud_hacker_palette.md`. Summary:
  * Start: toxic matrix-green primary (`#00ff66`/`#19ff9b`) on charcoal, monospace `Share Tech Mono`, amber+red alarm accents.
  * "more gorgeous": emerald->cyan gradient text on titles/logo, violet/magenta glitch accents, richer gradient base, stronger-but-balanced glow.
  * "more deep": near-black void `#01040a`, saturated neon (`#0dff8c`/`#00ffa6`), bigger outer glow (80px) + deeper inset (120/260px), darker panel fills.
  * PRESERVE the central fusion-core orb (orange/red) + `--red` alarm as the danger centerpiece — do NOT green those.
  * Intensity is the AGENT'S call (operator said "decided yourself") — pick a balanced premium value and implement+verify+commit; do NOT ask.
  * Verify color edits WITHOUT a screenshot: `node --check` the inlined script + `curl /` = 200. (Vision service was 401 this session, so visual confirm was impossible — rely on structural + endpoint checks and tell the operator to open the screenshot file.)

### No-overlap layout (CSS Grid) — THE fix for "panels overlap / not compatible for any display"
If the operator says panels stack over each other, convert the absolute-positioned
content containers to a CSS Grid (full recipe + verify in `references/hud_no_overlap_layout.md`).
Key: `#app` is a 4-row grid (header/main/bottom/footer); `.main` is a 4-col grid; `#center` is
a 2-row grid (brainPanel/matrix); `.cmd` lives INSIDE `footer` as grid col 1 (NEVER
`position:fixed`). Preserve every element ID — only container CSS changes. After the
swap `grep "position:fixed"` must return NOTHING for content containers.

### Per-panel animated function glyphs (additive, 2026-08-29)
Operator: "every panel have an animated image based on function name, centered in the
middle of every panel." Delivered as a JS injector that drops a centered, function-keyed
inline-SVG emblem behind each panel's live data. Full recipe + exact glyph/accent map +
the bulk-recolor regex gotcha in `references/hud_panel_glyphs.md`. Summary of the durable rules:
- Build inline `<svg viewBox="0 0 100 100">` emblems from SAFE elements only
  (circle/line/path/rect/polygon/polyline/g) — NO `foreignObject`, NO inline `<style>`, NO
  CSS `transform` on bare shapes (put animation on a `<g class="spin|pulse|scan|dash|breathe">`).
- `.pglyph{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:0;
  opacity:.22;pointer-events:none;mix-blend-mode:screen;color:var(--emerald)}` → centered,
  behind content, non-blocking, glows through the dark panel.
- `injectGlyphs()` runs AFTER `connect()`; picks `data-glyph` → panel `id` → header text →
  regex fallback; sets `div.style.color` from a per-function ACCENT map (threat=red,
  eye/radar=amber, net/cpu=cyan, brain/core=violet, agent/chat=green, diamond=magenta) so
  panels read distinct + informative. Idempotent (skip if `.pglyph` exists).
- GENERAL additive polish pattern — reuse whenever the operator wants "every panel show its
  function as an icon/glyph." Copy the structure; swap the SVG strings.

### Operator autonomy on cosmetic intensity (2026-08-29 — override the "ask" reflex)
When the operator says "make it look good / deeper / more gorgeous / tune it by your own
decision", they have EXPLICITLY delegated the aesthetic call. DO NOT ask which value —
pick a balanced premium intensity and implement + verify + commit. For HUD color: opacity
~.18-.24, outer glow 14-22px, near-black gradient base, saturated-but-readable neon
(`--text` greens like `#9dffc4`/`#b6ffe0`, NOT eye-searing). The "decide yourself" directive
applies to PURELY COSMETIC HUD color/intensity work; it does NOT override safety/correctness
gates (keep the fusion-core orb + `--red` alarm as the danger centerpiece; still `node --check`
after every edit; still verify backend HEALTHY).

### PLAN-MODE + LIVE PREVIEW BEFORE APPROVAL (2026-08-29 — OVERRIDES "decide yourself" for STRUCTURAL removals)
The "decide yourself / don't ask" rule applies to PURELY COSMETIC intensity/color choices.
It does NOT apply when the operator asks to **REMOVE a visible element** (a face, the amber
bloom, the orbital rings, the fiery backdrop, or the background *inside* an attached image).
This session the operator interrupted repeatedly and forced a different workflow:
- "build plan mode for ensure what it look like and what you suggested me for my understanding
  after that i approve it" → write a plan (`.hermes/plans/*.md` or inline) describing the
  CURRENT look, what you'd remove/keep, and what changes — then STOP and wait for approval.
- "first show me what you suggested and how its look" + "not approve for this stop this task and
  start new" → for any visual change, RENDER a live preview (headless `--screenshot`, or for an
  image edit a MEDIA attachment of the candidate) and SHOW it before swapping anything in.
- Hard rule: **no swap of the served asset / no deletion of a visible HUD element until the
  operator has SEEN the proposed result and approved it.** Generate a candidate to `/tmp`,
  attach it as MEDIA, and ask (A) use as-is / (B) adjust / (C) other. Only then edit the repo.
This is a durable correction: when the change is a *removal* or a *image-background isolation*,
plan + preview + wait — do not auto-apply just because an earlier cosmetic task gave you
aesthetic autonomy. (Background isolation recipe: `references/webp_core_isolation.md`.)

### FATAL JS bug that kills the whole HUD (re-confirmed 2026-08-29)
A duplicate `const` declaration in the inlined `<script>` (e.g. `const integ` declared
twice in the same function) is a `SyntaxError` that makes the ENTIRE script fail to parse
-> no `connect()`, no WS, terminal 100% dead on every machine ("not functional"). This is
distinct from the CSS-leaked-into-`<script>` bug. **Always `node --check` the extracted
inlined script after ANY HTML edit** (not just JS edits):
`python3 -c "import re;h=open('web/moon_terminal.html').read();open('/tmp/m.js','w').write('\n'.join(re.findall(r'<script>(.*?)</script>',h,re.S)))" && node --check /tmp/m.js`


  "tweak intensity / decided yourself / make it look good (you decide)" → DO NOT ask. Pick a
  balanced premium value and implement+verify+commit: saturated-but-readable hot-red text
  (`--text:#ff6e6e`, NOT the eye-searing `#ff5a5a`), strong frame glow, and a *softened* CRT
  (gentle 8s ease-in-out opacity breathe `.97<->1`, NOT a hard `6s steps(60)` jitter which looks
  broken). The operator explicitly approved this: "yes i want to tweak intensity what is best for
  looking good decided yourself and make this terminal Moon default terminal."
- **"remove the rounded stick / make corners square"** (NEW, 2026-08-16): the operator dislikes the
  rounded "stick" frame that wraps the whole interface. Make it MILITARY SQUARE:
  * Whole-frame: `.energy{...border-radius:0}` and the `#app` outer frame has NO radius.
  * Panels: `.panel{clip-path:polygon(0 2px,2px 0,calc(100% - 2px) 0,100% 2px,100% calc(100% - 2px),calc(100% - 2px) 100%,2px 100%,0 calc(100% - 2px))}`
    (was 9px corners → 2px sharp corners). Keep glow/borders; just kill the rounding.
  Verify by VISION (vision reliably reports "all panels have sharp 90-degree square corners").
- **"make it idle / more sci-fi advanced look + auto-display"** (NEW, 2026-08-16):
  * **Auto-display**: the TERMINAL panel should be open by default → `<div id="terminal" class="open">`
    (and the backend already serves the file per-request, no restart needed for HTML edits).
  * **Idle / attract-state**: when no interaction for ~9s, MOON "breathes" calmly + a slow rotating
    RADAR SWEEP scans the central brain + a "◌ MOON IDLE — NEURAL CORE STANDBY" readout fades in.
    Implement as a `#center.idle` class: `.brainPanel{animation:corebreathe 6s...}`, a `.radar`
    element (conic-gradient sweep, 5.5s rotate) inside the brain panel, and an `.idleTag`. JS:
    `setIdle(true)` on boot + after 9s of inactivity; any `click`/`keydown`/`touchstart` (capture
    phase) OR a backend WS message calls `wakeFromIdle()` which clears the timer and re-arms it.
    Hook the WS message by wrapping `window.MOON_UI.onMessage` (guard with `typeof===function`).
- **"ensure every button has its own genuine function (no fake)"** (NEW, 2026-08-16): every footer
  tab / Function-Dock / nav / core-click MUST call a REAL backend action or do a REAL local action
  (toggle panel, focus input, `command(...)`). AUDIT each `doX()` — if it only does
  `addLog("[X] ...")` with NO `wsSend`/real effect, it is a FAKE stub. This session found
  `doAiChat`/`doTasks`/`doUpdates` were fake (addLog-only) → fixed to fire `send_message`/`status`/
  * Verify genuinely by opening a python WS to `/ws` and confirming the action returns a
  real framed reply (frames use `"type"`, NOT `"action"` — filter on `type`). See the data-path
  proof in `references/headless-live-data-verification.md`.
  - **Pitfall — a WS-action button that sets a flag is only as good as the code that checks it.** A button can `wsSend({action:"stop"})` and the backend can set `_stop_requested=True` and reply `assistant_done`, yet the button still be *cosmetic* if no later code path reads that flag. This session found the function-dock STOP button did exactly that: `_stop_requested` was set but never checked by `send_message` or `run`, so pressing STOP then chatting still started a task. **Diagnose**: after a button's WS action returns, send a *follow-up* action that the flag should block and confirm it is refused (not just that the first reply arrived). **Fix pattern**: declare the flag `global` at the TOP of `_handle()` (before the first branch that reads it) and check it at the top of EVERY task-starting path (`send_message`, `run`, and any wake-triggered action). Clear the flag only when a task actually starts (the `run` path), so the block persists across multiple UI attempts until real work begins. See `references/ui_button_audit.md` for the full recipe + the raw-WS verification that proves a block is real.
    so it always has a non-empty command — an empty `command` makes the backend `return` early
    with no reply.)
- **"add a boot-up sequence / per-panel glitch+scan / whole-HUD scanline sweep / sound cue"**
  (NEW, 2026-08-16): all delivered additively. Concrete recipe (HTML+CSS+JS) in
  `references/hud_fx_recipe.md` — COPY from there rather than hand-typing. Key points:
  * **Boot sequence**: `#boot` overlay (logo + progress bar + staggered steps, current step
    in green) plays once on the WS `ready` frame, then fades out (`bootChime()` on complete).
    **CRITICAL**: `handle()`'s `case "ready":` did NOT call `window.MOON_UI.onReady` by default —
    you MUST add `if(m.type==="ready" && typeof window.MOON_UI.onReady==="function") window.MOON_UI.onReady(m);`
    inside that case, and set the `onReady` hook BEFORE `connect()`, or the boot never fires.
  * **Per-panel scan + glitch**: `.panel:after` = a thin red scan bar travelling down each panel
    (staggered per `:nth-child`); `.panel.glitch` = RGB-split jitter. Use ONE shared
    `triggerGlitch()` called by both an ambient `glitchLoop()` AND the `onMessage` wrapper, so a
    glitch fires on every incoming backend frame (throttle to 220ms so bursts don't stack).
  * **Whole-HUD sweep**: `.sweep` = a thin bright bar travelling top→bottom across the whole
    interface (`mix-blend-mode:screen`, always ≥ faintly visible). Scale its duration with idle speed.
  * **Configurable idle speed**: idle animations consume `--idle-speed` via
    `calc(6s / var(--idle-speed,1))`; an IDLE SPEED selector in the DISPLAY panel sets the var on
    `#app` (SLOW 2 / NORMAL 1 / FAST 0.5 / HYPER 0.25) and persists to localStorage.
  * **Self-contained WebAudio cues**: UI audio uses the browser `AudioContext` synth (NOT the
    backend TTS — unavailable in this CPU-only sandbox). `bootChime()` (rising arpeggio) on boot
    complete; `blip()` on reactive glitch. Resume the context on first gesture (autoplay policy).
    Works OFFLINE, no files, no deps.
  * **`0.0.0.0` LAN binding**: change `main.py _run_terminal()` uvicorn `--host 127.0.0.1` →
    `0.0.0.0` so the terminal is reachable from other devices at `http://<host-ip>:8777`. Verify
    with `ss -ltnp | grep 8777` → `0.0.0.0:8777`. (Operator offered this earlier; he later said
    "build all you suggested", so it is now part of the default build.)
  * **Verify by VISION on a headless `--screenshot`**: boot screen at `--virtual-time-budget=900`
    (≈25 KB, logo + partial bar); full HUD after boot (≈590 KB) with per-panel scan lines visible
    and square corners intact. Also `node --check` the inlined script after every JS edit.

## Fiery backdrop (reference image → DIM backdrop, never recolor the HUD)
When the operator attaches a fiery/amber/orange image (e.g. a holographic-sphere core) and
says "rebuild with THIS" / "use this as the backdrop", the durable MOON rule is: **the
fiery image is a DIM BACKDROP only — it must NEVER recolor the canonical red/black HUD.**
Keep `--text`/`--red`/`--line` red; the image sits behind at low opacity and glows through
panel gaps. Concrete recipe (used 2026-08-17, verified by VISION):
- **Asset**: `convert '<img>.webp[0]' -resize 1920x1080^ -gravity center -extent 1920x1080`
  `-modulate 80,58,100 -brightness-contrast -25x-10 web/assets/moon_fiery.jpg` (single frame
  ONLY — a multi-frame webp explodes into 30+ JPGs if you omit `[0]`; see Pitfalls).
- **Backend route**: `@app.get("/moon_fiery.jpg")` → `FileResponse(WEB_DIR/"assets"/"moon_fiery.jpg",`
  `media_type="image/jpeg")` (mirrors `/moon_core.png`). Verified 200 `image/jpeg`.
- **CSS**: one `.backdrop` div as the FIRST child inside `#app` (behind `.grid`):
  `position:absolute;inset:0;z-index:0;background:#030000 center/cover no-repeat;`
  `opacity:.40;filter:saturate(.65) brightness(.66);mix-blend-mode:screen;pointer-events:none`
  plus `.backdrop:after` = radial vignette `transparent 0 28%, rgba(0,0,0,.5) 76%, #000 100%`
  so edges recede to black for HUD contrast. Bump opacity to ~.5 in a very dark room.
- **Verify**: serve, `curl /moon_fiery.jpg` → 200, then VISION on a *full-HUD* screenshot must
  confirm "red/black HUD intact + fiery glow behind, not recoloring red." If VISION says the red
  elements turned orange/amber, opacity/blend is too high — lower it.
Full recipe also in `references/fiery_backdrop.md`.

### DOMINANT central orb core — the fiery image AS the core (2026-08-17, ESCALATES the dim-backdrop)
The operator attached the SAME fiery holographic sphere and iterated from "dim backdrop only" to
"**rebuild the terminal WITH this — make the orb the dominant central core**". So the durable lesson
refines the rule: the fiery image can be BOTH a dim full-screen backdrop AND, at higher fidelity, the
**literal glowing centerpiece** of the central core — as long as the red/black HUD stays canonical
(red text/borders never turn orange). Use this variant when the operator says "rebuild with THIS" and
wants the image front-and-center, not merely background glow.

Concrete recipe (verified by VISION 2026-08-17 — center dominated by bright fiery sphere, red HUD intact):
- **Orb asset** (bright, edges faded to black so it screen-blends as a glowing sphere):
  `convert '<img>.webp[0]' -resize 760x760^ -gravity center -extent 760x760 -modulate 112,96,100`
  `\( -size 760x760 radial-gradient:"gray(255)"-"gray(0)" \) -compose multiply -composite`
  `-brightness-contrast 4x8 web/assets/moon_orb.jpg`
  (radial multiply → transparent/black edges; keeps the sphere shape instead of a square photo.)
- **Backend route**: mirror the pattern — `@app.get("/moon_orb.jpg")` → `FileResponse(WEB_DIR/"assets"/"moon_orb.jpg", media_type="image/jpeg")`.
- **CSS**: a `.fusionOrb` div INSIDE `.fusionCore` (behind the data panels, `z-index:-1`), screen-blended
  and reactive via a `--core-e` var the JS sets on every brain event:
  `.fusionOrb{position:absolute;left:50%;top:50%;width:118%;height:118%;transform:translate(-50%,-50%) scale(calc(1 + var(--core-e,0)*0.10));`
  `background:#000 center/cover no-repeat;filter:saturate(1.05) brightness(calc(1 + var(--core-e,0)*0.55));`
  `mix-blend-mode:screen;opacity:calc(.82 + var(--core-e,0)*0.18);border-radius:50%;`
  `box-shadow:0 0 calc(60px + var(--core-e,0)*70px) rgba(255,120,40,calc(.5 + var(--core-e,0)*.4));pointer-events:none}`
- **HTML**: `<div class="fusionCore"><div class="fusionOrb" id="fusionOrb" style="background-image:url('/moon_orb.jpg')"></div><canvas id="coreFx"></canvas></div>`
  (keep the `#coreFx` canvas too — it still draws the geodesic conduit glow on top of the orb).
- **JS reactivity** — extend `window.MOON_UI.onCorePulse` to set `--core-e` (so the REAL brain events
  pulse the orb) alongside the existing `coreEnergy` logic:
  `const e=Math.min(1,(coreEnergy||0)/1.5); document.documentElement.style.setProperty("--core-e", e.toFixed(3));`
  `const orb=document.getElementById("fusionOrb"); if(orb){orb.style.filter="brightness("+(1+Math.min(0.8,amt||0.6))+") saturate(1.2)";clearTimeout(orb._t);orb._t=setTimeout(()=>orb.style.filter="",700+(amt||0.6)*500);}`
- **Verify**: serve, `curl /moon_orb.jpg` → 200 `image/jpeg`; VISION on a full-HUD screenshot must
  confirm "central core dominated by bright fiery/amber sphere, framed by the data panels, red/black
  HUD intact." Keep the dim `moon_fiery.jpg` full-screen backdrop too — they layer (backdrop behind, orb center).

### Auto-open the HUD on MOON's boot (NOT system/login boot) — 2026-08-17
The operator drew a hard line: **"auto-open on Moon boot not system on boot."** So the
browser-open rides MOON's own startup, not an XDG/login autostart. Implementation:
inside `_run_terminal()` (in `main.py`) spawn a daemon thread that waits for `:8777`, then
launches Chromium kiosk (`--app=http://127.0.0.1:8777/ --kiosk`). It is **display-gated**
(skips on headless/SSH where `$DISPLAY` is unset) and **port-waits** before opening. The
login-time XFCE `.desktop` autostart was DELETED to honor "not system on boot."
Full recipe + verified check: `references/auto_open_on_boot.md` (primary = MOON-boot; the
login/system path is documented there as SUPERSEDED).
- **Verify live (no screenshot):** after `python main.py terminal`, `curl /` → 200 AND
  `pgrep -af chromium | grep -o '\-\-app=http://127.0.0.1:8777/'` returns the flag.
- **Idempotent single-window auto-open (2026-08-17):** the daemon thread opens a browser once per
  backend process, BUT if you (or the operator) manually launch extra Chrome windows OR restart the
  backend while the old one is still alive, windows STACK into many duplicates. Fix: a **lockfile**
  `/tmp/moon_hud_open.lock` records the opener child pid; on entry, if the lock exists AND
  `/proc/<pid>` is still alive, `_auto_open_ui` returns early (no second window). Write the pid only
  after a successful `Popen`. This makes "open the terminal" always yield exactly ONE window.
  Verify: `xdotool search --onlyvisible --name MOON | wc -l` → 1 after a fresh start. Clear the lock
  (`rm -f /tmp/moon_hud_open.lock`) before a deliberate restart so the new process opens its own.
- **Kill the `--no-sandbox` warning banner (2026-08-17):** launching Chrome with `--no-sandbox`
  paints a top banner "You are using an unsupported command-line flag: --no-sandbox" that looks like
  a broken/black launch in a screenshot. Switch the launch flag to `--disable-setuid-sandbox`
  (no banner, identical behavior on this box). The operator screenshotted the banner and thought the
  HUD was broken — it wasn't; the banner alone was the artifact. Always use `--disable-setuid-sandbox`.
- **Full HD resolution (2026-08-17):** the operator wants the HUD "full HD for a better visual."
  * Launch `--window-size=1920,1080 --start-maximized` (was 1366×768).
  * Add a scalable UI base: `#app{font-size:clamp(13px,1.02vw,19px)}` and `#app.hd{font-size:clamp(15px,1.3vw,24px)}`
    so the interface density fills a 1080p+ screen instead of looking small. Canvases already render at
    `devicePixelRatio` (crisp) — no canvas change needed.
  * **Settings RESOLUTION toggle** (HD RICH / COMPACT DENSE): add `resolution` to `_DEFAULT_SETTINGS`
    + the `/api/settings` POST allowlist; a `#setRes` button group sets `_resolution` and
    `applyResolution()` toggles `#app.hd` (`app.classList.toggle("hd", _resolution!=="compact")`).
    Persist `localStorage('moon-ui-resolution')`; `restoreSettings()` re-applies on load. This is the
    operator's "make it manually configurable" wish applied to resolution.
- **When you EDIT the central orb image, also soften the `coreFx` canvas core (2026-08-17).** The
  operator attached a fiery image, had the yellow circle removed via inpainting (see
  `references/remove_object_inpaint.md`), and wanted it applied as the core. Applying the image to
  `moon_orb.jpg` alone is NOT enough — `coreFx(t)` ALSO paints a bright **white→orange→red core disc**
  (`fxCtx.arc(cx,cy,R*0.18*pulse … rgba(255,255,250,…)`) ON TOP of the orb, recreating the exact
  yellow circle the user wanted gone. Fix: lower the canvas core's center brightness from near-white
  to a warm amber and shrink the solid inner point — e.g. gradient `rgba(255,210,150,.55)`→
  `rgba(255,130,40,.70)`→`rgba(210,60,20,.6)`→transparent, and a small soft `rgba(255,200,140,.35)`
  inner highlight (`R*0.10`) instead of the `R*0.18` white-hot point. Result: a soft fiery glow that
  lets the edited backdrop show through, no hard yellow disc. `node --check` after the edit.

### SETTINGS HUB + display-agnostic auto-open + swappable central avatar (2026-08-17, RECURRING class)
When the operator says "put all interface changes in a SETTINGS button / make it manually
configurable / change into interface / I want to swap the central brain avatar", build a
**single Settings hub** that owns EVERY interface change. Concrete, reusable recipe:

- **SETTINGS button**: add `<button id="setBtn" class="setBtn">⚙ SETTINGS</button>` to the
  top bar; `el("setBtn").onclick=()=>toggleSettings(true);`. The CONFIGURATION nav item also
  opens it. Everything else (host/port/display/browser/aspect/avatar/idle) lives inside.
- **Backend persistence**: `GET/POST /api/settings` in `app/terminal_interface.py` reads/writes
  `web/moon_settings.json` (defaults in `_DEFAULT_SETTINGS`: host, port, display, browser, aspect,
  avatar_mode, autostart, idle_speed). Frontend `loadSettingsUI()` GETs + merges `localStorage`
  fallbacks; `saveSettings()` POSTs and falls back to `localStorage` if the server is offline
  (never throw).
- **Display-agnostic auto-open** (in `main.py _run_terminal`): detect X11 (`DISPLAY`) /
  Wayland (`WAYLAND_DISPLAY`) / headless (skip) — `_detect_display()` returns `(disp, wayland)`.
  `_detect_browser()` tries settings override → `google-chrome`/`chromium`/`edge` → known
  absolute paths (`/opt/google/chrome/chrome`). Launch with `--app=<URL>`; add
  `--ozone-platform=wayland` + `--wayland-display=` on Wayland, `--display=` on X11. Honor
  `autostart` (skip if false) and never crash if no GUI. **This SUPERSEDES the earlier
  "MOON-boot-only" kiosk launcher** — same intent (open on MOON's own boot, not system/login),
  but now portable to any display.
- **Manual aspect-ratio control** (in Settings + keep the floating `#aspect` panel): `setAspect(r)`
  sets `#app` width/height to `min(100vw, {w/h*100}vh)` etc., syncs both button groups, persists
  `localStorage('moon-ui-ratio')`. Supported: auto/16:9/21:9/32:9/16:10/4:3/1:1/9:16.
- **Swappable central avatar** (the operator's recurring "change the central brain" wish, now a
  toggle instead of a rebuild): add a second `<canvas id="neuralFx">` next to `#coreFx` inside
  `.fusionCore`. `applyAvatarMode()` shows `#fusionOrb`+`#coreFx` for `avatar_mode="fusion"` (the
  fiery sphere), or `#neuralFx` for `"neural"` (animated neural-brain lattice). `neuralFx(t)` draws
  ~26 rotating nodes + synapses that energize via the existing `coreEnergy` var (shared with
  `coreFx`), so both avatars react to MOON's brain events. Settings `data-m="fusion|neural"`
  buttons set `_avatarMode`; persist `localStorage('moon-ui-avatar')`. `restoreSettings()` on load
  re-applies saved aspect + avatar + idle speed.
- **Live backend power (WS `exec` + `log_stream`) + SHELL console (2026-08-17, SOLID pattern):**
  The operator's "push it further → A: backend power" = a real operator shell + live log stream. Recipe:
  * Backend WS actions in `app/terminal_interface.py`:
    - `elif action == "exec":` → `out, code = _shell_dispatch(cmd); _log(f"exec[{code}] {cmd}", ...); await send(type="exec_output", cmd=cmd, exit=code, output=out)`. Use the existing **allowlist** `_shell_dispatch` (safe cmds: status/ps/df/free/uname/uptime/netstat/ip/ls/pwd/echo/date/whoami/env/nproc/cat<file>). Non-listed → `denied` (security holds). NEVER expose arbitrary shells.
    - `elif action == "log_stream":` → append the connection's `send` coroutine to a module-level `_LOG_SUBSCRIBERS` list; replay last ~30 `_LOG_BUF` entries; then every `_log()` call broadcasts `type:"log"` to all subscribers. **CRITICAL**: `_log` is synchronous, so broadcast with `asyncio.ensure_future(sub(...))` — NOT `sub(...)` (which silently no-ops; see Pitfalls). Remove the subscriber on disconnect.
  * Frontend: a `consoleMode` var (`"chat"|"shell"`) toggled by footer tabs (AI CHAT → chat, new **SHELL** tab → shell). `command(cmd)` routes: shell → `wsSend({action:"exec",cmd})` and renders the `exec_output` frame in `#cliOut`; chat → existing `send_message` path. `connect()` sends `wsSend({action:"log_stream"})` on open so System Logs gets live backend events. `handle()` gains `case "exec_output":` (append pre+body lines) and `case "log":` (→ `addLog`).
  * Add a **SHELL footer tab** (`<div class="btn" id="shellBtn">▦ SHELL</div>`) and wire `el("shellBtn").onclick`. **Footer grid must hold ALL tabs** — see FOOTER GRID OVERFLOW (now 13 tabs → `grid-template-columns:13% repeat(13,minmax(0,1fr))`).
  * Verify: raw WS test sends `exec` for status/ps/df (real output, exit 0) + `bogus_cmd` (denied, exit 1) + `log_stream` (≥N live `log` frames). Counting frames proves delivery — the 0-frame case is the `ensure_future` bug.
- **Live-tunable canvas parameter via a Settings slider (2026-08-17, reuse pattern):** for any canvas effect the operator wants to "tweak intensity," expose a `range` input in Settings and a module-level multiplier (e.g. `let coreGlow=1.0`) applied in the draw fn. `oninput` sets the var + `localStorage`; `collectSettings`/`loadSettingsUI`/`applySettingsNow`/`resetSettings` + on-load restore carry it; backend `_DEFAULT_SETTINGS` + POST allowlist add the field (`core_glow`). The **Core glow** slider (0.2–2.0) in the avatar fieldset is the worked example — the `coreFx` bloom alphas/shadow multiply by `gl=coreGlow` with `Math.min(1, base*gl)` to clamp. This lets the operator dial the look LIVE with no reload — far better than round-trip edits. Add a slider whenever the operator says "tweak the X intensity."
- **Verify (no screenshot)**: CDP `Runtime.evaluate` asserting `document.getElementById('setBtn')`
  exists, `#settingsPanel` exists, `#neuralFx` exists, `#setAspect .ratio` count == 8,
  `#setAvatar .ratio` count == 2, and `typeof applyAvatarMode == "function"`. Then hit
  `GET /api/settings` → default JSON; `POST /api/settings` with `{"avatar_mode":"neural","aspect":"16:9"}`
  → `ok:true` and `cat web/moon_settings.json` shows the write. Full reusable code in
  `references/settings_hub.md`.

### Functional-backend WS test pattern (proves the backend actually works)
A naive test that opens a second recv-coroutine while sending races with the main recv and
errors `cannot call recv while another coroutine is already running recv`. Correct pattern:
single `async with websockets.connect` + one `async def next_frame(): return json.loads(await asyncio.wait_for(ws.recv(),10))`. First drain a few inbound push frames (up to 4) to absorb `ready`/`status`, THEN `await ws.send(...)` and read exactly one frame per action with `next_frame()`. Action round-trips seen live this session (all real): `status`→`status`, `diagnostics`→`assistant_start`, `memory_search`/`knowledge`→`workflow`, `capabilities`→`assistant_chunk`. This proves the moon-brain answers — do this before claiming "backend functional." (Frames carry `"type"`, not `"action"` — filter on `type`.)

### Root cause of "monitoring did not properly functional" (2026-08-17)
Operator reported the HUD panels showed `--%` / `1.02 PB` / `MINIMAL` — looked dead.
**Root cause**: the WebSocket only sent a bare `ready` frame on connect (`{type:"ready",
message:"..."}`) — NO `status` payload with a `system` object. The frontend's `applyStatus()`
therefore fell back to the **static HTML defaults** in `web/moon_terminal.html` (every panel
ships with a placeholder like `<b id="smCpu">--%</b>`). The HUD was wired correctly; it just
never received live data.
**Fix (committed)**: in `app/terminal_interface.py`, after sending `ready`, immediately send a
real `status` frame — `await send(type="status", **_moon_status(orch))` (which includes
`system.cpu`, `system.ram_pct`, `system.temp_c`, `agents`, etc. at top level, NO `status`
sub-key, so the frontend `applyStatus(m.status||m)` resolves correctly). PLUS a frontend 3s
heartbeat: `setInterval(()=>wsSend({action:"status"}), 3000)` so panels always reflect live
data, with a boot-safety reveal if the boot overlay never clears.
**Lesson**: when a WS-driven HUD "shows nothing live," first confirm the backend actually
PUSHES a data-carrying frame on connect (raw WS client — see
`references/ws_live_data_verification.md`). Don't assume the frontend binding is broken.
And a periodic heartbeat makes monitoring resilient to a missed initial frame.

### Central crowding fixes (additive polish, 2026-08-17)
- **THREAT ASSESSMENT GRID**: was a cramped `display:grid; grid-template-columns:60% 40%`
  (red radial map + 5 long stat lines) → overflowed. Fix: `.threat{display:flex;
  flex-direction:column;gap:6px;overflow:auto}` with `.map{height:42%;flex:0 0 auto}` on top
  and `.threat .stats{position:static;width:auto}` below. No more collision.
- **AI BRIDGE**: nudge the `#terminal` panel left edge `9% → 12.5%` for clearance, and
  contain the cell: `<div class="term" style="overflow:hidden">` + a readable muted-hint
  color (`#b06a3a`, `font-size:.86em`) so lines don't bleed into the panel edge.
- Verify by `--dump-dom` + grep for `THREAT ASSESSMENT GRID` / `AI BRIDGE` present (no
  screenshot needed — avoids the boot-overlay capture pitfall).

### Launch-readiness: bake the PYTHONPATH fix into `main.py` (2026-08-17)
The operator's run ritual should be a plain `python main.py terminal` with NO manual `env -u PYTHONPATH`.
Bake it into `_run_terminal()` so the launcher is launch-ready on its own:
```python
def _run_terminal() -> None:
    import os, subprocess, sys
    env = dict(os.environ); env.pop("PYTHONPATH", None)  # drop Hermes 3.11 site-packages that shadows venv 3.13 pydantic_core
    print("🌙 MOON Terminal starting at http://0.0.0.0:8777 ...")
    subprocess.run([sys.executable, "-m", "uvicorn", "app.terminal_interface:app",
                    "--host", "0.0.0.0", "--port", "8777", "--log-level", "info"], env=env)
```
- Non-destructive: only affects the child subprocess, never mutates the parent shell. After this, the
launcher self-clears the blocker and `python main.py terminal` just works. (Runtime verification this
session: started under the still-set global PYTHONPATH and it booted fine → proves the fix.)

### System Logs legibility polish (additive, 2026-08-17)
The System Logs panel (`.logs #logs`) is a real-time event stream the operator flagged as "too dim / blank".
Fix additively — do NOT remove the panel; make the stream legible and severity-coded.
- **CSS**: brighten base lines + color by a `data-s` attribute (keeps red/black HUD, just adds readable hue):
  `.logs #logs .line{color:#ff8e8e;text-shadow:0 0 5px rgba(255,40,40,.35);padding:1px 4px;border-left:2px solid transparent;white-space:pre-wrap;word-break:break-word}`
  `.logs #logs .line:hover{background:rgba(255,0,0,.07)}`
  `.logs #logs .line[data-s="ok"]{color:#7dffa6;border-left-color:#1f8a4c}`
  `.logs #logs .line[data-s="warn"]{color:#ffd36a;border-left-color:#a8761f}`
  `.logs #logs .line[data-s="err"]{color:#ff6b6b;border-left-color:#a31f1f}`
  `.logs #logs .line[data-s="sys"]{color:#9fd6ff;border-left-color:#1f5ea3}`
  `.logs #logs .line[data-s="moon"]{color:#ffb0d6;border-left-color:#a31f6a}`
- **JS**: auto-tag each line in `addLog(t)` by its `[TAG]` prefix, BEFORE `d.textContent`/`prepend`:
  `const s=(t.match(/^\[(\w+)\]/)||[])[1]; const sev={"OK":"ok","SYS":"sys","SYSTEM":"sys","MOON":"moon","ERR":"err","WARN":"warn","TALK":"warn"}[s]; if(sev) d.setAttribute("data-s",sev);`
- **Verify WITHOUT a screenshot**: after load, `chromium --headless --no-sandbox --disable-gpu --dump-dom <url> | grep 'data-s="'` → expect `data-s="ok|sys|moon|warn|err"` present (boot seeds OK/SYS/MOON lines). That proves the coloring path executed — no headless screenshot needed (and avoids the boot-overlay capture pitfall above).

### TALK button self-declares JARVIS duplex (additive, 2026-08-17)
The 🎙 TALK footer button drives the JARVIS duplex voice (see its section). Relabel it so the capability is
self-evident (operator approved): `<div class="btn" id="talkBtn" title="JARVIS duplex voice — MOON listens via mic, replies in her real female voice (toggle)">🎙 TALK · JARVIS</div>`. Keep it BEFORE the DISPLAY button so it stays in the visible footer grid (see FOOTER GRID OVERFLOW pitfall). Verify the voice engine is live via `curl /status` → `voice.available: true, mode: AUTO` (39 agents, qwen3:0.6b this session) — never claim voice is "ready" without that proof.

## Pitfalls
- Do NOT set 16:9 selected default (user removed it; AUTO is default).
- Vision models mis-read tiny app-bar text and can't see JS-applied attrs — confirm
  defaults at CODE level (`grep data-ar="auto"`, `grep -c 'selected>16:9'`), not by trusting
  the screenshot narrative.
- Stale screenshots: `/status` WS fills panels ~1s after load; use a CDP audit (not a
  `--virtual-time-budget` screenshot, which hangs on this HUD).
- MOON venv MUST be Python 3.13; tests run with `env -u PYTHONPATH` (Hermes venv breaks
  pydantic_core). Run `pytest` only when backend .py changed; for HTML/CSS/JS-only edits,
  CDP DOM-audit + endpoint check IS the verification.
- **Repo push mapping — CORRECTED (2026-08-29).** The EARLIER note in this file
  claiming the remote is `master` is WRONG for the current repo. Local branch is
  `master`; GitHub remote default is **`main`** (`git@github.com:crsuvo100-gif/MOON.git`).
  A bare `git push` prints a config hint and pushes NOTHING. **Reliable push:**
  `git push origin HEAD:main` (updates `origin/main`). Pre-push gate:
  `git fetch origin --quiet && git rev-list --left-right --count HEAD...origin/main`
  must read `0\t0`. Do NOT use `git push origin master` (remote has no `master` branch).
  Full terminal↔brain WS-wiring diagnosis (300s LLM floor, swallowed `_handle`
  exceptions, unlocked `run_task` stall) is in `references/terminal_brain_wiring.md`.
    The untracked `MOON_3D_Neural_Terminal_Build/` and `Moon_terminal.py` are **legacy duplicate
    terminal artifacts** — when the operator says "remove old terminal", DELETE them from the
    working tree (they are unreferenced by `main.py`); otherwise just keep them out of commits.
- **Restart backend to surface boot-time hooks**: the terminal
  (`app.terminal_interface.py`) registers default peers / inits the voice engine at
  PROCESS STARTUP (`main.py start` or uvicorn). If you ADD such a hook, a backend that
  was already running will NOT show the new behavior until you kill it and relaunch.
  Symptom seen this session: `connect` showed "no connections" until the backend was
  restarted to load the seeded peer. Always restart before the final live-WS verification
  after touching startup code.
  **Preferred restart = the systemd user service** (repo ships `deploy/moon-terminal.service`;
  install once via `bash tools/install_terminal_service.sh`). It auto-starts on login, survives
  crashes + logout, and clears the port cleanly: `systemctl --user restart moon-terminal.service`.
  Avoid `pkill -f "uvicorn app.terminal_interface:app"` — that pattern ALSO matches the very
  shell command you just typed, so pkill SIGTERMs its own parent shell (exit -15, no error
  message) and the kill never lands. This self-match bit the agent repeatedly this session.
  **Safe kill instead:** `PID=$(ss -ltnp 2>/dev/null | grep ':8777' | grep -oP 'pid=\K[0-9]+' | head -1); [ -n "$PID" ] && kill "$PID"; sleep 2` then relaunch. General rule: for any long-lived
  server, prefer `ss`/`lsof`→PID→`kill` or `systemctl --user restart` over `pkill -f`, because
  a `pkill -f "<substring>"` whose `<substring>` is also in the command you are running will
  terminate the running shell.
- **NEW (2026-08-16) — `pkill -f` self-match gotcha (general)**: any `pkill -f "<substring>"`
  inline emoji (🔊 ⛶ ▣ etc.) fail repeatedly with "Could not find a match". Match on the
  surrounding **ASCII-only** text (e.g. `id="help">? HELP</div>`) and insert the emoji
  markup in the replacement. Do NOT loop retrying the same emoji old_string.
- **NEW (2026-08-16) — runtime dirs must be gitignored**: `voices/` (cloned-voice WAV
  samples + registry) and `connections/registry.json` are written at runtime and must stay
  out of the repo (user audio + local state). Add to `.gitignore` before committing any
  feature that writes there.

- **NEW (2026-08-16) — CDP `Runtime.evaluate` can return STALE-CACHE false negatives;
  use `chromium --dump-dom` for ground truth.** This session a live CDP session repeatedly
  reported `funcBtn exists: False` / `MOON_FUNCTIONS: undef` even though (a) `curl
  http://127.0.0.1:8777/` returned the new HTML with those markers, and (b)
  `chromium --headless --no-sandbox --disable-gpu --disable-dev-shm-usage
  --virtual-time-budget=5000 --dump-dom <url>` returned the live DOM WITH the new buttons
  rendered. The CDP browser was serving a cached page; `Page.navigate`/`Page.reload` with
  `Network.setCacheDisabled` did NOT reliably bypass it in this harness. **Rule: when a CDP
  `Runtime.evaluate` says a freshly-added element/JS is absent but `curl` shows it served,
  trust `curl` + `--dump-dom` — do NOT "fix" working code based on the stale CDP read.**
  `--dump-dom` does a fresh fetch (no cache) and prints the post-JS-parsed DOM, so it is the
  decisive check that your HTML/JS was actually served and executed. Use it before concluding
  a UI edit failed.

- **NEW (2026-08-16) — PURE-BLACK RENDER = MISSING `</style>` (not a GPU/JS issue).** This
  session the page returned HTTP 200, the WebSocket connected with ZERO JS errors, yet the
  browser showed a SOLID BLACK screen ("terminal did not open"). Root cause: the `<style>` block
  (opened at line 7) had **no `</style>` closing tag** — grep for `</style>` returned nothing.
  The browser implicitly closed it at `</head>`, leaving the HUD effectively unstyled → pure black.
  DECISIVE DIAGNOSIS: render a headless `--screenshot` and run `scripts/png_blackness_probe.py`
  on it. If `maxR == 0` (every pixel `(0,0,0)`) the CSS is NOT painting — check for (a) a missing
  `</style>` (grep `</style>`), (b) an unclosed `{`/`}` brace, (c) an `@import` mid-stylesheet
  (must be at the very top; external `@import` also BLOCKS first paint when offline — remove it
  and rely on local font fallbacks). A near-black HUD is normal (gradient `#060000`→`#010101` =
  pixels ~RGB(6,0,0)); the probe's `R>15` count distinguishes "renders fine" from "paints nothing".
  Fix: add the missing `</style>` (insert before `</head>`). No backend restart needed — the
  terminal reads the HTML per-request.
- **NEW (2026-08-29) — BLACK SCREEN via CSS compositing / unloaded font / orphaned declaration.**
  Beyond the missing-`</style>` cause above, this session hit THREE more black/looks-broken HUD
  causes — all CSS, all invisible to `node --check`, all isolated by the headless render-% A/B
  in `references/black_screen_compositing.md` ADDENDUM:
  1. **`mix-blend-mode:multiply` or `backdrop-filter:blur`** on a full-screen/large layer blacks
     the whole page on this X11/Chromium compositor (confirmed: commit `e2977b1` = 100% black).
     Same family hazard: `mix-blend-mode:screen` on `.crt`/`.pglyph`/`.backdrop` large layers.
     Prefer `opacity`-only overlays; validate any blend mode with the render-% test before commit.
  2. **Web font referenced but never loaded** (`--ff:'Share Tech Mono'` with no `@font-face`/`<link>`)
     → decorative glyphs (◉ ◈ ◇ ⬡ 🔥 🧠 ⛶) render as tofu boxes in every panel. Audit:
     `grep "Share Tech Mono"` must find a `<link>`/`<style>@font-face`, not just the `var`.
  3. **Orphaned CSS declaration** — a `patch` that replaced `background:` but left the follow-up
     `radial-gradient(...),` lines inside `#app{}` is invalid and can void the whole rule (HUD
     collapses to zero size → black). Re-read the whole rule after a `background` edit.
  Decisive diagnostic when vision API is 401: inject a `window.onerror`→`<div id="errbox">` handler,
  read it via `chromium --dump-dom | grep 'JS ERR:'`; an empty errbox + boot overlay still present
  = script halted before `connect()` (CSS bail, not a thrown error).
- **NEW (2026-08-16) — `node --check` the inlined `<script>` after EVERY JS edit.** The HUD's JS
  lives in one inlined `<script>` inside the HTML. A single dropped bracket/operator during a
  `patch` (this session: an audio-block insertion dropped the `if(typeof window.MOON_UI!=="undefined"){`
  opener, leaving a floating `}` → `SyntaxError: Unexpected token '}'`) produces a SILENT blank/
  broken HUD with no obvious cause. Extract + check in one line:
  `python3 -c "import re;h=open('web/moon_terminal.html').read();open('/tmp/m.js','w').write('\n'.join(re.findall(r'<script>(.*?)</script>',h,re.S)))" && node --check /tmp/m.js`
  If it fails, locate the failing line via the cumulative-line trick (concatenated blocks) and fix
  before committing. This catches the class of "edits broke the JS but rendered black" bugs early.

- **NEW (2026-08-17) — CSS RULES ACCIDENTALLY PLACED INSIDE `<script>` KILL THE ENTIRE HUD (the real "monitoring not functional" this session).** When you ADD CSS for a feature (e.g. the System Logs severity-coloring polish), it MUST go inside `<style>` — but it is easy to paste the rules immediately BEFORE a `function foo(){` line that lives inside the `<script>` block, which silently lands the CSS *inside* `<script>`. A CSS selector like `.logs #logs .line{color:...}` is INVALID JavaScript, so the **whole `<script>` fails to parse** → no `connect()`, no `runBoot()`, no WS, every panel frozen at its static HTML default (`--%`, `1.02 PB`, `MINIMAL`). The page LOOKS like a normal HUD (all static markup/CSS still paints) but is 100% dead JS — no console error is obvious to casual inspection. **Symptom discriminant**: if `--%` / static defaults persist AND `node --check` on the extracted script FAILS with `Unexpected token '.'` or a CSS-like line at the failure point → CSS leaked into `<script>`. (If `node --check` PASSES but `--%` persists → it's the backend-not-pushing-status cause in the "Root cause of monitoring" section, NOT a JS bug.) **Fix**: move the CSS lines into `<style>` (before `</style>`) and delete them from the script; then re-run `node --check` until clean. This session a logs-polish commit did exactly this and the HUD stayed dead for many turns until `node --check` surfaced the `.logs #logs .line{...}` leak — run the check IMMEDIATELY after ANY edit that touches CSS, not just edits you think of as "JS". The single-line extraction+check is the discriminator between "JS is dead" (CSS/syntax) and "JS alive but no data" (backend/WS).

- **NEW (2026-08-16) — REMOVING A CANVAS THAT IS CACHED AT INIT FREEZES THE BOOT SCREEN.**
  Code like `const c=el("brain"), x=c.getContext("2d");` captures the 2d context at script load.
  If you later DELETE that `<canvas id="brain">` from the HTML, `el("brain")` returns `null` and
  `c.getContext` THROWS at init → the entire `<script>` aborts (no WS connect, no `runBoot()`) →
  the page is stuck forever on the boot/INITIALIZING overlay (looks like a blank HUD, ~19 KB
  screenshot). **Null-guard every cached canvas ref:** `const c=el("brain"); const x=c?c.getContext("2d"):null;`
  and guard any function that uses it (`brain(t){ if(!c||!x) return; ... }`). Symptom: headless
  screenshot shows only the MOON logo + INITIALIZING (boot never clears) yet `curl /` = 200 and the
  DOM is served fine — that means the JS threw before `runBoot()`. Run `node --check` (catches
  syntax) AND dump-dom/load the page; a frozen boot with a 200 response is the tell. This bit the
  agent during the fusion-core rebuild when `#brain` was removed but the cached `getContext` stayed.

- **NEW (2026-08-16) — FOOTER GRID OVERFLOW CLIPS NEW BUTTONS.** When you add a footer tab
  (e.g. 🎙 TALK), you MUST widen `footer{grid-template-columns:...}` to fit ALL children, or the
  new button falls into an implicit off-screen-right column and is invisible. Count footer children
  and use `15% repeat(<N-1>,1fr)`. Symptom clue: DOM has the button but VISION says it is missing.
- **NEW (2026-08-16) — `setText()` escapes via `textContent`.** Never pass markup to `setText()`
  (e.g. `setText("cliOut",'<div class="line">...</div>')`) — it renders the literal `<div>` text.
  For styled lines, build a `document.createElement('div')` with `className` + `textContent` and
  `appendChild` (like `addLog()` does). Reserve `setText` for plain text only.

- **NEW (2026-08-17) — calling an async coroutine WITHOUT `await` silently does nothing (live log stream delivered 0 frames).** When you register a per-connection `send(**msg)` coroutine as a subscriber and call it from a SYNCHRONOUS function (`_log()`), writing `sub(type="log", ...)` just CREATES a coroutine object that is never scheduled → no frame is ever sent, and there is NO error. Symptom: WS `log_stream` subscribes fine (replays history) but receives 0 live frames even though the code path clearly runs. **Fix**: schedule it — `asyncio.ensure_future(sub(type="log", t=ts, sev=sev, msg=msg))` (or `asyncio.create_task` inside a coroutine). General rule: any time a sync function must invoke an async callback, wrap it in `ensure_future`. Verify a subscriber works by counting received frames in a raw WS test, not by assuming the code path executed.
- **NEW (2026-08-17) — `import -window <id> <file>` is the working screenshot capture on this box (the `import -window <id>` form WITHOUT a target file fails).** The ImageMagick `import` man-page usage is `import -window <id> <output.png>` (id THEN file). The earlier `import -window <id>` (no target) produced nothing. Always capture with `xdotool windowactivate <WID>; sleep 2; import -window <WID> /tmp/shot.png`. Then `vision_analyze` the PNG. This is the reliable human-visible verification path when CDP/headless is flaky.
- **NEW (2026-08-17) — `pkill -9 -f google-chrome` self-match / blocklist note.** `pkill -f` matching `google-chrome` is safe-ish, BUT inline `&&`-chains and `while read` loops with the kill get flagged by the agent's command blocklist (hardline: "command parser limit or malformed executable payload"). Prefer: kill via `PID=$(ss -ltnp | grep ':8777' | grep -oP 'pid=\K[0-9]+' | head -1); [ -n "$PID" ] && kill "$PID"` for the backend, and `pkill -9 -f google-chrome` is acceptable for Chrome (its cmdline won't match the agent's own shell). Avoid `while read` / heredoc loops around kills.
  overlay, NOT the HUD.** The boot screen (`#boot`, "INITIALIZING") only clears on the first
  WebSocket `ready` frame, and the boot bar animation runs ~1.8s after that. A short
  `--virtual-time-budget` (e.g. 6000) fires the screenshot BEFORE the WS handshake completes →
  you get an ~18KB PNG of just the MOON logo + INITIALIZING, which looks like a broken/blank HUD
  but ISN'T. Fix: use `--virtual-time-budget=14000` (≥12s) so the WS connects + boot clears; the
  full HUD PNG is ~600–700KB. OR don't trust a single screenshot — verify via `curl /` (HTML 200)
  + the WS status proof + `chromium --dump-dom` (post-JS DOM). A boot-only PNG is a capture-timing
  artifact, not a defect; do NOT "fix" working code to make the screenshot show the HUD. (Distinct
  from the older "screenshot hangs / 0-byte" pitfall: here chromium exits fine and writes a small
  boot frame.)
  **For INNER panels** (Settings, Workspace/AGENTS/TOOLS, any overlay) use the URL-hash deep-link
  method in `references/headless_deeplink_verify.md` — a plain `/` screenshot only shows the
  default HUD; to prove an inner panel renders, open it via `/#agents` etc. (the HUD auto-opens it
  after WS status) and capture with `--virtual-time-budget=6000`.
- **NEW (2026-08-17) — `convert` on a multi-frame WebP explodes into 30+ JPGs.** `convert img.webp
  ... out.jpg` splits an animated webp into `out-0.jpg … out-N.jpg`. Always pin frame 0:
  `convert 'img.webp[0]' ...`. Otherwise `ls web/assets/` fills with `moon_fiery-0..32.jpg` and
  your intended single backdrop file is never written (the `convert` returns exit 0 either way).

## Voice engine + Tools panel (added 2026-08-16)
The operator asked for (a) frontend+backend programs for ALL tool functions and the
terminal, and (b) a premium female voice with voice cloning. Both delivered additively.

### Backend
- `app/voice_engine.py` — `VoiceEngine`: multi-backend TTS, tried in order
  **XTTS-v2** (local, cloneable female) > **OpenAI `nova`/`shimmer`** (cloud alluring
  female, needs `OPENAI_API_KEY`) > **espeak female** (CPU-safe fallback, always works).
  Methods: `speak(text)`, `clone_voice(name, b64_sample)`, `list_voices()`,
  `set_voice(name)`, `backend_status()`. Keep `app/voice.py` (espeak `Voice`) intact —
  the engine imports it as the fallback backend.
- New WS actions in `app/terminal_interface.py`:
  * `voice` with sub-actions `status|list|set <name>|clone <name> <b64sample>|female`.
  * `tool` → runs ANY registered tool directly: `tool <name> key=val key=val`. The
    WS handler parses `key=val` and **strips surrounding quotes** from values (a missing
    quote-strip made `code='print(21*2)'` pass a literal-quoted string to Python → empty
    output). Confirmed live: `tool python_executor code='print(21*2)'` → `42`.
- `clone_voice` writes `voices/<name>.wav` + `voices/registry.json` (gitignored). XTTS
  uses the sample as the speaker embedding; on hosts without XTTS the sample is still
  stored and the engine reports cloning as pending (honest, never fake).

### Frontend
- Two new overlay panels + footer buttons in `web/moon_terminal.html`:
  * **VOICE** (`#voicePanel`): female-voice `<select>`, SET, STATUS, LIST VOICES,
    SPEAK TEST, MUTE toggle, and a clone-upload (`<input type=file>` → base64 →
    `voice clone`). `voiceLog` div shows status.
  * **TOOLS** (`#toolsPanel`): a `toolRun` input + RUN + REFRESH, and a `#toolGrid` that
    lists all 43 tools (fed by the `list_tools` WS response). Clicking a tool loads its
    name into the run box.
- Wire with the operator's own convention (one `doX()` per control, `el("xBtn").onclick`);
  track `lastAction` in `wsSend` so `handle()` can route `list_tools` chunks into the
  grid on `assistant_done`. Do NOT redefine `handle` as a self-wrapping wrapper (the WS
  `onmessage` still calls the original) — extend the existing `handle` switch instead.
- Verification: `node --check` on the inlined `<script>` (extract via regex) + the CDP
  audit clicking `voiceBtn`/`toolsBtn`/`toolRun` → **0 JS errors** (see
  `references/visual_verify.md`).

### Installer / deps
- `requirements.txt` + `install_moon.py` now pull `TTS`, `openai`, `vosk`, `pyaudio`
  best-effort so the premium/clone voice works on a capable host; espeak+sox remain the
  always-available fallback. `install_moon.py` `--no-models`/`--no-voice` flags already
  exist for skipping.

See `references/voice_engine.md` for the full VoiceEngine API + a ready-to-run live test.

## JARVIS duplex voice interaction (🎙 TALK) — full-duplex "talk & reply"
Operator asked for Iron-Man/JARVIS style: MOON **HEARS anyone** via the mic and **replies with voice**.
The backend ALREADY speaks — `send_message` → `_speak(answer)` → `type:"audio"` WAV frame
(`app/terminal_interface.py` ~lines 518-520). The missing half is **MIC INPUT**. Delivered as a
footer **🎙 TALK** button (`id="talkBtn"`). Vanilla-JS, additive.

Concrete recipe:
- **HTML**: footer `<div class="btn" id="talkBtn" title="JARVIS duplex voice — MOON listens via mic, replies in her real female voice (toggle)">🎙 TALK · JARVIS</div>` placed BEFORE the DISPLAY button so it sits in the
  visible grid; plus a centered status `<div id="talkState">◌ LISTENING ◌</div>` inside `#app` (near `.idleTag`). (Relabel to `TALK · JARVIS` so the duplex capability is self-declared — operator approved 2026-08-17.)
- **CSS**: `.btn.talking{background:#5a0a0a!important;color:#fff!important;box-shadow:0 0 20px rgba(255,40,40,.7);animation:talkpulse 1.1s ease-in-out infinite}` + `@keyframes talkpulse`.
  `#talkState{position:absolute;left:50%;top:5.3%;transform:translateX(-50%);z-index:35;...opacity:0;transition:opacity .3s}` `.show{opacity:.95}` `.live{color:#ff4040}`.
- **JS** (after the audio-cue block; reuses existing `audioCtx()`/`blip()`/`addLog()`/`wsSend()`/`el()`):
  * `let _recog=null,_talking=false,_moonSpeaking=false; const _talkBtn=el("talkBtn"),_talkState=el("talkState");`
  * `buildRecog()`: `const R=window.SpeechRecognition||window.webkitSpeechRecognition;` (NULL on Firefox → log + return
    null; needs Chromium). `r.lang="en-US"; r.continuous=true; r.interimResults=true;`
    `onresult`: accumulate `final` from `e.results[i].isFinal`; on a final → `onHeard(t.trim())`.
    `onerror`: `not-allowed` → `stopTalk()` + log "microphone permission denied".
    `onend`: `if(_talking && !_moonSpeaking){ try{r.start()}catch(_){} }` (continuous mode still fires onend → auto-restart).
  * `onHeard(text)`: `addLog("[YOU] "+text); setTalkState("◌ MOON IS THINKING ◌"); wsSend({action:"send_message",text}); blip();`
  * `startTalk()`: build recog if needed; **resume the AudioContext on the click gesture** (`audioCtx().resume()` — browser
    autoplay policy requires a gesture or her replies stay silent); `_talking=true`; add `.talking`; set state; `r.start()`.
  * `stopTalk()`: clear flag/class/state; `r.stop()`. `el("talkBtn").onclick=toggleTalk;`
- **Echo-cancellation (CRITICAL)**: MOON must not hear herself. In `handle()`:
  * `case "assistant_start"`: `_moonSpeaking=true; if(_recog)_recog.stop(); setTalkState("◌ MOON IS SPEAKING ◌")`.
  * `case "assistant_done"`: `_moonSpeaking=false; if(_talking&&_recog)_recog.start(); if(_talkState&&_talking) setTalkState("◌ LISTENING — SAY 'MOON' OR SPEAK ◌")`.
- **playWav must use the shared AudioContext** (the one the TALK gesture resumes), else replies are silent under autoplay
  policy: replace `new AudioContext()` with `const ac=audioCtx(); if(!ac)return; if(ac.state==="suspended")ac.resume();
  ac.decodeAudioData(buf.buffer.slice(0),a=>{ if(_muted)return; const src=ac.createBufferSource(); src.buffer=a; src.connect(ac.destination); src.start(); },()=>{});`
- **Verify**: a python WS `send_message "hello moon"` returns frames `assistant_start→workflow→assistant_chunk→audio(wav)→
  assistant_done` (proves MOON talks back). Mic capture can't be headless-tested (needs a real mic + Chromium SpeechRecognition);
  verify by VISION that `talkBtn` exists in the footer + `node --check` passes. On this CPU sandbox the spoken voice is the
  espeak female fallback; premium XTTS/OpenAI female + cloning engage on a capable host (same VoiceEngine path).
- **Pitfall**: Web Speech Recognition is **Chromium-only** (Chrome/Edge). On Firefox `SpeechRecognition` is undefined →
  TALK logs "speech recognition unavailable" and does nothing. That is HONEST, not a bug — document it, never fake a reply.

See `references/function_dock.md` for the Function Dock recipe (enumerate every backend
WS `action` as a rich button grid).

### Function Dock — surface EVERY backend function as a rich button grid (added 2026-08-16)
The operator asked: *"put all function button onto terminal interface and arranged
richfully look."* Delivered as a **FUNCTIONS** footer button → a wide overlay `#funcPanel`
with a 4-col `#funcGrid` of rich buttons (icon + name + one-line description). Each
button fires a REAL backend WS `action` (mapped to `app/terminal_interface.py` action
handlers), and a few open existing panels (TOOLS/VOICE).

**Why this is the right pattern (not per-button `doX` for 23 functions):** enumerate the
backend's real actions ONCE in a data array and render declaratively — keeps the UI in
sync with the backend and avoids 23 hand-written click handlers. Concrete recipe in
`references/function_dock.md`. Key points:
- Build a `MOON_FUNCTIONS` array: each entry `{i, n, d, a:{action,...}}` or `{...,click:"toggleTools"}`
  for buttons that open a panel instead of sending a WS action.
- `renderFuncGrid()` maps the array → `.f` divs with `onclick="doFunc(idx)"`. `doFunc`
  either calls `window[f.click](true)` (panel opener) or `wsSend(f.a)` (real action).
- The function list MUST mirror the backend's actual `elif action ==` handlers in
  `app/terminal_interface.py` — grep them with `search_files` before building, so no
  button is dead. (23 real actions as of 2026-08-16: send_message, diagnostics, status,
  memory_search, knowledge, run, connect_agents, stop, list_tools, voice, tool, network,
  capabilities/github, connect, settings, security, automation, dashboard, help, mute/unmute,
  wake.)
- Style: `.funcGrid{grid-template-columns:repeat(4,1fr)}`, `.f` cards with hover glow
  (`box-shadow:0 0 12px #d008;border-color:#ff2a2a`), responsive to 2 cols under 1000px.
- Verification: see `references/function_dock.md` + the dump-dom cache note below.

## Flaky live-federation test — now FIXED (was a real defect, 2026-08-16)
`tests/test_global_connector.py::test_federation_with_real_peer_agent` used to **HANG/SKIP**
on a cold Ollama model load (CPU-only box): the first `chat/completions` after a model is
pulled can take >45s while weights load into RAM, blowing the federation `wait_for` budget and
stalling the whole suite. The fix (already committed) makes it **deterministic PASS**:
  1. PRE-WARM Ollama before the federation call (one `chat/completions`, `max_tokens:2`).
  2. RETRY the warm call up to 3×, each bounded by a 60s per-call `httpx.Timeout`.
  3. Raise federation `wait_for` timeout 45→90s.
  Full run is now **`89 passed / 0 failed / 0 skipped`** on consecutive runs (exit 0).
  Root cause on the backend side: `app/connector/gateway.py::call_agent` now takes an explicit
  `timeout` param (fails fast instead of failing slow). If you ever re-touch this test, KEEP
  the pre-warm+retry — removing it reintroduces the stall.

## Whole-Moon deep-scan verification recipe (reuse for "make Moon ready/launch")
When the operator asks to scan/fix/verify the ENTIRE MOON (not just the HUD), run this
deterministic, non-fabricated probe (proven 2026-08-16):
  1. **Import every module**: `pkgutil.walk_packages(app.__path__, prefix="app.")` +
     `importlib.import_module` → assert NO broken imports (got 118/118 clean).
  2. **Boot the brain**: `o = Orchestrator(get_settings()); await o.setup()` → assert
     "Connected N agent brains" (39) and no exception.
  3. **Count registered tools**: `o._tools._registry`; `len(tools)` (43) — proves "all
     functions" exist. Spot-execute a safe local tool (e.g. `system_info.run({})`).
  4. **Unlock → real task**: `await o.run_task(Task.create("MOON love you 3000"))` flips
     `o._lock.locked` to False; then `await o.run_task(Task.create("Say hi in 3 words."))`
     must return real model output (e.g. "Hi there!") with `status=="completed"`.
     (The lock is BY DESIGN — a task without the unlock phrase returns the lock notice and
     short-circuits. That is correct security, NOT a bug.)
  5. **Endpoints**: `curl -o /dev/null -w '%{http_code}' / /status /theme` → all 200.
  6. **pytest**: `env -u PYTHONPATH .venv/bin/python -m pytest tests -q` → 89 passed.
  Use the user's venv at `/home/meow/Projects/MOON/.venv` (Python 3.13) and ALWAYS prefix
  with `env -u PYTHONPATH` (Hermes venv breaks pydantic_core).
