import subprocess
import sys
from pathlib import Path
import shutil
import pytest

@pytest.fixture
def repo_copy(tmp_path):
    """Copy the entire repository into a temporary directory for isolation."""
    src = Path(__file__).resolve().parents[2]  # project root
    dst = tmp_path / "MOON"
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return dst

def test_acceptance_flow(repo_copy):
    """Run the acceptance_test.py script and verify success and a summary.
    The script should exit with 0 and print a summary containing the word
    'Summar' or 'All tests passed'.
    """
    # The repo may contain a top-level 'MOON' package directory.
    script = repo_copy / "scripts" / "acceptance_test.py"
    if not script.is_file():
        # Fallback to nested layout where the package resides in a 'MOON' subdirectory.
        script = repo_copy / "MOON" / "scripts" / "acceptance_test.py"
    script.chmod(0o755)
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"Non-zero exit: {result.returncode}\n{result.stderr}"
    assert "Summar" in result.stdout or "All tests passed" in result.stdout, "No summary report found"
