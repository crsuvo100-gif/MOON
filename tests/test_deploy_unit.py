"""Regression tests for the installed MOON control-plane service."""

from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "deploy" / "moon-terminal.service"


def _unit() -> ConfigParser:
    parser = ConfigParser(interpolation=None)
    parser.read_string(UNIT.read_text(encoding="utf-8"))
    return parser


def test_control_plane_unit_starts_asgi_backend() -> None:
    """Systemd must own the API server, never the interactive terminal UI."""
    exec_start = _unit()["Service"]["execstart"]

    assert "-m uvicorn app.terminal_interface:app" in exec_start
    assert "main.py terminal" not in exec_start
    assert "--host 127.0.0.1" in exec_start
    assert "--port 8777" in exec_start


def test_control_plane_unit_is_restartable_and_installable() -> None:
    unit = _unit()

    assert unit["Service"]["restart"] == "always"
    assert unit["Install"]["wantedby"] == "default.target"
