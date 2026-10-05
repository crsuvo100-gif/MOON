"""Tests for the Session Manager implementation.

Covers creation, listing, attachment/detachment, renaming, and closing of
sessions. Uses the in‑memory manager; persistence is exercised via temporary
JSON file which is cleaned up after the test.
"""

import os
import json
import pytest
from app.terminal.session_manager import SessionManager, SESSION_STATE_FILE

@pytest.fixture(autouse=True)
def clean_state(tmp_path, monkeypatch):
    # Redirect persistence file to a temporary location
    temp_file = tmp_path / "sessions.json"
    monkeypatch.setattr("app.terminal.session_manager.SESSION_STATE_FILE", temp_file)
    yield
    # Ensure cleanup
    if temp_file.exists():
        temp_file.unlink()

def test_session_lifecycle():
    mgr = SessionManager(persist=True)
    sess = mgr.create_session(shell="bash")
    assert sess.shell == "bash"
    # List contains the new session
    assert any(s.session_id == sess.session_id for s in mgr.list_sessions())
    # Rename
    mgr.rename_session(sess.session_id, "mysession")
    assert mgr.get_session(sess.session_id).name == "mysession"
    # Detach and attach
    mgr.detach_session(sess.session_id)
    assert not mgr.get_session(sess.session_id).active
    mgr.attach_session(sess.session_id)
    assert mgr.get_session(sess.session_id).active
    # Close
    mgr.close_session(sess.session_id)
    assert mgr.get_session(sess.session_id) is None
