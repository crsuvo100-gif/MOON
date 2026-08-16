#!/usr/bin/env bash
# Install MOON's terminal backend as a systemd *user* service so it:
#   - starts automatically on login
#   - restarts itself if it ever crashes
#   - (with `loginctl enable-linger`) keeps running after logout
#
# Usage:
#   ./tools/install_terminal_service.sh          # install + enable + start
#   ./tools/install_terminal_service.sh --stop   # stop the service
#   ./tools/install_terminal_service.sh --status # show status
#
# Safe / additive: only writes to ~/.config/systemd/user and enables the unit.
set -euo pipefail

MOON_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SVC_SRC="$MOON_HOME/deploy/moon-terminal.service"
SVC_DIR="$HOME/.config/systemd/user"
SVC_DST="$SVC_DIR/moon-terminal.service"

if [[ "${1:-}" == "--status" ]]; then
  systemctl --user status moon-terminal.service --no-pager || true
  exit 0
fi

if [[ "${1:-}" == "--stop" ]]; then
  systemctl --user stop moon-terminal.service || true
  echo "MOON terminal service stopped."
  exit 0
fi

echo "MOON home: $MOON_HOME"
mkdir -p "$SVC_DIR"

# Substitute the repo path into the unit template.
sed "s|__MOON_HOME__|$MOON_HOME|g" "$SVC_SRC" > "$SVC_DST"
echo "Wrote $SVC_DST"

systemctl --user daemon-reload
systemctl --user enable moon-terminal.service
systemctl --user restart moon-terminal.service

# Keep running after logout if the user allows lingering.
if command -v loginctl >/dev/null 2>&1; then
  loginctl enable-linger "$(id -un)" 2>/dev/null || true
fi

sleep 4
echo "--- status ---"
systemctl --user is-active moon-terminal.service || true
echo "--- health ---"
curl -s --max-time 5 -o /dev/null -w 'MOON terminal HTTP %{http_code}\n' http://127.0.0.1:8777/ || true
echo
echo "Done. The MOON terminal now auto-starts on login and survives crashes."
echo "Manage it with: systemctl --user {status|restart|stop|disable} moon-terminal.service"
