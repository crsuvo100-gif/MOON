"""Factory for selecting the appropriate memory store backend.

Environment variable ``MOON_MEMORY_BACKEND`` determines which concrete
implementation is instantiated:

* ``local`` (default) → :class:`LocalMemoryStore`
* ``cloud`` → :class:`CloudMemoryStore` (in‑memory stub; replace with a real
  remote backend in production).

The function returns a singleton instance so that the same store is used
throughout the process.
"""

from __future__ import annotations

import os
from typing import Final

from .store import LocalMemoryStore
from .cloud_store import CloudMemoryStore


_BACKEND_ENV_VAR: Final = "MOON_MEMORY_BACKEND"
_DEFAULT_BACKEND: Final = "local"

# Cache the singleton after first creation.
_instance: LocalMemoryStore | CloudMemoryStore | None = None


def memory_store_factory() -> LocalMemoryStore | CloudMemoryStore:
    """Return the configured memory store.

    The result is cached; subsequent calls return the same object.
    """
    global _instance
    if _instance is not None:
        return _instance

    backend = os.getenv(_BACKEND_ENV_VAR, _DEFAULT_BACKEND).lower()
    if backend == "cloud":
        _instance = CloudMemoryStore()
    else:
        # Fallback to local SQLite regardless of typo or unknown value.
        _instance = LocalMemoryStore()
    return _instance

__all__ = ["memory_store_factory", "_BACKEND_ENV_VAR", "_DEFAULT_BACKEND"]
