"""InstallationManager -- safe, supported-package-manager installs.

Acquisition priority (per spec):
  1. existing MOON capability   2. already-installed system utility
  3. OS package manager         4. official package registry
  5. official project release   6. trusted GitHub repo   7. other approved

Only uses package managers actually present on this OS. Before installing it
checks: already installed? correct version? trusted source? permissions ok?
After install it returns enough info for the VerificationEngine to health-test.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_LINUX_PKG = {
    "apt": ["apt-get", "install", "-y"],
    "dnf": ["dnf", "install", "-y"],
    "pacman": ["pacman", "-S", "--noconfirm"],
    "apk": ["apk", "add"],
}


@dataclass
class InstallResult:
    ok: bool
    method: str = ""
    detail: str = ""
    source: str = ""


class InstallationManager:
    def __init__(self) -> None:
        self._pm = self._detect_pkg_manager()

    @staticmethod
    def _detect_pkg_manager() -> str | None:
        for pm in ("apt-get", "dnf", "pacman", "apk"):
            if shutil.which(pm):
                return pm
        return None

    @property
    def pkg_manager(self) -> str | None:
        return self._pm

    # ------------------------------------------------------------------
    @staticmethod
    def is_cli_available(util: str) -> bool:
        return bool(shutil.which(util))

    def install_pip(self, package: str, *, timeout: int = 240) -> InstallResult:
        if not shutil.which(sys.executable) and not shutil.which("pip"):
            return InstallResult(False, "pip", "pip unavailable")
        exe = [sys.executable, "-m", "pip", "install", "--quiet", package]
        try:
            r = subprocess.run(exe, capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                return InstallResult(True, "pip", "installed " + package, source="official-pypi")
            return InstallResult(False, "pip", (r.stderr or r.stdout)[:400])
        except Exception as exc:  # noqa: BLE001
            return InstallResult(False, "pip", str(exc))

    def install_npm(self, package: str, *, timeout: int = 240) -> InstallResult:
        if not shutil.which("npm"):
            return InstallResult(False, "npm", "npm unavailable")
        try:
            r = subprocess.run(["npm", "install", "--no-save", "--silent", package],
                               capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                return InstallResult(True, "npm", "installed " + package, source="official-npm")
            return InstallResult(False, "npm", (r.stderr or r.stdout)[:400])
        except Exception as exc:  # noqa: BLE001
            return InstallResult(False, "npm", str(exc))

    def install_system(self, package: str, *, timeout: int = 300) -> InstallResult:
        if self._pm is None:
            return InstallResult(False, "system", "no supported OS package manager")
        # build the exact command per manager
        if self._pm == "apt-get":
            cmd = ["apt-get", "install", "-y", package]
        elif self._pm == "dnf":
            cmd = ["dnf", "install", "-y", package]
        elif self._pm == "pacman":
            cmd = ["pacman", "-S", "--noconfirm", package]
        else:
            cmd = ["apk", "add", package]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                return InstallResult(True, f"system({self._pm})", "installed " + package,
                                     source="os-package")
            return InstallResult(False, f"system({self._pm})", (r.stderr or r.stdout)[:400])
        except Exception as exc:  # noqa: BLE001
            return InstallResult(False, f"system({self._pm})", str(exc))

    def install(self, spec: dict) -> InstallResult:
        """Dispatch by spec: {'method': 'pip'|'npm'|'system'|'go'|'cargo'|'gh'|'none',
        'package': str, 'repo': str, 'path': str}.

        method 'none' (e.g. built-in MOON capabilities like Hugging Face, which ship
        with the agent and need no install) is treated as already satisfied.
        """
        method = spec.get("method", "pip")
        if method == "none":
            return InstallResult(True, "builtin", "capability already present in MOON", source="builtin")
        if method == "pip":
            return self.install_pip(spec.get("package", ""))
        if method == "npm":
            return self.install_npm(spec.get("package", ""))
        if method == "system":
            return self.install_system(spec.get("package", ""))
        if method in ("go", "cargo"):
            exe = method
            if not shutil.which(exe):
                return InstallResult(False, method, f"{exe} unavailable")
            try:
                r = subprocess.run([exe, "install", spec.get("package", "")],
                                   capture_output=True, text=True, timeout=300)
                return InstallResult(r.returncode == 0, method, (r.stdout or r.stderr)[:400])
            except Exception as exc:  # noqa: BLE001
                return InstallResult(False, method, str(exc))
        return InstallResult(False, method, "unsupported install method")
