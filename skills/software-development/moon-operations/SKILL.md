---
name: moon-operations
description: Operate and verify MOON service, API, and tests.
---

# moon-operations — Operating & Verifying MOON in Production

## When to use
- Any task that touches MOON's running service, API, tests, git state, or deployment.
- Verifying MOON is healthy and complete after a build, install, or config change.
- Mapping a specification's phases to evidence (e.g. a 31-phase professional-agent spec).

## Always-on rules

### Plain English (USA) only
- Write in plain, simple English (USA). Short sentences. No jargon without explanation.
- The user has stated verbatim: "please language, text fonts make english(usa) cause what you say in written i do not understant."
- Every report, summary, and commit message must be readable by someone who does not speak English fluently.
- Avoid: nested bullet hierarchies deeper than 2 levels, Latin abbreviations (i.e., e.g., etc.), or academic phrasing.

### Decisive action — do not stall on clear tasks
- When the task is clear, execute + verify. Do not re-confirm, re-summarize, or ask low-stakes questions.
- The user has stated verbatim: "do what is best", "don't block things that waste".
- If a decision has real trade-offs, pick the best one and note it in the summary — do not ask.

### No extra work after completion sign-off
- When a project or task is declared complete, sign off and stop. Do not add extra work, extras, or "one more thing".
- In the next session, ask "what's the next move" rather than resuming unfinished work.

### Preserve working functionality — additive only
- Never remove or rewrite working code. Add new modules/packages; wire them in through new `__init__` exports or registries.
- If a fix requires touching a working file, isolate the minimal change (add an import, add a key to a dict) and leave the rest byte-for-byte.
- The user treats previously-working code as sacred — breaking it is a hard failure regardless of how "cleaner" a refactor looks.

### Never expose credentials
- TELEGRAM_BOT_TOKEN and all other secrets live in `.env` (gitignored). Never read, print, or commit them.
- If a command would print a secret, redirect or mask it: `curl ... | python3 -c "..."` (do not `cat .env`).

### Thinking models exhaust default max_tokens — always pass explicit max_tokens
- **Symptom**: TUI or API returns empty/garbage responses; model appears to "not work" despite healthy service.
- **Why**: thinking models (qwen3, deepseek-r1, etc.) spend their entire token budget on reasoning (`<think>` block), leaving 0 tokens for actual content. The default `max_tokens=2048` is consumed entirely by reasoning.
- **Fix**: always pass explicit `max_tokens` to `llm.complete()` — use `4096` for main/agent loops, `1024` for smaller tasks (planning, reflection, consolidation).
- **Rule**: grep for `.complete(` calls without `max_tokens` after any LLM signature change. Every call site must pass it explicitly.

### Test mocks must accept **kwargs when real signatures change
- **Symptom**: tests fail with `TypeError: complete() got an unexpected keyword argument 'max_tokens'` after adding a parameter to the real method.
- **Why**: hand-rolled `FakeLLM` mocks in tests reimplement the old signature and break when the real method gains parameters.
- **Fix**: always use `async def complete(self, messages, **kwargs)` in test mocks — accepts any current or future parameters.
- **Rule**: when changing a method signature that mocks implement, grep the test tree for the mock class and update it in the same commit.

## TUI troubleshooting

### Pitfall: TUI "not working" = model returning empty, not input broken
- **Symptom**: user reports "moon terminal open but not working" — TUI is running, input is accepted, but responses are empty or garbage.
- **Why**: the TUI process is alive and accepting keystrokes; the real issue is the LLM returning empty content because thinking models exhaust the default token budget on reasoning.
- **Diagnosis**: check `ps aux | grep main.py` to confirm TUI is running, then test the LLM directly:
  ```bash
  curl -s -X POST http://127.0.0.1:11434/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"qwen3:0.6b","messages":[{"role":"user","content":"Say hello"}],"max_tokens":50}' \
    --max-time 30
  ```
  If this returns empty `content`, the model config is the problem, not the TUI.
- **Fix**: pass `max_tokens=4096` to all `llm.complete()` calls (see pitfall above).

### Pitfall: TUI "not working" = dead lock check, not model issue
- **Symptom**: user reports "moon terminal open but not working" — TUI renders, but ALL input is ignored; chat shows "Locked" or no response to any message.
- **Why**: `SessionLock.observe()` was changed to always return `None` (lock mode removed), but `_handle_input` still checked `if notice and "unlocked" in notice.lower()` — since `notice` is `None`, the condition is `False`, so it falls to the `else` branch and shows "Locked" forever. The TUI opens but ignores all input.
- **Diagnosis**: check if TUI shows "Locked" in the HUD or chat panel. If yes, the lock check is the problem, not the model.
- **Fix**: remove the dead lock-check in `_handle_input`, default `locked` reactive to `False` in all TUI widgets, and set `CLIState.locked = False`.
- **Rule**: when a security/lock mode is removed, grep for ALL references to the lock state in the UI layer — reactive defaults, watch methods, and input handlers. A dead check that always evaluates to `False` will silently break input handling.

## Service lifecycle (systemd user unit)

MOON runs as a **user systemd service** (`moon-terminal.service`), not system-wide. The canonical commands:

```bash
# Check status
systemctl --user status moon-terminal.service

# Restart
systemctl --user restart moon-terminal.service

# Start / stop / enable
systemctl --user start   moon-terminal.service
systemctl --user stop    moon-terminal.service
systemctl --user enable  moon-terminal.service   # auto-start on login

# View logs
journalctl --user -u moon-terminal.service -f
```

### Pitfall: sudo/system-wide systemd will not work
- **Symptom**: `sudo systemctl restart moon.service` fails with "Sorry, try again. sudo: no password was provided" or similar.
- **Why**: the MOON service is installed as a **user unit** (`/home/meow/.config/systemd/user/moon.service`), not a system unit. `sudo systemctl` targets system-level units and cannot see or control user units. Additionally, the user has no sudo password configured in this environment.
- **Fix**: always use `systemctl --user` for MOON service management. There is no password prompt and no sudo needed.
- **Do not try**: `sudo systemctl`, `systemctl` without `--user`, or editing the unit to move it to system-level. The user-unit path is intentional and correct.

### Pitfall: stale service state after config changes
- After changing `.env`, `pyproject.toml` dependencies, or source code, restart the service before testing: `systemctl --user restart moon-terminal.service`.
- Verify readiness before assuming it's up: `curl -s --max-time 5 http://127.0.0.1:8777/api/health` must return `{"status":"HEALTHY", ...}`.
- If health check fails, check `journalctl --user -u moon-terminal.service -n 30` for the crash reason before retrying.

## API health verification

### Health endpoint
```bash
curl -s http://127.0.0.1:8777/api/health
# Expected: {"status":"HEALTHY","summary":"8/8 subsystems nominal","checks":[...],"model":"qwen3:0.6b","locked":false,"timestamp":...}
```

### Agents endpoint — defensive parsing required
- **Symptom**: `curl .../api/agents | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d))"` exits 1 or returns a wrong count.
- **Why**: the `/api/agents` response is NOT a bare JSON array. It returns a dict envelope (e.g. `{"agents": [...], "count": N}`) or a different shape. `json.load` into a list fails on a dict.
- **Fix — always inspect raw shape first**:
  ```bash
  curl -s http://127.0.0.1:8777/api/agents | head -c 500   # inspect shape before parsing
  ```
- **Then write a defensive parser**:
  ```python
  import sys, json
  d = json.load(sys.stdin)
  if isinstance(d, dict):
      agents = d.get("agents", d)   # fallback: the whole dict if no "agents" key
  else:
      agents = d
  print(f"Agent count: {len(agents)}")
  ```
- **Rule**: before reporting an API as broken, read the real response shape. Never assume a root array.

### Other endpoints
| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | Service health + agent count |
| `POST /api/moon-agent` | Send message to main agent |
| `POST /api/moon-agent/stream` | Streaming agent response |
| `GET /api/tools` | List all tools |
| `GET /api/tools/<name>` | Tool detail |
| `GET /api/agents` | List all registered agents (defensive parse) |
| `GET /api/agents/<name>` | Agent detail |

## Test suite

```bash
cd /home/meow/Projects/MOON
python -m pytest tests/ -v        # full verbose run
python -m pytest tests/ -q        # quiet: pass/fail only
python -m pytest tests/test_api.py -v   # API tests specifically
```

- **Green bar**: 156/156 passed (current as of 2026-10-03). Any run that drops below this is a real regression — investigate. The count grows as new modules are added; update it after each test addition.
- Always run the full suite after any source change, not just the obviously-related test file.
- The test suite takes ~50s; budget for it in long operations.

## Git workflow

```bash
cd /home/meow/Projects/MOON

# Check state
git status --short          # empty = clean at HEAD
git diff --stat HEAD        # empty = nothing uncommitted
git log --oneline -3       # recent commits
git remote -v               # confirm github.com/crsuvo100-gif/MOON.git

# Commit + push (no secrets)
git add <files>
git commit -m "<type>: <what changed>"
git push origin master
```

### Pitfall: committing secrets
- **Rule**: `git ls-files | grep -c '^\.env$'` must print `0` before every push. The `.env` file is gitignored — if it shows up in `git status`, do NOT add it. Confirm with `git ls-files | grep '^\.env$'` (count must be 0).
- TELEGRAM_BOT_TOKEN and all other secrets live ONLY in `.env` which is `.gitignore`d.

## Spec-phase verification methodology

When given a multi-phase specification (e.g. a 31-phase professional AI assistant build spec), verify phase-by-phase rather than claiming overall completion:

1. **Extract the phases.** Read the full spec attachment. List every phase as a row.
2. **Map each phase to evidence.** For each phase, find the concrete artifact that proves it: a file, a running service, a test count, an API response, a doc.
3. **Mark each phase ✅ or ❌.** Do not skip phases. A phase with no evidence is ❌ even if the overall system seems complete.
4. **Fill gaps before claiming done.** For any ❌ phase, create the missing artifact (doc, Dockerfile, script, test) and re-verify.
5. **Final report = phase table.** Deliver a table of all phases with status + evidence, not a prose summary.

### Pitfall: claiming completion from partial evidence
- **Symptom**: you check the service is running and tests pass, then claim the full spec is done.
- **Why**: a running service + green tests prove the SYSTEM works, not that every DOCUMENTATION or DELIVERABLE phase of a spec is complete. Documentation phases require doc files; Docker phases require Dockerfiles; CI phases require workflow files.
- **Rule**: for each spec phase, identify the DELIVERABLE (not just the capability). A capability living in code does not satisfy a "document X" phase until the doc file exists.

## Python venv

- The MOON venv is at `/home/meow/Projects/MOON/.venv` (project root, not a subdirectory).
- Always activate before running Python: `cd /home/meow/Projects/MOON && source .venv/bin/activate && python3 <script>`.
- Alternatively use the absolute path: `/home/meow/Projects/MOON/.venv/bin/python3 <script>`.
- **Do not** run `python3` from the system Python when the project has a venv — dependency resolution will be wrong.

## Attachments

- Task attachments live in `/home/meow/.hermes/attachments/`.
- When a task references an attachment by path (e.g. `@file:/home/meow/.hermes/attachments/pasted_content_...txt`), read it directly with `read_file`.
- Attachment filenames use the pattern `pasted_content_<date>_<time>_<code>.txt`.
- When a task says "task 2 : attached." with no body, the actual content may be in a separate attachment file — always check the attachments directory for additional files before concluding the task body is empty.

## Fresh install from GitHub

MOON is designed to be installable from GitHub anytime. The canonical fresh-install workflow:

```bash
# Clone the CORRECT branch (master = current structure; main = legacy/old structure)
git clone --branch master git@github.com:crsuvo100-gif/MOON.git /tmp/moon-fresh-install

# Run the installer (skip model downloads and service install for speed)
cd /tmp/moon-fresh-install
python script.py --yes --no-models --no-service

# Verify the install
cd /tmp/moon-fresh-install
.venv/bin/python -c "import sys; sys.path.insert(0, '.'); from app.config.settings import get_settings; from app.brain.orchestrator import Orchestrator; print('OK')"
```

### Pitfall: GitHub remote has TWO branches — always use `--branch master`
- **Symptom**: `git clone git@github.com:crsuvu100-gif/MOON.git` defaults to `main` branch which has the OLD/legacy structure (no `script.py`, no `app/`, no `deploy/`, no `pyproject.toml`).
- **Why**: the remote has two branches: `main` (legacy structure with `agent/`, `terminal/`, `main.py`) and `master` (current structure with all files). The default clone picks `main`.
- **Fix**: always use `git clone --branch master git@github.com:crsuvu100-gif/MOON.git <dir>` for fresh installs.
- **Rule**: before running the installer, verify the clone has `script.py`, `app/`, `deploy/`, and `pyproject.toml` at the root.

### Pitfall: verify_install treats optional components as hard requirements
- **Symptom**: fresh install fails acceptance check with `CLONING_READY=False` even though the install is functional.
- **Why**: `verify_install` in `script.py` treated f5-tts/cloning as a hard requirement, but f5-tts is optional and lazy-fetches on first use.
- **Fix**: `verify_install` should print a NOTE for optional components but not fail the overall acceptance.
- **Rule**: when writing install verification, distinguish between REQUIRED components (must pass) and OPTIONAL components (warn but don't fail).

### Pitfall: running installer from temp dir hardcodes temp path into launcher
- **Symptom**: `moon terminal` fails with "No such file or directory" or "cd: /tmp/moon-fresh-install: No such file or directory" after the temp dir is cleaned up.
- **Why**: `install_launcher()` in `script.py` uses `ROOT = Path(__file__).resolve().parent` to determine the install path. When run from `/tmp/moon-fresh-install`, it writes a launcher pointing to that temp path. After `rm -rf /tmp/moon-fresh-install`, the launcher is broken.
- **Fix**: After running the installer from a temp dir, either (a) re-run `install_launcher()` from the canonical path, or (b) manually rewrite `~/.local/bin/moon` to point to the canonical path. The canonical launcher should be:
  ```bash
  #!/usr/bin/env bash
  cd "/home/meow/Projects/MOON" || exit 1
  exec env -u PYTHONPATH "/home/meow/Projects/MOON/.venv/bin/python" main.py "$@"
  ```
- **Rule**: when testing a fresh install from a temp dir, always check `cat ~/.local/bin/moon` after cleanup. If it points to the temp dir, rewrite it to the canonical path before declaring the install verified.

## References

- `references/api-endpoints.md` — full MOON API endpoint reference with expected shapes.
- `references/spec-verification-checklist.md` — the phase-by-phase verification template and the documentation deliverable mapping.
- `references/service-troubleshooting.md` — service won't start, health check fails, agent count wrong.
- `references/fresh-install-workflow.md` — complete fresh-install-from-GITHUB procedure with verification steps.
