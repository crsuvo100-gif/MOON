"""Environment manager for MOON terminal sessions.

Handles:
- Shell detection (bash, sh, zsh, fish)
- Environment variable management
- Secret redaction
- Session-specific environment
- PATH, HOME, USER, SHELL, PWD, VIRTUAL_ENV tracking
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

# Patterns that indicate a secret value
_SECRET_KEY_PATTERN = re.compile(
    r"(?i)(key|token|password|secret|api_key|apikey|auth|credential|private)"
)

# Environment variable names that are always secret
_SECRET_VAR_NAMES: Set[str] = {
    "API_KEY", "APIKEY", "TOKEN", "PASSWORD", "SECRET", "AUTH_TOKEN",
    "ACCESS_TOKEN", "REFRESH_TOKEN", "PRIVATE_KEY", "SECRET_KEY",
    "OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
    "HF_TOKEN", "HUGGINGFACE_TOKEN", "TELEGRAM_BOT_TOKEN",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    "GITHUB_TOKEN", "GH_TOKEN", "NPM_TOKEN",
}

# Environment variables that should never be exposed
_SENSITIVE_VARS: Set[str] = _SECRET_VAR_NAMES | {
    "SSH_AUTH_SOCK", "SSH_AGENT_PID", "GPG_AGENT_INFO",
    "GNUPGHOME", "KEYCHAIN", "SECURITYSESSIONID",
}


class EnvironmentManager:
    """Manages shell detection, environment variables, and secret redaction."""

    def __init__(self):
        self._detected_shell: Optional[str] = None
        self._available_shells: Dict[str, str] = {}
        self._detect_shells()

    def _detect_shells(self):
        """Detect available shells on the system."""
        for shell in ("bash", "sh", "zsh", "fish"):
            path = shutil.which(shell)
            if path:
                self._available_shells[shell] = path

    @property
    def available_shells(self) -> Dict[str, str]:
        """Return dict of {shell_name: path} for available shells."""
        return dict(self._available_shells)

    def detect_default_shell(self) -> str:
        """Detect the user's default shell."""
        if self._detected_shell:
            return self._detected_shell
        # Try SHELL env var first
        shell = os.environ.get("SHELL", "")
        if shell and shell in self._available_shells:
            self._detected_shell = shell
            return shell
        # Try /etc/passwd
        try:
            import pwd
            entry = pwd.getpwuid(os.getuid())
            shell = entry.pw_shell
            if shell and shell in self._available_shells:
                self._detected_shell = shell
                return shell
        except Exception:
            pass
        # Fallback to sh
        self._detected_shell = "sh"
        return "sh"

    def get_shell_path(self, shell: str) -> Optional[str]:
        """Get the path to a specific shell."""
        return self._available_shells.get(shell)

    def is_shell_available(self, shell: str) -> bool:
        """Check if a shell is available."""
        return shell in self._available_shells

    def get_environment(self, session_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Get the current environment, optionally merged with session env.

        Secrets are NOT redacted here — this is the real environment for
        subprocess execution. Use `get_redacted_environment` for display/logging.
        """
        env = dict(os.environ)
        if session_env:
            env.update(session_env)
        return env

    def get_redacted_environment(self, session_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Get environment with secrets redacted for display/logging."""
        env = self.get_environment(session_env)
        return self.redact_environment(env)

    def redact_environment(self, env: Dict[str, str]) -> Dict[str, str]:
        """Return a copy of env with secret values redacted."""
        redacted = {}
        for key, value in env.items():
            if self.is_secret_var(key):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = value
        return redacted

    def is_secret_var(self, name: str) -> bool:
        """Check if an environment variable name looks like a secret."""
        upper = name.upper()
        if upper in _SENSITIVE_VARS:
            return True
        if upper in _SECRET_VAR_NAMES:
            return True
        # Check if the name contains secret-like words
        if _SECRET_KEY_PATTERN.search(upper):
            return True
        return False

    def redact_value(self, value: str) -> str:
        """Redact a value if it looks like a secret."""
        # If it's a long string that looks like a key/token, redact it
        if len(value) > 20 and re.match(r"^[A-Za-z0-9_\-]+$", value):
            return "***REDACTED***"
        return value

    def get_python_version(self) -> str:
        """Get the Python version string."""
        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    def get_python_executable(self) -> str:
        """Get the path to the current Python executable."""
        return sys.executable

    def get_virtual_env(self) -> Optional[str]:
        """Get the active virtual environment path, if any."""
        return os.environ.get("VIRTUAL_ENV")

    def get_os_info(self) -> Dict[str, str]:
        """Get OS information."""
        import platform
        return {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": self.get_python_version(),
        }

    def get_git_state(self, cwd: Optional[Path] = None) -> Dict[str, str]:
        """Get git repository state for a directory."""
        cwd = cwd or Path.cwd()
        result = {
            "is_repo": "false",
            "branch": "",
            "remote": "",
        }
        try:
            # Check if in a git repo
            proc = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip() == "true":
                result["is_repo"] = "true"
                # Get branch
                proc = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if proc.returncode == 0:
                    result["branch"] = proc.stdout.strip()
                # Get remote
                proc = subprocess.run(
                    ["git", "remote", "get-url", "origin"],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if proc.returncode == 0:
                    result["remote"] = proc.stdout.strip()
        except Exception:
            pass
        return result

    def build_session_env(
        self,
        cwd: Optional[Path] = None,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Build a complete environment for a session."""
        env = dict(os.environ)
        if cwd:
            env["PWD"] = str(cwd)
        if extra_env:
            env.update(extra_env)
        return env


# Module-level singleton
environment_manager = EnvironmentManager()
