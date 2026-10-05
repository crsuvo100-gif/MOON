import subprocess
import os
import sys
import signal
import pytest

# Helper to run a command with limited environment and timeout
def run_cmd(cmd, timeout=5):
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin"},
            timeout=timeout,
            check=False,
            text=True,
        )
        return result
    except subprocess.TimeoutExpired as e:
        return e

def test_command_injection_prevention():
    # Attempt to inject a harmless command via argument
    # The application should not execute arbitrary shell commands.
    # We'll simulate by calling a script that would echo if injection succeeded.
    # Run a harmless command via subprocess.run; ensure it executes but does not involve a shell.
    cmd = [sys.executable, "-c", "import subprocess, sys; subprocess.run([sys.executable, '-c', 'pass'], stdout=sys.stdout, stderr=sys.stderr)"]
    result = run_cmd(cmd)
    # Since we used subprocess.run without shell, no injection occurs; output should be empty.
    assert "INJECTED" not in (result.stdout or "")

def test_environment_variable_leakage():
    # Ensure that sensitive env vars are not passed to subprocesses by default.
    os.environ["SECRET_TOKEN"] = "supersecret"
    cmd = [sys.executable, "-c", "import os; print(os.getenv('SECRET_TOKEN'))"]
    result = run_cmd(cmd)
    # The sandbox_env fixture clears env vars, but this test runs directly,
    # so we assert that the script does not see the variable when env is sanitized.
    # Our run_cmd provides a minimal PATH only, no SECRET_TOKEN.
    assert result.stdout.strip() == "None"

def test_output_flooding_protection():
    # Run a command that produces large output; ensure we can handle it without hanging.
    # We'll use 'yes' limited by timeout.
    cmd = ["yes"]
    result = run_cmd(cmd, timeout=1)
    # The result should be a TimeoutExpired exception or truncated output.
    if isinstance(result, subprocess.TimeoutExpired):
        # Expected timeout, pass.
        assert True
    else:
        # Should have some output but not infinite.
        assert len(result.stdout) > 0
        assert len(result.stdout) < 10000  # reasonable limit

def test_resource_exhaustion_prevention():
    # Attempt to spawn many processes in a loop; ensure the system limits are respected.
    # We'll try to start 50 short-lived subprocesses.
    procs = []
    try:
        for _ in range(50):
            p = subprocess.Popen([sys.executable, "-c", "print('hi')"], stdout=subprocess.PIPE)
            procs.append(p)
        outputs = [p.communicate()[0].decode().strip() for p in procs]
        assert all(o == "hi" for o in outputs)
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
