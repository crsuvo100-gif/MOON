"""PTY manager for interactive terminal sessions.

Provides real PTY (pseudo-terminal) support for interactive applications
like python, ssh, top, htop, vim, nano, etc.

Uses the `pty` module from the standard library. Falls back gracefully
when PTY is unavailable (e.g., Windows without conpty).
"""

from __future__ import annotations

import errno
import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import termios
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .models import ExecutionRequest, ExecutionResult


class PTYManager:
    """Manages pseudo-terminal execution for interactive commands."""

    def __init__(self):
        self._active_ptys: Dict[str, dict] = {}  # execution_id → {proc, master_fd, thread}
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        """Check if PTY is supported on this platform."""
        try:
            # Test if we can create a PTY pair
            master_fd, slave_fd = pty.openpty()
            os.close(master_fd)
            os.close(slave_fd)
            return True
        except Exception:
            return False

    def run_interactive(
        self,
        request: ExecutionRequest,
        on_output: Optional[Callable[[str], None]] = None,
        on_exit: Optional[Callable[[int], None]] = None,
    ) -> ExecutionResult:
        """Run a command in a PTY.

        This is a blocking call that streams output via `on_output` callback.
        For non-blocking interactive sessions, use `start_session` instead.
        """
        import uuid

        execution_id = str(uuid.uuid4())
        cwd = request.cwd or Path.cwd()
        env = {**os.environ, **(request.env or {})}

        # Build command
        if request.shell:
            cmd = request.command
            shell_cmd = ["/bin/sh", "-c", cmd]
        else:
            import shlex
            try:
                shell_cmd = shlex.split(request.command)
            except ValueError:
                shell_cmd = ["/bin/sh", "-c", request.command]

        # Create PTY
        try:
            master_fd, slave_fd = pty.openpty()
        except Exception as exc:
            return ExecutionResult(
                execution_id=execution_id,
                command=request.command,
                backend=request.backend,
                cwd=cwd,
                status="failed",
                exit_code=None,
                stdout=None,
                stderr=None,
                pid=None,
                duration=0.0,
                verified=False,
                verification_result=None,
                error=f"Failed to create PTY: {exc}",
            )

        # Set window size (default 80x24)
        try:
            winsize = struct.pack("HHHH", 24, 80, 0, 0)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

        # Fork and exec
        try:
            pid = os.fork()
        except Exception as exc:
            os.close(master_fd)
            os.close(slave_fd)
            return ExecutionResult(
                execution_id=execution_id,
                command=request.command,
                backend=request.backend,
                cwd=cwd,
                status="failed",
                exit_code=None,
                stdout=None,
                stderr=None,
                pid=None,
                duration=0.0,
                verified=False,
                verification_result=None,
                error=f"Failed to fork: {exc}",
            )

        if pid == 0:
            # Child process
            try:
                os.close(master_fd)
                os.setsid()
                # Make slave the controlling terminal
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
                os.dup2(slave_fd, 0)  # stdin
                os.dup2(slave_fd, 1)  # stdout
                os.dup2(slave_fd, 2)  # stderr
                if slave_fd > 2:
                    os.close(slave_fd)
                os.chdir(str(cwd))
                os.execvpe(shell_cmd[0], shell_cmd, env)
            except Exception:
                os._exit(127)
        else:
            # Parent process
            os.close(slave_fd)
            start_time = time.time()
            output_parts: List[str] = []
            exit_code = None

            try:
                while True:
                    # Check if child exited
                    try:
                        wpid, status = os.waitpid(pid, os.WNOHANG)
                        if wpid == pid:
                            if os.WIFEXITED(status):
                                exit_code = os.WEXITSTATUS(status)
                            elif os.WIFSIGNALED(status):
                                exit_code = -os.WTERMSIG(status)
                            break
                    except ChildProcessError:
                        break
                    except OSError as e:
                        if e.errno == errno.ECHILD:
                            break
                        raise

                    # Read output with timeout
                    try:
                        ready, _, _ = select.select([master_fd], [], [], 0.1)
                        if ready:
                            try:
                                data = os.read(master_fd, 4096)
                                if data:
                                    text = data.decode("utf-8", errors="replace")
                                    output_parts.append(text)
                                    if on_output:
                                        try:
                                            on_output(text)
                                        except Exception:
                                            pass
                            except OSError:
                                break
                    except (OSError, ValueError):
                        break

                # Read any remaining output
                try:
                    while True:
                        ready, _, _ = select.select([master_fd], [], [], 0.1)
                        if not ready:
                            break
                        data = os.read(master_fd, 4096)
                        if not data:
                            break
                        text = data.decode("utf-8", errors="replace")
                        output_parts.append(text)
                        if on_output:
                            try:
                                on_output(text)
                            except Exception:
                                pass
                except (OSError, ValueError):
                    pass

            finally:
                os.close(master_fd)
                # Ensure child is dead
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                try:
                    os.waitpid(pid, 0)
                except (ChildProcessError, OSError):
                    pass

            duration = time.time() - start_time
            stdout = "".join(output_parts)

            if exit_code is None:
                exit_code = -1

            if on_exit:
                try:
                    on_exit(exit_code)
                except Exception:
                    pass

            return ExecutionResult(
                execution_id=execution_id,
                command=request.command,
                backend=request.backend,
                cwd=cwd,
                status="success" if exit_code == 0 else "failed",
                exit_code=exit_code,
                stdout=stdout,
                stderr=None,
                pid=pid,
                duration=duration,
                verified=False,
                verification_result=None,
                error=None,
            )

    def start_session(
        self,
        request: ExecutionRequest,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Start a non-blocking interactive PTY session.

        Returns execution_id immediately. Output is streamed via `on_output`.
        Use `send_input`, `resize_pty`, and `stop_session` to manage the session.
        """
        import uuid

        execution_id = str(uuid.uuid4())
        cwd = request.cwd or Path.cwd()
        env = {**os.environ, **(request.env or {})}

        if request.shell:
            shell_cmd = ["/bin/sh", "-c", request.command]
        else:
            import shlex
            try:
                shell_cmd = shlex.split(request.command)
            except ValueError:
                shell_cmd = ["/bin/sh", "-c", request.command]

        master_fd, slave_fd = pty.openpty()

        # Set window size
        try:
            winsize = struct.pack("HHHH", 24, 80, 0, 0)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

        pid = os.fork()
        if pid == 0:
            # Child
            try:
                os.close(master_fd)
                os.setsid()
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
                os.dup2(slave_fd, 0)
                os.dup2(slave_fd, 1)
                os.dup2(slave_fd, 2)
                if slave_fd > 2:
                    os.close(slave_fd)
                os.chdir(str(cwd))
                os.execvpe(shell_cmd[0], shell_cmd, env)
            except Exception:
                os._exit(127)
        else:
            # Parent
            os.close(slave_fd)

            def _reader():
                while True:
                    try:
                        ready, _, _ = select.select([master_fd], [], [], 0.1)
                        if ready:
                            try:
                                data = os.read(master_fd, 4096)
                                if data:
                                    text = data.decode("utf-8", errors="replace")
                                    if on_output:
                                        try:
                                            on_output(text)
                                        except Exception:
                                            pass
                            except OSError:
                                break
                    except (OSError, ValueError):
                        break
                try:
                    os.close(master_fd)
                except OSError:
                    pass

            thread = threading.Thread(target=_reader, daemon=True)
            thread.start()

            with self._lock:
                self._active_ptys[execution_id] = {
                    "pid": pid,
                    "master_fd": master_fd,
                    "thread": thread,
                    "request": request,
                    "start_time": time.time(),
                }

            return execution_id

    def send_input(self, execution_id: str, data: str) -> bool:
        """Send input to a running PTY session."""
        with self._lock:
            entry = self._active_ptys.get(execution_id)
        if not entry:
            return False
        try:
            os.write(entry["master_fd"], data.encode("utf-8"))
            return True
        except OSError:
            return False

    def resize_pty(self, execution_id: str, rows: int, cols: int) -> bool:
        """Resize a PTY session."""
        with self._lock:
            entry = self._active_ptys.get(execution_id)
        if not entry:
            return False
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(entry["master_fd"], termios.TIOCSWINSZ, winsize)
            # Also resize the slave side
            # Note: we don't have slave_fd stored, but the master resize
            # should propagate to the child via SIGWINCH
            return True
        except OSError:
            return False

    def stop_session(self, execution_id: str) -> bool:
        """Stop a PTY session."""
        with self._lock:
            entry = self._active_ptys.pop(execution_id, None)
        if not entry:
            return False
        try:
            os.kill(entry["pid"], signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            os.close(entry["master_fd"])
        except OSError:
            pass
        return True

    def list_sessions(self) -> List[str]:
        """List active PTY session IDs."""
        with self._lock:
            return list(self._active_ptys.keys())

    def cleanup(self):
        """Clean up all active PTY sessions."""
        with self._lock:
            ids = list(self._active_ptys.keys())
        for eid in ids:
            self.stop_session(eid)


# Module-level singleton
pty_manager = PTYManager()
