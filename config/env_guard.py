"""env_guard.py -- decontaminate the process environment at launch.

When MOON is launched from a shell that has PYTHONPATH pointing at a *foreign*
virtualenv (e.g. the Hermes agent environment on this host), naive imports can
resolve packages from that foreign venv and crash with confusing errors
(e.g. "No module named 'pydantic_core._pydantic_core'"). This guard strips
PYTHONPATH so the interpreter always uses MOON's own .venv. Import it FIRST,
before importing anything else.
"""

from __future__ import annotations

import os
import sys


def decontaminate_pythonpath() -> None:
    """Remove PYTHONPATH so only the active interpreter's stdlib + site-packages
    are used. Safe to call multiple times; idempotent."""
    os.environ.pop("PYTHONPATH", None)
    # Also clear any sys.path entries that point outside this interpreter's
    # prefix (defensive: only when a foreign PYTHONPATH leaked into sys.path).
    try:
        base = os.path.realpath(sys.prefix)
        suspicious = [p for p in sys.path if p and "site-packages" in p
                      and base not in os.path.realpath(p)]
        for p in suspicious:
            if p in sys.path:
                sys.path.remove(p)
    except Exception:  # noqa: BLE001
        pass


# Run immediately on import.
decontaminate_pythonpath()
