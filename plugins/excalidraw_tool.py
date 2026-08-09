"""Excalidraw diagram tool -- generates .excalidraw JSON (from the Hermes
excalidraw skill). Dependency-free: builds labeled boxes + arrows following
the skill's element format (container binding for labels)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.tools.base import BaseTool, ToolResult


class ExcalidrawTool(BaseTool):
    name = "excalidraw"
    description = "Generate a hand-drawn Excalidraw diagram (.excalidraw JSON) from nodes/edges."

    async def execute(
        self,
        title: str = "Diagram",
        nodes: list[str] | None = None,
        edges: list[str] | None = None,
        out: str = "diagram.excalidraw",
        **kwargs,
    ) -> str:
        nodes = nodes or []
        edges = edges or []
        elements: list[dict] = []
        # title
        elements.append({
            "type": "text", "id": "title", "x": 100, "y": 40,
            "width": max(200, len(title) * 12), "height": 30, "text": title,
            "fontSize": 24, "fontFamily": 1, "strokeColor": "#1e1e1e",
            "originalText": title, "autoResize": True,
        })
        pos = {}
        cols = max(1, int(len(nodes) ** 0.5) or 1)
        for i, name in enumerate(nodes):
            cid = f"n{i}"
            col = i % cols
            row = i // cols
            x = 100 + col * 260
            y = 120 + row * 160
            pos[name] = (cid, x, y)
            elements.append({
                "type": "rectangle", "id": cid, "x": x, "y": y,
                "width": 220, "height": 90, "roundness": {"type": 3},
                "backgroundColor": "#a5d8ff", "fillStyle": "solid",
                "boundElements": [{"id": f"t_{cid}", "type": "text"}],
            })
            elements.append({
                "type": "text", "id": f"t_{cid}", "x": x + 10, "y": y + 35,
                "width": 200, "height": 25, "text": name, "fontSize": 18,
                "fontFamily": 1, "strokeColor": "#1e1e1e", "textAlign": "center",
                "verticalAlign": "middle", "containerId": cid,
                "originalText": name, "autoResize": True,
            })
        arrow_id = 0
        for e in edges:
            m = re.match(r"\s*(.+?)\s*(?:->|=>)\s*(.+?)\s*$", e)
            if not m:
                continue
            a, b = m.group(1).strip(), m.group(2).strip()
            if a in pos and b in pos:
                aid = f"a{arrow_id}"; arrow_id += 1
                ax, ay = pos[a][1], pos[a][2]
                bx = pos[b][1]
                elements.append({
                    "type": "arrow", "id": aid, "x": ax + 220, "y": ay + 45,
                    "width": max(20, bx - ax), "height": 0,
                    "points": [[0, 0], [max(40, bx - ax - 200), 0]],
                    "endArrowhead": "arrow", "strokeColor": "#1e1e1e",
                    "startBinding": {"elementId": pos[a][0], "fixedPoint": [1, 0.5]},
                    "endBinding": {"elementId": pos[b][0], "fixedPoint": [0, 0.5]},
                    "boundElements": [{"id": f"t_{aid}", "type": "text"}],
                })
                elements.append({
                    "type": "text", "id": f"t_{aid}", "x": ax + 230, "y": ay + 20,
                    "width": 60, "height": 20, "text": "", "fontSize": 14,
                    "fontFamily": 1, "strokeColor": "#1e1e1e", "containerId": aid,
                    "originalText": "", "autoResize": True,
                })
        doc = {
            "type": "excalidraw", "version": 2, "source": "moon",
            "elements": elements, "appState": {"viewBackgroundColor": "#ffffff"},
        }
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=2))
        return f"Wrote Excalidraw diagram with {len(nodes)} nodes, {len(edges)} edges -> {path}"
