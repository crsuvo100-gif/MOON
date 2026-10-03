---
name: did-avatar-terminal
description: Chrome-free D-ID avatar terminal with proxy and watchdog.
---

# D-ID Avatar Terminal (chrome-free, proxied, self-healing)

## When to use
- User has a D-ID agent **share link** (`studio.d-id.com/agents/share?id=v2_agt_...&key=...`)
  and wants it rehosted as their own terminal-themed page, OR wants a local
  "forever-on" avatar that survives reboot and token expiry.
- Anything touching the D-ID agent SDK / `api.d-id.com` CORS, or "clone this agent".

## Key facts (learned the hard way)
- **v2 agent id** (`v2_agt_…`) => use the v2 SDK: `https://agent.d-id.com/v2/index.js`
  (dynamic `import()` of that URL). It is CORS-open (ACAO: *).
- The SDK's `init({agentId, auth, didApiUrl, mode:"full", targetElement, monitor})`
  fetches `didApiUrl + /agents/<id>/runtime`. `api.d-id.com` does NOT send
  `Access-Control-Allow-Origin` on authed responses => direct browser calls fail
  with "Network request failed". **Fix: same-origin CORS proxy.**
- `init()` returns a controller with **`subscribeToEvents((event, raw)=>{})`** —
  NOT `.on()`/`.emit()`. Message payloads carry `{role, content}`. The agent's
  spoken text streams here; extract via `content/text/message/script` fields and
  filter `role` in (agent/assistant/ai). (Do NOT wire `sdk.on("message")` — it
  never fires.)
- SDK `getAuth({username,password})` only needs **throwaway** creds (e.g. did/did);
  the REAL credential is injected **server-side** by the proxy. Never put the
  real key in the browser.
- **Auth form**: D-ID Studio credential is `google-oauth2|<id>:<secret>` =>
  `Authorization: Basic base64("google-oauth2|<id>:<secret>")`. Works against
  `api.d-id.com` (returns 200 + client_key). Client key alone (from `key=` param)
  is SDK-scoped and 401s on the studio API.
- **Clone** the source agent into your account (POST `/agents` with persona
  fields kept, admin fields stripped) so you own the agent id (`v2_agt_…`).
- **D-ID bills REST `/agents/{id}/chat` per use (HTTP 402)** when no credits.
  The avatar's own voice (SDK stream) is free. Degrade gracefully: log the user
  input + any SDK-streamed reply; don't 400 on 402.

## Architecture (proven, launch-ready)
- `server.py` — static host + **CORS-reversing proxy** to `api.d-id.com`. Injects
  auth server-side. Locks a **path whitelist** to only `/agents/<YOUR_ID>` and
  `/agents/<YOUR_ID>/runtime` (GET/POST/PATCH), DELETE disabled, everything else
  403. Binds `127.0.0.1` by default. Exposes `/didapi/_auth` returning only
  throwaway creds + agentId.
- `launch.py` — cross-platform supervisor + **health-check watchdog** (stdlib
  only). Spawns `server.py`, every `HEALTH_INTERVAL` (default 30s) probes
  `/didapi/agents/<id>/runtime`; on 401/crash it kills + respawns the child.
  `python3 launch.py --check` = one-shot health (exit 0/1). No systemd needed
  (works on macOS/Windows too).
- `advanced.py` — additive companion on :8778: `/api/health`, `/api/metrics`,
  `/api/voice` (GET/POST), `/api/command` palette (`/status /metrics /health
  /clone /say /voice on|off /help`), and a **same-origin `/didapi/*` relay** to
  the locked :8777 proxy (so the advanced page mounts CORS-free reusing the
  whitelist + secret isolation). Calls D-ID server-side for `/say`/`/clone`.
- `advanced.html/.js/.css` — richer terminal: avatar + CHAT TRANSCRIPT
  (user bubbles from `/say`, agent bubbles from `subscribeToEvents`) + live
  SYSTEM metrics + VOICE on/off toggle (browser Web Speech API + mutes avatar
  audio). ADDITIVE — original `index.html`/`app.js` untouched.
- `install.sh` / `install-advanced.sh` — systemd **user** services; `enable-linger`
  so they survive reboot + session end. Hardened `stop`/`restart` kills the
  port-holding child (systemd can leave stale children) and **verifies the new
  process is actually listening** before reporting ready.

## Build checklist
1. Decode `key=` (base64) → client key; identify agent id from URL.
2. Probe auth: `Basic base64("google-oauth2|<id>:<secret>")` against
   `api.d-id.com/agents/<id>` → 200 means creds good.
3. `clone_agent.py` → clone into your account, set `DID_SOURCE_AGENT` to new id.
4. `server.py` with whitelist + `_auth` + localhost bind.
5. `launch.py` watchdog; test `--check` and kill-child-respawns.
6. (optional) `advanced.py` + page for transcript/voice/metrics.
7. `install.sh` + `install-advanced.sh`; `install` both; verify both `:8777`/`:8778`
   return 200 and a headless browser shows `STATUS: live`, 0 console errors.
8. `.gitignore` the `.env` (secret isolation). Confirm no cred substring in any
   served static file.

## Verification (must actually run)
- `systemctl --user is-active` both services = active; both ports LISTEN.
- `curl` each endpoint matrix = 200; `python3 launch.py --check` = OK/exit 0.
- Headless Selenium (chromedriver, `--headless=new`, fake media + autoplay):
  assert `document.getElementById('status').textContent === 'live'` and
  `get_log('browser')` has 0 SEVERE/WARNING. Screenshot + vision_analyze to
  confirm avatar + panels render.
- Watchdog test: `kill -9` the `server.py` child, wait > HEALTH_INTERVAL, confirm
  `:8777` back to 200 (supervisor respawned it).

## Pitfalls
- **Stale systemd code**: after editing `server.py`/`advanced.py`, `systemctl
  stop` may leave the old child on the port → new start gets "Address already in
  use" but the OLD process keeps serving (health checks pass against stale code).
  FIX: install `stop` must `fuser <port>/tcp` + `kill -9`, and `start` must
  `curl` the endpoint to confirm the NEW process listens before reporting ready.
- `advanced.py` must NOT inherit `server.py`'s `PORT` (would bind :8777). Default
  its own port (8778). And `.env` must not contain a blank `PROXY_BASE=` line
  (overrides the default and breaks the relay → 404/connection-refused).
- The D-ID v2 SDK bundle path changed across versions (`/v2/index.js` redirects to
  a versioned file); `import()` the stable `/v2/index.js` URL, not a pinned hash.
- urllib honors `http_proxy` env — for localhost relay set `no_proxy` or bypass;
  but normally fine when no proxy is set.
