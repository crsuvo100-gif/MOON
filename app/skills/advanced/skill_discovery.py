"""Skill discovery from filesystem and knowledge base.

Discovers available skills from:
1. The Hermes skills directory (~/.hermes/skills/)
2. The MOON skills directory (app/skills/)
3. The knowledge base (indexed skills)
4. Plugin-provided skills
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class SkillDiscovery:
    """Discovers and catalogs available skills.

    Scans multiple sources for skill definitions and builds a
    unified catalog of available skills with their metadata.
    """

    def __init__(self):
        self._discovered: dict[str, dict[str, Any]] = {}
        self._scan_paths: list[Path] = []

    def add_scan_path(self, path: str | Path) -> None:
        """Add a directory to scan for skills."""
        p = Path(path).expanduser().resolve()
        if p.is_dir() and p not in self._scan_paths:
            self._scan_paths.append(p)

    def discover(self) -> dict[str, dict[str, Any]]:
        """Discover all skills from all scan paths.

        Returns:
            Dict mapping skill_name -> skill_metadata
        """
        self._discovered.clear()

        # Default scan paths
        default_paths = [
            Path.home() / ".hermes" / "skills",
            Path(__file__).resolve().parent.parent.parent / "skills",
        ]
        for p in default_paths:
            if p.is_dir() and p not in self._scan_paths:
                self._scan_paths.append(p)

        for scan_path in self._scan_paths:
            self._scan_directory(scan_path)

        return dict(self._discovered)

    def _scan_directory(self, path: Path) -> None:
        """Scan a directory for skill definitions."""
        try:
            for entry in path.iterdir():
                if entry.is_dir():
                    # Check for SKILL.md
                    skill_md = entry / "SKILL.md"
                    if skill_md.exists():
                        self._parse_skill_md(entry.name, skill_md)
                    else:
                        # Check for skill.py
                        skill_py = entry / "skill.py"
                        if skill_py.exists():
                            self._parse_skill_py(entry.name, skill_py)
                elif entry.suffix == ".md" and entry.stem != "README":
                    # Standalone skill markdown
                    self._parse_skill_md(entry.stem, entry)
        except (PermissionError, OSError):
            pass

    def _parse_skill_md(self, name: str, path: Path) -> None:
        """Parse a SKILL.md file for skill metadata."""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            meta = self._extract_metadata(content)
            meta["source"] = str(path)
            meta["format"] = "markdown"
            self._discovered[name] = meta
        except (OSError, UnicodeDecodeError):
            pass

    def _parse_skill_py(self, name: str, path: Path) -> None:
        """Parse a skill.py file for skill metadata."""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            meta = self._extract_metadata(content)
            meta["source"] = str(path)
            meta["format"] = "python"
            self._discovered[name] = meta
        except (OSError, UnicodeDecodeError):
            pass

    def _extract_metadata(self, content: str) -> dict[str, Any]:
        """Extract metadata from skill file content.

        Parses YAML frontmatter (---\n...\n---) and inline metadata
        (# key: value) from skill files.
        """
        meta: dict[str, Any] = {
            "name": "",
            "description": "",
            "keywords": [],
            "tags": [],
            "instructions": "",
            "examples": [],
            "constraints": [],
        }

        # YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                import yaml
                try:
                    frontmatter = yaml.safe_load(parts[1])
                    if isinstance(frontmatter, dict):
                        meta.update(frontmatter)
                except Exception:
                    pass
                body = parts[2].strip()
            else:
                body = content
        else:
            body = content

        # Inline metadata from comments
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                if ":" in line[2:]:
                    key, _, value = line[2:].partition(":")
                    key = key.strip().lower()
                    value = value.strip()
                    if key in ("name", "description", "instructions"):
                        meta[key] = value
                    elif key in ("keywords", "tags", "constraints"):
                        meta[key] = [v.strip() for v in value.split(",") if v.strip()]

        # Use body as instructions if no explicit instructions
        if not meta.get("instructions") and body:
            meta["instructions"] = body[:2000]

        # Ensure name is set
        if not meta.get("name"):
            meta["name"] = "unknown"

        return meta

    def get_skill(self, name: str) -> dict[str, Any] | None:
        """Get metadata for a specific skill."""
        return self._discovered.get(name)

    def list_skills(self) -> list[str]:
        """List all discovered skill names."""
        return list(self._discovered.keys())

    def search_skills(self, query: str) -> list[tuple[str, dict[str, Any]]]:
        """Search discovered skills by query string.

        Returns:
            List of (skill_name, metadata) tuples matching the query
        """
        query_lower = query.lower()
        results: list[tuple[str, dict[str, Any]]] = []
        for name, meta in self._discovered.items():
            if query_lower in name.lower():
                results.append((name, meta))
                continue
            desc = meta.get("description", "").lower()
            if query_lower in desc:
                results.append((name, meta))
                continue
            keywords = [k.lower() for k in meta.get("keywords", [])]
            if any(query_lower in k for k in keywords):
                results.append((name, meta))
        return results
