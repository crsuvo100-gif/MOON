"""Runtime (spec 6: core/runtime.py). Re-exports the runtime integration spine."""

from app.runtime import integration  # noqa: F401

__all__ = ["integration"]
