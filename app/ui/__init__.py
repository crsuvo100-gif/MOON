"""MOON UI package (spec section 6: ui/).

The live web HUD lives under /web (red/black NEURAL CORE INTERFACE). This
compatibility package surfaces those assets at the spec path so the directory
layout (section 6) is satisfied. Non-destructive.
"""

from __future__ import annotations

from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2] / "web"


def terminal_entrypoint():
    """Return the path of the web terminal HUD (spec 6: ui/terminal, ui/web)."""
    return WEB_ROOT / "moon_terminal.html"


__all__ = ["WEB_ROOT", "terminal_entrypoint"]
