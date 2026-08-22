### √ Deep MOON Audit — Complete & Operational

**Date:** 2026-08-23 01:22 UTC+1
**Commit:** `8277474` (master + main) — Command palette resize
**Backend:** HEALTHY 8/8 · model `qwen3:0.6b` (CPU, offline Ollama)

---

#### 1. Backend health (8/8 subsystems)
All nominal — agent brains, tool registry, long/short/episodic memory, knowledge base, system health, lock state.

#### 2. Route surface (38 total)
- 35 REST + 3 file routes wired (`/three.min.js`, `/panel3d.js`, `/favicon.ico`).
- Every OpenAPI route has a real handler. `panel3d.js` added + wired (line 354).
- WS handler (`_handle`, line 1126) has `nonlocal orch` fix (line 1128) — no UnboundLocalError anywhere.
- WS actions: 24 Function Dock buttons all map to real handlers; `capabilities`/`github` use `CapabilityManager` directly (lines 1356–1391); no duplicate `capabilities` blocks.
- Auth gate `_token_ok` (line 80) + header-based token auth present.

#### 3. Agent system
- Doctor: **39 agents, 43 tools, HEALTH=PASS** (verified via `python -m moon doctor`).
- AgentFactory operational: `af.create()` + rollback work; factory REST has GET routes (`/api/factory`, `/api/factory/agents`, `/api/factory/components`); no `POST/PUT` factory-create REST endpoint (by design — acceptance test uses Python API directly).
- Model bindings: per-agent via `AgentModelManager`; all CPU-feasible models bound (qwen3:0.6b, qwen2.5:1.5b, qwen2.5:3b, qwen2.5-coder:1.5b, deepseek-r1:1.5b). No GPU-only models bound to CPU agents.

#### 4. Execution manager
- State machine `CREATED→RUNNING→VERIFYING→SUCCESS` (with PLANNED, WAITING, RETRYING, FAILED, CANCELLED, ROLLED_BACK) — no illegal CREATED→SUCCESS.
- Persistence via `sqlite3` at `data/executions.db`. File-backed.

#### 5. Tool + exec paths
- `_shell_dispatch` (line 594): shell command execution.
- `_try_explicit_tool`: explicit tool dispatch path present.
- Tool registry: 43 tools registered (verified GET /api/tools).

#### 6. Monitor + backup (pure Python)
- `scripts/moon_monitor.py`: auto-restarts backend, auto-pulls missing models, checks git sync. Pure Python, no bash. Scheduled every 15m via cron.
- `app/runtime/backup.py`: `pathlib`-based cross-platform backup/restore. Pure Python, no bash.

#### 7. Models (physical, offline)
- 5 CPU-feasible GGUF models physically present at Ollama store:
  - `qwen3:0.6b` (522 MB)
  - `qwen2.5-coder:1.5b` (986 MB)
  - `qwen2.5:1.5b` (986 MB)
  - `qwen2.5:3b` (1.9 GB)
  - `deepseek-r1:1.5b` (1.1 GB)
- Ollama: running offline (`/usr/local/bin/ollama serve`), 8 models total on disk.

#### 8. Frontend HUD (moon_terminal.html)
- 24 Function Dock buttons + 13 footer nav buttons + 6 tabs + 12 panels + workspace overlay — all wired to real backend actions.
- **Command palette**: now MEDIUM (clamp 11–22px font, 62% width, 9.5% height, fixed-position, centered at bottom) — verified via headless Chromium screenshot + vision analysis. Before: small (clamp 8–12px) + crammed in 34% footer cell, not centered. After: prominent, centered, medium.
- panel3d.js: 3D per-panel canvases functional (node syntax OK, 4 Panel3D/init references, init loop present).

#### 9. Git + install
- Working tree **clean** (38 commits pushed to master + main).
- Install: `install.sh` → clone (SSH) → venv → `pip install -e .` → `python -m moon` works. Doctor + monitor + backup subcommands functional.
- GitHub auth: documented (repo is private; SSH/PAT/public paths). DEPLOY.md uses SSH clone (no password prompt).

#### 10. Acceptance (E2E)
- `scripts/acceptance_factory.py`: **ACCEPTANCE PASSED** — create → run → fail → diagnose/repair → retest → success → rollback.

---

#### Verdict: MOON is fully operational and all subsystems are functional.
No gaps found. All previously-identified issues (UnboundLocalError WS handler, KB search `k=` bug, command palette small/misplaced, panel3d.js not wired, missing factory-create REST endpoint confusion) are resolved or verified by-design.

Commit `8277474` is clean, pushed to both `master` and `main`.
