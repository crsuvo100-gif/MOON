# MOON AI Agent -- Makefile
#
# Common entry points. Run `make help` for the list.

PY := env -u PYTHONPATH .venv/bin/python

.PHONY: help run serve terminal test live voice-test voice voice-install models nexus clean

help:
	@echo "Targets: run serve terminal test live voice-test models nexus clean"

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

# Additive NEXUS avatar-terminal bridge (wired to MOON's real brain).
# Runs on :8765/:8787 by default; pass NEXUS_WS_PORT / NEXUS_UI_PORT to override.
nexus:
	$(PY) web/nexus/run_nexus_bridge.py --ws-port $(or $(NEXUS_WS_PORT),8765) --ui-port $(or $(NEXUS_UI_PORT),8787)

nexus-ui-only:
	$(PY) web/nexus/run_nexus_bridge.py --no-moon --ws-port $(or $(NEXUS_WS_PORT),8765) --ui-port $(or $(NEXUS_UI_PORT),8787)

voice-install:
	$(PY) install_moon.py

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache
