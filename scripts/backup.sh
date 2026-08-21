#!/usr/bin/env bash
# MOON backup script (spec section 6: scripts/backup.sh)
# Snapshots the data/ directory (agents, knowledge, memory, skills, evaluations,
# logs) and the agent_factory sqlite into timestamped archives. Non-destructive.
set -uo pipefail
cd "$(dirname "$0")/.."
TS=$(date +%Y%m%d_%H%M%S)
DEST="backups/moon_${TS}"
mkdir -p "$DEST"
echo "==> MOON backup -> $DEST"
[ -d data ] && cp -r data "$DEST/data" 2>/dev/null || true
[ -f data/agents/agent_factory.db ] && cp data/agents/agent_factory.db "$DEST/" 2>/dev/null || true
[ -f moon_settings.json ] && cp moon_settings.json "$DEST/" 2>/dev/null || true
echo "==> backup complete: $DEST"
