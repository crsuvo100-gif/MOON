import subprocess
import sys
from pathlib import Path
import shutil
import pytest

@pytest.fixture
def repo_copy(tmp_path):
    """Copy the entire repository into a temporary directory for isolation.

    The copy is selective (settings exclude tool caches, version control and
    virtualenv directories) so the fixture stays fast on large monorepos.
    """
    src = Path(__file__).resolve().parents[2]  # project root
    dst = tmp_path / "MOON-AI"
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".git", ".gitnexus", ".hermes", "node_modules",
            ".pre_commit_checkpoint", ".venv", "build", "dist", "MOON-AI_HOME",
            "*.egg-info", "backups", "data", "deploy", "skills", "regexr", "voices",
            "moon_ui", "web", ".claude", ".claude-plugin", ".github", ".vscode",
            ".pytest_cache", ".moon", ".moon_logs",
        ),
    )
    return dst

def test_acceptance_flow(repo_copy):
    """Run the acceptance_test.py script and verify success and a summary.
    The script should exit with 0 and print a summary containing the word
    'Summar' or 'All tests passed'.
    """
    # The repo may contain a top-level 'MOON-AI' package directory.
    script = repo_copy / "scripts" / "acceptance_test.py"
    if not script.is_file():
        # Fallback to nested layout where the package resides in a 'MOON-AI' subdirectory.
        script = repo_copy / "MOON-AI" / "scripts" / "acceptance_test.py"
    script.chmod(0o755)
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"Non-zero exit: {result.returncode}\n{result.stderr}"
    assert "Summar" in result.stdout or "All tests passed" in result.stdout, "No summary report found"
