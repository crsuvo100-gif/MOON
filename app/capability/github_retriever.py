"""GitHubRetriever -- search, inspect, and trust-evaluate repositories.

REUSES existing MOON GitHub integration (app.tools.github_feed for search +
app.tools.github_sync_tool for auth/owner-repo parsing) instead of duplicating
it. Adds: README/release/manifest inspection, dependency-file analysis, an
executable/install-script scan, a permission/trust evaluation, and candidate
selection. All read-only before any install; nothing is executed here.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RepoCandidate:
    full_name: str
    url: str
    default_branch: str = "main"
    stars: int = 0
    description: str = ""
    readme: str = ""
    trust_score: float = 0.0
    flags: tuple[str, ...] = field(default_factory=tuple)
    install_hints: tuple[str, ...] = field(default_factory=tuple)
    language: str = "unknown"
    permissions: tuple[str, ...] = field(default_factory=tuple)


# Operations a repo's install scripts must NOT perform without confirmation.
_SUSPICIOUS = (
    "rm -rf /", "mkfs", "dd if=/dev", "shutdown", "reboot",
    "curl | sh", "wget | sh", "sudo ", ">/etc/", "ssh-copy-id",
    "chmod 777 /", "iptables", "ufw disable", "systemctl disable",
)


class GitHubRetriever:
    def __init__(self, registry_cache_get=None, registry_cache_put=None) -> None:
        # optional cache hooks backed by CapabilityRegistry
        self._cget = registry_cache_get
        self._cput = registry_cache_put

    # ------------------------------------------------------------------
    def search(self, query: str, limit: int = 5) -> list[RepoCandidate]:
        cached = self._cget(f"gh_search::{query}") if self._cget else None
        if cached:
            return [RepoCandidate(**c) for c in cached]
        try:
            from app.tools.github_feed import search_github
            raw = search_github(query, limit=limit)
        except Exception as exc:  # noqa: BLE001
            logger.info("github search unavailable: %s", exc)
            return []
        out = [RepoCandidate(full_name=r["full_name"], url=r["url"],
                             default_branch=r.get("default_branch", "main"),
                             stars=r.get("stars", 0)) for r in raw]
        if self._cput:
            self._cput(f"gh_search::{query}", [c.__dict__ for c in out])
        return out

    # ------------------------------------------------------------------
    def inspect(self, candidate: RepoCandidate) -> RepoCandidate:
        """Read README + manifest files (read-only clone), analyze deps, score trust."""
        tmp = tempfile.mkdtemp(prefix="moon_gh_inspect_")
        try:
            url = f"https://github.com/{candidate.full_name}.git"
            r = subprocess_clone(url, candidate.default_branch, tmp)
            if r.returncode != 0:
                candidate.flags = ("clone_failed",)
                return candidate
            repo = Path(tmp) / "src"
            # README
            readme = ""
            for name in ("README.md", "readme.md", "README.rst", "README.txt"):
                p = repo / name
                if p.exists():
                    readme = p.read_text(errors="replace")[:6000]
                    break
            candidate.readme = readme
            # Analyze manifests via the shared DependencyAnalyzer.
            try:
                from app.capability.dependency_analyzer import analyze_path
                a = analyze_path(repo)
                candidate.language = a.language
                candidate.install_hints = a.install_hints
            except Exception as exc:  # noqa: BLE001
                logger.debug("manifest analysis skipped: %s", exc)
            # Suspicious install-script scan.
            flags = self._scan_scripts(repo)
            candidate.flags = tuple(flags)
            candidate.permissions = ("github.read", "network.http",
                                     "workspace.read", "workspace.write")
            candidate.trust_score = self._score(candidate)
            return candidate
        except Exception as exc:  # noqa: BLE001
            logger.info("inspect failed: %s", exc)
            candidate.flags = ("inspect_error",)
            return candidate
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    def _scan_scripts(self, repo: Path) -> list[str]:
        flags: list[str] = []
        scripts = list(repo.rglob("*.sh")) + list(repo.rglob("Makefile"))
        scripts = scripts[:20]
        for s in scripts:
            try:
                text = s.read_text(errors="replace")[:8000]
            except Exception:  # noqa: BLE001
                continue
            for marker in _SUSPICIOUS:
                if marker in text:
                    flags.append(f"suspicious:{marker.strip()}")
        return flags

    def _score(self, c: RepoCandidate) -> float:
        score = 0.0
        if c.stars >= 1000:
            score += 0.5
        elif c.stars >= 50:
            score += 0.3
        elif c.stars > 0:
            score += 0.1
        if "clone_failed" in c.flags or "inspect_error" in c.flags:
            score -= 0.4
        if any(f.startswith("suspicious") for f in c.flags):
            score -= 0.5
        if c.readme:
            score += 0.2
        return round(max(0.0, min(1.0, score)), 2)

    def select(self, candidates: list[RepoCandidate]) -> RepoCandidate | None:
        safe = [c for c in candidates if not any(f.startswith("suspicious") for f in c.flags)]
        if not safe:
            return None
        return max(safe, key=lambda c: (c.trust_score, c.stars))


def subprocess_clone(url: str, branch: str, tmp: str):
    import subprocess
    return subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", branch, url, "src"],
        cwd=tmp, capture_output=True, text=True, timeout=120,
    )
