"""ASCII art tool -- text banners via pyfiglet (from the Hermes ascii-art skill).
Graceful fallback to a simple block banner if pyfiglet is not installed."""

from __future__ import annotations

from app.tools.base import BaseTool, ToolResult


class AsciiArtTool(BaseTool):
    name = "ascii_art"
    description = "Render text as ASCII art banner (pyfiglet; fallback block style)."

    async def execute(self, text: str = "", font: str = "standard", **kwargs) -> str:
        if not text:
            return "[no text]"
        try:
            from pyfiglet import Figlet

            return Figlet(font=font).renderText(text)
        except Exception:
            # dependency-free fallback: uppercase + border
            line = text.upper()
            bar = "+-" + "-" * (len(line) + 2) + "-+"
            return f"{bar}\n| {line} |\n{bar}"
