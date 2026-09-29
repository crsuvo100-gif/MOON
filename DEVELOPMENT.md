# MOON — Development Guide

## Prerequisites

- Python 3.10+
- Git
- Ollama (for local LLM)
- Chromium/Chrome (for HUD, optional)

## Setup for Development

```bash
git clone https://github.com/crsuvo100-gif/MOON.git
cd MOON
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-optional.txt
pip install -e .
pip install pytest pytest-asyncio          # for running tests
python setup_wizard.py --yes               # create .env with defaults
```

## Running Tests

```bash
# All tests
make test
# or:
python -m pytest tests -q

# Specific test file
python -m pytest tests/test_imports.py -v

# With coverage (if installed)
python -m pytest tests --cov=app --cov-report=term-missing
```

### Test Categories

| Directory | Focus |
|-----------|-------|
| `tests/unit/` | Individual component unit tests |
| `tests/integration/` | Component communication tests |
| `tests/agent/` | Agent planning, execution, memory, recovery |
| `tests/runtime/` | Runtime subsystem tests |
| `tests/security/` | Security boundary tests |
| `tests/test_*.py` | Feature-specific tests |

Total: **130 tests**

---

## Code Structure

```
MOON/
├── main.py              # Entry point
├── engine.py            # Core agent engine
├── app/                 # Core application
│   ├── __init__.py
│   ├── voice.py         # TTS
│   ├── memory.py        # Memory system
│   └── ...
├── src/
│   ├── agents/          # 50+ specialist agents
│   │   ├── __init__.py
│   │   ├── base.py       # Base agent class
│   │   ├── general.py    # General-purpose agent
│   │   ├── cyber/        # Red-team agents
│   │   ├── research/     # Research agents
│   │   ├── coding/       # Coding agents
│   │   ├── security/     # Security agents
│   │   ├── voice/        # Voice agents
│   │   ├── admin/        # Admin agents
│   │   ├── creative/     # Creative agents
│   │   └── monitor/      # Monitor agents
│   └── tools/            # Tool registry
│       ├── __init__.py
│       ├── tools_core.py
│       ├── tools_pro.py
│       ├── tools_advanced.py
│       └── ...
├── tests/
├── deploy/               # systemd service files
├── scripts/              # Utility scripts
├── install.sh            # Installer
├── install_moon.py      # Python bootstrap
├── install_moon_full.py # Full installer
├── setup_wizard.py      # Config wizard
├── Makefile             # Build targets
└── pyproject.toml       # Package config
```

---

## Adding a New Tool

1. Add the tool function to `src/tools/tools_core.py`, `tools_pro.py`, or `tools_advanced.py`
2. Function must start with `_tool_` prefix
3. Include docstring with description
4. Register in the tool registry
5. Add a test in `tests/`
6. Rebuild the tool registry: the registration is auto-discovered via AST

Example:

```python
def _tool_my_new_tool(params: dict) -> dict:
    """Brief description of what this tool does.

    Args:
        params: dict with expected keys

    Returns:
        dict with result data
    """
    # implementation
    return {"result": "..."}
```

---

## Adding a New Agent

1. Create a new file in the appropriate `src/agents/` subpackage
2. Subclass the base agent
3. Implement the agent's capabilities
4. Register the agent
5. Add a test

---

## Code Style

- Python 3.10+ type hints where practical
- Docstrings on all public functions
- No hard-coded secrets — use environment variables
- Error handling: fail explicitly, never silently swallow errors

---

## Running the Linter

```bash
# ruff (if installed)
ruff check .
ruff format .

# Or let CI handle it
```

---

## Submitting Changes

```bash
git add .
git commit -m "desc: what changed and why"
git push origin master
```

TI run tests before pushing:

```bash
make test
```
