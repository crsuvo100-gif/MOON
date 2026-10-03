---
name: autonomous-ai-agent-build
description: Build or extend a self-hosted Python AI-agent system.
---

# Autonomous AI-Agent Build (Clean Architecture)

## When to use
- User wants to add/redesign agent features, pipeline stages, agents, plugins,
  memory, or performance infra in a local, self-hosted AI-agent codebase.
- Tasks like "build the Advanced AI Brain", "add the missing pipeline stages",
  "wire the terminal to the pipeline", "make the multi-agent fan-out work".
- The repo is typically under a path with spaces (e.g.
  `.../uncensored standalone ai with own model`), uses a `app/` package with
  `agents/ brain/ memory/ tools/ core/ services/ models/`, a `terminal/` TUI,
  and `scripts/` generators.

## Operating principles (THIS USER — non-negotiable)
- **Be decisive. Do not ask clarifying questions on low-stakes decisions.**
  Pick a reasonable default and proceed; if a decision has real trade-offs,
  pick the best one and note it in the summary. The user has said, verbatim and
  repeatedly: *"do what is best", "don't block things that waste"*. Asking
  "which X?" when you could reasonably default is a failure mode for this user.
- **Execute for real.** Actually run it against the local model / tmux /
  tests and report what *truly* happened. Never fabricate success, output, or
  results. If a step is impossible (no GPU, no network), say so plainly and
  pick a real alternative.
- **Don't waste cycles.** Batch independent reads; avoid redundant re-runs;
  don't re-verify the same thing twice. One decisive end-to-end proof beats
  many partial checks.
- **Additive by default — and the user will SAY SO explicitly.** This user
  states the rule verbatim, e.g. *"do not change or remove already you build it
  just build what you are not build"* and *"build what is missing"*. Honor it
  strictly: ADD new modules/packages and wire them in through new `__init__`
  exports or registries. Do NOT rewrite, delete, or "improve" working files. If
  a fix seems to require touching a working file, isolate the minimal change
  (e.g. add an import line, add a key to a dict) and leave the rest byte-for-byte.
  The user treats previously-working code as sacred — removing/breaking it is a
  hard failure regardless of how "cleaner" your refactor looks.

### Additive-collision pitfall ⚠️ (hit live this session)
- **Symptom**: you create a NEW subpackage that reuses an existing module name
  and the whole test suite collapses with
  `ImportError: cannot import name 'X' from 'pkg.subpkg'`.
- **Concrete case**: added `moon_agent/agents/` (a package) while
  `moon_agent/agents.py` (the module defining `MultiAgentCouncil`) already
  existed. Python cannot have a package and a module with the same name in one
  directory — the package silently shadows the module, so
  `from .agents import MultiAgentCouncil` now resolves to the package's
  `__init__` (which doesn't export it) and ALL test collection fails.
- **Fix applied**: rename the new subpackage (e.g. `moon_agent/agents/` →
  `moon_agent/workers/`), keep the original `agents.py` untouched.
- **Rule to prevent this**: before adding a subpackage with `name X`, check for
  an existing `X.py` at the same level. If it exists, name the package
  differently (`X_workers/`, `X_core/`, `X_svc/`). Grep first:
  `grep -rn "from .X import\|from moon_agent.X import" .` to see what the
  existing `X.py` is imported as, then avoid shadowing it.

## Architecture conventions this user expects
- **Brain pipeline (15 stages)** runs every task by default: Input Analyzer →
  Intent Detector → Context Builder → Planner → Reasoning Engine → Tool
  Selector → Agent Router → Execution Manager → Memory Manager →
  Self-Reflection → Fact Checker → Safety Validator → Response Formatter →
  Output. Compose new stages around the existing `Orchestrator`; don't fork it.
- **Chief multi-agent**: `ChiefAgent` decomposes multi-intent prompts and runs
  specialist agents (coding/research/browser/writing/vision/planning/memory/
  review/debug/terminal/file/database/api/math/testing/security) in parallel,
  aggregating. `BrainPipeline.run_multi` triggers it when >1 intent.
- **Plugins**: auto-discovered via `plugins/registry.py` (scan subpackages for
  `Plugin` subclasses). Add a package + `plugin.py`, no manual registration.
- **DI / events / workers** live in `app/core` (`Container`, `EventBus`,
  `WorkerPool`, `RateLimiter`, `TTLCache`, `Metrics`, `HealthCheck`).
- **Entrypoints**: `main.py run` (default `--mode pipeline`, `--agent auto`,
  `--timeout`), `main.py serve` (FastAPI), `run_terminal.py` (textual + tmux +
  espeak voice). Terminal chat/voice drive `--agent auto --mode pipeline` and
  parse both `Answer :` (pipeline) and `Output :` (legacy) result lines.

## Persona + Security Lock Mode (reusable pattern)
When the user says "give it a personality / behave like X" with a system-prompt
spec, make it REAL and wired, not just a pasted prompt:

1. **Base persona prepended to EVERY agent.** Put the persona text in
   `app/prompts/templates/<name>_system.md` and have `PromptManager.system_prompt`
   prepend it (e.g. `f"{moon}\n\n---\n\n{agent_text}"`) so the model stays
   in-character regardless of which specialist runs. Load file-backed and cache
   it. Keep a short inline fallback in `_seed_defaults` so it works without the
   file. The MOON build did exactly this (file `moon_system.md`, prepended for
   coding/research/planning/…).
2. **Lock Mode must be a CODE GATE, not a prompt.** A "starts locked, unlock
   with exact phrase" requirement is only dependable if enforced in code.
   Implement a `SessionLock` with `.observe(prompt)` returning either the lock
   notice, the unlock-accepted banner, or `None` (unlocked). Enforce it at the
   very top of `Orchestrator.run_task` BEFORE any model/tool call. If locked,
   return the notice and run nothing; if the prompt IS the unlock phrase, write
   the banner and still return (do NOT fall through and execute the phrase as a
   task). Only a subsequent message (`observe` returns `None`) executes.
3. **Persist the lock across processes.** The CLI/TUI spawns a fresh
   `main.py run` per message, so an in-memory lock resets every call. Persist
   state to a file (`unlocked`/`locked`) and load it in the lock constructor;
   `reset()` (session end) writes `locked`. Missing/garbage file = locked
   (safe default). This is what makes "unlock once, stays unlocked" work when
   each chat message is a separate subprocess.
4. **Wire the unlock phrase in the TUI too.** The terminal's chat handler must
   (a) detect the unlock phrase and flip its own TopBar state + pulse the orb,
   and (b) refuse to launch the agent while locked — mirroring the orchestrator
   gate so the UI and the engine agree. Exact phrase match, stripped; tolerate
   surrounding whitespace, require exact wording/case.
5. **Tests**: assert the persona is prepended to every agent, the lock starts
   locked, rejects wrong phrases (wrong case / extra word / incomplete), unlocks
   on the exact phrase, resets, AND persists across instances via a temp file.

## Pitfalls (learned the hard way, under LIVE execution)

### 4. `write_file`-inside-execute_code newline corruption ⚠️ (hit live this session)
- **Symptom**: a generated module fails with `SyntaxError: unterminated string literal`
  on a line that *looks* like `f.write(rec.to_json() + "\n")` — but on disk the `\n`
  became a REAL line break, splitting the string literal across two lines.
- **Why**: when you assemble Python source as a string and pass it through `write_file`
  (often from `execute_code`'s `write_file`), a `\n` inside an f-string / normal string
  literal is written as an actual newline, not the two characters backslash-n.
- **Fix**: never put a literal newline escape inside generated source. Use `chr(10)` for
  line separators in generated code, e.g. `f.write(rec.to_json()); f.write(chr(10))`. Or
  build the file with `os.linesep`. After writing, ALWAYS `python3 -m py_compile` the new
  file before relying on it.

### 5. `queue.PriorityQueue` needs an orderable item
- **Symptom**: `TypeError: '<' not supported between instances of 'QueueItem' and 'QueueItem'`
  when you `.put()` a dataclass into a `PriorityQueue`.
- **Fix**: `@dataclass(order=True)` on the item, with the priority field FIRST and the
  non-comparable payload marked `compare=False`:
  ```python
  @dataclass(order=True)
  class QueueItem:
      priority: int = 5
      task: Task = field(default=None, compare=False)
  ```

### 6. Push to a fresh GitHub repo: rebase onto remote `main`, keep secrets out
- A user-supplied GitHub URL may already hold an "Initial commit" (`main` branch, 1 commit)
  while local work is on `master`. A plain `git push` is rejected (non-fast-forward) or
  clobbers the remote base.
- **Workflow that worked (verified, SSH auth as the repo owner)**:
  1. `git remote add origin git@github.com:<user>/<repo>.git` (SSH, not HTTPS — there is no
     token in env and HTTPS prompts interactively; an existing `~/.ssh/id_ed25519`
     authenticated fine: `ssh -T git@github.com` → "Hi <user>!").
  2. `git fetch origin main`; `git ls-remote origin` to see the remote HEAD + branch.
  3. `git rebase origin/main` — resolve conflicts per file; for files where the remote
     version is irrelevant to THIS project (e.g. a generic `.gitignore` template, a stub
     `README.md`), take ours: `git checkout --ours <file> && git add <file>`.
  4. Continue non-interactively — `git rebase --continue` opens an editor and HANGS in a
     non-interactive shell. Use `GIT_EDITOR=true git rebase --continue` so it accepts the
     default message and proceeds.
  5. **Before pushing, assert no secret is tracked**: `git ls-files | grep -c '^\.env$'` →
     must print `0`. The key lives only in a gitignored `.env`; never commit or push it.
  6. `git push origin master:main` (map local `master` → remote `main`).
  7. Verify the push for real: `git ls-remote origin main` HEAD must equal your local tip,
     and re-confirm `.env` count is `0` in `origin/main`.
  8. Sync any local bare save-mirrors (`git push --force save master`) — a rebase rewrites
     SHAs so the old mirror history is behind; force-update is safe for YOUR OWN mirrors.

## References
- `references/local_model_quirks.md` — qwen3 `thinking`-field answer quirk, dual-brain
  (`brain_model` vs local `model`), and OpenAI-quota 429 handling. Read before wiring a
  local+Ollama fallback brain.
- `references/additive_extend_lifecycle.md` — proven additive-scaffold + safe-build
  + gitignored-secrets + save-mirror lifecycle (use when extending without touching
  working code).
### 1. Stateful-`Task` retry crash  ⚠️ top hit
- **Symptom**: `ValueError: Cannot run task in state TaskStatus.RUNNING`
  (or PENDING/FAILED) when you wrap `orchestrator.run_task(task)` or
  `agent.run(task)` in a `retry`/retry-style loop.
- **Why**: `Task` is stateful — `run_task` calls `task.mark_running()`, which
  raises unless status is PENDING/FAILED. A `retry` that re-invokes the SAME
  task object after attempt 1 (already RUNNING or FAILED) hits the guard.
  Offline unit tests NEVER catch this; only a real model run does.
- **Fix**: never wrap a stateful task run in `retry`. Use **timeout-only**
  (`with_timeout`). The orchestrator already does internal retries. If you
  must re-run, reset `task.status = TaskStatus.PENDING` first, or hand it a
  fresh cloned task. Applied in both `ExecutionManager.run_orchestrator` and
  agent `run_with_recovery`.

### 2. Delegate timeout too short for local CPU models
- The `AgentCapabilities` mixin defaults `_timeout = 120.0`. On a CPU-only
  local model (e.g. `llama3.2:3b`), a single cognition loop can exceed 120s,
  so every Chief delegate dies at 120s and the aggregate returns
  `(no delegate produced output)`.
- **Fix**: thread the pipeline's longer timeout (600–900s) into `ChiefAgent`
  and onto each delegate's `_timeout` before running (`agent._timeout = ...`).
  Proof: after the fix, `TimeoutError` count in a live fan-out run dropped to 0
  and the Chief aggregated 3 real delegate outputs at confidence 0.90.

### 3. Project-root resolution under symlink + spaces
- `Path(__file__).resolve().parent.parent` can collapse to the wrong parent
  when the project dir has spaces / is symlinked. Anchor `ROOT` to an imported
  package's realpath instead: `ROOT = Path(some_pkg.__file__).resolve().parent.parent`.

### 4. Deep-audit methodology for a Python AI-agent project (learned live)
- **Symptom**: you are asked to "deeply check and audit full MOON and fix any
  non-functional or error issue" — a full health pass over a large multi-module
  agent codebase (203 .py files, 164 importable modules, 14+ subsystems).
- **Workflow that worked (verified end-to-end)**:
  1. **Enumerate + parse every .py file.** Walk the project tree, skip
     `.venv`, `skills`, `tests`, `backups`, `data`, `__pycache__`. Run
     `ast.parse` on every file — all must compile. A syntax failure in ANY
     file is a real bug; flag it immediately.
  2. **Import every module.** Build the full module list from the tree walk,
     then `importlib.import_module` each one. A `ModuleNotFoundError` or
     `ImportError` is a real wiring break. (Note: run the import loop from the
     project root so `main` and top-level modules resolve — `sys.path` matters.)
  3. **Exercise every subsystem by calling its REAL public APIs**, not just
     importing. For each subsystem instantiate the class and call its methods:
     EventBus (subscribe/publish/unsubscribe cycle), SessionLock (observe
     unlock phrase, verify `.locked` flips), ExecutionManager (full state
     cycle CREATED→RUNNING→VERIFYING→SUCCESS + assert illegal transitions
     raise), CapabilityManager (discover/status/list/search_github), Connection-
     Gateway (list + inspect records), AgentRegistry (all/select/get), Skill-
     System (all/list_ids/stats), VoiceEngine (backend_status + speak/clone/
     set_voice), LTM (async store/query/all/purge/wipe), terminal_interface
     (route set, _SHELL_ALLOW, _speak callable), TUI (all attrs + handler
     source inspection).
  4. **Verify cross-module wiring in source.** For each named cross-reference
     (e.g. "does the orchestrator use EventBus?", "does terminal_interface
     reference SessionLock?", "does tui import _speak from terminal_interface?"),
     read the actual source with `inspect.getsource` and grep — do NOT assume.
  5. **Run the test suite + doctor + live health.** `pytest tests/ -q`, `moon
     doctor`, and `curl http://127.0.0.1:8777/api/health` against the running
     backend. A passing compile + import pass means nothing if tests fail or the
     live backend is down.
- **Pitfall — the API-guessing trap (hit live this session, 17 false failures):**
  an audit script that GUESSES API names (e.g. `ToolRegistry.list_tools()`,
  `SessionLock.is_locked()`, `CapabilityManager.discover()` with no arg,
  `VoiceEngine.cloning_ready` as an attribute, `LongTermMemory.retrieve(key)`,
  `_SHELL_ALLOW` being a set) will report failures that are ALL FALSE POSITIVES
  — the real APIs are `ToolRegistry.all()/get()/tool_names`, `lk.locked`
  (attribute), `discover(task:str)`, `backend_status()["cloning_ready"]`, LTM has
  `store(data: dict) + query(keyword) + all() + purge(n) + wipe()` with NO
  `retrieve(key)`, and `_SHELL_ALLOW` is a dict mapping command→safe-expansion.
  **Rule**: before reporting a subsystem failure, READ THE REAL SOURCE FILE for
  that subsystem's public methods. Never assume. Every one of the 17 "failures"
  in this session vanished once the real signatures were used.
- **Rule to prevent this**: for any subsystem you haven't personally exercised
  before, read its `__init__`/class definition source FIRST (one `read_file` or
  `grep -n "def \|class "`), then write the audit call against the real API.

### 5. TUI closes when unlock phrase is typed — three independent bugs (learned live)
- **Symptom**: typing the unlock phrase (e.g. "MOON love you 3000") in a Textual
  TUI instantly closes/kills the TUI instead of unlocking and staying open.
- **Why it is three bugs, not one**: the crash usually comes from a combination:
  1. **Missing callback referenced in the handler.** The chat handler passes
     `run_task(on_event=self._on_event)` (or similar) but `_on_event` was never
     defined on the TUI class. The first message AFTER unlocking hits the handler
     → `AttributeError` on the missing method. Even if caught by a broad try/
     except, the error path can destabilize the session.
     **Fix**: define the missing callback on the TUI class (e.g. `async def
     _on_event(self, ev: dict) -> None: ...`) and verify it is referenced
     correctly in the handler source.
  2. **Malformed Rich/Text markup OUTSIDE any try/except.** The unlock response
     is written with e.g. `Text.from_markup(f"[{MOON_GLOW}]MOON[/]: ...")`
     where `[/]` has nothing to close → Rich raises `MarkupError`. If that line
     is NOT wrapped in try/except, the exception propagates and kills the TUI.
     **Fix**: every `Text.from_markup` / `write(Text.from_markup(...))` line must
     use well-formed markup (`[/{tag}]` to close `[tag]`, never bare `[/]`), AND
     the unlock-response write must be inside a try/except or the markup must be
     verified correct. Check ALL markup strings in the unlock path, not just the
     obvious one.
  3. **Unlock path not exception-safe.** If the unlock branch does anything
     besides flipping a flag and writing a known-good string (e.g. pushes an
     event, updates a status bar widget, calls `set_locked`), and that code is
     outside try/except, any failure there kills the TUI at the moment of
     unlocking.
     **Fix**: wrap the entire unlock branch body in try/except, or verify every
     call in it is safe in the current environment (e.g. a widget `query_one` that
     fails if the widget isn't mounted yet).
- **How to reproduce**: boot the TUI headless (`asyncio.create_task(app.run_async())`,
  await a few seconds, check `task.done()` — if True the boot crashed), then submit
  the unlock phrase via `app._handle(unlock_phrase)` or the input path, then submit
  a follow-up message. If the TUI dies at unlock OR at the follow-up, you have
  the bug. Verify the fix by repeating and confirming `task` stays running.
- **Rule to prevent this**: after any TUI patch, (a) headless-boot the TUI and
  confirm it does not crash within a few seconds, (b) submit the unlock phrase and
  a follow-up message in sequence and confirm the TUI stays running, (c) check
  that every `Text.from_markup` / `.write(Text.from_markup(...))` call in the
  unlock + intake path uses well-formed markup.

## Verification workflow (real, not claimed)
- **Unit**: `python -m pytest tests tests_advanced_brain.py tests_terminal.py -q`
  (expect ~192 passing for this project). Use `pytest-asyncio` for async tests.
- **Live pipeline proof**: launch the EXACT command the TUI sends inside a real
  tmux session and parse the pane — this proves the terminal↔pipeline glue:
  ```bash
  SESS=proof; tmux new-session -d -s $SESS -n agent -c "$(pwd)"
  tmux send-keys -t $SESS 'python3 main.py run "What is 2 plus 2?" --agent auto --mode pipeline --timeout 900' Enter
  # poll:
  tmux capture-pane -t $SESS -p -S -200 | grep -E "(?:Answer|Output)\s*:"
  ```
  A match like `Answer : The answer is 4.` confirms the full pipeline + the
  Jarvis parser both work. For multi-agent, use a 2–3 intent prompt and confirm
  the aggregated `Answer : ## Coding agent ... ## Testing agent ...` block.
- **Generator scripts**: run `scripts/create_agent.py <name>` etc. — they must
  create files, register modules, generate a test, then the test's `finally`
  cleans up. Guard template strings: do NOT `.replace("__name__", name)` where
  it would clobber Python's builtin `get_logger(__name__)` — use distinct
  placeholders (`AGENTNAME`/`TOOLNAME`/`FLOWNAME`).

## References
- `references/additive_extend_lifecycle.md` — proven additive-scaffold + safe-build
  + gitignored-secrets + save-mirror lifecycle (use when extending without touching
  working code).
- `references/stateful_task_retry.md` — the antipattern + minimal fix snippets.
- `references/local_model_live_verification.md` — full tmux + parse recipe and
  what good/bad output looks like.
- `references/project_layout.md` — condensed module map of this user's agent
  project so a future session knows where things live.
- `references/moon_persona_lock.md` — the exact `SessionLock` + `PromptManager`
  prepend recipe and the unlock-phrase gate that enforces MOON's lock mode.
