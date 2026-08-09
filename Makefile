# MOON AI Agent -- Makefile
#
# Common entry points. Run `make help` for the list.

PY := env -u PYTHONPATH .venv/bin/python

.PHONY: help run serve terminal test live voice-test clean

help:
	@echo "Targets: run serve terminal test live voice-test clean"

run:
	$(PY) main.py run "$(TASK)" --agent $(AGENT)

serve:
	$(PY) main.py serve

terminal:
	@echo "The Textual TUI was removed. Use the web UI instead:"
	@echo "  make serve   # then open http://localhost:8000/brain"

test:
	$(PY) -m pytest tests -q

live:
	$(PY) scripts/live_smoke_pipeline.py

voice-test:
	$(PY) scripts/voice_test.py

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache
