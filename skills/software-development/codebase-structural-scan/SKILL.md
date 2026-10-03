---
name: codebase-structural-scan
description: "Scan codebase structure: weight, trees, borders."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [codebase, structural, architecture, disk-weight, boundaries, file-tree, LOC]
    related_skills: [codebase-inspection]
prerequisites: []
---

# Codebase Structural Scan

Deep structural inspection of a codebase beyond simple LOC counts. Produces a layered picture: version/identity, disk weight breakdown, file and line counts, full directory tree, subsystem deep dives, and boundary interfaces.

## When to Use

- User asks for "terminal length, weight, border" or "full terminal of X info"
- User wants a deep architectural picture of a codebase or subsystem, not just metrics
- User asks "how big is this" and means structurally, not just line count
- User wants to understand subsystem boundaries, interfaces, and weight distribution
- User is evaluating a codebase for integration, migration, or build rationale
- User wants to feed structural info into another project's build reasoning

## Relationship to codebase-inspection

`codebase-inspection` covers pygount-based LOC/language/ratio metrics. This skill covers everything pygount does NOT: disk weight, file trees, per-module line counts, subsystem boundary analysis, and full file enumeration. Use both together for a complete picture.

## Phase 1: Identity & Version

Identify what you're scanning:

```bash
# If it's a git repo
cd /path/to/repo && git log --oneline -3 && git describe --tags 2>/dev/null

# If it's an installed tool
which <command> && <command> --version 2>/dev/null

# Find the actual install location
ls -la ~/.local/bin/<command> 2>/dev/null
python3 -c "import <module>; print(<module>.__file__)" 2>/dev/null
pip show <package> 2>/dev/null

# Find all copies on disk
find /home -maxdepth 4 -name "<repo-name>" -type d 2>/dev/null | head -10
```

## Phase 2: Disk Weight Breakdown

```bash
# Total install size
du -sh /path/to/repo

# Sans vendor (venv, node_modules, .git, __pycache__)
du -sh --exclude='venv' --exclude='node_modules' --exclude='.git' \
       --exclude='__pycache__' --exclude='tests-js' /path/to/repo

# Per-subdir breakdown (top N)
du -sh --exclude='venv' --exclude='node_modules' --exclude='.git' \
       --exclude='__pycache__' /path/to/repo/* 2>/dev/null | sort -rh | head -15

# Individual heavy dirs
du -sh /path/to/repo/venv /path/to/repo/node_modules /path/to/repo/.git
```

## Phase 3: File & Line Counts

```bash
# Total non-vendor files (code + data + docs)
find /path/to/repo -not -path "*/venv/*" -not -path "*/node_modules/*" \
     -not -path "*/.git/*" -type f | wc -l

# Python source lines only (sans vendor)
find /path/to/repo -name "*.py" -not -path "*/venv/*" -not -path "*/node_modules/*" \
     -not -path "*/.git/*" -not -path "*/__pycache__/*" \
     -exec wc -l {} + 2>/dev/null | tail -1

# All source lines (py/js/ts/md/yaml/json/css/html/rs/...)
find /path/to/repo -type f -not -path "*/venv/*" -not -path "*/node_modules/*" \
     -not -path "*/.git/*" -not -path "*/__pycache__/*" \
     -not -path "*/tests-js/*" -exec wc -l {} + 2>/dev/null | tail -1

# By-language breakdown (source files only)
find /path/to/repo -type f -not -path "*/venv/*" -not -path "*/node_modules/*" \
     -not -path "*/.git/*" -not -path "*/__pycache__/*" \
     -not -path "*/tests-js/*" -not -path "*/assets/*" \
     | sed 's/.*\.//' | sort | uniq -c | sort -rn

# Python line count by directory (top N)
find /path/to/repo -name "*.py" -not -path "*/venv/*" -not -path "*/node_modules/*" \
     -not -path "*/.git/*" -not -path "*/__pycache__/*" \
     -not -path "*/tests-js/*" -exec dirname {} \; | sort | uniq -c | sort -rn | head -15
```

## Phase 4: Full File Tree

```bash
# List all source files (sans vendor), sorted
find /path/to/repo -not -path "*/cache/*" -not -path "*/__pycache__/*" \
     -not -path "*/.git/*" -not -path "*/node_modules/*" -type f | sort

# For very large trees, filter to specific extensions
find /path/to/repo -not -path "*/venv/*" -not -path "*/node_modules/*" \
     -not -path "*/.git/*" -type f \( -name "*.py" -o -name "*.js" -o -name "*.ts" \) | sort
```

## Phase 5: Subsystem Deep Dives

When the user asks about a specific subsystem or module:

```bash
# Find all files mentioning a keyword
find /path/to/repo -name "*.py" -not -path "*/venv/*" -not -path "*/node_modules/*" \
     -not -path "*/.git/*" -type f | xargs grep -l -i "<keyword>" 2>/dev/null \
     | grep -v __pycache__ | sort

# Read key files (head + tail as needed)
# Use read_file with limit/offset for large files
read_file(path="/path/to/repo/path/to/key_file.py", limit=120)

# For the top-level entrypoints, read first 60-80 lines to understand structure
head -80 /path/to/repo/run_agent.py
head -80 /path/to/repo/cli.py
```

## Phase 6: Boundary/Interface Analysis ("Border")

Identify where subsystems meet — these are the interfaces that define the system's architecture:

- **Tool registry** (`tools/registry.py`) — border between tools and agent loop
- **Agent entrypoint** (`run_agent.py`, `cli.py`) — border between model/user and tools
- **Command registry** (`hermes_cli/commands.py`, `app/cli/commands.py`) — border between user input and dispatch
- **Gateway + platforms/** — border between external messaging apps and agent
- **Config files** (`config.yaml`, `.env`) — border between user configuration and internals
- **Environment backends** (`tools/environments/`) — border between execution contexts
- **Web server routers** (`web_routers/`, `web_server.py`) — border between HTTP API and internals
- **Tool handler signatures** — each tool's `check_fn`, `requires_env`, and handler signature define its contract

For each boundary, identify:
1. What files define it
2. What data/protocol crosses it
3. What environment variables or config keys gate it
4. What the interface contract looks like (function signatures, message schemas)

## Phase 7: Assembly & Output

Present the scan as a structured report:

1. **Identity** — version, install location, entry points, runtime
2. **Disk weight** — total, per major directory, vendor breakdown
3. **File/line counts** — total files, Python lines, all-source lines, by-language, by-directory
4. **Architecture tree** — top-level directory layout with descriptions
5. **Subsystem deep dives** — for each subsystem the user cares about: file count, line count, key files, what it does
6. **Boundaries/interfaces** — where subsystems meet, what crosses the borders
7. **Lessons** — actionable takeaways for the consuming project (patterns to adopt, interfaces to mimic, pitfalls to avoid)

Keep each section tight. The user wants the picture, not a narrative.

## Phase 8: Insight Compilation (Optional)

When the user asks for "deep analysis", "whole-project insight", "compile the project", or "make as a professional AI assistant agent" — go beyond structural metrics to compile a comprehensive insight document covering capabilities, components, and architecture.

### Trigger

- User says "deeply analyze my project", "compile whole project insight", "understanding my whole project and its components"
- User wants capabilities, skills, functions, programs mapped — not just metrics
- User says "make as a professional AI assistant agent" — implies understanding the whole system
- User wants to know what the system CAN DO, not just how big it is

### Procedure

1. **Enumerate all source files** — `find` with vendor exclusions (`.git`, `venv`, `__pycache__`, `node_modules`), `wc -l` per file for line counts
2. **Read every module fully** — `read_file` with `offset`/`limit` for large files; chunk reads for files >2000 lines; do not skip any major module
3. **Map component categories**:
   - Core engine (agent loop, tool execution, persona/agent system, intent routing)
   - Tool inventory (all `_tool_*` definitions, registration block, persona tool wiring)
   - Memory systems (storage backends, semantic search, knowledge base injection)
   - Orchestration (plan-and-execute, swarm, auto-agent, agent handoff)
   - Interfaces (REST API endpoints, CLI, TUI, entry points)
   - Capabilities by domain (cyber/red-team, research, code generation, data/file, system/infra, etc.)
4. **Compile insight document** — structured markdown with sections per category; tables for tool listings; bullet lists for capabilities; ~500-700 lines for a project of this scale
5. **Verify coverage** — every major component has a section; tool counts match registrations; no fabricated capabilities

### Pitfalls

- **Reading without a map** — enumerate files first with `find`, then read; don't guess which modules matter
- **Chunk-read large files** — use `read_file` `offset`/`limit`; files >2000 lines need multiple reads to avoid truncation
- **Metrics ≠ insight** — LOC counts tell you size; insight compilation tells you what the system CAN DO. Don't stop at structural scan when the user asks for "insight" or "capabilities"
- **Fabricating capabilities** — read the actual `_tool_*` definitions before claiming what a tool does; every claimed capability must be backed by source code
- **One monolithic file** — prefer sectioned markdown with tables and lists over a single wall of text; tables for tool inventories, bullets for capability lists
- **Skipping integration artifacts** — when the project has recent merges (e.g. Hermes tool wrappers in a separate file), read those files too; they carry capabilities not visible in the core modules

## Phase 9: Programmatic Structural Verification (cross-wiring + compile check)

When the user asks to "confirm all folders/subfolders are wired one-to-one" or "make a program to verify the project compiles and all parts connect to the main brain" — build a single deterministic Python script (no LLM calls) that scans the project tree, extracts every definition, maps cross-package imports by AST analysis, checks `python3 -m py_compile` on every `.py`, and hits the live service health endpoint. Save output as JSON for both human reading and machine re-check.

### Procedure

1. **Tree scan** — `find` with vendor exclusions (`.git`, `venv`, `__pycache__`, `node_modules`), dump full tree (dirs + files) to a JSON field. Report top-level directories with per-directory file counts.
2. **Definition extraction** — `ast.walk` every `.py` (vendor-excluded), collect every `ast.FunctionDef`, `ast.AsyncFunctionDef`, `ast.ClassDef` name+file. Count total definitions; flag duplicate names (same name in 2+ files). Categorize duplicates: *expected* (install utilities copied across scripts, e.g. `make_venv`, `verify_install`, `ensure_env`) vs *structural* (same class/function defined in two packages — the main wiring signal).
3. **Cross-package wiring** — for each top-level package (e.g. `Moon_Twin/`, `app/`, `terminal_moon/`), parse imports with `ast.walk` looking for `ast.Import`/`ast.ImportFrom` whose module path starts with another top-level package name. Report per-pair import counts. A zero count between two co-resident top-level packages is a silo signal, not a passing grade.
4. **Compile check** — `python3 -m py_compile` each `.py` (vendor-excluded). Report files_checked and failures. A clean compile is necessary but NOT sufficient — it does not prove wiring.
5. **Live service check** — `requests.get` the health endpoint (e.g. `http://127.0.0.1:8778/api/health`); parse JSON; report status, agent_count, lock_state. This proves the main brain actually boots, which static analysis cannot.
6. **Save JSON** — write to `<project_root>/MOON_STRUCTURAL_VERIFICATION_REPORT.json` (or the project's equivalent artifact name). Keep the script re-runnable: `python3 verify_structural.py` with no arguments.
7. **Summarize for the user** — top-level: dirs, files, modules, definitions, duplicates (split expected vs structural), missing imports, compile result, live health. Then the wiring matrix (which package imports which). Then the actionable finding: which silo gap to close first.

### MOON-specific wiring finding (apply when scanning MOON)

MOON has three co-resident top-level Python packages that should form one brain:

- **`app/`** — the main brain: orchestrator, planner, reasoning, self-improvement, tool-manager, memory-manager, intent-detector, context-builder, all tools, all memory subsystems, agent factory. **Fully wired internally** — every `app/X/` subfolder imports from `app` and from sibling `app/` folders.
- **`Moon_Twin/`** — the live `:8778` service package (agent/api.py, engine.py, llm.py, memory.py, tools_pro.py, swarm.py…). **SILOED**: `Moon_Twin/agent/` has its own parallel implementations of agent/memory/tool logic that never import `app`. `Moon_Twin/main.py` imports `app`, but the agent layer does not. Cross-import count between `Moon_Twin` and `app` is **zero in both directions**.
- **`terminal_moon/`** — second service package. Imports `app` (43 imports) but `app` does not import back.

**The main gap**: `Moon_Twin/agent/api.py` and `engine.py` should import tools, memory, and brain components from `app/` rather than maintaining parallel implementations. Closing that one-direction gap wires the live `:8778` service to the main brain.

### Pitfalls

- **Compile clean ≠ wired** — `py_compile` passing with zero cross-imports between co-resident packages is a false positive. Always report the cross-import matrix alongside the compile result.
- **Don't report install-utility duplicates as a problem** — `make_venv`, `verify_install`, `check_python`, `install_service`, `ensure_env`, `ollama_up` appearing in both `install_moon.py` and `install_moon_full.py` (and launcher scripts) is expected duplication of bootstrap helpers, not a wiring defect. Classify before reporting.
- **`main.py` imports are misleading** — a top-level `main.py` that imports `app` does NOT mean the agent layer (api.py, engine.py) is wired. Check the agent layer specifically.
- **Shared file paths = 0 is a finding, not a neutral result** — when two packages have zero shared file paths and zero cross-imports, they are independent silos. Report it as the actionable gap.
- **Health endpoint_json is the ground truth for "does it boot"** — static analysis cannot tell you whether the live service starts. Always hit the health endpoint and parse the JSON; a healthy service with agent_count > 0 is the real accept criterion.

### References

- `references/structural_verification_program.py` — reusable template for the verification script (tree scan + AST definition extraction + cross-import matrix + py_compile + live health check, JSON output).

1. **Don't stop at pygount** — LOC counts tell you size, not structure. The user asking for "length, weight, border" wants architecture, not a number.
2. **Exclude vendor dirs everywhere** — venv, node_modules, .git, __pycache__, tests-js all skew counts massively. Always exclude.
3. **Read entrypoints first** — `head -80` on `run_agent.py`, `cli.py`, `main.py` gives you the structural skeleton before reading deep files.
4. **grep -l before read_file** — find which files touch a topic before reading any of them.
5. **Large trees need filtering** — don't dump 10,000 file paths to the user; filter to the extensions and directories that matter.
6. **Disk weight != source weight** — a 4 GB install may be 500 MB of actual source. Always report both.
7. **"Border" is an interface concept** — don't just list directories; identify the actual interfaces (registries, env vars, config keys, message schemas) that connect subsystems.

## References

- `references/hermes-agent-scan.md` — full structural scan of Hermes Agent v0.20.6 (terminal subsystem focus, 4.1 GB install, 351K Python lines across 4,776 .py files). Includes terminal tool internals (tools/terminal_tool.py, 4,213 lines), CLI/TUI architecture (prompt_toolkit + CommandDef registry), agent core (run_agent.py + agent/ 154 files), messaging gateway (151 files, ~20 platforms), web server (FastAPI, port 9119), Electron desktop (746 files, 415 MB), config/state layout, and 10 lessons for consuming projects.
- Hermes Desktop delivery: when pushing structural scan data to a running Hermes Desktop Electron app (PID found via `pgrep -fa hermes`), write reference files to `~/.hermes/desktop/` — the Electron app has host FS access and can read them. Direct WebSocket push to `ws://127.0.0.1:{port}/api/ws` rejects external connections (HTTP 403) without the Electron app's session cookie context (`Sec-WebSocket-Protocol: websocket-subprotocol-ticket` + session token from `window.__HERMES_SESSION_TOKEN__`). The desktop renderer communicates via the Electron main process IPC bridge, not raw WS from outside. Files on the host filesystem is the correct delivery mechanism.
