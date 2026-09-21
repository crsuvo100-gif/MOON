"""MOON Python-first console entry shim.

This thin package lets operators run MOON as a module:

    python -m moon <command>

It simply delegates to the project's real CLI entrypoint in ``main.py``
(``main:main``), which is the canonical, fully-functional application. Nothing
here re-implements MOON -- it is a portable, cross-platform launcher so the
project does not depend on a shell wrapper to start.

The actual application lives in the ``app`` package; ``main.py`` is the CLI
front-end. Both remain the single source of truth.
"""
