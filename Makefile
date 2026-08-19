# MOON AI Agent -- Makefile
#
# Common entry points. Run `make help` for the list.

PY := env -u PYTHONPATH .venv/bin/python

.PHONY: help run serve terminal test live voice-test voice voice-install models clean install start deploy

help:
	@echo "Targets: run serve terminal test live voice-test models install start clean"
	@echo "  install   - install Ollama systemd service (sudo make install)"
	@echo "  start     - launch MOON (ensures Ollama is up first)"

run:
	$(PY) main.py run "$(TASK)" --agent $(AGENT)

serve:
	python3 scripts/moon_launcher.py terminal

terminal:
	python3 scripts/moon_launcher.py terminal

# Install MOON's model backend (Ollama) as a service. Uses sudo when not root.
install:
	@echo "== Installing Ollama service (model backend for MOON) =="
	@python3 scripts/install_ollama.py

# Launch MOON anywhere: boots Ollama if needed, then MOON's terminal UI.
start:
	@python3 scripts/moon_launcher.py $(MODE)

test:
	$(PY) -m pytest tests -q

live:
	$(PY) scripts/live_smoke_pipeline.py

voice-test:
	$(PY) -c "import asyncio; from app.voice import Voice; w=asyncio.run(Voice(preset='seductive').speak('Hello, I am MOON.')); print('female voice WAV:', w)"

voice:
	$(PY) scripts/voice_loop.py

models:
	$(PY) main.py models

voice-install:
	$(PY) install_moon.py

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache
