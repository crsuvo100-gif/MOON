"""DependencyAnalyzer -- inspect a repo / manifest and resolve requirements.

Reads common manifest files (package.json, requirements.txt, pyproject.toml,
Cargo.toml, go.mod, Gemfile, pom.xml, build.gradle, Makefile, Dockerfile,
README.md) and classifies the capability's language, runtime, package deps,
and CLI utilities it needs. All read-only; never mutates the inspected repo.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MANIFEST_FILES = (
    "package.json", "requirements.txt", "pyproject.toml", "Pipfile",
    "Cargo.toml", "go.mod", "Gemfile", "pom.xml", "build.gradle",
    "Makefile", "Dockerfile", "setup.py", "setup.cfg", "environment.yml",
    "README.md", "readme.md", "README.rst",
)

_REQUIREMENTS_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)", re.MULTILINE)
_PYPROJECT_DEP_RE = re.compile(r'^\s*"?([A-Za-z0-9_.\-]+)"?\s*=', re.MULTILINE)


@dataclass
class Analysis:
    language: str = "unknown"
    runtime: str = "native"
    package_dependencies: tuple[str, ...] = field(default_factory=tuple)
    cli_utilities: tuple[str, ...] = field(default_factory=tuple)
    manifests_found: tuple[str, ...] = field(default_factory=tuple)
    install_hints: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


def _read(path: Path, limit: int = 20000) -> str:
    try:
        return path.read_text(errors="replace")[:limit]
    except Exception:  # noqa: BLE001
        return ""


def analyze_path(repo_path: Path) -> Analysis:
    """Analyze an already-cloned repository directory (read-only)."""
    repo_path = Path(repo_path)
    manifests: list[str] = []
    pkg: list[str] = []
    hints: list[str] = []
    language = "unknown"

    for mf in _MANIFEST_FILES:
        p = repo_path / mf
        if not p.exists():
            continue
        manifests.append(mf)
        text = _read(p)
        if mf == "package.json":
            language = "node"
            try:
                data = __import__("json").loads(text) if text.strip().startswith("{") else {}
                for sec in ("dependencies", "devDependencies", "peerDependencies"):
                    if isinstance(data.get(sec), dict):
                        pkg.extend(data[sec].keys())
                if data.get("scripts", {}).get("test"):
                    hints.append("npm test")
            except Exception:  # noqa: BLE001
                pass
        elif mf in ("requirements.txt", "Pipfile"):
            language = "python"
            pkg.extend(_REQUIREMENTS_RE.findall(text))
        elif mf in ("pyproject.toml", "setup.py", "setup.cfg"):
            language = "python"
            pkg.extend(_PYPROJECT_DEP_RE.findall(text))
            if "poetry" in text:
                hints.append("poetry install")
            if "setuptools" in text:
                hints.append("pip install .")
        elif mf == "Cargo.toml":
            language = "rust"
            hints.append("cargo build")
        elif mf == "go.mod":
            language = "go"
            hints.append("go build")
        elif mf == "Gemfile":
            language = "ruby"
            hints.append("bundle install")
        elif mf in ("pom.xml", "build.gradle"):
            language = "java"
            hints.append("mvn package" if mf == "pom.xml" else "gradle build")
        elif mf == "Dockerfile":
            hints.append("docker build")
        elif mf == "Makefile":
            for t in re.findall(r"^(?!PHONY)([a-zA-Z0-9_-]+):", text, re.MULTILINE):
                if t in ("install", "test", "build"):
                    hints.append(f"make {t}")
        elif mf.lower().startswith("readme"):
            # README often names the runtime + install command
            for line in text.splitlines()[:120]:
                if any(k in line.lower() for k in ("npm i", "pip install", "apt install",
                                                   "cargo install", "go install", "brew install")):
                    hints.append(line.strip().lstrip("#").strip()[:200])

    # Infer CLI utilities from common names in the repo.
    cli_candidates = ("ffmpeg", "imagemagick", "tesseract", "youtube-dl", "yt-dlp",
                      "pdftotext", "sox", "git", "docker", "node", "npm", "python3")
    found_cli = [c for c in cli_candidates if (repo_path / c).exists()] if repo_path.is_dir() else []
    return Analysis(
        language=language,
        runtime="native" if language == "unknown" else language,
        package_dependencies=tuple(dict.fromkeys(pkg)),
        cli_utilities=tuple(found_cli),
        manifests_found=tuple(manifests),
        install_hints=tuple(dict.fromkeys(hints)),
        notes=f"inspected {len(manifests)} manifest(s)",
    )


def analyze_text(name: str, manifest_text: str) -> Analysis:
    """Lightweight analysis of an inline manifest (no filesystem clone)."""
    return _analyze_inline(name, manifest_text)


def _analyze_inline(name: str, text: str) -> Analysis:
    if name.endswith(".py") or "requirements" in name:
        return Analysis(language="python",
                        runtime="python",
                        package_dependencies=tuple(dict.fromkeys(_REQUIREMENTS_RE.findall(text))),
                        manifests_found=(name,),
                        notes="inline python manifest")
    if name.endswith(".toml"):
        return Analysis(language="python",
                        runtime="python",
                        package_dependencies=tuple(dict.fromkeys(_PYPROJECT_DEP_RE.findall(text))),
                        manifests_found=(name,), notes="inline toml")
    if name.endswith(".json"):
        return Analysis(language="node", runtime="node", manifests_found=(name,), notes="inline json")
    return Analysis(manifests_found=(name,), notes="inline unknown manifest")
