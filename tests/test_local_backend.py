import unittest
from pathlib import Path
import os, sys, glob

# Ensure hermes_tools package is discoverable – it lives in the Hermes cache directory.
if "~/.hermes/cache/scratch" not in sys.path:
    sys.path.append(os.path.expanduser('~/.hermes/cache/scratch'))
for p in glob.glob(os.path.expanduser('~/.hermes/cache/scratch/*/hermes_tools.py')):
    sys.path.append(os.path.dirname(p))
    break

from app.terminal.models import ExecutionRequest
from app.terminal.backend_manager import BackendManager

class TestLocalBackend(unittest.TestCase):
    def setUp(self):
        self.manager = BackendManager()

    def test_foreground_echo(self):
        req = ExecutionRequest(
            command="echo hello",
            cwd=Path('.'),
            backend="local",
            shell=False,
            background=False,
        )
        res = self.manager.execute(req)
        self.assertEqual(res.status, "success")
        self.assertIn("hello", res.stdout.strip())

if __name__ == "__main__":
    unittest.main()
