"""Plugin loader -- discovers plugin tools under plugins/ and registers them."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_plugins(registry) -> dict:
    """Best-effort: import modules under plugins/ and register BaseTool subclasses."""
    summary: dict[str, int] = {}
    plugins_dir = Path(__file__).resolve().parent
    for mod_file in sorted(plugins_dir.glob("*.py")):
        if mod_file.name in ("__init__.py", "loader.py"):
            continue
        try:
            mod = importlib.import_module(f"plugins.{mod_file.stem}")
            count = 0
            for attr in vars(mod).values():
                from app.tools.base import BaseTool

                if isinstance(attr, type) and issubclass(attr, BaseTool) and attr is not BaseTool:
                    try:
                        registry.register(attr())
                        count += 1
                    except Exception:
                        pass
            summary[mod_file.stem] = count
        except Exception as exc:  # noqa: BLE001
            logger.warning("plugin %s failed: %s", mod_file.stem, exc)
    return summary
