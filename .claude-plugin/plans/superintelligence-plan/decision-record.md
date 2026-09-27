# Decision Record: Feature Selection for MOON Superintelligence Upgrade

**Date**: 2026-02-28  
**Status**: Accepted  
**Decider**: Agent (auto-generated via `plan` tool)

## Context

MOON agent v1.0 has a solid foundation:
- 8 specialized personas (general, code, security, research, voice, admin, creative, monitor)
- Intent-based agent routing
- 30+ tool schemas defined (but most are stubs/not wired)
- SQLite-backed session memory
- WebSocket + REST API on port 8778
- Rich TUI terminal

However, the pipeline is **stub-heavy**: `generate_response()` returns a canned string, most tool schemas lack real handlers, and there is no self-improvement loop.

## Options Considered

### Option A: Full tool implementation pass (≈20 tool handlers)
- Implement every tool schema as a real handler
- Pros: Comprehensive, each tool independently useful
- Cons: Scattergun; no unifying intelligence narrative; huge surface area

### Option B: Self-improvement pipeline (PLAN → REFLECT → SELF-EVOLUTION → EVIDENCE-HUB → SWARM)
- Implement the 5 advanced operational tools as a coordinated loop
- Add real LLM-backed `generate_response()` via Ollama
- Pros: Creates an actual "superintelligence" narrative; each piece reinforces the others; matches the persona/vision; smaller focused surface
- Cons: Depends on Ollama being available and models present

### Option C: Multi-agent swarm + council
- Add a council of agents that debate/vote on responses
- Pros: "Superintelligence" flavor; novel
- Cons: Requires multiple LLM calls per query (expensive); complex orchestration; less concrete value than B

### Option D: Streaming + voice upgrades
- WebSocket streaming responses; voice synthesis improvements
- Pros: UX polish
- Cons: Incremental, not "more advanced" in the intelligence sense

## Decision

**Selected: Option B — Self-improvement pipeline + real LLM backend.**

Rationale:
1. The 5 tools (plan, reflect, self_evolve, evidence_hub, spawn_swarm) already have schemas — they form a natural "think → act → learn → research → parallelize" loop.
2. Wiring a real Ollama-backed `generate_response()` is the single highest-leverage change: everything else (tool calls, persona injection, memory) becomes actually useful once responses come from a real model.
3. This creates a coherent upgrade story: "MOON now thinks before answering, critiques its own answers, learns from injected knowledge, researches across sources, and can parallelize work — all backed by a real local LLM."
4. Scope is bounded and testable: 5 tool handlers + 1 LLM integration + memory/context wiring.

## Implementation Plan (ordered)

1. **LLM integration** — `generate_response()` calls Ollama with persona system prompt + conversation history; returns real text.
2. **`plan` tool** — decomposes a goal into ordered steps (calls LLM with planning prompt).
3. **`reflect` tool** — critiques an answer given the original prompt (calls LLM with critique prompt).
4. **`self_evolve` tool** — ingests text from URL/file into a knowledge store (SQLite FTS or JSON), retrievable in later prompts.
5. **`evidence_hub` tool** — dispatches a query to multiple source tools (web_search, web_extract, memory_read, system_info, etc.), aggregates results.
6. **`spawn_swarm` tool** — runs N independent LLM queries in parallel (asyncio.gather), returns aggregated results.
7. **Context wiring** — inject knowledge base snippets + recent memory into the system prompt sent to Ollama.
8. **Terminal integration** — ensure `!ask`/chat flow uses the new generate_response; add `!plan`, `!reflect`, `!evolve`, `!research`, `!swarm` shortcuts if they fit the command scheme.

## Verification

- Unit test each tool handler in isolation with known inputs/outputs.
- Integration test: send a message through the terminal, confirm response comes from Ollama (not stub).
- Integration test: run `!plan`, `!reflect`, `!evolve`, `!research`, `!swarm` and confirm real outputs.
- End-to-end: `moon` terminal → chat → response backed by Ollama with persona injection visible.

## Fallback

If Ollama is unreachable or no models are present, implement `generate_response()` as a structured mock that echoes the persona + tools_used, and document the limitation clearly. The tool handlers (plan, reflect, etc.) can still be implemented to call a fallback heuristic.
