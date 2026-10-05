"""Security tests for the MOON terminal.

Covers:
- ``sanitize_command`` correctly redacts secret‑like tokens.
- ``RiskEngine`` evaluates commands using token‑aware matching and returns the
  appropriate risk level.
"""

import pytest
from app.terminal.security import sanitize_command
from app.terminal.risk_engine import RiskEngine
from app.terminal.models import ExecutionRequest

def test_sanitize_redacts_secrets():
    cmd = "curl -H 'Authorization: Bearer my_secret_token' http://example.com"
    sanitized = sanitize_command(cmd)
    assert "***REDACTED***" in sanitized
    assert "my_secret_token" not in sanitized

@pytest.fixture
def risk_engine():
    return RiskEngine()

@pytest.mark.parametrize(
    "command,expected",
    [
        ("rm -rf /", "high"),
        ("sudo apt-get update", "high"),
        ("kill -9 1234", "medium"),
        ("ls -la", "low"),
        ("echo hello; rm -rf /tmp", "high"),
        ("cat ../../etc/passwd", "low"),
    ],
)

def test_risk_engine_levels(risk_engine, command, expected):
    req = ExecutionRequest(command=command)
    assert risk_engine.evaluate(req) == expected
