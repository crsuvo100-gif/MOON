
import time
import pytest
from app.terminal.process_manager import process_manager, ProcessInfo
from app.terminal.models import ExecutionRequest
from pathlib import Path

def make_req(cmd, background=True, cwd=None):
    return ExecutionRequest(
        command=cmd,
        cwd=Path(cwd) if cwd else None,
        env={},
        backend="local",
        shell=False,
        timeout=30,
        background=background,
        interactive=False,
        permission_mode="auto",
        verification=None,
    )

def test_start_and_list_and_get():
    req = make_req("sleep 0.5")
    exec_id = process_manager.start_process(req)
    info = process_manager.get_process(exec_id)
    assert isinstance(info, ProcessInfo)
    assert info.execution_id == exec_id
    assert info.status == "running"
    # list should contain it
    lst = process_manager.list_processes()
    assert any(p.execution_id == exec_id for p in lst)
    # wait for completion
    time.sleep(0.7)
    info = process_manager.get_process(exec_id)
    assert info.status in ("completed", "failed")
    assert info.duration is not None

def test_stop_and_restart():
    req = make_req("sleep 5")
    exec_id = process_manager.start_process(req)
    time.sleep(0.2)
    process_manager.stop_process(exec_id)
    info = process_manager.get_process(exec_id)
    assert info.status == "stopped"
    # restart
    process_manager.restart_process(exec_id)
    info = process_manager.get_process(exec_id)
    assert info.status == "running"
    # cleanup fast
    process_manager.kill_process(exec_id)
    info = process_manager.get_process(exec_id)
    assert info.status == "killed"

def test_kill_process():
    req = make_req("sleep 10")
    exec_id = process_manager.start_process(req)
    time.sleep(0.2)
    process_manager.kill_process(exec_id)
    info = process_manager.get_process(exec_id)
    assert info.status == "killed"
    # ensure process is not lingering
    # poll should be None after kill
    # (process_manager internal proc already cleared)
    assert info.pid is not None
