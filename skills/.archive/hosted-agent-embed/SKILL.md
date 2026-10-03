---
name: hosted-agent-embed
description: Embed a hosted-agent share link via iframe.
---

# Hosted Agent Embed

Use when a user hands you a **share link** to a hosted AI avatar/agent (D-ID studio share, Tavus, HeyGen, etc.) and asks you to "clone it", "extract the code", "build a clone for my project", or "embed this agent". The key insight: **these links are not code repos** — they are credentials to a SaaS agent that runs on the vendor's servers. Your deliverable is a thin host page that mounts that agent, themed to the user's project.

## Trigger conditions
- User pastes a `studio.d-id.com/agents/share`, `tavus.io`, `heygen.com` share/embed URL.
- Phrases: "extract code from this", "build a clone of this agent", "embed this avatar in my app", "save the generated code to my project".
- The link contains `?id=` + `?key=` / `?token=` params (decoded credentials).

## The big pitfall (read this first)
A hosted agent embed looks trivial but has a **cross-origin auth trap**:

1. The vendor's JS SDK (`import("https://agent.d-id.com/v2/index.js")`) loads fine and `init()` runs — but its first runtime call (`GET /agents/{id}/runtime`) is **rejected cross-origin**. The API returns `401` AND **drops the `Access-Control-Allow-Origin` header** on the error response, so the browser reports a generic `CORS error → "Network request failed"`. You will waste time thinking it's a header/format bug. It isn't.
2. The raw `Client-Key` / `Authorization` header from the SDK is an **SDK-scoped embed key**, not a raw API key. Calling `api.d-id.com/agents/{id}` directly with it returns `401 Unauthorized` regardless of header format. Don't brute-force header permutations — they all 401.
3. The only cross-origin-safe method is to **frame the vendor's public share/embed route** (exactly what the vendor's own "Embed" / "Share" tab produces). The share route sends **no `X-Frame-Options` and no `Content-Security-Policy: frame-ancestors`**, so it frames cleanly, and the avatar's WebRTC + chat run *inside* the iframe — no CORS, no auth block.

> Rule: for a free share link, default to the **iframe embed**. Reserve the JS-SDK / raw-API path for when the user supplies their OWN paid API key and wants zero vendor branding.

## Workflow (verified on D-ID, 2026-08-10)
1. **Fetch the share page HTML** (it's a SPA shell — minor). Extract `id` and `key` from the URL query. The `key` param is often **base64** of the real key: decode with `echo "<param>" | base64 -d`.
2. **Probe framing headers** before committing to iframe:
   `curl -sI "<share-url>" | grep -iE 'x-frame-options|content-security-policy'`
   Empty output = safe to frame. If present, fall back to the JS-SDK path (or tell the user the link blocks embedding).
3. **Build a host page** that:
   - renders your theme/shell (terminal look, etc.),
   - drops an `<iframe>` pointing at the share URL, with
     `allow="microphone; camera; autoplay; clipboard-write"` and
     `referrerpolicy="strict-origin-when-cross-origin"`.
   - drives cosmetic status from the iframe's `load`/`error` events (you CANNOT read the iframe's internals cross-origin — don't try; just reflect load state).
4. **Verify in a real browser** (headless Chrome via Selenium — see references/did-agent-embed.md). Confirm: status pill = `live`, **0 SEVERE console errors**, and the iframe's HTML contains the vendor widget marker (`didagent` for D-ID) + a `<video>`/`<canvas>`.

## Diagnostic recipe (when SDK path fails)
- Confirm it's CORS, not a bad key: `curl -sI -H "Origin: <your-origin>" -X OPTIONS <api-url>` → if preflight shows `access-control-allow-origin: *` but the real `GET` with auth shows no ACAO + `HTTP/2 401`, the browser will block it. That's the trap.
- `curl -s -D - -o /dev/null -H "Origin: <your-origin>" -H "Authorization: Client-Key <key>..." <api-url>` → `401` confirms the key is SDK-scoped, not a raw API key.

## CORS allowlist note
Preflight for `api.d-id.com` returns `access-control-allow-origin: *` and lists `Authorization` in `access-control-allow-headers`. The auth failure is a runtime 401 on the authed GET, not a missing preflight grant. Don't confuse the two.

## Decoding the D-ID v2 flow (so you understand, not cargo-cult)
D-ID v2 share page does: `const mod = await import("https://agent.d-id.com/v2/index.js"); mod.init({ agentId, auth: mod.getAuth({clientKey}), mode:"full", targetElement, monitor:true })`. The SDK then calls `/agents/{id}/runtime` cross-origin → 401/CORS block. Hence the iframe fallback.

## References
- `references/did-agent-embed.md` — D-ID specifics: decoded credentials for the example agent, exact curl probes, and the Selenium verification recipe.
- `templates/` — a known-good, self-contained terminal-themed clone. Copy the folder (`terminal-avatar-clone.html`, `style.css`, `app.js`, `favicon.svg`), replace `AGENT_ID` and the share URL's `id`/`key`, serve, verify. Uses the iframe method.

## Anti-patterns
- Don't spend turns brute-forcing `Authorization` / `Client-Key` / `X-*` header variants against `api.d-id.com` — the key is SDK-scoped and will always 401.
- Don't claim "no code exists" and stop — deliver the working host-page clone. The "code" the user wants is the embed integration, which you CAN build and verify.
