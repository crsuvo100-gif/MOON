"""
env_guard — strip foreign-venv PYTHONPATH on import so this project's own
packages resolve first. Imported FIRST in main.py before any other imports.
"""
from __future__ import annotations

import os
import sys

# Default allowed roots — always keep these
_STDLIB_ROOTS = frozenset([
    os.path.dirname(os.__file__),           # stdlib
    os.path.dirname(sys.executable),        # venv/bin or system python
    os.path.dirname(os.path.dirname(sys.executable)),  # venv parent
])

_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _guard() -> None:
    """Remove PYTHONPATH entries that point outside this project or stdlib."""
    kept: list[str] = []
    for p in sys.path:
        if not p:
            kept.append(p)
            continue
        real = os.path.realpath(p)
        # Keep stdlib / venv paths
        if any(real.startswith(r) for r in _STDLIB_ROOTS):
            kept.append(p)
            continue
        # Keep editable install entry (the project itself)
        if _proj_root in real or real.startswith(_proj_root + os.sep):
            kept.append(p)
            continue
        # Keep anything inside site-packages
        if "site-packages" in real:
            kept.append(p)
            continue
        # Everything else (foreign venv PYTHONPATH) — drop
    sys.path[:] = kept


_guard()
