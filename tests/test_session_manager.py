"""Tests for the Session Manager implementation.

Covers creation, listing, attachment/detachment, renaming, and closing of
sessions. Uses the in‑memory manager; persistence is exercised via temporary
JSON file which is cleaned up after the test.
"""

import app.terminal.session_manager as sm_module
import os
import json
import pytest
from app.terminal.session_manager import SessionManager

@pytest.fixture(autouse=True)
def clean_state(tmp_path):
    # Redirect the module-level persistence path to a temp file. Setting the
    # module global directly (rather than monkeypatching a dotted name) avoids
    # pytest's derive_importpath resolution, which tries to resolve
    # 'app.terminal.session_manager.SESSION_STATE_FILE' onto the instance and
    # raises AttributeError. The SessionManager.__init__ reads the module
    # global at construction time, so swapping it here is picked up.
    global SESSION_STATE_FILE
    import app.terminal.session_manager as _sm
    SESSION_STATE_FILE = str(tmp_path / "sessions.json")
    _sm.SESSION_STATE_FILE = SESSION_STATE_FILE
    yield
    # Ensure cleanup
    if os.path.exists(SESSION_STATE_FILE):
        os.unlink(SESSION_STATE_FILE)
    # Restore the module global to its original value
    _sm.SESSION_STATE_FILE = ".moon_sessions.json"

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
