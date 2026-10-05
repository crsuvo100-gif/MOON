
"""Output Engine for buffering and streaming command output.
Provides:
- In‑memory buffering of stdout and stderr with a configurable max size.
- Persistent rotating log files under ``~/.hermes/cache/scratch/output_logs``.
- ``stream_output(execution_id, start_line=0, max_lines=200)`` API returning
  slices of the captured output.
"""

import os
import threading
from collections import deque
from pathlib import Path

# Configuration constants
MAX_BUFFER_SIZE = 5 * 1024 * 1024  # 5 MiB per execution buffer
MAX_LOG_FILES = 5  # keep up to 5 rotated logs per execution / stream
BASE_LOG_DIR = Path(os.getenv('HOME')) / '.hermes' / 'cache' / 'scratch' / 'output_logs'
BASE_LOG_DIR.mkdir(parents=True, exist_ok=True)

class OutputEngine:
    """Singleton handling output buffering and persistence."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()

        return cls._instance

    def _init(self):
        self.buffers = {}  # execution_id -> {'stdout': deque, 'stderr': deque, 'size': int}
        self.file_locks = {}

    def _ensure_entry(self, execution_id: str):
        if execution_id not in self.buffers:
            self.buffers[execution_id] = {'stdout': deque(), 'stderr': deque(), 'size': 0}
            self.file_locks[execution_id] = threading.Lock()

    def _rotate_if_needed(self, path: Path, extra_bytes: int):
        if path.exists() and path.stat().st_size + extra_bytes > MAX_BUFFER_SIZE:
            # rotate existing files: .4 -> .5, ..., .1 -> .2, current -> .1
            for i in range(MAX_LOG_FILES - 1, 0, -1):
                older = path.with_name(f"{path.name}.{i}")
                newer = path.with_name(f"{path.name}.{i+1}")
                if older.exists():
                    older.rename(newer)
            # current becomes .1
            path.rename(path.with_name(f"{path.name}.1"))

    def _write_to_file(self, execution_id: str, stream_name: str, data: str):
        base = BASE_LOG_DIR / f"{execution_id}_{stream_name}.log"
        lock = self.file_locks[execution_id]
        with lock:
            self._rotate_if_needed(base, len(data.encode()))
            with base.open('ab') as f:
                f.write(data.encode())

    def capture(self, execution_id: str, stdout: str | None = None, stderr: str | None = None):
        """Capture stdout / stderr fragments for an execution.
        Stores lines in an in‑memory deque and appends to rotating log files.
        """
        self._ensure_entry(execution_id)
        entry = self.buffers[execution_id]

        def _process(text: str, name: str):
            lines = text.splitlines(keepends=True)
            for line in lines:
                entry[name].append(line)
                entry['size'] += len(line.encode())
                # Trim oldest lines if buffer exceeds limit
                while entry['size'] > MAX_BUFFER_SIZE and entry[name]:
                    removed = entry[name].popleft()
                    entry['size'] -= len(removed.encode())
            self._write_to_file(execution_id, name, ''.join(lines))

        if stdout is not None:
            _process(stdout, 'stdout')
        if stderr is not None:
            _process(stderr, 'stderr')

    def stream_output(self, execution_id: str, start_line: int = 0, max_lines: int = 200):
        """Return a slice of the captured output.
        Result format: {"stdout": str, "stderr": str} where each value is a
        concatenated string of the selected lines.
        """
        self._ensure_entry(execution_id)
        out = {}
        for name in ('stdout', 'stderr'):
            lines = list(self.buffers[execution_id][name])
            if start_line >= len(lines):
                out[name] = ''
            else:
                slice_ = lines[start_line:start_line + max_lines]
                out[name] = ''.join(slice_)
        return out
