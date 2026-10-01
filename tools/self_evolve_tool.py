"""self_evolve_tool.py -- bounded self-evolution: ingest a resource into MOON's KB.

The system prompt says MOON should "evolve automatically from the internet
digital world." This tool makes that concrete and SAFE: given a URL or a
local file/repo, it fetches the text and learns it into MOON's knowledge base
(via the same auto-learning path). It is operator-triggered, not autonomous
crawling -- MOON evolves when Psycho points her at a source.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.tools.base import BaseTool


class SelfEvolveTool(BaseTool):
    name = "self_evolve"
    description = "Ingest a URL or local file into MOON's knowledge base (bounded self-evolution)."

    async def execute(self, source: str = "", max_chars: int = 8000, **kwargs) -> str:
        if not source:
            return "[self_evolve] supply a URL or local path to learn from"
        text = ""
        if urlparse(source).scheme in ("http", "https"):
            try:
                import httpx
                r = httpx.get(source, timeout=20, follow_redirects=True)
                text = re.sub(r"<[^>]+>", " ", r.text)
                text = re.sub(r"\s+", " ", text).strip()
            except Exception as exc:  # noqa: BLE001
                return f"[self_evolve] fetch failed: {exc}"
        else:
            try:
                from pathlib import Path
                p = Path(source)
                if p.is_file():
                    text = p.read_text(errors="replace")
                elif p.is_dir():
                    text = "\n".join(f.read_text(errors="replace") for f in list(p.glob("*.md"))[:10] if f.is_file())
            except Exception as exc:  # noqa: BLE001
                return f"[self_evolve] read failed: {exc}"
        if not text:
            return "[self_evolve] no text extracted"
        text = text[:max_chars]
        # learn into the brain via the orchestrator's consolidator if available
        try:
            from app.brain.orchestrator import Orchestrator
            from app.config.settings import get_settings
            o = Orchestrator(get_settings())
            await o._consolidator.consolidate(prompt=f"learned from {source}", response=text, success=True, agent="moon")
            return f"[self_evolve] ingested {len(text)} chars from {source} into MOON's brain."
        except Exception as exc:  # noqa: BLE001
            return f"[self_evolve] ingested but learn-step skipped: {exc}"
