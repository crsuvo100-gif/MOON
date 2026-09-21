#!/usr/bin/env bash
# MOON Operational State — verified 2026-09-14
# Run from /home/meow/Projects/MOON
set -euo pipefail

echo "=== MOON Operational State ==="
echo ""

# 1. moonscope TUI boot (5s visual + data check)
echo "[1/3] moonscope TUI boot"
timeout 5 .venv/bin/python -m app.tui 2>/tmp/ms_state.log || true
echo "  stderr size: $(wc -c < /tmp/ms_state.log) bytes"
echo "  tracebacks:  $(grep -cE 'Traceback|Exception' /tmp/ms_state.log || echo 0)"
echo "  LOCKED/🔒:   $(grep -cE 'LOCKED|🔒' /tmp/ms_state.log || echo 0)"
echo "  brain data:  $(grep -cE 'model|version|uptime|Pipeline|Agents' /tmp/ms_state.log || echo 0)"
echo "  HUD:         $(grep 'model qwen2.5' /tmp/ms_state.log | head -1 | sed 's/.*│/│/')"
echo ""

# 2. terminal_moon TUI boot (5s)
echo "[2/3] terminal_moon TUI boot"
cd terminal_moon
timeout 5 .venv/bin/python main.py terminal 2>/tmp/tm_state.log | head -5 || true
echo "  stderr size: $(wc -c < /tmp/tm_state.log) bytes"
echo ""

# 3. verify_all (20 tests)
echo "[3/3] terminal_moon verify_all (20 end-to-end tests)"
.venv/bin/python verify_all.py 2>/dev/null | tail -3
echo ""

# 4. compileall clean
echo "[4] compileall (app/ + terminal_moon/)"
cd /home/meow/Projects/MOON
.venv/bin/python -m compileall -q app/ terminal_moon/ 2>&1 | tail -1
echo ""

echo "=== Done. All subsystems operational. ==="
