# MOON — Troubleshooting Guide

## MOON won't start

**Symptom:** `moon terminal` exits immediately or hangs.

**Check:**
```bash
# Is Ollama running?
curl -s http://127.0.0.1:11434/api/tags
# If empty: start Ollama
ollama serve

# Is the model pulled?
ollama list
# If missing: ollama pull <model>

# Check .env
cat .env
# Verify OLLAMA_BASE_URL and OLLAMA_MODEL are set correctly
```

---

## Health check fails

**Symptom:** `curl http://127.0.0.1:8777/api/health` returns error or empty.

**Check:**
```bash
# Is the service running?
systemctl --user status moon-terminal.service

# Check logs
journalctl --user -u moon-terminal.service -n 50 --no-pager

# Port conflict?
ss -tlnp | grep 8777
# If something else is on 8777, change MOON_PORT in .env
```

---

## Model not responding

**Symptom:** MOON responds with "model unavailable" or similar.

**Check:**
```bash
# Is Ollama reachable?
curl http://127.0.0.1:11434/api/tags

# Is the model loaded?
ollama list

# Try a direct Ollama query:
curl http://127.0.0.1:11434/api/generate -d '{"model":"qwen2.5:0.5b","prompt":"hi"}'
```

---

## Import errors / module not found

**Symptom:** `ModuleNotFoundError` or `ImportError` on startup.

**Fix:**
```bash
# Reinstall in editable mode
source .venv/bin/activate
pip install -e .

# Reinstall dependencies
pip install -r requirements.txt

# Check for broken imports
python -c "import importlib, pkgutil, app; [importlib.import_module(m.name) for m in pkgutil.walk_packages(app.__path__,'app.')]"
```

---

## Voice not working

**Symptom:** No audio output, or espeak error.

**Check:**
```bash
# Is espeak installed?
which espeak
# If not: make voice-install

# Test espeak directly:
espeak "Hello" -v f5

# Check SoX:
which sox
# If not: apt install sox (or equivalent)
```

---

## systemd service issues

**Symptom:** Service fails to start or restart.

**Check:**
```bash
# Status
systemctl --user status moon-terminal.service

# Logs
journalctl --user -u moon-terminal.service -n 100 --no-pager

# Reload after config change
systemctl --user daemon-reload
systemctl --user restart moon-terminal.service

# Enable linger (keep running after logout)
loginctl enable-linger $(whoami)
```

---

## Memory database issues

**Symptom:** Memory not persisting, or database errors.

**Check:**
```bash
# Database file exists?
ls -la moon_memory*.db

# Can Python read it?
source .venv/bin/activate
python -c "import sqlite3; conn=sqlite3.connect('moon_memory.db'); print(conn.execute('SELECT count(*) FROM memory').fetchone())"
```

---

## Ollama not starting

**Symptom:** Ollama fails to start or crashes.

**Check:**
```bash
# Is Ollama installed?
which ollama

# Try starting manually:
ollama serve

# Check logs:
cat ~/.ollama/ollama.log 2>/dev/null || true

# Reinstall Ollama:
curl -fsSL https://ollama.com/install.sh | sh
```

---

## Tests failing

**Symptom:** `make test` shows failures.

**Check:**
```bash
# Run specific failing test with verbose output:
python -m pytest tests/path/to/test.py -v --tb=long

# Check if Ollama is available (some tests require it):
curl http://127.0.0.1:11434/api/tags

# Some tests auto-skip when Ollama is unavailable — that's expected
```

---

## Port already in use

**Symptom:** MOON fails to bind to port 8777.

**Fix:**
```bash
# Find what's using the port:
ss -tlnp | grep 8777

# Change MOON_PORT in .env to a different port
# Then restart MOON
```

---

## Getting Help

1. Check this troubleshooting guide first
2. Review service logs: `journalctl --user -u moon-terminal.service`
3. Check MOON health: `curl http://127.0.0.1:8777/api/health`
4. Verify Ollama: `curl http://127.0.0.1:11434/api/tags`
5. Re-run the setup wizard: `python setup_wizard.py`
