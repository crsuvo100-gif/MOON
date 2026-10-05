# Backend manager – resolves backend name to concrete implementation and executes.

from typing import Literal
from .models import ExecutionRequest, ExecutionResult
from .backends.local import LocalBackend
# future imports placeholder
from .backends.docker import DockerBackend
from .backends.ssh import SSHBackend

_BACKENDS = {
    "local": LocalBackend,
    "docker": DockerBackend,
    "ssh": SSHBackend,
}

class BackendManager:
    def __init__(self):
        self._instances = {}

    def get_backend(self, name: Literal["local", "docker", "ssh"]):
        """Return (and cache) a backend instance.
        
        The original code tried to call a non‑existent ``_get_backend`` helper.
        This implementation performs the lookup directly and raises a clear
        ``ValueError`` for unknown back‑ends.
        """
        if name not in _BACKENDS:
            raise ValueError(f"Unknown backend: {name}")
        if name not in self._instances:
            self._instances[name] = _BACKENDS[name]()
        return self._instances[name]

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        backend = self.get_backend(request.backend)
        return backend.execute(request)