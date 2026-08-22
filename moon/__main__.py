"""``python -m moon`` console entry point.

Delegates to the real MOON CLI (``main.main``). The MOON application is Python
and this shim exists only so the canonical invocation ``python -m moon`` works
on Linux / macOS / Windows without a shell script.
"""
from __future__ import annotations

import sys


def main() -> None:
    # Import the real CLI front-end. ``main.py`` is at the project root and is
    # already on sys.path when invoked via ``python -m moon`` from the root.
    import main

    main.main()


if __name__ == "__main__":
    main()
