# REPRODUCE / DIAGNOSE DIAGNOSTIC — MOON
# Directive: DISCOVER -> MAP -> UNDERSTAND -> AUDIT -> REPRODUCE -> DIAGNOSE
# Recorded: 2026-10-16 (main session, live execution)

## 1. REPRODUCTION (real execution, not assumption)
- Command:  cd /home/meow/Projects/MOON && .venv/bin/python -m pytest tests/integration tests/test_mcp_real tests/runtime/test_gap_closures.py tests/runtime/test_registry_factory.py tests/runtime/test_spec_subsystems.py tests/runtime/test_runtime_subsystems.py tests/regression tests/security -q
- Result: PYTEST_EXIT=1 (FAILED)
- Failure: tests/test_mcp_real/test_stdio_connector_real.py::test_stdio_connector_real
- Failure message: "MCP stdio connect failed: unhandled errors in a TaskGroup"
- Concrete trace:
    - MCPConnector.connect() -> stdio transport -> mcp.client.stdio.stdio_client(server)
    - stdio_client internally manages the spawned server subprocess + stdio streams
      inside an asyncio.TaskGroup.
    - The test then kills the spawned subprocess (proc.kill()) in its finally block
      while the connector is still connected; stdio_client's TaskGroup is left with
      an unreaped/subprocess-exit error, surfacing as "unhandled errors in a TaskGroup".

## 2. AFFECTED COMPONENT
- File: app/connector/connectors.py, class MCPConnector, stdio transport branch
  (lines ~186-205). Relies on mcp.client.stdio.stdio_client() (external MCP SDK),
  which uses an asyncio.TaskGroup to drive the child process and the read/write
  streams. No local guard exists for a mid-connection subprocess kill.
- Test: tests/test_mcp_real/test_stdio_connector_real.py (spawn stdio_server.py,
  round-trip initialize -> list_tools -> call_tool("echo",...)).

## 3. ROOT CAUSE
- stdio_client's TaskGroup does not properly await/clean up the subprocess-exit
  error when the server is killed from the outside (test finally block). The error
  is reported as "unhandled errors in a TaskGroup" and propagates as a hard
  AssertionError in connect(), before any MCP protocol round trip can happen.
- This is a real stdio-MCP transport defect (not a flaky test): the connector's
  subprocess lifecycle is not cleaned up safely when external kill occurs.

## 4. EXPECTED vs ACTUAL
- Expected: connect -> list_tools -> call_tool("echo",{"msg":"..."}),
  round trip succeeds (the stdio_server.py is a real working JSONRPC-over-stdin
  server implementing init/list_tools/call).
- Actual: connect() raises "unhandled errors in a TaskGroup" (AssertionError),
  blocking the entire round trip.

## 5. FIX STRATEGY (DEFERRED to REPAIR/IMPLEMENT phase — baseline locked)
- Do NOT touch the test baseline now (locked: 791 collected; full-run exit 1 =
  7 failed + 1 short, all slow integration/real-MCP).
- Planned repair: wrap stdio_client's connect in a safe subprocess lifecycle
  guard (TaskGroup cleanup on external kill), or fail fast with a clean
  CallResult instead of propagating a TaskGroup error through connect().
- Scope check: this is a genuine capability gap in the stdio-MCP outbound bridge;
  fixing it touches app/connector/connectors.py only, and must preserve the
  existing behaviour for the healthy path.

## 6. EVIDENCE
- Diagnostic driven by real test output (PYTEST_EXIT=1, failure trace above).
- Restored working-tree state not modified by this diagnostic run.
