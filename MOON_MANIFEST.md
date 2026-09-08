# MOON — Unified Machine Manifest
> Generated 2026-09-08. Every MOON-related piece on this host, in one place.
> Canonical checkout: `/home/meow/Projects/MOON` (live dev tree; service + launcher point here).
> Release bundle: `/home/meow/Downloads/MOON` (second clone — install-from-release template; kept in sync and GitHub-pushed).

---

## 1. Canonical checkout

| Item | Path |
|---|---|
| Project root | `/home/meow/Projects/MOON` |
| Git remote | `git@github.com:crsuvo100-gif/MOON.git` (SSH, verified live) |
| HEAD commit | `88609bb fix(cli): ensure saved files end with newline (empty-file fix)` |
| Branch | `master` (local == origin/master, ahead 1) |
| Python | `.venv/bin/python` → 3.14.6 |
| Venv | `.venv/` |

### Subsystems (all live per wiring map)
- Main brain: `app/brain/orchestrator.py :: Orchestrator`
- 39 agents, 43 tools
- Voice: `app/voice_engine.py` (kokoro TTS primary, F5-TTS fallback)
- Web HUD: `web/moon_terminal.html` → WS `ws://127.0.0.1:8777/ws`
- Agent brains: `data/agents/`
- CLI Terminal (Hermes-style): `app/cli/` package — REPL + 28 slash commands + 5 subcommands + LLM oneshot

---

## 2. Runtime entrypoints (all verified live)

| Entrypoint | Command | Wires to |
|---|---|---|
| Terminal/API server | `python main.py terminal` / `moon` / `moon terminal` → uvicorn on :8777 | Orchestrator + WS `/ws` + HTTP `/api/*` |
| Moon Shell (TUI) | `python main.py shell` / `moon shell` / `moon tui` | Orchestrator directly + TTS + `!shell` + `/cli` |
| CLI Terminal (Hermes-style) | `python main.py cli` / `moon cli` / `moon cli doctor/status/model/oneshot/setup` | `app/cli/` package: REPL + 28 slash commands + 5 subcommands + LLM oneshot |
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
| `data/agents/agent_factory.db` | Agent definitions |
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
| `moon-monitor.service` | `~/.config/systemd/user/moon-monitor.service` | inactive (oneshot, triggered by timer) | `/home/meow/Projects/MOON` ✓ |
| `moon-watchdog.service` | `~/.config/systemd/user/moon-watchdog.service` | inactive (oneshot, triggered by timer) | `/home/meow/Projects/MOON` ✓ |
| `moon-hud.service` | `~/.config/systemd/user/moon-hud.service` | inactive (placeholder, no-op) | n/a (HUD opens on-demand) |
| `moon-monitor.timer` | `~/.config/systemd/user/moon-monitor.timer` | **active** | every 15 min |
| `moon-watchdog.timer` | `~/.config/systemd/user/moon-watchdog.timer` | **active** | every 15 min |

### Health (last monitor run)
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
|---|---|---|---|
| Canonical (live) | `/home/meow/Projects/MOON` | Dev checkout — systemd units + launcher + running backend point here | HEAD `88609bb`, `master` == `origin/master`, pushed |
| Release bundle | `/home/meow/Downloads/MOON` | Second clone (HTTPS→SSH migrated); kept in sync with canonical | HEAD `88609bb`, `master` == `origin/master` (identical files, no push needed) |

Both clones carry the same committed UI+backend+CLI fixes; the live running service reads from the canonical copy.

---

## 10. Git state

```
origin  git@github.com:crsuvo100-gif/MOON.git (fetch/push, SSH verified)
Branch  master (local == origin/master, ahead 1, 88609bb pushed to GitHub)

Remote branches tracked:
  main                    (remote HEAD)
  moon/capability-system  (up to date)

Current HEAD: `88609bb fix(cli): ensure saved files end with newline (empty-file fix)`

Last 8 commits on master:
```
88609bb fix(cli): ensure saved files end with newline (empty-file fix)
50e2f22 fix(cli): register /cli as proper subcommand in app.cli.main
7c9b34d fix(cli): complete interactive CLI audit — 30/30 slash commands pass
eeb2865 fix(cli): _build_state return CLIState not dict (type annotation fix)
05c0814 build(cli): add Hermes-style Moon CLI terminal package (app/cli/)
3f364bc fix(cli): add _stream_chunk helper + fix flush in streaming + remove stale self._scratch from MoonCLI
```

---

## 11. Entry points / how to open MOON

One terminal. No auto-start — open only when you run it.

**MOON** — Hermes-style CLI terminal (`moon` / `moon run` / `moon terminal` / `moon cli` / `python main.py`):

1. **CLI**: `moon` (bare) or `moon run` — launches the Hermes-style CLI REPL (default)
2. **One-shot task**: `moon run "your task here"` or `moon run --task "..." --agent auto`
3. **Direct Python**: `cd /home/meow/Projects/MOON && .venv/bin/python main.py` or `python main.py run "task"`

Subcommands (all via the CLI terminal package):
- `moon doctor` — health check (Python/deps/config/DB/agents/tools/model/git)
- `moon status` — live backend health
- `moon cli doctor` / `moon cli status` / `moon cli model` / `moon cli oneshot` / `moon cli setup` — CLI subcommands

REPL slash commands (28): `/help`, `/help <cmd>`, `/history`, `/new`, `/title`, `/retry`, `/undo`, `/save` (json|md|html), `/chat`, `/oneshot`, `/doctor`, `/status`, `/setup`, `/model` [--query], `/agent`, `/compress`, `/shell`, `/clear`, `/statusbar` (alias `/bar`), `/indicator` (alias `/think`), `/timestamps` (alias `/time`), `/quit`, `/exit`, `/version`.

Unlock phrase: `MOON love you 3000`

---

*End of manifest. If anything here is stale, update it.*