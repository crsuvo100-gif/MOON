"""Docker backend stub.
Implements the same interface as LocalBackend but raises NotImplementedError
when the required ``docker`` binary is not available. This allows the
system to register the backend without providing full functionality.
"""

from ..models import ExecutionRequest, ExecutionResult
import shutil

class DockerBackend:
    def __init__(self):
        # Check for docker binary; we only care about existence for the stub.
        if not shutil.which('docker'):
            self.available = False
        else:
            self.available = True

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise NotImplementedError(
            "Docker backend is not implemented – missing required binary or functionality"
        )
