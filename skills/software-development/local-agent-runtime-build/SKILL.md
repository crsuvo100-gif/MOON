---
name: local-agent-runtime-build
description: Build or extend a local-first Python AI agent.
category: software-development
---

# Local-first AI Agent Runtime — Build & Extend

Use when building or extending a local-first Python AI agent: a runtime with tools,
memory, a multi-agent "council", an imported skill/knowledge corpus, and a local LLM
brain — packaged as a pip-installable wheel. Worked example: the MOON agent
(`moon_agent/` package at `/home/meow/projectterminal/RED_TEAMING_HACKER_INTERFACE/Moon_AI_AGENT`).

## Principles
- **Additive rebuild over monolith repair.** Keep legacy files (e.g. `moon.py`, `terminal/`)
  untouched except for syntax fixes; build a clean new package (`moon_agent/`) as the real
  foundation. Never remove working features.
- **Real tools, scoped.** No `shell=True`, no `eval`/`exec` of arbitrary strings except a
  temp-folder code executor with a timeout; file tools confined to project root via `safe_path`.
- **Verify, don't claim.** Run `py_compile` + `pytest` + an actual `pip install -e .` + the
  console command. A passing compile is NOT a build.

## Workflow
1. Inventory the project and the source skill corpus.
2. Build the runtime package: `runtime.py` (lock/unlock + tool dispatch), `memory.py` (JSONL),
   `tools/core.py` (registry + real tools), `agents.py` (council), `config.py`,
   `api.py` (optional Flask), `cli.py`.
3. Ingest the imported skill corpus: copy `SKILL.md` into `moon_agent/skills/sk_db/`, index with
   a `SkillCatalog`, and wrap real dependency-light scripts as callable tools. See
   references/skill-corpus-ingestion.md.
4. Wire a **hardware-aware** local LLM brain — empirically verify it loads first. See
   references/model-fit-check.md.
5. Package so data files ship. See references/packaging-data-files.md.
6. Test: `tests/` covering tools, memory, council (assert it lists ONLY real registered tool
   names), skill catalog, API factory, CLI entrypoint. Run `pytest` + a real install.

## Pitfalls
- **Council listing phantom tools**: if `agents.py` references tool names absent from the
  registry, a council step silently claims capabilities it lacks. Always assert
  `council_usable_tools ⊆ registered_tools`.
- **Stale imports after refactor**: renaming a module (e.g. `moon_agent/skills.py` →
  `moon_agent/skills/` package) leaves dangling `from moon_agent.skills import X` and dead
  classes referencing removed symbols. Grep for the old symbol names after moving code.
- **Duplicate/unreferenced data trees**: a top-level `skills/` mirroring
  `moon_agent/skills/sk_db/` is dead weight — confirm nothing imports it, then remove.
- **pyproject without `packages`**: `pip install .` fails with a setuptools "package discovery"
  error. Declare `packages` + `package-data` explicitly (references/packaging-data-files.md).
- **Wheel omits data**: without `package-data`/`MANIFEST.in`, the `SKILL.md` corpus and vendored
  scripts are missing from the wheel → broken install. Verify with `zipfile` on the built wheel.
- **Tool-name collision across registries**: if core and skills both define `web_search`, the
  later `.update()` silently overwrites. Rename or be deliberate.

## Verification checklist
- `python3 -m py_compile` all modules → COMPILE_OK
- `python3 -m pytest tests/ -q` → green
- `pip install -e .` (in a venv; Kali is PEP 668) → builds & installs
- console command (e.g. `moon --unlock '/tools'`) lists the real tools
- `pip wheel .` → inspect with `zipfile` that `SKILL.md` + vendor scripts are present

## References
- references/model-fit-check.md — empirical local-model load verification + OOM failure mode
- references/packaging-data-files.md — pyproject snippet + wheel-content check
- references/skill-corpus-ingestion.md — turning an imported skill backup into tools + indexed KB
