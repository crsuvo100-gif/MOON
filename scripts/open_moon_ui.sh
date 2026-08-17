#!/usr/bin/env bash
# Open MOON's Neural Core HUD in Chromium on login (kiosk-style, no chrome UI).
# Waits for the backend to be reachable, then launches the browser once.
set -euo pipefail

URL="http://127.0.0.1:8777/"
CHROME="$(command -v google-chrome || command -v google-chrome-stable || command -v chromium || command -v chromium-browser || true)"

# Wait up to ~30s for the MOON backend to answer (it auto-starts via the
# moon-terminal systemd user service; this just paces the browser launch).
for _ in $(seq 1 30); do
  if curl -s -o /dev/null --max-time 2 "$URL"; then break; fi
  sleep 1
done

# Prefer app/kiosk mode. --app gives a clean chromeless window on the HUD.
exec "$CHROME" --no-sandbox --disable-gpu --app="$URL" \
  --window-size=1366,768 --start-maximized \
  --disable-infobars --no-first-run --no-default-browser-check 2>/dev/null || \
exec "$CHROME" --no-sandbox --disable-gpu "$URL" 2>/dev/null
