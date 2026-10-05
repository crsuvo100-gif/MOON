"""Session model for MOON terminal.

Each session tracks its own working directory, environment, backend, and PTY state.
"""

import uuid
from pathlib import Path
from typing import Optional, Dict
from .models import ExecutionRequest

class Session:
    def __init__(self, backend: str = "local", cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None, shell: str = "sh"):
        self.session_id: str = str(uuid.uuid4())
        self.backend = backend
        self.cwd = cwd or Path.cwd()
        self.env = env or {}
        self.shell = shell  # e.g., "bash", "zsh", "sh"
        self.name: str = ""  # user‑friendly name
        self.created_at = None  # could be datetime
        self.last_activity = None
        self.active = True
        # PTY placeholder – not implemented yet
        self.pty = None

    def update_activity(self):
        from datetime import datetime
        self.last_activity = datetime.utcnow()
