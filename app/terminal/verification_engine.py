"""Verification engine – post‑execution checks.

The engine receives the original ``ExecutionRequest`` and the raw backend
response dictionary (as produced by ``LocalBackend``).  It returns a tuple
``(verified: bool, result: dict)``.

The default implementation performs a very small set of generic checks:

* ``exit_code == 0`` – a non‑zero exit is always a verification failure.
* If a ``verification`` spec is present in the request, the engine dispatches
  to a tiny plug‑in system that knows how to handle a few built‑in types
  (currently ``file_exists`` and ``http_status``).  The spec format is a dict:

  ``{"type": "file_exists", "path": "/tmp/out"}``

  ``{"type": "http_status", "url": "https://example.com", "code": 200}``

  Adding new verification types is a matter of extending the ``_handlers``
  mapping.

If no spec is provided, the engine simply returns ``verified = True`` when the
exit code is zero.
"""

from __future__ import annotations

import os
import requests
from pathlib import Path
from typing import Dict, Tuple, Callable


class VerificationEngine:
    """Simple, extensible verification of command results.

    The public ``verify`` method returns ``(bool, dict)`` where the dict holds
    any additional verification payload (e.g. file size, HTTP response body).
    """

    def __init__(self):
        # Mapping ``type`` → callable(request, resp) -> (bool, dict)
        self._handlers: Dict[str, Callable[[Dict, Dict], Tuple[bool, Dict]]] = {
            "file_exists": self._verify_file_exists,
            "http_status": self._verify_http_status,
        }

    # -------------------------------------------------------------------
    # Built‑in verification handlers
    # -------------------------------------------------------------------
    def _verify_file_exists(self, request: Dict, resp: Dict) -> Tuple[bool, Dict]:
        spec = request.get("verification", {})
        path = spec.get("path")
        if not path:
            return False, {"error": "no path supplied in verification spec"}
        exists = Path(path).exists()
        return exists, {"path": str(path), "exists": exists}

    def _verify_http_status(self, request: Dict, resp: Dict) -> Tuple[bool, Dict]:
        spec = request.get("verification", {})
        url = spec.get("url")
        expected = spec.get("code")
        if not url or expected is None:
            return False, {"error": "missing url or code in spec"}
        try:
            r = requests.get(url, timeout=5)
            ok = r.status_code == expected
            return ok, {"url": url, "expected": expected, "got": r.status_code}
        except Exception as exc:
            return False, {"error": str(exc)}

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------
    def verify(self, request: Dict, resp: Dict) -> Tuple[bool, Dict]:
        """Verify execution result.

        - Fails if ``exit_code`` != 0.
        - If a ``verification`` spec is provided, dispatch to the appropriate handler.
        - Otherwise success when ``exit_code`` == 0.
        """
        # Basic exit‑code check – non‑zero always fails verification.
        if resp.get("exit_code") != 0:
            return False, {"error": f"exit_code={resp.get('exit_code')}"}
        # If no verification spec, success.
        spec = request.get("verification")
        if not spec:
            return True, {}
        vtype = spec.get("type")
        handler = self._handlers.get(vtype)
        if not handler:
            return False, {"error": f"unknown verification type: {vtype}"}
        return handler(request, resp)

# End of verification_engine.py
