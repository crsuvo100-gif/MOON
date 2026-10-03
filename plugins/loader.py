"""Plugin loader (spec 45).

Spec 45: a new agent/tool must be able to register itself WITHOUT rewriting the
Main Brain. MOON's orchestrator already calls ``load_plugins(registry)`` at
setup, but the module had been removed, so plugin discovery silently no-op'd
(the import is inside a try/except).

Discovery order:
  1. ``plugins/`` at the project root -- every ``*.py`` that defines a
     ``BaseTool`` subclass or an explicit ``register(registry)`` hook.
  2. ``plugins/generated/`` -- tools written at runtime by the capability
     manager / agent factory.

Contract for a plugin file (any one of):
  * define ``register(registry) -> None``
  * expose ``PLUGIN`` / ``TOOLS`` (a BaseTool instance or list of them)
  * subclass ``app.tools.base.BaseTool`` and have a no-arg constructor

Failures are reported per-file and never abort startup (spec 51: a bad plugin
must not take MOON down).
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_PLUGIN_DIRS = [_ROOT / "plugins", _ROOT / "plugins" / "generated"]


def _load_module(path: Path):
    """Import a plugin file under a unique, non-colliding module key.

    A stable key per file plus ``sys.modules.pop`` before exec avoids the
    stale-module-cache bug where a second load in the same process silently
    reuses the previous module object.
    """
    key = f"moon_plugin_{path.stem}_{abs(hash(str(path))) % 10**8}"
    sys.modules.pop(key, None)
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _tools_from_module(mod: Any) -> list[Any]:
    """Collect tool instances a plugin module exposes."""
    out: list[Any] = []
    # explicit PLUGIN / TOOLS export
    for attr in ("PLUGIN", "TOOLS", "TOOL"):
        obj = getattr(mod, attr, None)
        if obj is None:
            continue
        out.extend(obj if isinstance(obj, (list, tuple)) else [obj])
    # BaseTool subclasses with a no-arg constructor
    try:
        from app.tools.base import BaseTool
    except Exception:  # noqa: BLE001
        BaseTool = None  # type: ignore
    if BaseTool is not None:
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if obj is BaseTool or not issubclass(obj, BaseTool):
                continue
            if obj.__module__ != mod.__name__:
                continue  # imported, not defined here
            try:
                sig = inspect.signature(obj)
                if any(p.default is inspect.Parameter.empty
                       and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                       for p in sig.parameters.values()):
                    continue
                out.append(obj())
            except Exception as exc:  # noqa: BLE001
                logger.debug("plugin %s: cannot instantiate %s: %s",
                             mod.__name__, obj.__name__, exc)
    return out


def load_plugins(registry: Any) -> dict[str, bool]:
    """Discover and register plugins into ``registry`` (spec 45).

    Returns ``{filename: loaded?}`` so callers can log/report what happened.
    """
    summary: dict[str, bool] = {}
    seen: set[str] = set()

    for d in _PLUGIN_DIRS:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.py")):
            if path.name.startswith("_") or path.name in seen:
                continue
            seen.add(path.name)
            try:
                mod = _load_module(path)
                if mod is None:
                    summary[path.name] = False
                    continue
                registered = False
                # 1. explicit register() hook wins
                hook = getattr(mod, "register", None)
                if callable(hook):
                    try:
                        hook(registry)
                        registered = True
                    except Exception as exc:  # noqa: BLE001
                        logger.info("plugin %s register() failed: %s", path.name, exc)
                # 2. declarative tool exports
                for tool in _tools_from_module(mod):
                    try:
                        registry.register(tool)
                        registered = True
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("plugin %s: register tool failed: %s", path.name, exc)
                summary[path.name] = registered
            except Exception as exc:  # noqa: BLE001
                logger.info("plugin %s load skipped: %s", path.name, exc)
                summary[path.name] = False
    return summary


__all__ = ["load_plugins"]
