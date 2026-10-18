# CYCLONE TERMINAL AI V10.0

A local-first, futuristic AI terminal with a generated female holographic assistant avatar. Built with vanilla HTML/CSS/JavaScript and a Node.js server; designed for editing in VS Code.

## Run in VS Code
1. Install Node.js 18+.
2. Open this folder in VS Code.
3. Run `npm start` in the integrated terminal.
4. Visit `http://127.0.0.1:8765/`.
5. Run `npm test` to execute server/API regression tests.

## V10 capabilities
- Female CYCLONE holographic avatar and upgraded responsive HUD.
- Skill registry: safe arithmetic calculator, unit conversions, JSON formatting/validation, Base64 encode/decode, SHA-256 hashing, UUID, slug creation, checklist builder, text summary, regex tester.
- Goal-to-task planning, task queue, local reminders, stopwatch and Pomodoro/focus timer.
- Workspace file explorer and text editor with explicit save confirmation and server-side path/extension/size checks.
- Browser speech input/output with preferred female voice where the browser offers one.
- Local memory, notes, command history, aliases, themes, settings and JSON session export.
- Safe project file listing/reading/search, health endpoint, rate limiting, security headers and optional server-side OpenAI-compatible chat completions.

## Example commands
`help`, `skills`, `skill slug Hello CYCLONE`, `calc (12+8)/4`, `convert 10 km to mi`, `json {"ok":true}`, `base64 encode hello`, `hash hello`, `uuid`, `plan Build a landing page`, `pomodoro 25`, `remind 30 stretch`, `stopwatch`, `files`, `edit README.md`, `search telemetry`, `remember preferred accent cyan`, `ask Explain this project`.

## Optional remote AI
Set `CYCLONE_AI_API_KEY`, and optionally `CYCLONE_AI_BASE_URL` and `CYCLONE_AI_MODEL`, in the server environment. Never put provider keys in browser files. Without a key, local responses are rule-based and utility skills work without a model.

## Safety boundaries
- The server binds to `127.0.0.1` by default.
- No arbitrary OS shell execution is exposed.
- File operations stay inside this project folder and deny sensitive paths.
- The editor permits only selected text/source extensions, caps writes at 64 KiB, and asks for user confirmation before overwrite.
- Telemetry visuals in the browser are illustrative; use `/api/health` for real server diagnostics.
- Voice recognition and a female voice depend on browser and OS support.


## V9 workflow features

- Multi-agent review: `agents <goal>` runs Planner, Architect, Implementer, and Reviewer specialist prompts. Without a configured API key, the result clearly identifies itself as local simulation.
- Provider configuration: `providers` opens server-side settings for OpenAI-compatible APIs, OpenRouter, or Ollama-compatible endpoints. API keys are never returned to the browser and runtime-entered keys are held in memory until server restart.
- Diff-aware editor: `edit <file>` lets you preview a change diff before explicitly approving a write. Every approved save creates a rollback snapshot for the current server session.
- Approval-gated workflows: `workflow <goal> | step one; step two` creates a staged workflow. Each step must be approved before it can start, and completion is tracked explicitly.
- New API endpoints: `/api/providers`, `/api/agents`, `/api/diff`, `/api/rollback`, and `/api/workflows`.

### Provider setup notes

Provider keys configured through the UI exist in server memory only and are cleared when the server restarts. For persistent deployment, set `CYCLONE_AI_API_KEY`, `CYCLONE_AI_BASE_URL`, `CYCLONE_AI_MODEL`, and optionally `CYCLONE_AI_PROVIDER` in your process environment. Keep the server bound to localhost unless you add authentication and TLS.

Workflow actions track and gate operator-approved steps; they do not execute arbitrary operating-system commands or autonomously alter files. The multi-agent endpoint produces advice, not automatic code changes. Rollback snapshots are held in memory and are available only while the server process remains alive.


## Bind external AI assistants (V9)

Run `npm start`, open the terminal, then enter `bindagents` (or `providers` → **BIND OTHER AI ASSISTANTS**). Bind Planner, Architect, Implementer, and Reviewer independently to an OpenAI-compatible `/chat/completions` endpoint such as OpenAI, OpenRouter, or a local Ollama server. Each role can use a different endpoint/model/key. Credentials are held in server memory only and are not returned to the browser; blank key fields preserve an existing role key. Disable a role's dedicated binding to make it inherit the primary provider. Run `agents <goal>` to route the goal to the configured specialist assistants. Agent output remains advisory and does not automatically modify files; use the diff editor and approval checkpoints for changes.


## V10 durability and interaction upgrade

- Durable local state stored outside the served project folder at `~/.cyclone-terminal-ai/state-v10.json` (Windows: under the current user's home directory). Override with `CYCLONE_DATA_DIR` for isolated profiles or backups.
- Workflow checkpoints, step status, timestamps, and a bounded audit trail persist across server restarts. Up to 100 workflows are retained.
- Approved editor saves retain up to 50 rollback snapshots across restarts. Rollback refuses to overwrite a file whose current content no longer matches the saved snapshot hash.
- External-agent binding metadata persists; API secrets are deliberately excluded from disk and must be re-entered after restart. Primary provider keys set in environment variables remain the recommended deployment method.
- New interactive controls: `workflows` browses saved workflow history and audit trails; `persistence` shows storage health, counts, and security posture. Both are available from the operator control deck and command palette.
- Improved keyboard focus, mobile workspace cards, scrollable audit details, and reduced-motion compatibility.

## V10 safety and durability notes

The data file is written atomically with restrictive file permissions where supported. This is a local single-user application, not a multi-user hardened service; keep it bound to localhost. Snapshots may contain source code, so protect the local user account and data directory. Persistent backups do not replace a version-control system.
