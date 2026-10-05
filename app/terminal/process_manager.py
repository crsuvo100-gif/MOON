"""Process manager for tracking background processes in MOON terminal.
Provides an in‑memory registry of running / completed processes.
"""

import os
import uuid
import signal
import subprocess
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from pydantic import BaseModel, Field
from .output_engine import OutputEngine

class ProcessInfo(BaseModel):
    execution_id: str = Field(..., description="Unique ID for this execution")
    pid: Optional[int] = Field(None, description="Process ID")
    command: str = Field(..., description="Command line string")
    cwd: Path = Field(..., description="Working directory when launched")
    backend: str = Field(..., description="Backend name, e.g., 'local'")
    status: str = Field(..., description="One of 'running', 'stopped', 'completed', 'failed', 'killed'")
    start_time: datetime = Field(default_factory=datetime.utcnow)
    duration: Optional[float] = Field(None, description="Seconds elapsed; set when finished")
    stdout: Optional[str] = Field(None)
    stderr: Optional[str] = Field(None)

class ProcessManager:
    """Singleton-like manager tracking background processes.
    Stored in a module‑level instance for easy import.
    """
    def __init__(self):
        # Mapping execution_id -> dict with 'proc' (Popen) and 'info' (ProcessInfo)
        self._registry: Dict[str, Dict] = {}

    def _finalize(self, execution_id: str):
        entry = self._registry.get(execution_id)
        if not entry:
            return
        proc: subprocess.Popen = entry['proc']
        info: ProcessInfo = entry['info']
        if proc.poll() is not None:
            # Capture output via OutputEngine (if not already captured)
            try:
                OutputEngine().capture(
                    execution_id,
                    stdout=proc.stdout.read() if proc.stdout else None,
                    stderr=proc.stderr.read() if proc.stderr else None,
                )
            except Exception:
                pass
            info.status = 'completed' if proc.returncode == 0 else 'failed'
            info.duration = (datetime.utcnow() - info.start_time).total_seconds()
            # Close pipes
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            entry['proc'] = None

    def start_process(self, request) -> str:
        """Start a background process based on an ExecutionRequest-like object.
        The ``request`` must have attributes: command (str), cwd (Path or None),
        env (Mapping[str, str] or None), shell (bool), timeout (int or None).
        Returns the generated execution_id.
        """
        execution_id = str(uuid.uuid4())
        cwd = request.cwd or Path.cwd()
        env = {**os.environ, **(request.env or {})}
        # Use subprocess.Popen for async execution
        proc = subprocess.Popen(
            request.command if request.shell else request.command.split(),
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=request.shell,
        )
        info = ProcessInfo(
            execution_id=execution_id,
            pid=proc.pid,
            command=request.command,
            cwd=Path(cwd),
            backend=getattr(request, 'backend', 'local'),
            status='running',
            start_time=datetime.utcnow(),
        )
        self._registry[execution_id] = {'proc': proc, 'info': info}
        return execution_id

    def list_processes(self) -> List[ProcessInfo]:
        # Update statuses before returning
        for eid in list(self._registry.keys()):
            entry = self._registry[eid]
            proc = entry['proc']
            if proc is not None and proc.poll() is not None:
                self._finalize(eid)
        return [entry['info'] for entry in self._registry.values()]

    def get_process(self, execution_id: str) -> Optional[ProcessInfo]:
        entry = self._registry.get(execution_id)
        if not entry:
            return None
        proc = entry['proc']
        if proc is not None and proc.poll() is not None:
            self._finalize(execution_id)
        return entry['info']

    def stop_process(self, execution_id: str) -> None:
        entry = self._registry.get(execution_id)
        if not entry or entry['proc'] is None:
            return
        proc: subprocess.Popen = entry['proc']
        try:
            proc.send_signal(signal.SIGSTOP)
            entry['info'].status = 'stopped'
        except Exception:
            pass

    def restart_process(self, execution_id: str) -> None:
        entry = self._registry.get(execution_id)
        if not entry or entry['proc'] is None:
            return
        proc: subprocess.Popen = entry['proc']
        try:
            proc.send_signal(signal.SIGCONT)
            entry['info'].status = 'running'
        except Exception:
            pass

    def kill_process(self, execution_id: str) -> None:
        entry = self._registry.get(execution_id)
        if not entry:
            return
        proc = entry['proc']
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
        # Force finalize as killed
        entry['info'].status = 'killed'
        entry['info'].duration = (datetime.utcnow() - entry['info'].start_time).total_seconds()
        entry['info'].pid = proc.pid if proc else None
        # Capture any output that may be available
        if proc and proc.stdout:
            try:
                entry['info'].stdout = proc.stdout.read()
            except Exception:
                pass
        if proc and proc.stderr:
            try:
                entry['info'].stderr = proc.stderr.read()
            except Exception:
                pass
        entry['proc'] = None

# Export a module‑level singleton for easy import elsewhere
process_manager = ProcessManager()
