"""Session manager for MOON terminal.

Provides in‑memory tracking of terminal sessions and optional JSON persistence.
"""

import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from .models import ExecutionRequest

SESSION_STATE_FILE = Path(".moon_sessions.json")

class Session:
    def __init__(self, shell: str = "sh", cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None):
        self.session_id: str = str(uuid.uuid4())
        self.shell = shell
        self.cwd = cwd or Path.cwd()
        self.env = env or {}
        self.name: str = ""
        self.created_at = None
        self.last_activity = None
        self.active = True
        # placeholder for PTY state
        self.pty = None

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "shell": self.shell,
            "cwd": str(self.cwd),
            "env": self.env,
            "name": self.name,
            "active": self.active,
        }

class SessionManager:
    def __init__(self, persist: bool = True):
        self._sessions: Dict[str, Session] = {}
        self.persist = persist
        if self.persist and SESSION_STATE_FILE.exists():
            try:
                data = json.loads(SESSION_STATE_FILE.read_text())
                for sid, sdata in data.items():
                    sess = Session(shell=sdata.get("shell", "sh"), cwd=Path(sdata.get("cwd", ".")), env=sdata.get("env", {}))
                    sess.session_id = sid
                    sess.name = sdata.get("name", "")
                    sess.active = sdata.get("active", True)
                    self._sessions[sid] = sess
            except Exception:
                pass

    def _save(self):
        if not self.persist:
            return
        data = {sid: sess.to_dict() for sid, sess in self._sessions.items()}
        SESSION_STATE_FILE.write_text(json.dumps(data, indent=2))

    def create_session(self, shell: str = "sh", cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> Session:
        sess = Session(shell=shell, cwd=cwd, env=env)
        self._sessions[sess.session_id] = sess
        self._save()
        return sess

    def list_sessions(self) -> List[Session]:
        return list(self._sessions.values())

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def attach_session(self, session_id: str) -> Session:
        sess = self.get_session(session_id)
        if sess:
            sess.active = True
            self._save()
            return sess
        raise KeyError(f"Session {session_id} not found")

    def detach_session(self, session_id: str) -> None:
        sess = self.get_session(session_id)
        if sess:
            sess.active = False
            self._save()
            return
        raise KeyError(f"Session {session_id} not found")

    def rename_session(self, session_id: str, new_name: str) -> None:
        sess = self.get_session(session_id)
        if sess:
            sess.name = new_name
            self._save()
            return
        raise KeyError(f"Session {session_id} not found")

    def close_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]
            self._save()
            return
        raise KeyError(f"Session {session_id} not found")
