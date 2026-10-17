# PLAN — REPAIR / IMPLEMENT (directive step PLAN)
# Directive: DISCOVER -> MAP -> UNDERSTAND -> AUDIT -> REPRODUCE -> DIAGNOSE -> PLAN -> REPAIR -> IMPLEMENT
# Recorded: 2026-10-16
# Status: plan drafted (details at doc/repro_diagnose_20261016.md)

## 1. Scope of work
- Fix the stdio-MCP connector's subprocess-lifecycle defect in
  app/connector/connectors.py (class MCPConnector, stdio transport branch).
- Do NOT modify the test baseline (locked: 791 collected; full-run exit 1 =
  7 failed + 1 short, all slow integration/real-MCP).

## 2. Root cause (confirmed in real code)
- stdio_client (mcp.client.stdio in the MCP SDK) drives the spawned server
  subprocess + stdio streams inside an asyncio.TaskGroup.
- When the spawned server is killed mid-connect (test finally block), the
  TaskGroup teardown raises "unhandled errors in a TaskGroup", which propagates
  out of connect() as a hard AssertionError, masking the successful connection.

## 3. Fix strategy
- In the stdio connect branch, catch the teardown TaskGroup error.
- If the connection was genuinely established (session bound + read/write
  streams available), return CallResult(ok=True) instead of failing the
  connection on the benign teardown error.
- If the connection genuinely failed (session/streams not bound), clear state
  and return CallResult(ok=False) with the original error.

## 4. Verification gates
- REPRODUCT: re-run tests/test_mcp_real (and the reproduction subset) -> expect
  zero failures in that subset.
- REGRESSION: full suite -> expect baseline locked (791 collected; exit 1 =
  7 failed + 1 short, unchanged).
- INTEGRATE: connector round-trip (list_tools -> call_tool("echo",...)) on real
  stdio server returns ok=True.

## 5. Non-negotiable principles applied
- EVIDENCE: fix driven by reproduced test failure + real code trace.
- REAL IMPLEMENTATION: patch is real code in app/connector/connectors.py, no
  mocks, no placeholders.
- PRESERVE WORKING FUNCTIONALITY: healthy-path behavior unchanged; only the
  teardown-error path is modified.
- ROOT CAUSE: fix addresses the TaskGroup teardown error, not symptoms.
- NO FALSE COMPLETION: every gate verified with real test output.
