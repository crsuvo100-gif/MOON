---
name: hosted-agent-embedding
description: Embed hosted agents chrome-free via SDK proxy.
---

# Hosted Agent Embedding (chrome-free)

Use when a user pastes a "share" / "embed" link to a hosted AI agent (avatar,
voice, chatbot) and wants to clone or embed it inside their own app/UI without
the vendor's branding/chrome (no "Share", "Create agent", "Build your own"
buttons, etc.).

## Core principle
A hosted agent link is NOT a code repo — it's a *hosted service* identified by a
public agent ID plus an auth credential. There is no source to download. Your
job is to (1) extract the agent ID + credential from the link, (2) mount the
agent via the vendor's official SDK (so it renders inside YOUR DOM), and (3) fix
the CORS wall the vendor puts in front of its API.

## Three viable embed strategies (in order of preference)
1. **SDK + same-origin proxy (chrome-free, best).** Import the vendor's JS SDK
   and call its `init()` with `auth` + an `apiUrl`/`didApiUrl` pointed at YOUR
   local proxy. The browser only ever talks to your origin → no CORS. The proxy
   forwards to the vendor API and injects the credential server-side.
2. **Iframe to the share URL (works, but shows vendor chrome).** Easiest, but
   you inherit the vendor's "Share / Create agent" UI. Good fallback. Works only
   if the share host sends no `X-Frame-Options` / no CSP `frame-ancestors` (most
   do not).
3. **Raw REST against vendor API (usually blocked).** Direct browser calls to
   the vendor API fail CORS because the vendor omits `Access-Control-Allow-Origin`
   on authenticated responses. Avoid; route via strategy 1.

## Step-by-step (the pattern that worked)
1. **Fetch the share HTML** (`curl -A <browser> <url>`). It's a SPA — the agent
   config loads at runtime, so don't expect source. Note the `id=` and `key=`
   params in the URL.
2. **Decode the credential.** `key=` is often base64 of a client key, e.g.
   `echo <key> | base64 -d`. The agent id is the `id=` param.
3. **Find the SDK + embed snippet.** Download the studio bundle JS, grep for the
   agent/page chunk, and extract the exact `<script>`/embed the vendor generates
   (it reveals the SDK URL, `data-client-key`, `data-agent-id`, `data-mode`).
4. **Probe CORS.** `curl -sI -H "Origin: http://localhost" <SDK_URL>` → if
   `access-control-allow-origin: *`, the SDK loads. But the *agent runtime* API
   call will still 401+no-ACAO from the browser.
5. **Build the proxy** (`server.py`): same-origin static host + `/didapi/*`
   forwarder to `https://api.<vendor>.com`. On every forwarded request, **set
   `Authorization` server-side** and add `Access-Control-Allow-Origin: *`. The
   browser never sees the secret.
6. **Mount via SDK.** `app.js`: `const mod = await import(SDK_URL); mod.init({
   agentId, auth: mod.getAuth({username,password}), didApiUrl: "/didapi",
   mode: "full", targetElement, monitor: true })`. If `getAuth` requires creds
   but you inject auth in the proxy, send throwaway creds from the browser — the
   proxy overwrites `Authorization` anyway.
7. **Verify headlessly** (Selenium + ChromeDriver) — assert `STATUS: live`,
   **0 severe console errors**, and `agent-root` hydrates (or `video`/`canvas`
   appears on session start). Vision-analyze a screenshot to confirm no vendor
   chrome.

## Pitfalls (learned the hard way)
- **"No auth method provided" from the SDK is a CORS-success signal.** When you
  switch from cross-origin to proxy, the SDK stops throwing a network/CORS error
  and instead says "No auth method provided" — that means the CORS block is GONE
  and you only need to supply creds. Don't mistake it for a regression.
- **Vendor "client key" (`ck_...`) ≠ API key.** The embed/share key is an
  SDK-scoped key; calling the raw API with it 401s. The real credential is the
  Studio account token.
- **D-ID credential quirk:** the pasted Studio token was base64 of
  `google-oauth2|<id>:<secret>`. D-ID expects `Authorization: Basic
  base64(<that exact pasted string>)` — i.e. base64 the *base64* again, OR pass
  `Basic base64(decoded identity:secret)`. The SDK's `getAuth({username,password})`
  builds `Basic base64(username:password)~<clientKeyId>`. Sending the raw pasted
  token as `DID_BASIC` (base64 form) worked; sending the *decoded* plaintext 401'd.
  See `references/d-id-recipe.md`.
- **`http.server.BaseHTTPRequestHandler` has no `guess_type`** — use
  `mimetypes.guess_type()` instead, or inherit `SimpleHTTPRequestHandler`.
- **Kill-then-restart a server:** `pkill -f server.py` returns exit -15 (killed),
  which is EXPECTED, not a failure. Verify with `ss -ltn | grep :<port>` before
  restarting — don't loop on the same pkill command (it trips the tool loop guard).
- **Secret hygiene:** never echo a pasted credential; test it transiently from a
  file (`TOK=$(cat /tmp/tok.txt)`), save only to a local `.env`, and delete the
  temp file. Decode structure locally (base64) to identify type without leaking.

## When the user gives you a credential
Treat it as a secret: redact in logs, use transiently, save to local `.env` only,
never ship to the browser bundle. Verify it authenticates, then wire it through
the proxy (server-side injection), not into client code.

## Verify, don't assume
Always close the loop with a real headless-browser run + screenshot. A 200 from
`curl` through the proxy is necessary but not sufficient — confirm the SDK
actually mounts in-browser with no console errors.

## Production hardening (before exposing the proxy)
The dev `server.py` is NOT safe to expose as-is. Before any public/network
deployment: bind localhost only (`BIND=127.0.0.1`, behind your own TLS proxy),
add a **path whitelist** locked to `DID_SOURCE_AGENT` (`403` for anything else,
`405` for DELETE), and keep server-side secret injection. Full recipe + a
verified curl test matrix (list→403, other-agent→403, billing→403, DELETE→405,
your-agent→200) is in `references/proxy-hardening.md`. The #1 miss is forgetting
the whitelist check on `do_GET` (it silently forwards `/didapi/agents` as a list).
For the watchdog supervisor + additive-companion-layer recipe (extend a working
service without editing it), see `references/watchdog-companion.md`.

## Advanced patterns (extend + keep alive)

### Cross-platform watchdog supervisor (survive token expiry, not just crashes)
`systemd Restart=on-failure` only catches crashes, not **silent** failures — e.g.
the vendor token expires → API returns **401** → the avatar dies quietly with no
restart. Add a small dependency-free Python supervisor (`launch.py`) that:
- spawns `server.py` as a managed child,
- every `HEALTH_INTERVAL` (default 30s) runs a **one-line health check**
  (`GET /didapi/agents/<id>/runtime` → 200?),
- on 401 / crash / port-down, kills and respawns the child,
- handles SIGINT/SIGTERM cleanly (no orphans).
On Linux, `install.sh` wraps `launch.py` (not `server.py`) as the systemd unit, so
you get **both** reboot-survival and token-expiry recovery. On macOS/Windows just
run `python3 launch.py`. Full recipe + verified respawn test in
`references/watchdog-companion.md`.

### Additive companion layer (extend WITHOUT touching the working service)
When the user says "make it more advanced but don't change anything that already
works", build the new capability as a **separate** service on a NEW port that
**relays** to the locked proxy — never modify `server.py`/`app.js`/the clone.
Verified pattern (`advanced.py` on :8778, relaying to locked `server.py` on :8777):
- `advanced.py` exposes `/api/health`, `/api/metrics`, `/api/command` (palette:
  `/status /metrics /clone /say <text> /help`), and a **same-origin**
  `/didapi/*` relay to `PROXY_BASE` (the locked proxy).
- The richer page (`advanced.html`) mounts the avatar via `didApiUrl: "/didapi"`
  (same origin → CORS-free) and gets `agentId` from `/api/health` (same origin,
  no cross-origin fetch).
- The relay forwards to the locked proxy, which **still enforces its whitelist +
  injects the credential** — so the new layer adds features without weakening
  security or editing the proven service.
- Register it as a SECOND systemd unit (`install-advanced.sh`) — `install.sh`
  stays untouched.
Key lesson: same-origin relay = reuse the existing security boundary instead of
forking it. See `references/watchdog-companion.md`.

### Additive advanced UI: voice toggle + chat transcript
When the user wants the terminal "more advanced" (voice on/off, transcript log)
without breaking the working avatar, add them to the **companion** page
(`advanced.html`/`advanced.js` + `advanced.py`), never to `app.js`/`server.py`.
Verified recipe:
- **Voice toggle** (genuine TTS, not cosmetic): server holds `VOICE={"on":True}`
  with `GET/POST /api/voice`; client mutes avatar `<audio>/<video>` and gates
  browser `speechSynthesis` on the flag; state shown in SYSTEM panel.
- **Chat transcript**: YOU bubble added client-side the instant `/say <text>`
  runs; MOON bubble captured from the SDK talk channel (`sdk.on("message",...)` /
  `sdk.subscribe("message",...)`), then spoken when voice is on.
- **D-ID 402 billing**: REST `/agents/{id}/chat` is billed per use → 402 with no
  credits. Return **HTTP 200** `{"ok":false,"http":402}` from the command
  endpoint (NOT 400) so the browser logs a clear note with no console error. The
  avatar's built-in SDK voice stays FREE.
- **Cross-origin agentId trap**: the advanced page (`:8778`) must NOT fetch the
  locked proxy (`:8777`) directly — CORS blocks it, agentId comes empty, SDK says
  "No agent provider". Expose `agentId` via same-origin `/api/health` and set
  `didApiUrl: "/didapi"` (relayed same-origin). Full recipe in
  `references/advanced-ui.md`.

## Pitfalls (learned the hard way)
- **Stale systemd service silently serves OLD code and holds the port.** After
  editing `server.py`, `./install.sh` (which does `systemctl restart`) can fail
  with `OSError: [Errno 98] Address already in use` because a **previous child
  process is still bound** — and you then test against the *old* code (e.g. a
  missing `/_auth` endpoint) without realizing it. The kill+restart sequence:
  `systemctl --user stop <svc>` → `fuser <port>/tcp` (or `ss -ltnp | grep <port>`)
  to find the REAL holding PID → `kill -9 <pid>` → confirm `ss -ltn | grep <port>`
  is FREE → then start. Verify the new endpoint actually responds (e.g.
  `curl /didapi/_auth` → 200) BEFORE declaring success.
- **Empty env var overrides the code default.** A blank `PROXY_BASE=` line in
  `.env` makes `os.environ.get("PROXY_BASE", "http://127.0.0.1:8777")` return `""`,
  so the relay targets `<empty>/didapi/...` → 404/502. When adding a config knob,
  leave it OUT of `.env` unless set, or validate non-empty. (Don't put
  `PROXY_BASE=` as an empty line.)
- **`pkill -f server.py` returns exit -15 (killed)** — that's EXPECTED, not a
  failure. Don't loop on the same pkill; verify the port with `ss` instead.
- **Relay must forward ALL `/didapi/*` methods**, not just `_auth`. Routing only
  `/didapi/_auth` to the proxy while letting other GETs fall through to static
  serving yields 404 on `/runtime`. Relay every `/didapi/*` GET/POST/OPTIONS.

## Related skills
- `headless-render-screenshot` — for visual verification of the mounted agent.
- `hosted-agent-clone` — cloning the source agent into your own account.
- `moon-ops` — this technique was first applied to embed a D-ID avatar into the
  MOON terminal project.
