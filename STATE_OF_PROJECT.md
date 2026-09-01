# MOON — State of Project (2026-09-01)

Two-terminal consolidation COMPLETE. All 5 prior channels folded into:

1. **Moon UI** — Web terminal (`moon` / `moon terminal` / `python main.py terminal`)
   - HTTP + WebSocket on :8777, red/black NEURAL CORE HUD
   - 25 WS actions + REST endpoints + live voice (kokoro "aria", auto-on)
   - Allowlisted shell exec, diagnostics, memory/knowledge search, agent factory,
     security posture, automation status, settings, help
   - Live via systemd `moon-terminal.service` (no auto-start; run `moon` to open)

2. **Moon Shell** — Textual TUI (`moon shell` / `moon tui`)
   - TTS-spoken replies, `!shell` commands, `/cli` ops, `!voice` control
   - Starfield + brain panel + chat panel + status bar
   - No browser, no auto-start, runs on any machine with a terminal

## CLI surface (`moon <cmd>`)
- `moon` (no args) → Moon UI (default)
- `moon terminal` → Moon UI explicitly
- `moon shell` → Moon Shell (TUI)
- `moon tui` → Moon Shell (backward-compatible alias)
- `moon run "<task>"` / `moon models` / `moon doctor` / `moon status`
- `moon backup` / `restore` / `install` / `setup` / `uninstall` / `update` / `version` / `monitor`

## What changed in this session
- **WS batching**: `_stream_text` gained `yield_every` param. All enumeration
  handlers (capabilities, connect, agents, tools, skills, tasks, executions,
  audit, factory list, list_tools, connect_agents, security) batch large output
  into 1-2 frames instead of one WS frame per word (580x speedup on 193-agent
  lists). Short-response handlers keep live-typing.
- **TUI bugfix**: `_say()` now stores the asyncio task in `self._speech_task`
  so `action_quit` / Esc can cancel pending TTS on exit.

## Verified
- pytest 126/126 PASS
- `moon doctor` PASS 16/16
- `moon status` → backend HEALTHY
- Web UI :8777 live (HTTP 200 /, /status, /api/health; WS /ws → ready)
- TUI boots, orchestrator online
- EventBus: subscribe + publish + unsubscribe all present (no subscriber leak)
- 39 agents, 43 tools, memory + knowledge + voice + capability manager + global
  connector + agent factory all wired
- Git: `master` pushed to `origin` (SSH `git@github.com:crsuvo100-gif/MOON.git`)

## Commitments
- No API keys, tokens, passwords, or connection strings in this file or any
  commit. SSH remote uses deploy key; Telegram bot activation needs token in `.env`.
- Dashboard + Telegram bot code retained in-tree but NOT exposed as top-level
  `moon` subcommands (consolidation: only `moon` and `moon shell` are the two
  terminals; everything else is operational CLI).
