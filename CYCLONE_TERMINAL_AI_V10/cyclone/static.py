"""Serving the Cyclone UI static assets under MOON's web tree.

Returns a Starlette ``StaticFiles`` mount that serves every file inside the
Cyclone directory (index.html, hud.html, ui.html, app.js, styles.css,
config.js, assets, ...).  MOON mounts it at ``/cyclone``.
"""

from __future__ import annotations

from fastapi.staticfiles import StaticFiles

from .config import CYCLONE_DIR


def get_cyclone_static_files() -> StaticFiles:
    return StaticFiles(directory=CYCLONE_DIR, follow_symlink=True, html=True)
