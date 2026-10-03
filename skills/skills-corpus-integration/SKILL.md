---
name: skills-corpus-integration
description: "Index a Hermes skills backup into a runnable agent library."
category: software-development
---

# Skills Corpus Integration

Use when a user hands you a folder of skills (e.g. a Hermes backup of `SKILL.md`
files plus `scripts/`) and wants their agent to actually USE that knowledge — not just
sit on disk. This is the "import all my skills into the agent" task.

## When to use
- User says "gain/implement those skills", "make the agent use my skills backup",
  "import the skills folder", or points at a `*/skills` directory full of `SKILL.md`.
- You are building or extending an agent that should recall AND/OR execute skills.

## Build recipe (verified working — produced a 97-skill indexed library)
1. **Inventory first.** Count `SKILL.md` files, list categories, and split
   `scripts/*.py` into stdlib-only vs dependency-heavy. (Concrete shape in
   `references/build_recipe.md`.)
2. **Copy the knowledge base.** Mirror the `SKILL.md` tree into
   `<agent>/skills/sk_db/<category>/<skill>/SKILL.md`. Preserve the category/skill
   path so search results are namespaced (`research/arxiv`, `red-teaming/godmode`).
3. **Index with a `SkillCatalog`.** Parse each file's YAML-ish frontmatter
   (`name`, `description`), store the body for `/skill-view`, expose `search()`
   (token-overlap scoring) and `get(full_name)`.
4. **Vendor the runnable scripts.** Copy only scripts that need no exotic deps into
   `<agent>/skills/vendor/`. Wire them as tools that run the script via
   `subprocess` (real output, no hallucination). For scripts needing optional libs,
   lazy-`import` and return a clear "pip install X" message when missing.
5. **Add pure-Python skill tools** that need no external script: `humanize`
   (deterministic AI-ism strip), `ascii_banner` (pyfiglet with a box fallback),
   `plan` (write markdown to `.hermes/plans/`), `code_review` (ruff/pyflakes if
   present).
6. **Wire into runtime.** Merge the skill tools into the main registry:
   `self.tools._tools.update(build_skill_tools(...)._tools)`.
7. **Verify with REAL calls, not promises:**
   - `SkillCatalog().size()` == number of copied `SKILL.md` (97 in the reference run).
   - `/skill-search <topic>` returns a real `SKILL.md` snippet.
   - a vendored tool that hits a live API (arxiv `export.arxiv.org`,
     polymarket `gamma-api.polymarket.com`) returns real data — no key required.

## Pitfalls
- **Package/module name collision.** Adding a subpackage `skills/` beside an existing
  module `skills.py` makes `import parent.skills` resolve to the PACKAGE and breaks code
  expecting the module (`ImportError: cannot import name ...`). Audit the parent dir
  BEFORE creating a subpackage; delete or merge the stale `.py`. (Bit the Moon_AI_AGENT
  build: `moon_agent/skills.py` had to be removed when `moon_agent/skills/` arrived.)
- **Dependency-heavy scripts.** A 97-skill corpus can ship 44+ Python scripts, most
  needing torch / marker-pdf / pyfiglet / youtube-transcript-api. Do NOT `pip install`
  the world into the agent runtime. Copy only stdlib-capable scripts as live tools; for
  the rest, either index the `SKILL.md` as knowledge OR vendor + guard with an
  optional-dep check.
- **Newline-in-source corruption.** Composing Python source via `patch`/`write_file`
  that contains `"\n".join(...)` or f-strings with embedded `\n` can silently insert a
  LITERAL newline inside the quotes → `SyntaxError: unterminated string literal`. See
  `moon-ops` "Recurring pitfalls" for the fix. Always `py_compile` immediately.
- **Frontmatter arrays.** Some `SKILL.md` frontmatter has `tags: [a, b]`. Parse
  `key: [..]` as a list, not a string, or search/scoring degrades silently.
- **Broken `skills/` symlink masquerading as a populated corpus.** A `skills/`
  symlink that points to a machine-local path (e.g. `~/.hermes/skills`) looks
  populated on the dev host but resolves to nothing on a fresh `git clone`.
  The symptom: `SkillSystem().list_ids()` returns `[]` and the runtime-subsystems
  test fails with `assert 0 > 0`, while the knowledge-base indexer silently
  skips ("skills/ dir absent; skipping skills index") and never fails. **Always
  verify the corpus with `SkillSystem().list_ids()` on a path that will exist
  after clone — not with `ls skills/` on the dev machine.** The fix is to commit
  real `skills/*/SKILL.md` files, not a host-specific symlink. (Concrete example:
  MOON's `skills/` symlink pointed to `~/.hermes/skills` — removed, replaced with
  two real bundled skills in `skills/moon-operations/` and `skills/agent-management/`.)

## Files
- `references/build_recipe.md` — concrete `SkillCatalog` + `build_skill_tools` code
  shape, directory layout, and the working verification commands.

## Build-and-ship verification (don't trust "it built")
A corpus integration is only correct if the *installed* package actually contains the
knowledge. Common failure: `pyproject.toml` omits `package-data` / `MANIFEST.in`, so
`pip install` ships the code but **drops every `SKILL.md`** — the agent indexes nothing.
- Declare the data explicitly:
  ```toml
  [tool.setuptools]
  include-package-data = true
  packages = ["moon_agent", "moon_agent.tools", "moon_agent.skills", "moon_agent.skills.vendor"]
  [tool.setuptools.package-data]
  "moon_agent.skills" = ["sk_db/**/*.md", "vendor/*.py"]
  ```
  and `MANIFEST.in`: `recursive-include moon_agent/skills/sk_db *.md` (+ vendor scripts).
- **Prove the wheel ships the corpus** (zipfile count, not a promise):
  ```bash
  pip wheel . -w dist --no-deps --no-build-isolation
  python3 -c "import zipfile,glob; z=zipfile.ZipFile(sorted(glob.glob('dist/*.whl'))[-1]); \
    print('SKILL.md in wheel =', sum(1 for n in z.namelist() if 'sk_db' in n and n.endswith('SKILL.md')))"
  ```
  Must equal `SkillCatalog().size()` (97 in the reference run). If it's 0, the install is
  broken even though `pip install` reported success.
- On PEP 668 / Kali, build inside a venv: `python3 -m venv .venv && . .venv/bin/activate &&
  pip install -e . --no-deps`. The console command (`moon = "moon_agent.cli:main"`) then works.

## Wiring the brain for a corpus-backed agent
Integrating a skill corpus usually goes hand-in-hand with giving the agent a real "brain"
(LLM). The non-obvious pitfalls — local-model RAM cap, the qwen3 `/think` field quirk, the
remote-vs-local brain-model split, gitignored `.env` secrets, and PEP 668 packaging — are
documented in `local-ai-agent-engineering/references/local_brain_wiring.md`. Read that
before you set `Settings.model`/`brain_model`.
