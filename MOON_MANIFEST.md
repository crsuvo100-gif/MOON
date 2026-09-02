# MOON — Unified Machine Manifest
> Generated 2026-09-02. Every MOON-related piece on this host, in one place.
> Canonical checkout: `/home/meow/Projects/MOON` (live dev tree; service + launcher point here).
> Release bundle: `/home/meow/Downloads/MOON` (second clone — install-from-release template; kept in sync and GitHub-pushed).

---

## 1. Canonical checkout

| Item | Path |
|---|---|
| Project root | `/home/meow/Projects/MOON` |
| Git remote | `git@github.com:crsuvo100-gif/MOON.git` (SSH, verified live) |
| HEAD commit | `51d7ffb fix: audit+repair all MOON UI buttons A-to-Z` |
| Branch | `main` (local == origin/main, in sync) |
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

## 9. Copies on this host

| Copy | Path | Role | Sync state |
|---|---|---|---|---|
| Canonical (live) | `/home/meow/Projects/MOON` | Dev checkout — systemd units + launcher + running backend point here | HEAD `51d7ffb`, `main` == `origin/main`, pushed |
| Release bundle | `/home/meow/Downloads/MOON` | Second clone (HTTPS→SSH migrated); kept in sync with canonical | HEAD `51d7ffb`, `main` == `origin/main` (identical files, no push needed) |

Both clones carry the same committed UI+backend fixes; the live running service reads from the canonical copy.

---

## 10. Git state

```
origin  git@github.com:crsuvo100-gif/MOON.git (fetch/push, SSH verified)
Branch  main (local == origin/main, in sync, 51d7ffb pushed to GitHub)

Remote branches tracked:
  main                    (remote HEAD, local in sync)
  moon/capability-system  (up to date)

Current HEAD: `51d7ffb fix: audit+repair all MOON UI buttons A-to-Z`

Last 8 commits on main:
```
51d7ffb fix: audit+repair all MOON UI buttons A-to-Z
87e7184 fix: moon ui works in headless session + HUD already-open message
4aa9371 feat: rewire moon CLI — bare `moon` launches TUI/shell; `moon ui` opens web HUD
383d970 refactor(cli + tui): graceful CLI shutdown + Moon Shell unlock chain
0b19de7 fix(main): `${MOON_TUI_UNLOCK}` env → free-text unlock phrase (was literal "MOON")
06d7f2e fix(core): fix crash in mock mode — first 3 LLM replies now sample the real backend
6ea8559 fix(main): fix duplicate module list in `moon` CLI
873da3c feat(main): Moon Shell — dual GPT-oss mode + webpack-less browserless HUD boot
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
