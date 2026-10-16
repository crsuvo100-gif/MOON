# Contributing to MOON

Thank you for contributing to MOON, the neural brain command center.

## Getting Started
- Clone the repo: `git clone git@github.com:crsuvo100-gif/MOON.git`
- Install: `./install.sh` or `pip install -e .`
- Verify: `moon doctor`

## Development
- Branch naming: `feature/`, `fix/`, `docs/`
- All PRs must pass CI (GitHub Actions)
- Tests: `python -m pytest tests -q`

## Code Style
- Python 3.14+ (primary venv in `.venv`)
- Type hints required
- Docstrings required for all public functions

## Architecture
- `main.py` -- CLI entry point
- `app/` -- core application modules
- `app/orchestrator/` -- agent orchestration
- `app/api/` -- REST/WS API
- `app/terminal/` -- TUI and web UI

## Pull Request Process
1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Run tests: `python -m pytest tests -q`
5. Submit a PR

## Code of Conduct
- Be respectful
- Keep discussions focused on technical merit
- No personal attacks or harassment

## Contact
- Maintainer: crsuvo100-gif
- GitHub: https://github.com/crsuvo100-gif/MOON
