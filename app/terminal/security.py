"""Security utilities for terminal commands.

Provides `sanitize_command` which redacts secret-like tokens from a command string.

The function uses `shlex.split` to safely parse the command into tokens, then
replaces any token that matches common secret keywords (case‑insensitive) such
as "key", "token", or "password" with the placeholder "***REDACTED***". The
sanitized tokens are rejoined with spaces to produce a safe command string.
"""

import shlex
import re
from typing import List

# regex to match secret tokens – any token containing these substrings
_SECRET_PATTERN = re.compile(r"(?i)(key|token|password|\*{3})")


def _redact_token(token: str) -> str:
    """Return redacted placeholder if token looks like a secret.

    The check is simple: if the token contains any of the secret keywords we
    replace the whole token with a fixed placeholder.
    """
    if _SECRET_PATTERN.search(token):
        return "***REDACTED***"
    return token


def sanitize_command(command: str) -> str:
    """Redact secrets from a raw command string.

    Parameters
    ----------
    command: str
        The raw command line as entered by the user.

    Returns
    -------
    str
        A potentially modified command where secret‑like tokens have been
        replaced with ``***REDACTED***``. Tokens are parsed using ``shlex`` to
        respect quoting and shell escaping.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        # Fallback – if parsing fails, treat the whole command as a single token.
        tokens = [command]
    redacted: List[str] = [_redact_token(t) for t in tokens]
    return " ".join(redacted)
