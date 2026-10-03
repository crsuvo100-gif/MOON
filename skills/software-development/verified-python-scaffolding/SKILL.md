---
name: verified-python-scaffolding
description: Scaffold and verify Python projects end-to-end.
---

# verified-python-scaffolding

Use when a user asks to "generate a complete project", "scaffold an X", "build a
production-ready agent/app", or hands you a full folder-structure spec to realize.
Also trigger on requests for many interdependent Python files that must import
and actually run.

Core principle (matches the standing operating standard): deliver on disk with
REAL code, not printed snippets, and verify with real tool output before
claiming success. Report what actually happened.

## Workflow

1. **Inspect the environment first** (terminal): `python3 --version`, check key
   deps (`pydantic`, `fastapi`, `pytest`, `httpx`, `openai`) via
   `python3 -c "import X; print(X.__version__)"`. Locate the target dir.
2. **Scaffold meta files**: `requirements.txt`, `pyproject.toml`, `Dockerfile`,
   `docker-compose.yml`, `.env.example`, `README.md`, top-level `main.py`.
3. **Build the package in dependency order** so each layer imports the one below:
   `models → config/utils → services → memory → tools → brain → agents →
   workflows → api → database/cache`. Every file: imports, class(es), docstrings,
   type hints, logging, error handling, example/TODO. No empty files.
4. **Wire the composition root last** (orchestrator / app factory).
5. **Verify** (below). Fix every failure before reporting done.

## Verification recipe

```bash
python3 -m py_compile $(find app main.py scripts examples -name "*.py") && echo COMPILE OK
python3 -c "import app; from app.api.main import app; print('IMPORTS OK')"
pytest -q
python3 scripts/live_smoke.py   # live model (slower; needs endpoint up)
```

Write tests/scripts as files and run them with `pytest` in the terminal for
real execution (durable, re-runnable, avoids one-shot execution paths).

## Clean Architecture layout

```
app/
  api/ agents/ brain/ memory/ tools/ workflows/ models/
  services/ config/ database/ cache/ prompts/ planner/ reasoning/ utils/ logs/
tests/        # unit + integration (fake service) + whole-tree import test
```
Dependency direction points inward. Program to ABCs (`VectorStore`,
`CacheBackend`) so backends swap without touching callers.

## Pitfalls (hard-won this session)

- **Dataclass + mixin `created_at`**: a non-dataclass mixin that sets
  `self.created_at` in `__init__` does NOT run — the dataclass `__init__` skips
  it -> `AttributeError: object has no attribute 'created_at'`. Make the mixin
  NOT define `__init__`; declare `created_at: float = field(default_factory=time.time)`
  in EACH subclass and `import time`. See `references/dataclass-mixin-pitfall.md`.
- **Subprocess stdout swallow**: redirecting `sys.stdout = io.StringIO()` in a
  sandbox prologue means user `print()` is captured into the buffer and never
  reaches the PIPE -> always-empty output. Run user code directly; let PIPE
  capture. See `references/python-subprocess-execution.md`.
- **Async tests w/o pytest-asyncio**: `async def test_*` is collected but never
  awaited; `asyncio_mode` warns as unknown. Convert to `def test_*` driving
  `asyncio.run(coro())`, or install pytest-asyncio. Use a **fake service** injected
  into the composition root to run the real loop with scripted responses. See
  `references/async-testing-patterns.md`.
- **Offline embeddings**: no endpoint -> deterministic hashed bag-of-words
  projection keeps RAG/semantic search runnable on CPU. See
  `references/offline-embedding-fallback.md`.
- **Whole-tree import test** (`tests/test_import_all.py`) catches NameErrors
  (`ChatMessage` used-but-not-imported) and circular imports unit tests miss.

## Local-model wiring note

Point the model client at an OpenAI-compatible endpoint the user controls
(default `http://127.0.0.1:11434/v1` Ollama; `127.0.0.1:11435` Mew). The agent
is a *client* -- no cloud provider needed. CPU 1-3B models take ~30-90s/call;
budget time for live smoke tests.

## References
- `references/dataclass-mixin-pitfall.md`
- `references/python-subprocess-execution.md`
- `references/async-testing-patterns.md`
- `references/offline-embedding-fallback.md`
- `templates/fake_llm_service.py`
