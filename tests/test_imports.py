"""Smoke test: every app module imports cleanly."""

import importlib
import pkgutil
from pathlib import Path

import app as app_pkg


def _module_names(pkg, prefix):
    names = []
    for mod in pkgutil.walk_packages(pkg.__path__, prefix=prefix):
        names.append(mod.name)
    return names


def test_all_app_modules_import():
    names = _module_names(app_pkg, "app.")
    failures = []
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            failures.append((name, str(exc)))
    assert not failures, f"import failures: {failures}"


def test_settings_defaults():
    from app.config.settings import get_settings

    s = get_settings()
    assert s.model_name
    assert s.enable_auto_learning is True
