#!/usr/bin/env bash
# MOON stop script (spec section 6: scripts/stop.sh)
# Stops the backend process listening on the MOON port (default 8777).
set -uo pipefail
PORT="${MOON_PORT:-8777}"
PIDS=$(ss -ltnp 2>/dev/null | grep ":$PORT" | grep -oP 'pid=\K[0-9]+' | sort -u || true)
if [ -z "$PIDS" ]; then
  echo "MOON not running on :$PORT"
  exit 0
fi
echo "==> stopping MOON (pids: $PIDS)"
for p in $PIDS; do kill -9 "$p" 2>/dev/null || true; done
rm -f /tmp/moon_hud_open.lock 2>/dev/null || true
echo "==> MOON stopped"
