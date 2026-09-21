#!/usr/bin/env bash
# MOON health script (spec section 6: scripts/health.sh)
# Reports backend health, agent/tool counts, and factory status.
set -uo pipefail
PORT="${MOON_PORT:-8777}"
echo "==> MOON health (http://127.0.0.1:$PORT/health)"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:$PORT/health" 2>/dev/null || echo "000")
if [ "$code" = "200" ]; then
  echo "backend: OK ($code)"
else
  echo "backend: DOWN ($code)"
  exit 1
fi
echo "agents (registry): $(curl -s --max-time 5 'http://127.0.0.1:'$PORT'/api/registry/agents' | python3 -c 'import sys,json;print(json.load(sys.stdin).get("total","?"))' 2>/dev/null || echo '?')"
echo "factory components: $(curl -s --max-time 5 'http://127.0.0.1:'$PORT'/api/factory/components' | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("components",{})))' 2>/dev/null || echo '?')"
