#!/usr/bin/env bash
# Live, non-destructive mitigations for Intel Ice Lake eDP panel flicker.
# Reversible (revert: xset +dpms; xset s on; xrandr --output eDP-1 --mode 1366x768 --rate 60).
set -e
echo "== [1] Disable DPMS (no panel power-state transitions) =="
xset -dpms || true
echo "== [2] Disable X screensaver blank timeout =="
xset s off || true
xset s 0 0 || true
echo "== [3] Re-assert stable 60Hz mode on eDP-1 (avoid PSR-only 40Hz) =="
xrandr --output eDP-1 --mode 1366x768 --rate 60 || true
echo "== [4] Report resulting state =="
echo "--- DPMS/blank ---"
xset q | sed -n '/DPMS/,/^$/p'
echo "--- eDP mode ---"
xrandr | grep -A1 "eDP-1 connected"
echo "DONE: live mitigations applied."
