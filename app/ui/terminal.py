"""Terminal UI (spec 6: ui/terminal.py). The live terminal surface is the
websocket terminal in app.terminal_interface (mounted at /ws)."""
from app.ui import terminal_entrypoint  # noqa: F401
__all__ = ["terminal_entrypoint"]
