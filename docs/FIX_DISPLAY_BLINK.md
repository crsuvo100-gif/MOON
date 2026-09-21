# MOON Display Blink — Root Cause & Fix

Investigated 2026-08-24 on host `Meow` (Kali, Intel Ice Lake Iris Plus G1, eDP-1
1366x768@60, Xorg on :0.0).

## Symptom
The MOON terminal (HUD) "blinks" / flickers repeatedly on the laptop display.

## Root causes found (2 layers)

### 1) MOON systemd crash-loops (DOMINANT cause of the HUD blink)
Two user units were fighting over port :8777 and restarting in tight loops since
boot, which dropped the HUD WebSocket and made the visible Chrome window
open→die→reopen every few seconds:

- `moon-terminal.service` (NRestarts=242): ran `main.py start`, which spawned a
  2nd uvicorn on :8777 — but `moon.service` (uvicorn PID 859) already owned the
  port. Bind failed → `Restart=always` → crash loop. Each loop also reopened the
  Chrome HUD window, which is exactly the "blink".
- `moon-proxy.service` (NRestarts=405): pointed at a STALE path
  (`/home/meow/projectterminal/.../moon_proxy.py`) and a missing log dir
  `/tmp/moon_nexus_logs` → `Failed to set up standard output` → never started →
  crash loop every 3s. (moon_proxy.py does not exist in the real project.)
- `scripts/moon_monitor.py` (self-heal, every 15 min) did `pkill -f
  terminal_interface` on any single health miss — that killed the healthy
  `moon.service` backend, causing the HUD to drop/reconnect.

### 2) OS / Intel i915 panel power management (contributing)
Intel Ice Lake eDP at 60Hz uses Panel Self Refresh (PSR) + RC6 by default. On this
panel/BIOS combo PSR can cause real brightness/blank flicker independent of MOON.
Also DPMS + screensaver blanking could dim/blank the panel.

The HUD's own "CRT blink" animation was ALREADY disabled by the author
(`@keyframes crt` flattened; blink keyframes set to constant opacity), so the HUD
CSS was NOT the cause.

## Fixes applied (verified)

1. `moon-terminal.service` repurposed to run `scripts/open_hud.py` — a dedicated,
   single-instance HUD-window keeper that NEVER starts a backend and never touches
   :8777. `Restart=on-failure` (not `always`).
2. `main.py start` now self-guards: if :8777 is already served, it exits 0
   (attaches HUD only) instead of double-binding. No more bind crash-loop.
3. `moon-proxy.service` disabled + symlink removed (stale path; not part of the
   real project).
4. `scripts/moon_monitor.py` hardened: probes health twice, checks the port before
   touching anything, and NEVER `pkill`s a backend that is already answering.
5. Live GPU mitigation (reversible): `xset -dpms`, `xset s off`, re-assert
   60Hz on eDP-1. Script: `scripts/live_gpu_mitigate.sh`.

Verification (post-fix):
- backend PID 859 stable, NRestarts=0
- `curl /api/health` → HTTP 200
- WS handshake `/ws` → HTTP 101 (live)
- self-heal run once → "backend healthy", did NOT restart it
- 0 restart-flood lines in last 30s across all moon units
- HUD Chrome window: exactly one instance, lockfile consistent

## PERSISTENT GPU fix (needs root + reboot — apply when convenient)
To kill i915 PSR/RC6 flicker permanently, edit `/etc/default/grub`:

  GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_psr=0 i915.enable_rc6=0 i915.enable_dc=0 intel_idle.max_cstate=1"

then: `sudo update-grub` and reboot.

Optional X11 TearFree (stop any compositor tearing) — drop
`/etc/X11/xorg.conf.d/20-intel.conf`:

  Section "Device"
      Identifier "Intel Graphics"
      Driver "modesetting"
      Option "TearFree" "true"
  End Section

To make the live mitigation survive reboots without root, add to your
`~/.xprofile` / `~/.xinitrc`:
  xset -dpms; xset s off
