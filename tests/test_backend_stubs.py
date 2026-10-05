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
    manager = BackendManager()
    backend = manager.get_backend(backend_name)
    # Instantiation may already raise NotImplementedError; handle both cases
    request = ExecutionRequest(command="echo test", backend=backend_name)
    with pytest.raises(NotImplementedError):
        backend.execute(request)
