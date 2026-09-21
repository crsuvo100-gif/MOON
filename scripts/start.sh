#!/usr/bin/env bash
# MOON start script (spec section 6: scripts/start.sh)
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> MOON start"
exec make terminal
