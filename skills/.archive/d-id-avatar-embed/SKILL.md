---
name: d-id-avatar-embed
description: Embed a D-ID avatar chrome-free via v2 SDK + CORS proxy.
---

# D-ID Avatar Embed (chrome-free)

## When to use
The user has a D-ID **agent share link** (`studio.d-id.com/agents/share?id=v2_agt_...&key=...`)
and wants to run that avatar inside their own page **without D-ID's "Share /
Create agent / Build your own" chrome**, or wants to clone the agent into their
own account.

## Critical mental model
A D-ID share link is **not source code** — it's a *hosted agent*. The link only
carries two credentials, decoded as:
- `agent id`  ← `?id=` param (e.g. `v2_agt_AviWSg5f`) — public, not secret.
- `client key` ← base64 of `?key=` param (e.g. `ck_...`). An **embed key**, NOT
  valid for raw `api.d-id.com` calls (it 401s). Do not try to use it as an API key.

You cannot download the agent. You mount it via D-ID's SDK, which talks to
`api.d-id.com`. Everything below is about making that SDK work from a browser
you control.

## The mount technique (chrome-free)
Import the official v2 SDK (ES module) and call `init()` the way D-ID's own share
page does:

```js
const mod = await import("https://agent.d-id.com/v2/index.js");
mod.init({
  agentId,
  auth: mod.getAuth({ username, password }),  // see credential forms below
  didApiUrl: "/didapi",        // same-origin proxy (NOT https://api.d-id.com)
  mode: "full",
  targetElement: document.getElementById("agent-root"),
  monitor: true,
  onError: (e) => { /* surface e.message */ },
});
```

This mounts the avatar **inside** `agent-root` with no D-ID chrome.

## The CORS problem (and the fix)
`api.d-id.com` does **NOT** send `Access-Control-Allow-Origin` on authenticated
responses. A browser page calling it directly gets a CORS block
("Network request failed"), even though the request would otherwise succeed.

**Fix = same-origin local proxy.** The browser only ever talks to `localhost`
(same origin), so there is no CORS. The proxy forwards to `api.d-id.com` and
**injects the credential server-side**, then returns `Access-Control-Allow-Origin: *`.

This pattern is reusable for *any* authenticated third-party browser SDK/widget
that lacks CORS headers.

## Credential forms (what actually authenticates against api.d-id.com)
The SDK's `getAuth({...})` builds the header:
- `{username, password}` → `Basic base64(username:password)~<clientKeyId>`
- `{token}` → `Bearer <token>~<clientKeyId>`
- `{clientKey}` → `Client-Key <clientKey>.<id>_<clientKeyId>`

Working auth against `api.d-id.com`:
- **D-ID Studio account credential** — a token of the shape
  `google-oauth2|<numericId>@<handle>:<secret>`. Often delivered *base64-wrapped*
  (the whole `google-oauth2|...:<secret>` is base64). Send as
  `Basic base64("google-oauth2|<id>:<secret>")`. Set `DID_BASIC` to the **raw
  base64 token** and have the proxy compute `Basic base64(DID_BASIC)`. This is
  the form a pasted Studio session token takes and it WORKS (verified 200).
- **API key + secret** → `Basic base64(key:secret)`.
- **API key only** → `Bearer <key>`.
- **Embed client key `ck_...`** → 401 on `api.d-id.com`. Do not use for direct API.

Keep the secret **only in the proxy** (env / `.env`). The browser sends throwaway
creds (e.g. `username:"did", password:"did"`); the proxy **overwrites** the
`Authorization` header on every forwarded request.

## iframe fallback (shows D-ID chrome)
`studio.d-id.com/agents/share` sends **no `X-Frame-Options` and no CSP
frame-ancestors`**, so it frames cleanly — but you get D-ID's "Share / + Create
agent" chrome. Use only as a fallback. The SDK+proxy path above is the
branding-free one.

## Production hardening (apply before exposing)
- **Bind localhost by default** (`BIND=127.0.0.1`); only `0.0.0.0` behind your own
  TLS reverse proxy (nginx/Caddy).
- **Path whitelist**: forward only `/didapi/_auth`, `/didapi/agents/<YOUR_ID>`,
  and `/didapi/agents/<YOUR_ID>/runtime`. Everything else → 403; DELETE → 405.
  Lock the allowed id to `DID_SOURCE_AGENT`. This blocks listing agents,
  creating/deleting, `/billing`, and touching other users' agents.
- **Never echo the secret** to the client. `/_auth` returns only `agentId` +
  throwaway creds.

## Make it portable / always-on (user preference: "forever useful on any machine")
When given latitude, deliver self-contained + reboot-surviving:
- `server.py` calls a stdlib-only `load_dotenv()` (no python-dotenv dep) so
  `python3 server.py` just works with a `.env` beside it — no manual `source`.
- Client is **config-driven**: fetch `agentId` from `/_auth` instead of hardcoding,
  so the same files run unchanged on any host (just swap `.env`).
- Register a **systemd user service** + `loginctl enable-linger` so it starts on
  boot and restarts on crash. See `templates/moon-avatar.service` and
  `scripts/install.sh`.

## Pitfalls (learned the hard way)
- **v2 SDK does NOT auto-init from `data-*` attributes** (unlike v1). You must
  `import()` the module and call `init()` yourself.
- `agent-root` has **0 children until the user starts a call** (mic permission).
  That is expected — verify success via the status text (`"live"`) + **0 console
  errors**, not via child count.
- A `BaseHTTPRequestHandler` subclass has **no `guess_type`** (that's
  `SimpleHTTPRequestHandler`). Use `mimetypes.guess_type()`.
- The proxy's path-whitelist fn must reference a module-scope `SOURCE` — a
  `NameError` fires at request time if it's undefined.
- **Stale server holds the port**: `pkill -f server.py` then
  `ss -ltnp | grep :8777` to confirm/kill the real PID (`kill -9`) before
  restarting; otherwise you silently test the old instance.
- Selenium headless needs `--use-fake-ui-for-media-stream
  --use-fake-device-for-media-stream --autoplay-policy=no-user-gesture-required`
  or the avatar mic flow stalls.

## Verification recipe
Headless Chrome (chromedriver) on `http://localhost:PORT`:
1. assert status text == `"live"`,
2. assert 0 `SEVERE` console errors,
3. screenshot and visually confirm the avatar panel (no D-ID chrome).
Also curl the proxy: `GET /didapi/agents/<id>` → 200, `GET /didapi/agents` → 403.

## Support files
- `references/d-id-credentials-and-cors.md` — condensed knowledge bank: endpoint
  paths, credential forms, CORS behavior, clone-agent recipe.
- `templates/moon-avatar.service` — systemd user-unit template.
- `scripts/install.sh` — idempotent installer (install/status/stop/uninstall) that
  writes the unit, enables linger, and starts the service.
