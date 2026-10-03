# MOON Superintelligence Plan — Phase 1

**Date**: 2026-02-28  
**Scope**: Self-improvement pipeline + real LLM backend  
**Status**: In progress

## Goals

1. Replace stub `generate_response()` with real Ollama-backed LLM calls.
2. Implement 5 advanced operational tools as a coordinated self-improvement loop.
3. Wire knowledge base + memory into the LLM system prompt.
4. Add terminal commands for the new capabilities.

## Implementation Order

### Step 1: LLM Integration (generate_response)
- [ ] Read Ollama client from `agent/llm.py`
- [ ] In `generate_response()`, call Ollama with persona system prompt + conversation history
- [ ] Return real text from model
- [ ] Handle model not found / Ollama down gracefully

### Step 2: plan tool
- [ ] Implement `_tool_plan(args)` — calls LLM with planning prompt, returns structured steps
- [ ] Register in tool registry

### Step 3: reflect tool
- [ ] Implement `_tool_reflect(args)` — calls LLM with critique prompt, returns critique
- [ ] Register in tool registry

### Step 4: self_evolve tool
- [ ] Implement `_tool_self_evolve(args)` — ingests text from URL/file into knowledge store
- [ ] Use SQLite FTS or JSON file as knowledge base
- [ ] Register in tool registry

### Step 5: evidence_hub tool
- [ ] Implement `_tool_evidence_hub(args)` — dispatches to multiple source tools, aggregates
- [ ] Register in tool registry

### Step 6: spawn_swarm tool
- [ ] Implement `_tool_spawn_swarm(args)` — parallel LLM queries via asyncio.gather
- [ ] Register in tool registry

### Step 7: Context wiring
- [ ] Inject knowledge base snippets into system prompt
- [ ] Inject recent memory entries into context
- [ ] Test that injected context influences responses

### Step 8: Terminal commands
- [ ] Add `!plan`, `!reflect`, `!evolve`, `!research`, `!swarm` commands if appropriate
- [ ] Ensure `!ask`/chat uses new generate_response
- [ ] Test end-to-end in terminal

## Verification Gates

- [ ] `generate_response()` returns text from Ollama (not stub) — test with known prompt
- [ ] `plan` tool returns structured steps for a sample goal
- [ ] `reflect` tool returns critique for a sample Q&A pair
- [ ] `self_evolve` tool ingests text and it appears in later context
- [ ] `evidence_hub` tool returns aggregated results from multiple sources
- [ ] `spawn_swarm` tool returns parallel results
- [ ] End-to-end: `moon` terminal chat → real Ollama response with persona
- [ ] All existing tests still pass

## Notes

- Ollama base URL: http://127.0.0.1:11434 (default)
- Default model: llama3.2 (configurable)
- If Ollama unreachable: fallback to structured mock, document limitation
- Knowledge base storage: SQLite FTS table or JSON file in MOON data dir
