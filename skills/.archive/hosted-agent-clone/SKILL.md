---
name: hosted-agent-clone
description: Clone a hosted AI agent/avatar share link via a CORS proxy.
---

# hosted-agent-clone

## When to use
- User pastes a share/embed URL for an AI avatar or conversational agent (D-ID / HeyGen / Tavus / similar) and wants its "code", a "clone", or a "branding-free embed".
- The shared thing is almost always a **hosted** agent — there is no downloadable source. What you deliver is an embed/integration, not a reimplementation of the model.

## Mental model
1. A share link carries (at most) an **agent id** and a **scoped key**. The actual agent logic lives on the vendor's servers.
2. The vendor's own "Embed" / "Share" tab produces the canonical integration snippet. Your job is to reproduce or improve that.
3. Mount options, in order of preference:
   - **SDK mount in-page (chrome-free)** — best, but the vendor API is usually CORS-locked to the vendor's own origin.
   - **iframe to the share URL** — works when the share route lacks `X-Frame-Options` / `CSP frame-ancestors`; shows vendor chrome (e.g. "Create agent", "Build your own").
4. The CORS block is solved with a **local same-origin proxy** that forwards to the vendor API and injects the **real** API key server-side, so the browser never hits the vendor cross-origin and never sees the key.

## Workflow
1. **Fetch the share URL** (`curl -sL -A "<Chrome UA>"`). It is usually an SPA shell — real data loads via JS/API at runtime, not in the HTML.
2. **Decode the link params.** D-ID: `?key=` is base64 of a client key; `?id=` is the agent id. Always base64-decode before assuming a value is the raw key.
3. **Reverse-engineer the bundle** to find the fetch + mount mechanism (see `references/reverse-engineering.md`). Key goals:
   - What endpoint serves the agent config, and with what auth header?
   - Does the SDK export `init()`/`getAuth()` (v2) or set a `window.DID_AGENT_INIT` global (v1)? Is there an `apiUrl` / `didApiUrl` override to redirect the API host?
   - Is the share route iframe-embeddable? Check response headers for `X-Frame-Options` / `Content-Security-Policy: frame-ancestors`.
4. **Verify the CORS theory.** `curl -sI` the vendor API with `Origin: http://localhost:PORT` and an `Authorization` header. If the *authenticated* response drops `access-control-allow-origin`, the browser will block it → you need the proxy.
5. **Build the proxy + static host** (see `templates/server.py`). The browser only ever talks to `localhost`. The proxy adds the key and returns `Access-Control-Allow-Origin: *`.
6. **Mount via the SDK**, pointing `didApiUrl` (or equivalent) at `/didapi`. e.g. D-ID v2:
   `mod.init({ agentId, auth: mod.getAuth({}), didApiUrl: "/didapi", mode:"full", targetElement, monitor:true })`.
7. **Verify in a real browser** (headless Chrome + chromedriver + Selenium). Confirm `STATUS: live`, **0 SEVERE console errors**, and that the agent widget rendered (look for the vendor's widget class / `<video>` / `<canvas>`). Capture a screenshot and review it.

## Pitfalls
- **"Network request failed" on `init()` = CORS, not a code bug.** The vendor API 401s *without* `access-control-allow-origin`, so the browser treats it as a CORS failure. Fix = same-origin proxy.
- **Never ship the API key to the browser.** Inject it in the proxy. The share link's `ck_…` client key is embed-scoped and is often *rejected* by the raw API (401) — do not rely on it for the proxy; use the user's real API key.
- **`getAuth({})` with no creds → "No auth method provided".** Expected without the proxy key; do not confuse it with CORS.
- **Clone POST 400 `presenter is required`** — when cloning via `POST /agents`,
  KEEP the `presenter` block from the source GET (it carries `voice`, `source_url`,
  `thumbnail`, `type:"talk"`). My first clone attempt stripped `presenter`
  (wrongly treated it as server-only) and D-ID returned
  `ValidationError: 'presenter' is required`. Strip only admin fields
  (`id, owner_id, created_at, updated_at, access, client_keys, embed, score,
  playground_chats, created_by, chats, preview_thumbnail, status, modified_at,
  triggers, metadata, assets`) and KEEP `presenter, llm, knowledge, tools,
  greetings, vision, starter_message, advanced_settings, memory`.
- **Auth method in the clone script** must match the embed proxy: support
  `DID_BASIC` (base64 of `google-oauth2|<id>:<secret>`, sent as
  `Basic base64(<that>)`) the same way `server.py` does, not only `DID_API_KEY`.
  Guard the entrypoint on `if not (API_KEY or DID_BASIC)`.
- **iframe = vendor chrome.** If you must iframe (no proxy/key), the user sees the vendor's own buttons. Tell them.
- **Minified bundles:** the auth header is often rendered as `Authorization: ***` in the shipped bundle (obfuscated). Reconstruct it from the surrounding `Client-Key ${key}.${id}_${id}` template.
- **Versioned SDK redirects:** e.g. `agent.d-id.com/v2/index.js` re-exports from `../2.1.26/index-*.js`; fetch that chunk for analysis.
- **Run servers with `terminal(background=true)`**, never `&` in a foreground command (the tool rejects it).

## Deliverables to save (typical set)
- `index.html` (shell + mount div), `app.js` (SDK mount), `style.css` (theme), `server.py` (proxy + static host), `clone_agent.py` (clone source agent into the user's own account), `.env.example`, `README.md`, `favicon.svg`.

## Reference files
- `references/did-agent.md` — D-ID-specific extracted facts (tested, Aug 2026).
- `references/reverse-engineering.md` — how to pull share mechanics out of minified SPA bundles.
- `references/verification.md` — headless browser verification probe.
- `templates/server.py` — generic same-origin CORS proxy + static host.

## Production hardening (after clone)
Once the clone is live behind the proxy, lock it down before exposing: bind
localhost only, add a path whitelist locked to `DID_SOURCE_AGENT` (`403` for
anything else, `405` for DELETE), keep server-side secret injection. Full
recipe + verified curl test matrix: `hosted-agent-embedding` →
`references/proxy-hardening.md`.
