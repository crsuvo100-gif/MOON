"""SSH backend stub.
Implements the same interface as LocalBackend but raises NotImplementedError
when the required ``ssh`` binary is not available.
"""

from ..models import ExecutionRequest, ExecutionResult
import shutil

class SSHBackend:
    def __init__(self):
        if not shutil.which('ssh'):
            self.available = False
        else:
            self.available = True

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise NotImplementedError(
            "SSH backend is not implemented – missing required binary or functionality"
        )
