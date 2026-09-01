# MOON — Unified Machine Manifest
> Generated 2026-08-30. Every MOON-related piece on this host, in one place.
> Canonical checkout: `/home/meow/Projects/MOON` (only copy; stale duplicates removed).

---

## 1. Canonical checkout

| Item | Path |
|---|---|
| Project root | `/home/meow/Projects/MOON` |
| Git remote | `git@github.com:crsuvo100-gif/MOON.git` (SSH, verified live) |
| HEAD commit | `b0b657e fix(terminal): harden connect WS handler — _stream always set` |
| Branch | `master` (39 commits ahead of `origin/main`) |
| Python | `.venv/bin/python` → 3.13.14 |
| Venv | `.venv/` (2.8 GB — real ML deps: torch 725M, bitsandbytes 122M, transformers 110M, etc.) |
| Entry | `main.py` + `moon/__main__.py`; also `run_moon.py` |

### Subsystems (all live per wiring map)
- Main brain: `app/brain/orchestrator.py :: Orchestrator`
- 39 agents, 43 tools, 24 skills, 2 connections
- Voice: `app/voice_engine.py` (kokoro TTS primary, F5-TTS fallback)
- Web HUD: `web/moon_terminal.html` → WS `ws://127.0.0.1:8777/ws`
- Agent brains: `data/agents/`

---

## 2. Runtime entrypoints (all verified live)

| Entrypoint | Command | Wires to |
|---|---|---|
| Terminal/API server | `python main.py terminal` / `moon` / `moon terminal` → uvicorn on :8777 | Orchestrator + WS `/ws` + HTTP `/api/*` |
| Moon Shell (TUI) | `python main.py shell` / `moon shell` / `moon tui` | Orchestrator directly + TTS + `!shell` + `/cli` |
| Doctor (health) | `python main.py doctor` / `moon doctor` | 16 subsystems report |
| CLI task | `python main.py run "<task>"` / `moon run "<task>"` | `orch.run_task(...)` |
| Launcher (desktop/CLI) | `moon` (no args) → Moon UI default | `~/.local/bin/moon` → cd to project + venv python main.py |
| Systemd terminal | `moon-terminal.service` | uvicorn :8777, auto-restart (run `moon` to open; NOT auto-start) |
| Systemd monitor | `moon-monitor.service` (oneshot, timer every 15m) | `scripts/moon_deep_monitor.py` → 8 health checks |

---

## 3. Configuration

### `.env` (gitignored — NEVER commit)
`/home/meow/Projects/MOON/.env`
- `MODEL_BASE_URL=http://127.0.0.1:11434/v1`
- `MODEL_NAME=qwen2.5:1.5b`
- `STRONG_MODEL_NAME=qwen2.5:3b`
- `ENABLE_AUTO_LEARNING=true`
- Tool toggles: `ENABLE_BROWSER_AUTOMATION=true`, `ENABLE_OCR=true`, `ENABLE_PDF=true`
- Fallback backends: OpenAI, OpenRouter, HuggingFace keys (all present)
- `GITHUB_REPO=https://github.com/crsuvo100-gif/MOON`
- `MOON_TERMINAL_TOKEN=` (blank = local-only)

### `.env.example` (template, committed)
`/home/meow/Projects/MOON/.env.example` — same keys, placeholder values.

### Web settings
`web/moon_settings.json` — HUD front-end config (host/port/display/aspect/idle-speed/core-bg/glow).

---

## 4. Data (gitignored, runtime state)

| Path | Contents |
|---|---|
| `data/executions.db` | Execution history |
| `data/agents/agent_factory.db` | Agent definitions (177) |
| `data/agents/agent_registry/*.json` | Registered agent schemas |
| `data/agents/staging/*/` | Staging agent generators + tests |
| `data/knowledge/` | Knowledge store |
| `data/memory/` | Long-term memory |
| `data/skills/` | Skill data |
| `data/logs/` | Runtime logs |
| `app/data/brain_stats.json` | Orb maturity + state stats |
| `app/logs/long_term.jsonl` | Long-term event log |
| `app/logs/agent_brains/*` | Per-agent brain persistence |
| `capabilities/` | Capability cache + manifests + registry |
| `connections/` | Connection registry |
| `voices/` | Voice asset storage |
| `backups/` | `moon_20260822_*` snapshot backups |

---

## 5. Systemd units (user scope, `systemctl --user`)

| Unit | File | State | Points to |
|---|---|---|---|
| `moon-terminal.service` | `~/.config/systemd/user/moon-terminal.service` | **active (running)** | `/home/meow/Projects/MOON` ✓ |
| `moon-monitor.service` | `~/.config/systemd/user/moon-monitor.service` | inactive (oneshot, triggered by timer) | `/home/meow/Projects/MOON` ✓ (fixed this session) |
| `moon-watchdog.service` | `~/.config/systemd/user/moon-watchdog.service` | inactive (oneshot, triggered by timer) | `/home/meow/Projects/MOON` ✓ |
| `moon-hud.service` | `~/.config/systemd/user/moon-hud.service` | inactive (placeholder, no-op) | n/a (HUD opens on-demand) |
| `moon-monitor.timer` | `~/.config/systemd/user/moon-monitor.timer` | **active** | every 15 min |
| `moon-watchdog.timer` | `~/.config/systemd/user/moon-watchdog.timer` | **active** | every 15 min |

### Health (last monitor run, 2026-08-30 17:56)
```
health: HEALTHY (8 checks, all_ok=True)
agents=39 tools=43
OK: MOON fully operational (health + registry + real execution)
```

### Terminal (live)
`http://127.0.0.1:8777/` → HTTP 200, uvicorn PID tracked by systemd.

---

## 6. Launcher + desktop integration

| Piece | Path | Content |
|---|---|---|
| CLI launcher | `~/.local/bin/moon` | `#!/usr/bin/env bash` → cd to `/home/meow/Projects/MOON` + venv python main.py "$@" |
| Desktop entry | `~/.local/share/applications/moon-terminal.desktop` | Name=MOON Neural Core, Exec=/home/meow/.local/bin/moon terminal, Icon=utilities-terminal |

---

## 7. Scripts (operational)

| Script | Purpose |
|---|---|
| `scripts/start.sh` | Start MOON |
| `scripts/stop.sh` | Stop MOON |
| `scripts/health.sh` | Health check |
| `scripts/moon_deep_monitor.py` | 8-check deep health probe (run by monitor service) |
| `scripts/moon_monitor.py` | Self-heal watchdog |
| `scripts/moon_launcher.py` | Tunnel/launcher helpers |
| `scripts/open_hud.py` | Open HUD browser window on-demand |
| `scripts/open_moon_ui.sh` | Shell HUD opener |
| `scripts/voice_loop.py` | Voice loop |
| `scripts/voice_test.py` | Voice test |
| `scripts/live_gpu_mitigate.sh` | GPU liveliness mitigation |
| `scripts/agent_brains_audit.py` | Agent brains audit |
| `scripts/moon_functional_audit.py` | Functional audit |
| `scripts/backup.sh` | Backup |
| `scripts/install_ollama.py` | Ollama install helper |
| `scripts/apply_grub_psr_fix.sh` | GRUB PSR fix |

---

## 8. Deploy units (source of truth for systemd files)

`deploy/` contains the canonical unit file sources:
- `deploy/moon-terminal.service`
- `deploy/moon-monitor.service`
- `deploy/moon-monitor.timer`
- `deploy/moon-watchdog.service`
- `deploy/moon-watchdog.timer`
- `deploy/moon-hud.service`

These are the files that should be copied to `~/.config/systemd/user/` on fresh install.

---

## 9. Removed (stale duplicates — cleaned up 2026-08-30)

| What | Was at | Why gone |
|---|---|---|
| Desktop copy | `/home/meow/Desktop/MOON` | Stale clone (HEAD e8f971d), own dead venv, outdated .env — removed |
| Home copy | `/home/meow/MOON` | Stale clone (HEAD b62415d), own dead venv, no .env — removed |

`/home/meow/Projects/MOON` is now the ONLY MOON directory on this machine.

---

## 10. Git state (canonical checkout)

```
origin  git@github.com:crsuvo100-gif/MOON.git (fetch/push, SSH verified)
Branch  master (local == origin/master, 39 commits ahead of origin/main)

Remote branches tracked:
  main                    (remote HEAD)
  master                  (up to date, pushes to master)
  moon/capability-system  (up to date)
```

Current HEAD: `b0b657e fix(terminal): harden connect WS handler — _stream always set`

Last 8 commits on master:
```
b0b657e fix(terminal): harden connect WS handler — _stream always set
f569296 docs: add consolidation summary to MOON_MANIFEST.md
4c68b76 fix(terminal): batch WS list actions + fix TUI speech task cleanup
d720143 fix(terminal): harden Moon UI WS action handlers — list_tools, tool, connect
ead6f6e refactor(terminal): consolidate five terminals into two — Moon UI + Moon Shell
25f7d5e fix(terminal): make dashboard + TUI boot functional
89c8dc5 fix(event_bus + terminal): add EventBus.unsubscribe + WS lifecycle cleanup
d273f97 feat(terminal): on-demand HUD launch + auto-voice by default
```

---

## 11. Entry points / how to open MOON

Two terminals. No auto-start — open only when you run them.

**Moon UI** — web AI voice assistant (`moon` / `moon terminal` / `python main.py terminal`):
1. **Browser**: open `http://127.0.0.1:8777`
2. **CLI launcher**: `moon terminal` (opens HUD chrome-free on demand)
3. **Direct Python**: `cd /home/meow/Projects/MOON && .venv/bin/python main.py terminal`

**Moon Shell** — Textual TTS + shell terminal (`moon shell` / `moon tui` / `python main.py shell`):
1. **CLI**: `moon shell` (or `moon tui` — backward-compatible alias)
2. **Direct Python**: `cd /home/meow/Projects/MOON && MOON_TUI_UNLOCK="MOON love you 3000" .venv/bin/python main.py shell`

Unlock phrase (both): `MOON love you 3000`

Moon Shell also supports: `!status` `!ps` `!top` `!df` `!free` `!uname` `!uptime` `!netstat` `!ip` `!ls` `!pwd` `!echo` `!date` `!whoami` `!env` `!nproc` `!cat` (real shell, allowlisted). `/help` for CLI ops list. `Ctrl+V` toggles voice on/off.

---

*End of manifest. If anything here is stale, update it.*
