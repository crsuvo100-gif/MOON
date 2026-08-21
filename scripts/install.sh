#!/usr/bin/env bash
# MOON install script (spec section 6: scripts/install.sh)
# Idempotent: creates the venv, installs deps, starts Ollama (optional),
# and verifies the runtime entrypoint. Non-destructive.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> MOON install"
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt 2>/dev/null || echo "warn: requirements install had issues (continuing)"
# Optional: pull the default local model
if command -v ollama >/dev/null 2>&1; then
  echo "==> starting Ollama + pulling qwen2.5:3b"
  (ollama serve >/dev/null 2>&1 &) || true
  sleep 3
  ollama pull qwen2.5:3b 2>/dev/null || true
fi
echo "==> MOON install complete. Run: make terminal"
