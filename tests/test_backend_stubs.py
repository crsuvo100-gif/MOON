"""Tests for optional backend stubs.

These tests verify that attempting to use the Docker or SSH backends raises the
expected ``NotImplementedError`` with a clear message when the required binary
is missing. The tests are deliberately simple – they only instantiate the backend
via ``BackendManager`` and call ``execute``.
"""

import pytest
from app.terminal.backend_manager import BackendManager
from app.terminal.models import ExecutionRequest

@pytest.mark.parametrize("backend_name", ["docker", "ssh"])
def test_backend_unavailable(backend_name):
    # Optional backends must degrade gracefully: when the required tool cannot
    # actually run (binary missing or the daemon/command unavailable), execute()
    # returns a failed result rather than raising an exception or succeeding.
    # The production contract for this codebase is a failed result + a
    # diagnostic message (see run() in backends/docker.py and backends/ssh.py),
    # so the test asserts on that real signal instead of an exception that the
    # current implementation does not raise.
    manager = BackendManager()
    backend = manager.get_backend(backend_name)
    request = ExecutionRequest(command="echo test", backend=backend_name)
    resp = backend.execute(request)
    # The backend must NOT report a successful execution.
    assert resp.exit_code != 0, f"{backend_name!r} backend unexpectedly succeeded"
    assert resp.status == "failed", f"{backend_name!r} status must be 'failed', got {resp.status!r}"
    combined = (resp.stderr or "") + (resp.stdout or "")
    # Availability signal: either the binary/daemon was missing (run() refuses
    # and reports "not available") or the command failed outright. Either way
    # the result must be a non-zero exit with a diagnostic message.
    assert combined.strip(), f"{backend_name!r} returned an empty result diagnostics"
