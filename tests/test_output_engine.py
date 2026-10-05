import time
from pathlib import Path
from app.terminal.process_manager import process_manager
from app.terminal.output_engine import OutputEngine

class DummyReq:
    def __init__(self):
        self.command = 'seq 1 1000'
        self.cwd = Path('.')
        self.env = {}
        self.shell = True
        self.background = False
        self.backend = 'local'
        # No timeout or other attrs needed

def test_large_output_pagination():
    req = DummyReq()
    exec_id = process_manager.start_process(req)
    # Wait for process to complete
    for _ in range(200):
        info = process_manager.get_process(exec_id)
        if info and info.status != 'running':
            break
        time.sleep(0.01)
    else:
        assert False, 'Process did not finish in time'
    # Check first 10 lines
    out = OutputEngine().stream_output(exec_id, start_line=0, max_lines=10)
    expected_start = "\n".join(str(i) for i in range(1, 11)) + "\n"
    assert out['stdout'] == expected_start
    # Check tail lines (last 10 lines)
    tail = OutputEngine().stream_output(exec_id, start_line=990, max_lines=20)
    expected_tail = "\n".join(str(i) for i in range(991, 1001)) + "\n"
    assert tail['stdout'] == expected_tail
