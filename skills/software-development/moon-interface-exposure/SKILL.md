---
name: moon-interface-exposure
description: Add/expose MOON interactive surfaces; gate remote access.
---

# MOON Interface Exposure & Remote Access

MOON is reached through several interactive surfaces. When you add or expose one,
do it ADDITIVELY (extend modules; never replace/disable working surfaces) and keep
remote exposure auth-gated. This skill covers the inventory, the pattern for each
surface type, the autonomous-discoverability pitfall, and the verified authz/tunnel
recipe.

## When to use
- User asks to add a chat channel (Telegram, Discord, …), a TUI, or another UI.
- User asks "how many terminals / interfaces does MOON have?" → run the inventory.
- User wants to reach MOON from another machine / "open Moon remotely".
- You added a capability and want MOON's planner to autonomously *choose* it.

## Golden rules
- **ADDITIVE only** — extend modules; never replace/disable working MOON surfaces.
- **Secrets** (bot tokens, access tokens) live ONLY in the gitignored `.env`
  (read via pydantic-settings or `os.environ`); never commit or print them.
- **Remote exposure is NEVER open** — gate the Terminal WebSocket + `/status`
  behind `MOON_TERMINAL_TOKEN` (Bearer) and auto-generate a random token if none set.
- **Allowlist gate** on any inbound channel (e.g. Telegram `chat_id`).

## Surface inventory (verified this session)
See `references/moon_interfaces.md` for launch commands, ports, and the authz recipe.
1. **MOON Terminal** — FastAPI + WebSocket `/ws` (streams her brain events); port 8777. Primary rich UI. `python main.py terminal` / `moon_launcher.py terminal`.
2. **Dashboard** — Flask + SocketIO (`user_command` event → orchestrator); port 5000. `python main.py dashboard`.
3. **One-shot CLI** — `python main.py run "<prompt>"` → `Orchestrator.run_task`, stdout.
4. **Voice companion** — `scripts/voice_loop.py` is a *client* of Terminal's `/ws` (mic dictation + female TTS); needs MOON already running.
5. **Telegram** — polling bot (`python main.py telegram`); needs `TELEGRAM_BOT_TOKEN`.
6. **Programmatic** — `from app.brain.orchestrator import Orchestrator; orch.run_task(task)`.

All local surfaces bind 127.0.0.1 by default. No TUI/Gradio/Discord yet.

## Verified gaps fixed this session (2026-08-30)
- **Dashboard (#2 in inventory) did NOT have a real `app/dashboard.py`.** The inventory
  entry was aspirational — `python main.py dashboard` would import-fail. Created
  `app/dashboard.py` (Flask + SocketIO, port 5000) with real routes `/api/status`
  and `/api/telemetry` wired to the live orchestrator. See `references/dashboard_recipe.md`.
- **After creating `app/dashboard.py`, two blockers surfaced and were fixed:**
  1. `SOCKETIO.run(..., debug=False)` raised a werkzeug production guard error →
     add `allow_unsafe_werkzeug=True`.
  2. Flask routes `/api/status` and `/api/telemetry` called async functions
     (`_moon_status(orch)`, `_telemetry_snapshot(orch)`) WITHOUT `asyncio.run()` →
     returned un-awaited coroutines → 500. Wrap in `asyncio.run()`.
  Pattern: Flask route body is sync; any async MOON call inside must be wrapped in
  `asyncio.run(coro)`. Do NOT `return jsonify(async_fn(...))` directly.
- **TUI (`app/tui.py`) `on_mount` was renamed to `_on_mount`.** Textual lifecycle
  hooks are name-based — `_on_mount` is NOT called, so `query_one`/`run_worker` ran
  with no screen mounted → `ScreenStackError: No screens on stack`. Fix: keep the hook
  named `on_mount` (async def) and defer widget-touching to `call_later` or a helper
  method, OR put all widget work directly inside `on_mount` after Textual has composed.
  **Never rename `on_mount`, `on_input_submitted`, `action_*`, or any Textual hook** —
  the leading-underscore variant is a silent no-op, not an override.
- **`python-telegram-bot` vs `telegram` package confusion.** The placeholder PyPI
  package `telegram` (version 0.0.1) is NOT `python-telegram-bot`. Installing the
  wrong one makes the TelegramBot class importable but unusable. Always install
  `python-telegram-bot`; if `import telegram` yields the placeholder, uninstall it first.

## Patterns
### New in-process surface (no HTTP) — e.g. curses TUI
- `app/tui.py`: curses UI that calls `Orchestrator(get_settings()).setup()`, then
  `run_task(task, on_event=...)` to stream MOON's brain events (routing/cognition/
  reflection/consistency) into a live panel. Honor the lock: until the unlock phrase
  ("MOON love you 3000") is observed, only the lock notice / `quick_reply` is shown.
- Wire it: `main.py` adds `args.cmd == "tui"` → `app.tui.main()`; `moon_launcher.py`
  mode `"tui"` → `subprocess` the venv python.

### New chat channel — e.g. Telegram
- `app/services/telegram_bot.py`: long-polling listener. `_ensure()` lazily imports
  `python-telegram-bot` (optional dep). `run()` loops `bot.get_updates`, drops
  messages from non-allowlisted `chat_id`, routes authorized text through
  `Orchestrator.run_task(on_event=typing-indicator)` and replies (chunk >4000 chars).
- **Gate the chat id in BOTH `run()` and `_handle()`** (defense in depth).
- Wire: `main.py telegram`; token from `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` or
  `settings.telegram_bot_token`. Declare `python-telegram-bot` as optional `telegram` extra.

### Autonomous discoverability (CRITICAL pitfall)
Adding a tool is NOT enough for MOON to *choose* it. Register it in the capability
catalog or her planner won't route tasks to it:
- `app/capability/manager.py`: add a spec to `_BUILTIN_SPECS` (e.g.
  `"huggingface": {"type": "builtin", ...}`) and add discovery tokens in `discover()`.
- `app/capability/installer.py`: handle `method: "none"` so `type: builtin` resolves
  as already-present (no pip/network).
- `app/capability/verification.py`: add a `builtin` branch that checks the real MOON
  tool is registered (NOT an unrelated pip import) — otherwise `verify()` returns False
  and `acquire()` reports failure even though the capability works.

### Remote exposure (authz gate + tunnel)
- `app/terminal_interface.py`: `TERMINAL_TOKEN = get_settings().terminal_access_token
  or os.environ.get("MOON_TERMINAL_TOKEN","")`. Helper `_token_ok()` returns True when
  no token (local-only) or when `Authorization: Bearer <token>` matches. Apply it to
  `/status` (return 401 `Response`) and the `/ws` WebSocket (close code 1008 before
  `ws.accept()`).
- `scripts/moon_launcher.py` `start_tunnel()`: generate a random token if unset, start
  the Terminal (passing the token via env), then `cloudflared tunnel --url
  http://127.0.0.1:8777` if installed (best-effort). Prints
  `Authorization: Bearer <token>` for clients. Never expose without the token.

## Verification (always, before "done")
- Web: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8777/` → 200; same
  for `/avatar.svg` and `/status`.
- WS unlock smoke: connect `ws://127.0.0.1:8777/ws`, send
  `{"action":"send_message","text":"MOON love you 3000"}`, expect event types
  `ready, assistant_start, workflow, assistant_chunk, audio, assistant_done`.
- Tests: `env -u PYTHONPATH .venv/bin/python -m pytest tests` (MOON venv is Python 3.13;
  the Hermes PYTHONPATH breaks pydantic_core — always unset it).

### Verifying the MOON WEB UI (CSS / canvas / layout changes) — HEADLESS SCREENSHOT
Static `web/moon_terminal.html` is served from disk, so a fresh load reflects edits
immediately. **Playwright's chromium driver will NOT launch in this sandbox**
(`Connection.init: Connection closed while reading from the driver`) — do NOT waste
time on it. Use the system `chromium` CLI instead, then inspect with `vision_analyze`:
```
chromium --headless --no-sandbox --disable-gpu --disable-dev-shm-usage \
  --screenshot=/tmp/moon_ui.png --window-size=1440,900 http://127.0.0.1:8777/
chromium --headless --no-sandbox --disable-gpu --disable-dev-shm-usage \
  --screenshot=/tmp/moon_ui_small.png --window-size=1280,800 http://127.0.0.1:8777/
```
(GPU `SharedImageManager` / `GL Driver Message` stderr lines are harmless.)
Then `vision_analyze(image_url="/tmp/moon_ui.png", question="...")` to confirm:
no truncation/overlap/bleed, panels fully visible, canvas/orb renders, no JS error.
This is the authoritative verification for CSS/canvas work — there is NO pytest
suite for static HTML. `vision_analyze` reads the local PNG directly (Hermes vision).
Use `--window-size=1600,900` for a wider shot to prove no right-edge bleed.

## Pitfalls
- Forgetting capability-catalog registration → tool exists but MOON never *chooses* it.
- Token only in `os.environ` (not settings) → `.env` value ignored because
  pydantic-settings does NOT write back to os.environ; read `get_settings()` first.
- `FastAPI` route param `request: Request | None = None` breaks import (FastAPI treats
  it as a response model) → use `request: Request` (FastAPI injects it).
- Exposing `/ws` without the Bearer gate → anyone on the tunnel controls MOON.
- Treating `computer_use`/`xdg-open` browser-open as a capability claim — environment
  dependent; do not encode "browser tools don't work" as a rule. Just give the URL.
- **Verifying MOON web UI**: Playwright's chromium driver fails to launch in this
  sandbox (`Connection closed while reading from the driver`). Use `chromium
  --headless --screenshot=...` + `vision_analyze` on the PNG instead (see Verification).
  No pytest covers static `web/moon_terminal.html`; the screenshot+vision check is the
  real verification for CSS/canvas/face→orb changes.
- When replacing the center avatar: the 3D `#face3d` (Three.js) + `#avatarImg` + 
  `#meshDots` are separate elements in `.stage`; remove all three and keep
  `setMoonState`/`setMouthOpen` stubs so `playAudio` callers don't throw. Driven by
  `window.setOrbActivity(na)` fed from `apply()`'s neural_activity proxy.

See `references/moon_interfaces.md` for the full inventory + copy-ready recipes.
See `references/textual_tui_patterns.md` for the moonscope TUI rebuild patterns
(Textual 8.x compose/mount/qemu, status-panel box-drawing helpers, Hermes aesthetic
→ Textual widget translation, pitfalls).
See `references/textual_tui_patterns.md` for the moonscope TUI rebuild patterns
(Textual 8.x compose/mount/qemu, status-panel box-drawing helpers, Hermes aesthetic
→ Textual widget translation, pitfalls).
