# MOON AI Agent -- Makefile
#
# Common entry points. Run `make help` for the list.

PY := env -u PYTHONPATH .venv/bin/python

.PHONY: help run serve terminal test live voice-test voice voice-install models clean

help:
	@echo "Targets: run serve terminal test live voice-test models clean"

run:
	$(PY) main.py run "$(TASK)" --agent $(AGENT)

serve:
	$(PY) main.py start

terminal:
	$(PY) main.py start

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
