---
name: moon-nexus-bridge-ops
description: "Operate/debug MOON avatar-terminal brain WS bridge."
category: software-development
---

# moon-nexus-bridge-ops

Operating the **MOON Nexus avatar terminal ↔ brain bridge** — the runtime under
`/home/meow/projectterminal/RED_TEAMING_HACKER_INTERFACE/Moon_AI_AGENT` where a
tkinter avatar terminal (`MOON_NEXUS_FUNCTIONAL_FINAL/MOON_Avatar_Terminal_FINAL/run_nexus.py`)
serves `ws://127.0.0.1:8765/moon` (NEXUS web UI on `:8787`) and the
`MoonNexusBridge` (`moon_agent/integrations/moon_nexus.py`) connects the
`MoonAgent` brain so the avatar can actually speak.

Load this for: "is MOON online", wiring the brain to the avatar, the avatar is
silent / not connected, the WS socket drops, making MOON auto-start.

## The protocol (real, from terminal/server.py)
- Connect → send `{"type":"hello","role":...,"protocol":"MOON_AGENT_BRIDGE/1"}`.
- **Server registers a client into the AGENT set ONLY when `role == "AGENT"`.**
  UI clients use `role:"UI"`. If the bridge omits `role:"AGENT"`, `moon.chat`
  is never forwarded to the brain → avatar silent. This is the #1 breakage.
- UI → terminal: `{"type":"ui.action","action":"moon.chat","payload":{"text":...}}`.
- Terminal forwards to the AGENT as `{"type":"moon.ui.action","action":"moon.chat","text":...}`.
- AGENT replies `{"type":"avatar.speak","text":...}` (+ `avatar.state` around it) on
  its socket; terminal **broadcasts** `avatar.*` to all non-agent clients.
- `moon.system` / `moon.agent.status` / `moon.heartbeat` / `moon.metrics` are
  MOON-owned telemetry: terminal forwards unchanged, never executes.

## Three real bugs + verified fixes
1. **Avatar silent / "MOON Agent is not connected".** Bridge hello omitted
   `"role":"AGENT"` → chat never reached the brain. FIX: add `"role":"AGENT"`.
2. **Status lies `BRAIN: LOCKED` after unlock.** `_agent_status()` read a
   nonexistent `agent.auth.authenticated` (getattr→None→falsy→forced LOCKED).
   Violates the operator's "every state must be real" rule. FIX:
   `locked = bool(getattr(self.agent, "locked", False))`.
3. **WS dies at ~58s (keepalive ping timeout).** Server force-closed when its ping
   went unanswered. On loopback, keepalive is pointless and breaks the link. FIX:
   FIX: `ping_interval=None, ping_timeout=None` on BOTH `websockets.connect(...)` and
   `websockets.serve(...)`. Disable, don't tune.

4. **Gauges dead / brain "connected" but sends NOTHING (replacement server.py dropped
   the telemetry forwarding block).** A freshly dropped-in `terminal/server.py` (e.g. a
   whole new build folder) may be **missing the handler that forwards MOON-owned telemetry
   types**. Symptom: WS handshake works (`terminal.ready` + `hello.ack` arrive), the
   brain's socket is ESTABLISHED and stable, yet the UI receives ZERO `moon.system` /
   `moon.agent.status` / `moon.heartbeat` — ever. Root cause: `process()` has no
   `if typ in ("moon.system","moon.agent.status","moon.heartbeat","moon.metrics")`
   branch, so it falls through to `raise ValueError(f"Unknown message type: {typ}")`.
   The brain's `_metrics_loop` (`moon_nexus.py`, every 2s) sends inside `try/except: break`,
   so the ValueError kills the loop permanently. The OLD server had this block; the
   replacement silently omitted it.
   **Decisive diagnostic (two-client probe):** connect A as AGENT, send a `moon.system`
   message; connect B as UI. If B does NOT receive it, the server is not forwarding
   (reuse `scripts/moon_telemetry_forward_probe.py`).
   **FIX (additive, protocol-preserving — never reinterpret/execute these):** in
   `process()`, before the final `raise ValueError`, add:
   ```python
   if typ in ("moon.system", "moon.agent.status", "moon.heartbeat", "moon.metrics"):
       await self.bus.publish(msg)
       await self.broadcast(msg)
       return
   ```
   After patching, `pkill -f run_nexus.py`; the brain's supervisor relaunches it with the
   fixed code within ~3s. Re-probe: `moon.system` samples appear within ~5s.

## WHOLE-FOLDER BUILD SWAP (replace the terminal build with a new folder)
   When the operator says "put this folder inside MOON and rebuild the terminal from it /
   remove the old terminal build", do NOT hand-merge files. Architecture:
   - `moon_headless.py` is a **systemd user service** (`~/.config/systemd/user/moon.service`,
   `Restart=always`) that, on start, **spawns `run_nexus.py` as a child** with `cwd=AVATAR_DIR`.
   `AVATAR_DIR = REPO / "MOON_NEXUS_FUNCTIONAL_FINAL" / <folder>` (set in `moon_headless.py`).
   - So the **terminal build that runs is whichever folder `AVATAR_DIR` points at**. To swap the
   whole build: copy the new folder into `MOON_NEXUS_FUNCTIONAL_FINAL/`, repoint `AVATAR_DIR`
   to it (one-line edit in `moon_headless.py`), then `systemctl --user restart moon.service`.
   systemd restarts the brain, which spawns the NEW `run_nexus.py`.
   - Killing the brain process makes systemd respawn it (re-spawning the OLD `run_nexus.py`
   until `AVATAR_DIR` is repointed) — so **repoint first, then restart**; a bare `kill` won't stick.
   - Keep the live MOON brain (AGENT) owner: the new `run_nexus.py` must bind the SAME bridge
   port (`:8765`) the brain already knows, so it reconnects with no reconfig.
   - After swap confirm live `cwd`: `ls -l /proc/$(pgrep -f run_nexus.py|head -1)/cwd`.
   - **Fake-data trap in new builds:** a replacement `app.js` often ships a `demoMetrics()` that
   injects random CPU/RAM/DISK/NET/TEMP/FAN every second when "not connected". The operator
   **bans fabricated values** — disable `demoMetrics()` and drive gauges from real
   `moon.system` (see REAL TELEMETRY SCHEMA). Grep served file:
   `curl -s http://127.0.0.1:8787/app.js | grep -n "demoMetrics()"` — only the disabled
   definition line should remain, no active call.
   - **Post-swap gate:** `pytest tests/` in the new folder + the two-client telemetry probe.
   Visual match is the operator's call. Recipe: `references/nexus_build_swap_recipe.md`.
   - **Make a dropped-in build's tests collectable (flat-import trap).** A new build folder
   often uses FLAT top-level imports in its tests (`from core.config import Config`,
   `from security.policy import SecurityPolicy`) that only resolve when pytest runs from
   *inside* the folder. Run from the repo root → `ModuleNotFoundError: No module named 'core'`
   and the whole suite errors at collection (so it looks broken even though the app runs fine).
   FIX (additive, no app code touched): drop a `conftest.py` at the build root that puts the
   folder on `sys.path`:
   ```python
   import os, sys
   _HERE = os.path.dirname(os.path.abspath(__file__))
   if _HERE not in sys.path:
       sys.path.insert(0, _HERE)
   ```
   Then `pytest <build-folder>/` collects + passes from anywhere. (Verified this session:
   9/9 green after adding it; the earlier 9/9 "green" was only because the run was `cd`'d in.)
   - **Operator prefers the WHOLE-FOLDER SWAP over a side-by-side clone.** When handed a new
   build folder, this operator explicitly REJECTED the `clone.html` side-by-side approach and
   demanded the old terminal build be removed and replaced by the new folder (additive to the
   project, but a clean replacement of the terminal build itself). Use the swap recipe above;
   reserve `clone.html` only if the operator asks for a visual A/B compare.

## LIVE-PATH AUTHZ GATE (enforce PolicyEngine / Level / confirmation on the bridge path)
The live bridge calls `MoonAgent.run()` (runtime.py), which historically only had a `locked` boolean — `tools.run()` ran with NO `Level`/`requires_confirmation` enforcement, and `moon_headless.py` auto-unlocked at boot. The advanced `MOON` orchestrator *did* enforce the `PolicyEngine`, so the live path was the weak link. Full closure recipe (all additive, in-repo) is in `references/nexus_live_authz_gate.md`. Key points:
- Gate `ToolRegistry.run()` against the canonical `permissions.REGISTRY`; add `authorized_level` (default READ_ONLY) + `pending_confirm` + `__NEEDS_CONFIRM__:<cid>` sentinel for confirmation-gated tools.
- `runtime.observe_unlock` elevates `tools.authorized_level` to PROCESS_EXEC(3); init sets READ_ONLY while locked (lock state == authorized level).
- Bridge (`moon_nexus.py`) starts LOCKED, wires `Authenticator`+`PolicyEngine`, handles `moon.unlock` (real passphrase → PROCESS_EXEC) and `moon.confirm` (approve → re-run tool with `_confirm_id`).
- **Two bugs to expect when adding authz message types to a dropped-in server:** (1) server `process()` must whitelist `moon.unlock`/`moon.confirm` (else "Unknown message type"); (2) AGENT→UI responses must use a `broadcast_to_ui()` that **excludes `moon_clients`**, or the brain re-receives its own response and loops (infinite `moon.unlock {ok:False}` flood). Route by `self.roles.get(ws)=="AGENT"`.
- Tests that call `agent.tools.run(...)` directly will start blocking at READ_ONLY — unlock in-test or assert the `__NEEDS_CONFIRM__:` flow.

## WHICH FRONTEND DIRECTORY IS ACTUALLY LIVE (FIRST CLASS — edit the right files)
There are TWO copies of the NEXUS `futuristic/` UI tree and they are NOT the same:
- **LIVE (what the browser shows at `http://127.0.0.1:8787/`):** served by the
  running `run_nexus.py` process. Confirm its `cwd` first:
  `ls -l /proc/$(pgrep -f run_nexus.py | head -1)/cwd` → currently
  `/home/meow/projectterminal/RED_TEAMING_HACKER_INTERFACE/Moon_AI_AGENT/MOON_NEXUS_FUNCTIONAL_FINAL/MOON_FINAL_3D_FUNCTIONAL`
  (the old `MOON_Avatar_Terminal_FINAL` was DELETED — the live build is now the
  whole-folder swap target). The served files are
  `<that cwd>/futuristic/{index.html,app.js,style.css}`.
- **REPO COPY (looks identical, changes NOTHING visible):** `/home/meow/Projects/MOON/web/nexus/futuristic/`.
  A parallel/older snapshot. Editing it will NOT change what the user sees.
**Rule:** before patching the UI, `pgrep -f run_nexus.py` → read its `cwd` → edit
`<cwd>/futuristic/*`. Verify with `curl -s http://127.0.0.1:8787/<file> | grep <marker>`.
The HTTP server reads files per-request, so a browser hard-refresh picks up edits with
**NO restart** — but the `run_nexus.py` process must still be running. (The repo `Projects/MOON`
copy has its OWN bridge launcher `web/nexus/run_nexus_bridge.py`; do not confuse the two.)

## REAL TELEMETRY SCHEMA (no fabrication; gauges must read it right)
`moon_agent` (`moon_headless.py` → `MoonNexusBridge._metrics_loop`, every 2s) already
broadcasts the authoritative `moon.system` — **do NOT add a competing feeder** (a second
broadcaster fights over the gauges / schema). Exact `system` fields:
```
cpu, ram, ram_used_gb, ram_total_gb, disk, disk_used_gb, disk_total_gb  (all real)
cpu_freq_ghz          (real, from psutil.cpu_freq(); None if unavailable -> UI shows '—')
net_sent_mb, net_recv_mb   (cumulative MB counters, NOT a rate)
temp_c                (real, from psutil.sensors_temperatures(); None -> UI shows '—')
os, python
```
`moon.agent.status` also carries `tool_names` (the **real** list of registered tool names)
and `FUNCTIONS` (its count) — use `tool_names` to group the FUNCTIONS panel honestly
(see MATCHING THE REFERENCE IMAGE).
GOTCHA: there is **NO `net` percentage field** — only cumulative `net_sent_mb`/`net_recv_mb`.
To animate the NET gauge, derive a real throughput % from the delta between samples:
`tot=net_sent_mb+net_recv_mb; dmb=tot-prevTot; dt=(now-prevT)/1000;
 gbps=(dmb*8/1000)/dt; netPct=min(100, gbps/1.0*100)` (1 Gb/s reference).
An old UI set `net` from a non-existent `s.net` → gauge pinned at 0%.
`moon.agent.status` carries real `BRAIN/MEMORY/RETRIEVER/PLANNER/TOOLS/FUNCTIONS/VISION/
LISTENER` (FUNCTIONS = live tool count; VISION OFFLINE in this build) and `moon.heartbeat`
carries `uptime_s`. The UI's dot/status widgets already render these.

## MATCHING THE REFERENCE IMAGE (real-state, in-place) — ADDED THIS SESSION
When the operator attaches the **actual** reference screenshot (e.g. `MOON NEXUS v3.0`) and
says "match this terminal / find what's missing / fix it to look like this", the goal is a
**faithful match of STRUCTURE + STYLE driven by REAL MOON state** — NOT a mockup. The
reference image itself contains **fake numbers** (`FUNCTIONS: 312`, `138 tools loaded`,
`DATA FLOW 2.4 TB`, `TEMP 42°C`, `FAN 1280 RPM`, gauge sublabels `2.4 GHz`/`1.7/4GB`/
`98/298GB`/`120 Mbps`). Those are **reference flavor, not truth** — the operator's real-state
rule bans them. Match the *layout*, supply *real* values.

**The avatar is already present and wired** — do NOT go looking for a "missing" avatar.
It lives at `<cwd>/futuristic/assets/moon_avatar.jpg`, is referenced by
`<img id="avatar" src="assets/moon_avatar.jpg">` in `index.html`, and animated by `app.js`
(3D rings / gaze / mouth-sync). If the operator asks "where is my avatar", **confirm it's
there and serving** (`curl -s http://127.0.0.1:8787/futuristic/assets/moon_avatar.jpg -o /dev/null -w '%{http_code}'` → 200) rather than rebuilding it.

**In-place matching (the operator rejected the `clone.html` side-by-side approach for this):** edit the
LIVE `<cwd>/futuristic/{index.html,app.js,style.css}` directly (whole-folder swap already put the
reference-style build at the live cwd). No separate port needed. Verify with `curl` on `:8787`
and a browser hard-refresh (HTTP server reads per-request → no restart needed; the `run_nexus.py`
process must stay up).

**Real-state mapping for the reference's widgets (no fabrication):**
| Reference widget | Real source (add to bridge if missing) |
|---|---|
| Gauge sublabels CPU/RAM/DISK/NET | `moon.system.cpu_freq_ghz` (add via `psutil.cpu_freq()`), `ram_used_gb`/`ram_total_gb`, `disk_used_gb`/`disk_total_gb`, derived NET Mbps from `net_sent_mb+net_recv_mb` delta. Seed placeholders with `—`, never a fake constant. |
| MOON FUNCTIONS panel | Group the **real** `tool_names` by prefix (`x.split('_')[0]`) → `category: count` cards; total = real `FUNCTIONS`. Matches the reference's grouped list but is truthful (this build = 30 tools, not 312). |
| DATA FLOW footer | cumulative `(net_sent_mb+net_recv_mb)/1e6` TB (real). |
| TEMP footer | `moon.system.temp_c` (real `psutil.sensors_temperatures()`); `—` if None. |
| FAN footer | `—` (no fan sensor on this box) — do NOT show a fake RPM. |
| Agent status / VISION | real `moon.agent.status`; VISION stays OFFLINE (truth). |

**Bridge changes required for the above (all additive):** in `_real_system_metrics()` add
`cpu_freq_ghz = round(psutil.cpu_freq().current/1000, 1) if available else None` and keep
`temp_c` from `sensors_temperatures()`; in `_agent_status()` add `"tool_names": list(...tools.names())`.
**Quick Launch mislabel trap:** a `data-command` button labeled "Browser" sometimes runs
`pwd && ls`. Map it to a real browser-open attempt
(`python3 -c "import webbrowser; webbrowser.open('http://127.0.0.1:8787')"`) so the label
matches the action.

**Diff-first verification (operator's standing demand):** before claiming "done", run
`vision_analyze` on the reference AND on the live build, produce a FIELD-BY-FIELD diff
(present / missing / different), fix only real gaps, re-verify. The visual pixel-match is the
operator's call — report it as pending their eyeball, never claim it confirmed.

**Reference-match real-state recipe** (copy-paste): `references/nexus_reference_match_realstate.md`.

## AVATAR IMAGE PATH PITFALL (real HTTP 404 this session)
`futuristic/index.html` referenced `../assets/moon_avatar.jpg`, but `web_server.py` serves
from `futuristic/` and `..` is outside the root → **blocked, HTTP 404** (avatar blank).
FIX: copy the avatar into `futuristic/` (`cp <cwd>/assets/moon_avatar.jpg <cwd>/futuristic/`)
and set `<img src="moon_avatar.jpg">` (same dir, no traversal).

## Real neofetch-on-connect (terminal shows REAL host info)
On `terminal.ready`, have the UI issue a multi-line shell command via `terminal.exec` so the
terminal boots with real `uname`/mem/disk (matches the reference neofetch block). The bridge
executes it for real and streams `terminal.output`. Subscribe to `:8765` as a UI client and
confirm `terminal.start` with your neofetch command fires (do NOT fake the output).

## CLONING / REBUILDING THE NEXUS UI FROM A REFERENCE IMAGE (additive, real-state)
When the operator says "build the same clone of this terminal interface" against a screenshot
(or "match it exactly"), the goal is a **pixel-faithful clone driven by REAL MOON state** — not
a mockup. The operator bans fake/placeholder values, so every widget must map to a live source.

**Work additive, don't disturb the live UI:** build `futuristic/clone.html` (same dir as the
live `index.html`, so `moon_avatar.jpg` resolves with no path change) and serve it on a
**separate free port** (this session used **8796**) pointed at the same `futuristic/` root and
the **same real `ws://127.0.0.1:8765/moon` brain**. The user opens `:8796` side-by-side with the
live `:8787` to compare. Nothing on `:8787` changes. Promote `clone.html` → `index.html` only
after the operator eyeballs and approves (then KISS/DRY before commit).

**Real-state mapping for the clone (no fabrication):**
| Widget | Real source |
|---|---|
| CPU / RAM / DISK gauges | `moon.system` (`cpu/ram/disk`). NET gauge from **delta** of `net_sent_mb+net_recv_mb` (no `net` field exists). |
| Avatar | copy the reference `*.jpg` into `futuristic/`, `<img src="moon_avatar.jpg">` (same-dir, no `../`). |
| Terminal boot | real `neofetch` via `terminal.exec` on `terminal.ready`. |
| Agent status dots | `moon.agent.status` (FUNCTIONS = **real** tool count; **VISION: OFFLINE** is truth — do NOT paint it ONLINE). |
| DATA FLOW footer | cumulative `(net_sent_mb+net_recv_mb)/1e6` TB (real) — NOT a fictional "10 TB" cap. |
| TEMP footer | `GET /temp_c` → real `/sys/class/thermal/thermal_zone0/temp //1000`; show `N/A` if 204. |
| FAN footer | `GET /fan_rpm` → `hwmon/*/fan1_input`; show `N/A` if unreadable. |
| Heartbeat / uptime | `moon.heartbeat.uptime_s`. |
| Counts | derive from real events; never hardcode "312 functions" / fake latency. |

**Additive real-host endpoints** (patch `futuristic/web_server.py` `Handler.do_GET`, or run a
standalone server — see `references/nexus_clone_recipe.md`). Return **204 + empty body** when a
sensor is unreadable so the UI can honestly show `N/A` instead of a fake number.

**Serve-launcher pitfall:** a 2nd `ThreadingTCPServer` hit `OSError 98 Address already in use`
from a lingering TIME_WAIT socket. Set `ThreadingTCPServer.allow_reuse_address=True` AND verify
the port is free first (`ss -ltn | grep :PORT`); if still taken, pick the next free port. The
inline `python3 -c` launcher works and needs **no restart** of the live UI.

**Verifying a frontend-only file (no pytest covers `clone.html`/`index.html`):** the only real
checks are (a) `curl` the clone → `clone.html` 200, `moon_avatar.jpg` 200, `/temp_c` returns a
real integer; (b) simulate the clone's WS client (`hello` role `UI` + `system.info`) and assert
`terminal.ready` + real `moon.system` + `moon.agent.status` + `moon.heartbeat` arrive. The
**visual** pixel-match is the operator's call — report it as pending their eyeball, never claim
it confirmed. Concrete copy-paste recipe in `references/nexus_clone_recipe.md`.

## Env pitfall (cross-venv)
Hermes venv's PIL is broken (`cannot import name '_imaging'`). Launch the terminal
with **system** Python + sanitized env:
`env -u VIRTUAL_ENV -u PYTHONPATH -u PYTHONHOME PATH="/usr/bin:/bin:/usr/local/bin" /usr/bin/python3 run_nexus.py`.
Prefer a real `DISPLAY` (`:0.0`) over `xvfb-run` (flaky: process stayed alive but
server thread died → port gone while `poll()` looked healthy).

## Supervisor: supervise the PORT, not the process
tkinter `mainloop()` keeps the process alive after the WS server thread crashes,
so `proc.poll()` lies. Check the socket instead:
`socket.create_connection(('127.0.0.1', 8765), timeout=1.5)`.

## Make MOON persistent (systemd user service)
`~/.config/systemd/user/moon.service`: `Type=simple`, `Restart=always`,
`RestartSec=3`, env `PATH=/usr/bin:/bin:/usr/local/bin`,
`PYTHONPATH=<repo>`, `DISPLAY=:0.0`, `ExecStart=/usr/bin/python3 <repo>/moon_headless.py`.
Then `systemctl --user daemon-reload && systemctl --user enable --now moon`.
`Linger=yes` (`loginctl show-user meow -p Linger`) ⇒ starts at boot with no login.

## Verification recipe
Run the deterministic liveness probe `scripts/moon_nexus_liveness.py` after any
change — it mimics a UI client and asserts MOON's `avatar.speak` round-trips
(exit 0 = healthy). Also `pytest` in the repo (40 tests incl.
`tests/test_moon_nexus_bridge.py`). A known-good systemd unit lives in
`references/moon-systemd-user-service.md`.

**Frontend live-edit + verify playbook** (which files serve, avatar-404 fix, NET-gauge
delta math, no-restart verification, UI-client bridge probe): `references/nexus_ui_live_edit_recipe.md`.

**Cloning the NEXUS UI from a reference image** (free-port side-by-side, real-host `/temp_c`
+ `/fan_rpm` endpoints, additive serve launcher, WS-client verification, promote-to-live):
`references/nexus_clone_recipe.md`.

**Whole-folder build swap** (repoint `AVATAR_DIR` + `systemctl restart`, fake-metrics trap,
the missing-telemetry-forwarding bug, post-swap gates): `references/nexus_build_swap_recipe.md`.
Decisive two-client telemetry-forwarding probe: `scripts/moon_telemetry_forward_probe.py`
(exit 0 = server forwards `moon.system`/`moon.agent.status` to UI clients; 1 = broken).
