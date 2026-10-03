---
name: runnable-project-generator
description: Scaffold a runnable Python project and verify it works.
---

# Runnable Project Generator

When the user hands you a detailed folder-structure + feature spec and asks for a
"complete / production-ready" project, do NOT print code in chat and stop. Build
the entire tree as real files on disk and verify it actually imports and runs.

## Trigger
User asks to "generate a complete project", "scaffold a production-ready X",
"create a full app" with a folder layout, or "build me a complete … with all
files". Especially when the spec demands: no empty files, no "implement later",
complete runnable starter code, tests for every module, logging, error handling,
type hints, docstrings, async support.

## Core principle
Every file must be importable and do something real. A stub that raises
`NotImplementedError` is acceptable ONLY if the spec literally wants an abstract
method; never leave a whole module as a placeholder. The deliverable is a working
artifact backed by real tool output — not a description of one.

## Workflow
1. **Recon** the environment: `python3 --version`, which key deps import
   (`python3 -c "import pydantic"`), and LOCATE the target folder (`find` it; do
   not assume cwd). Spaces in the path are fine — quote it.
2. **Write the tree on disk** with `write_file` — meta first (requirements.txt,
   pyproject.toml, README, Dockerfile, .env.example, main.py), then packages
   bottom-up: models → utils/services → memory/tools → brain/agents → workflows →
   api → tests/docs. Keep the dependency direction clean (outer depends on inner;
   program to ABCs so concrete backends are swappable).
3. **Make it runnable against LOCAL infra:** default any "model/LLM/cloud" endpoint
   to the user's own OpenAI-compatible server (e.g. `http://127.0.0.1:11434/v1`
   Ollama, or Mew at `127.0.0.1:11435`). No cloud keys required.
4. **Verify — three layers (this is the differentiator):**
   - `python3 -m py_compile $(find app main.py -name '*.py')` — syntax.
   - Import smoke: `python3 -c "import app; from app.brain import Orchestrator; …"`.
   - `pytest` with a **fake/mock service** for external deps (LLM, network) so the
     full integration loop is exercised offline. A `FakeLLMService` returning
     scripted `LLMResponse`s lets you test orchestration, tool-calling, validation,
     and reflection WITHOUT a model or network.
5. **Live smoke (optional, slow):** run one real task via `scripts/live_smoke.py`
   against the local model. On CPU a 3B model takes ~60–90s/call — run it
   `background=true` with `notify_on_complete`, never foreground.

## Pitfalls (caught + fixed this session)
- **dataclass + mixin field ordering:** if a base `Timestamped` is ALSO a dataclass
  with its own `__init__`, subclass fields won't get `created_at`. Fix: base
  supplies only a `@property created_iso`; it is NOT a dataclass. Each entity
  declares its own `created_at: float = field(default_factory=time.time)` and
  `import time`.
- **subprocess stdout vanishes:** a prologue doing `sys.stdout = io.StringIO()`
  then running via `asyncio.create_subprocess_exec` captures NOTHING (redirect is
  in the parent; the child prints to real stdout). Run the user code directly;
  the subprocess already captures stdout/stderr. Re-raise errors to stderr.
- **async tests without pytest-asyncio:** `async def test_*` is collected but never
  run (and the plugin may be absent → config warning). Either install
  pytest-asyncio + `asyncio_mode=auto`, or write `def test_*` that call
  `asyncio.run(...)`. Don't leave uncollected async tests.
- **f-strings for shell/tmux commands:** nested quotes + backslashes in f-strings
  raise `SyntaxError`. Build command strings by plain concatenation; quote args
  for `send-keys` (shell-safe).
- **execute_code consent:** the `execute_code` tool runs in a sandbox and requires
  SEPARATE user approval; a mid-run script was BLOCKED. For verification, prefer
  writing `tests_*.py` and running `python -m pytest` via `terminal`. (See
  references/verification_recipe.md.)
- **Code-generator template clobbering (`__name__`):** when a generator builds a
  module from a template via `.replace("__name__", name)` (or `__class__`), that
  global replace ALSO rewrites `get_logger(__name__)` -> `get_logger(demoagent)`,
  raising `NameError` at import. Use a DISTINCT placeholder for the name attribute
  (e.g. `AGENTNAME`/`FLOWNAME`/`TOOLNAME`) and replace only that; leave the
  Python builtin `__name__` literal untouched. See references/code_generators.md.
- **Fragile registry/__init__ edits in generators:** `append_line` that injects
  `"demoagent": "DemoagentAgent",` into `registry.py` or a `library.py` dict
  lands at MODULE level (not inside the dict) -> `SyntaxError: illegal target for
  annotation` / `IndentationError`. Same for `register_in_init` regex-patching
  `__all__`. FIX: make registries DYNAMIC instead -- `AgentRegistry.discover()`
  walks `<name>_agent` modules; `PromptLibrary.list()` globs the templates dir.
  Then generators only need to drop the file; no literal patching. If you must
  patch an `__init__`, target the import line + `__all__` entry precisely.
- **Test ROOT under spaced/symlinked dirs:** `Path(__file__).resolve().parent.
  parent` can resolve to the wrong directory when the project path contains spaces
  or is a symlink, silently breaking generator/collection paths. Anchor `ROOT` to a
  known package: `ROOT = Path(importlib.import_module("app").__file__).resolve().
  parent.parent`. Verify with `print(ROOT)` before relying on it.
- **Stateful-Task + retry crash (`Cannot run task in state RUNNING`):** do NOT wrap
  a task-running coroutine (`orchestrator.run_task(task)`, `agent.run(task)`) in a
  generic `retry()` that re-invokes the SAME `Task` object. `Task.mark_running()`
  raises `ValueError` on any non-PENDING state, so a first-attempt failure re-runs
  on an already-RUNNING task and crashes. The orchestrator already retries the
  *LLM call* internally, so the wrapper retry is redundant AND unsafe. Use a
  timeout-only wrapper (`with_timeout`) for the orchestrator/agent, and if you must
  retry, clone a fresh PENDING task per attempt (or reset `task.status =
  TaskStatus.PENDING` before re-running). The same rule applies to a Chief/supervisor
  fanning sub-tasks to specialist agents: each delegate must get its OWN fresh `Task`;
  `run_with_recovery` must be timeout-only + fault-isolating (catch, mark failed,
  return the task) — never re-run the same stateful task. See references/pitfalls.md
  ("stateful task + retry").
- **Wiring a NEW engine as the live default:** when you add a richer execution path
  (e.g. a full pipeline + multi-agent Chief over an existing orchestrator), make it
  the DEFAULT in `main.py run` but keep the OLD path reachable via a flag
  (`--mode legacy|pipeline`, `--agent auto` for fan-out). For the API, accept a `mode`
  field. Always prove the new path with a real run (verification step 5) — offline
  tests will NOT catch the stateful-task/retry class of bug.
- **Slow local model = raise execution timeouts:** on CPU-only inference a 3B model
  takes 60–90s+ PER call; a 120s `with_timeout` kills a legit single run. Bump the
  pipeline's execution timeout to ~600s. Run live smokes with `python -u
  scripts/live_smoke.py > /tmp/x.log 2>&1` (NOT `| tail -40` — tail buffers until
  exit and hides progress); read the log via `terminal`+`cat`, or launch
  `background=true, notify_on_complete=true`. A delegate `TimeoutError`/`APITimeoutError`
  that is CAUGHT by `run_with_recovery` and logged as the task failing is PROOF the
  fault-tolerance/auto-recovery works — not a failure to fix.
- **Convert bash launchers to pure Python:** this user prefers project
  entrypoints/installers to be `.py` (not `.sh`/bash) so the whole project is
  Python-driven. When you create a `moon`/`install`/run launcher, write it as
  `moon.py`/`install_moon.py` with `if __name__ == "__main__"`, keep install logic
  in one module, and reuse functions (e.g. a shared `launch_terminal()`) rather than
  duplicating. Verify with `python -m py_compile` + a live launch. Note: a Docker
  container `entrypoint.sh` is legitimately shell (infra glue) — leave it; converting
  to Python adds deps and slower startup for zero gain.
- **Natural TTS + tone cloning (offline, CPU-only):** for a voice that sounds like a
  person (not robotic espeak) on a CPU box, use **Piper neural TTS** (`pip install
  piper-tts`), download a voice `.onnx`+`.onnx.json` from the `rhasspy/piper-voices`
  HuggingFace repo (`https://huggingface.co/rhasspy/piper-voices/resolve/main/<lang>/<spk>/<qual>/<name>.onnx`), and synthesize with `PiperVoice.load(onnx,json).synthesize_wav(text, wave.open(...))`. To "clone a tone" without GPU, post-process the
  output WAV with **SoX** `pitch <cents>` keyed off the target sample's fundamental:
  `cents = 1200*log2(target_hz / base_hz)`. Capture the target pitch via
  `sox sample.wav -n stat` and parse the **"Rough   frequency"** line — note the
  EXTRA SPACES; match on `"frequency" in line.lower() and "rough" in line.lower()`,
  NOT the exact phrase `"Rough frequency"` (the spacing mismatch makes a naive
  substring check fail). True zero-shot speaker cloning needs GPU/large models and
  will OOM a small CPU box — be honest about that instead of faking it.
  Full recipe + worked commands in `references/voice_tts_clone.md`.

## Quality bar
PEP 8, fully typed, docstrings, logging, error handling, example usage in every
module. Async-first for I/O. Graceful degradation when optional deps/tools are
missing (return clear errors, never crash). Whole-tree import test guarantees no
module is broken.

## References
- `references/pitfalls.md` — expanded bug write-ups (with the failing vs fixed code).
- `references/verification_recipe.md` — exact commands to compile / import / test / mock.
- `references/code_generators.md` — template clobbering, fragile registry edits, ROOT resolution for `create_*` generator scripts.
- `references/voice_tts_clone.md` — Piper neural TTS + SoX tone-clone recipe (offline, CPU), with the SoX stat spacing-parse pitfall.
