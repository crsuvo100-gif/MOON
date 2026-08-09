"""Architecture diagram tool -- generates a dark-themed SVG-in-HTML diagram
(from the Hermes architecture-diagram skill). Dependency-free, single file,
works offline in any browser."""

from __future__ import annotations

import re
from pathlib import Path

from app.tools.base import BaseTool, ToolResult

_TYPE_STYLE = {
    "frontend": ("rgba(8,51,68,0.4)", "#22d3ee"),
    "backend": ("rgba(6,78,59,0.4)", "#34d399"),
    "database": ("rgba(76,29,149,0.4)", "#a78bfa"),
    "cloud": ("rgba(120,53,15,0.3)", "#fbbf24"),
    "aws": ("rgba(120,53,15,0.3)", "#fbbf24"),
    "security": ("rgba(136,19,55,0.4)", "#fb7185"),
    "bus": ("rgba(251,146,60,0.3)", "#fb923c"),
    "external": ("rgba(30,41,59,0.5)", "#94a3b8"),
}


class ArchitectureDiagramTool(BaseTool):
    name = "architecture_diagram"
    description = "Generate a dark-themed SVG architecture diagram (.html) from components/connections."

    async def execute(
        self,
        title: str = "System Architecture",
        components: list[str] | None = None,
        connections: list[str] | None = None,
        out: str = "architecture.html",
        **kwargs,
    ) -> str:
        components = components or []
        connections = connections or []
        parts = []
        n = len(components) or 1
        cols = max(1, int(n ** 0.5))
        rects = []
        pos = {}
        for i, comp in enumerate(components):
            kind = "external"
            for k in _TYPE_STYLE:
                if k in comp.lower():
                    kind = k
                    break
            fill, stroke = _TYPE_STYLE[kind]
            col = i % cols
            row = i // cols
            x = 60 + col * 240
            y = 90 + row * 150
            name = re.split(r"[:\-]", comp)[0].strip()
            label = comp
            pos[comp] = (x, y)
            rects.append(
                f'<g><rect x="{x}" y="{y}" width="200" height="80" rx="6" '
                f'fill="#0f172a" stroke="{stroke}" stroke-width="1.5"/>'
                f'<rect x="{x}" y="{y}" width="200" height="80" rx="6" '
                f'fill="{fill}" stroke="none"/>'
                f'<text x="{x+100}" y="{y+45}" fill="#e2e8f0" font-size="13" '
                f'text-anchor="middle" font-family="JetBrains Mono, monospace">{name}</text>'
                f'<text x="{x+100}" y="{y+63}" fill="#94a3b8" font-size="9" '
                f'text-anchor="middle" font-family="JetBrains Mono, monospace">{kind}</text></g>'
            )
        lines = []
        for c in connections:
            m = re.match(r"\s*(.+?)\s*(?:->|=>)\s*(.+?)\s*$", c)
            if not m:
                continue
            a, b = m.group(1).strip(), m.group(2).strip()
            if a in pos and b in pos:
                ax, ay = pos[a]
                bx, by = pos[b]
                lines.append(
                    f'<line x1="{ax+200}" y1="{ay+40}" x2="{bx}" y2="{by+40}" '
                    f'stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow)"/>'
                )
        svg = (
            '<svg width="100%" viewBox="0 0 1200 800" xmlns="http://www.w3.org/2000/svg">'
            '<defs><pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">'
            '<path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.5"/></pattern>'
            '<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" '
            'orient="auto" markerUnits="strokeWidth"><path d="M0,0 L8,3 L0,6 Z" fill="#64748b"/></marker></defs>'
            '<rect width="100%" height="100%" fill="#020617"/>'
            '<rect width="100%" height="100%" fill="url(#grid)"/>'
            + "".join(lines) + "".join(rects) + "</svg>"
        )
        html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'><title>"
            + title
            + "</title></head><body style='margin:0;background:#020617;color:#e2e8f0;"
            "font-family:JetBrains Mono,monospace'>"
            f"<h2 style='padding:16px'>{title}</h2>"
            f"<div style='border:1px solid #1e293b;border-radius:12px;margin:0 16px'>{svg}</div>"
            "</body></html>"
        )
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html)
        return f"Wrote architecture diagram ({len(components)} components, {len(connections)} links) -> {path}"
