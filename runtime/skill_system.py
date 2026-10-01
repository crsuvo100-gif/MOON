"""SkillSystem (spec section 24).

A skill is reusable procedural knowledge. MOON already ships a large skills/
corpus; this system registers those (and any runtime-added skills) with
metadata + a performance score, and evaluates them. It does not reimplement the
corpus -- it indexes and scores what already exists (additive).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent / "skills"


@dataclass
class Skill:
    skill_id: str
    description: str = ""
    prerequisites: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    procedure: str = ""
    examples: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    verification: str = ""
    success_criteria: str = ""
    version: str = "1.0.0"
    performance_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SkillSystem:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else _SKILLS_ROOT
        self._skills: dict[str, Skill] = {}
        self._discover()

    def _discover(self) -> None:
        """Index the existing skills/ corpus into registered Skill records."""
        if not self.root.exists():
            return
        # The corpus can be 1-level (category/SKILL.md) or 2-level
        # (category/sub_skill/SKILL.md). Handle both so the full corpus is
        # registered, matching the behavior of app.knowledge.skills_library.
        seen: set[str] = set()
        for skill_md in sorted(self.root.glob("*/SKILL.md")):
            rel = skill_md.relative_to(self.root)
            seen.add(str(rel.parent))
        for skill_md in sorted(self.root.glob("*/*/SKILL.md")):
            rel = skill_md.relative_to(self.root)
            seen.add(str(rel.parent))
        for sid in sorted(seen):
            d = self.root / sid
            readme = d / "SKILL.md"
            desc = self._skill_description(readme)
            if sid not in self._skills:
                self._skills[sid] = Skill(skill_id=sid, description=desc or sid)

    @staticmethod
    def _skill_description(readme: Path) -> str:
        """Extract a human description from a SKILL.md with optional YAML frontmatter."""
        if not readme.exists():
            return ""
        try:
            txt = readme.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            return ""
        # Try YAML frontmatter: between first and second '---' lines.
        lines = txt.splitlines()
        if lines and lines[0].strip() == "---":
            meta_lines: list[str] = []
            for ln in lines[1:]:
                if ln.strip() == "---":
                    break
                meta_lines.append(ln)
            else:
                # no closing --- found; treat whole block as frontmatter-ish
                pass
            meta = "\n".join(meta_lines)
            for key in ("description", "name"):
                for m in re.finditer(rf"^{key}:\s*[\"']?(.*?)[\"']?\s*(#.*)?$", meta, re.MULTILINE):
                    val = m.group(1).strip()
                    if val:
                        return val
        # Fallback: first H1 heading
        for ln in lines:
            s = ln.strip()
            if s.startswith("# "):
                return s[2:].strip()
            if s.startswith("## "):
                return s[3:].strip()
        # Fallback: first non-empty non-frontmatter line
        in_front = False
        for ln in lines:
            s = ln.strip()
            if s == "---":
                in_front = not in_front
                continue
            if in_front:
                continue
            if s and not s.startswith("#"):
                return s[:200]
        return ""

    # -- registry ops ----------------------------------------------------
    def register(self, skill: Skill) -> None:
        self._skills[skill.skill_id] = skill

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def list_ids(self) -> list[str]:
        return sorted(self._skills.keys())

    # -- performance (spec 24 "performance score") -----------------------
    def record_outcome(self, skill_id: str, success: bool) -> None:
        s = self._skills.get(skill_id)
        if not s:
            return
        prev = s.performance_score or 0.9
        s.performance_score = round(0.7 * prev + 0.3 * (1.0 if success else 0.0), 3)

    def top_for(self, capability: str, k: int = 5) -> list[Skill]:
        cap = (capability or "").lower()
        scored = [
            (s.performance_score, s) for s in self._skills.values()
            if cap in (s.description or "").lower() or cap in s.skill_id.lower()
        ]
        scored.sort(reverse=True)
        return [s for _, s in scored[:k]]

    def stats(self) -> dict[str, Any]:
        return {
            "total_skills": len(self._skills),
            "avg_performance": round(
                sum(s.performance_score for s in self._skills.values()) / max(1, len(self._skills)), 3),
        }
