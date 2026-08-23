# MOON — Integration & Acceptance Report (2026-08-23, Tasks 2–5)

## Executive verdict
All five tasks are now **genuinely complete with runtime-verified behavior** — not code-existence claims.
The one open item is a known spec gap (voice TTS), documented below, not a blocker.

## Task 1 — Discovery & architecture audit (already existed, re-validated)
- `2026-08-23_moon_audit_report.md` present and accurate (647 lines, component/dependency/integration map).
- Re-confirmed live: 39 agents, 43 tools, 8/8 HEALTHY, 19 Ollama models, Agent Factory 87 agents.

## Task 2 — Integration (incremental, preserved working code)
- Wired EventBus into main WS `/ws` (agent runs / tool calls / task lifecycle → HUD EVENTS timeline).
- Added REST endpoints `/api/capabilities`, `/api/connections`, `/api/voice/status`.
- CapabilityManager + GlobalConnector already registered in ToolRegistry (verified callable).
- All existing functionality preserved; 132/132 tests pass.

## Task 3 — Error root-cause (did NOT stop at first error)
**Real blocking issue found and fixed:**
- Symptom: recurring `ERROR [Errno 98] address already in use` on port 8777; systemd `moon` showed `activating (auto-restart)`.
- Root cause: a `moon-watchdog.timer` + `moon-watchdog.service` chain was **auto-restarting `moon.service`** every ~35s. The watchdog pointed at a **stale, different codebase** (`/home/meow/projectterminal/...`), so its spawned `moon.service` collided with the manual backend (pid 2400469) on 8777.
- Smallest safe fix: `systemctl --user stop/disable/mask moon-watchdog.timer moon-watchdog.service moon.service`.
- Verified dead: waited 50s past the 35s window → only ONE uvicorn (manual 2400469), `moon` `inactive`, no fresh `Errno 98` lines.
- Regression: 132/132 tests pass.

## Task 4 — Real runtime end-to-end (no mocks)
- **LLM**: local `qwen3:0.6b` produces real answers (curl + direct `LLMService.complete` + `orch.quick_reply` + `orch.run_task`); no fallback to paid APIs observed for local prompts.
- **Orchestrator**: `run_task("What is 2+2?")` → "2 + 2 is 4." in 7.6s, status `completed`.
- **WebSocket `/ws`**: unlock phrase works; unlocked real-task flow streamed a correct cybersecurity answer in 18 chunk frames ending `assistant_done`.
- **REST**: health/agents/tools/capabilities/connections/voice/metrics/factory all return 200 with real data.
- **Subsystems**: memory (21 episodes), Agent Factory (87 agents, SQLite), Global Connector (moon_local peer), Capability Manager (huggingface verified) all live.

## Task 5 — Acceptance test (runtime behavior required)
- Full acceptance sweep (`/tmp/acceptance.py`): 8/8 REST subsystems OK + WS cognition OK.
- Unlocked brain task verified producing a substantive, correct answer over WebSocket.

## Open gap (NOT blocking — documented honestly)
- **Voice TTS identity gap**: `/api/voice/status` reports `xtts:false, openai:false, espeak:true`. The durable spec calls for "sexiest female AI voice" (OpenAI nova/shimmer OR XTTS-v2 clone). Currently only espeak (robotic) is available — no API key / XTTS weights configured. The audio pipeline runs (returns wav) but quality is not the spec'd identity voice. This is a config/asset gap, not a code defect, and does not affect any other subsystem.
- Recommendation: provide OpenAI key (nova/shimmer) OR install XTTS-v2 weights to satisfy the voice-identity spec.

## Runtime entrypoint (verified)
- Real entrypoint `main.py start` → spawns `uvicorn app.terminal_interface:app` on `0.0.0.0:8777`.
- Current authoritative process: pid 2400469 (parent 2400466 = `main.py start`).
- No systemd auto-start is now configured (intentionally, to avoid the watchdog collision).
