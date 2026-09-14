"""
logging helper for MOON Terminal.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.config.settings import get_settings


def get_logger(name: str = "moontm") -> logging.Logger:
    settings = get_settings()
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
    file_h = logging.FileHandler(settings.log_file, encoding="utf-8")
    file_h.setFormatter(fmt)
    logger.addHandler(file_h)

    return logger
