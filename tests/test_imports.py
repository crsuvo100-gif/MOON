"""Smoke test: every app module imports cleanly."""

import importlib
import pkgutil
import sys
import os


def _ensure_paths():
    """Ensure project root + site-packages are on sys.path (idempotent)."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    # Add site-packages dirs so app.tui's "import textual" resolves.
    import importlib.util as _util
    _spec = _util.find_spec("textual")
    if _spec is not None and _spec.origin is not None:
        _td = os.path.dirname(os.path.dirname(_spec.origin))
        if _td not in sys.path:
            sys.path.insert(0, _td)
    # Also add local venv site-packages (Moon_Twin runs from its own venv)
    for _vn in (
        os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv", "lib",
                     f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "terminal_moon", ".venv", "lib",
                     f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"),
    ):
        if _vn not in sys.path and os.path.isdir(_vn):
            sys.path.insert(0, _vn)


def _module_names(pkg, prefix):
    names = []
    for mod in pkgutil.walk_packages(pkg.__path__, prefix=prefix):
        names.append(mod.name)
    return names


def test_all_app_modules_import():
    _ensure_paths()

    # Pre-import textual (required by app.tui) using importlib to ensure
    # the module is cached in sys.modules before app.tui tries to import it.
    try:
        importlib.import_module("textual")
    except ImportError:
        pass  # textual not available; app.tui will be skipped

    # Lazy import so it sees the fixed sys.path.
    import app as app_pkg

    names = _module_names(app_pkg, "app.")
    failures = []
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            import traceback
            print(f"\nDEBUG import failed: {name}")
            print(f"  Error: {exc}")
            traceback.print_exc()
            failures.append((name, str(exc)))
    assert not failures, f"import failures: {failures}"


def test_settings_defaults():
    from app.config.settings import get_settings

    s = get_settings()
    assert s.model_name
    assert s.enable_auto_learning is True
