---
name: headless-render-screenshot
description: "Render and screenshot HTML prototypes headlessly."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [playwright, headless, screenshot, three.js, webgl, prototype, visual-verification, html]
    related_skills: [sketch, claude-design, pretext, p5js, popular-web-designs, runnable-project-generator, spike, moon-ops]
---

# Headless Render + Screenshot

Render any HTML/JS/CSS prototype in headless Chromium via Playwright and capture timed screenshots for visual verification. Use this when the default `computer_use` flow (raise the user's browser, navigate, look at it) is wrong for the job — either because the artifact is WebGL/Three.js (which often won't run from `file://`) or because you want a fully isolated proof-of-life capture that doesn't disturb the user's screen.

## When to use

- **WebGL / Three.js / Canvas2D / ES-module artifacts.** Many module loaders refuse to run from `file://` (CORS, MIME, importmap restrictions). You need a real HTTP origin.
- **Headless verification without disturbing the user.** The user is on Kali working in a terminal; raising a browser over their session is rude. A separate headless Chromium is invisible.
- **Comparing two animation states** (initial vs after N seconds) to prove a `requestAnimationFrame` loop is alive. The single-screenshot `computer_use` flow can't do this.
- **Visual regression checks** on a project that has no other test infrastructure. Render at commit A, render at commit B, diff.

This is infrastructure, not a workflow. It supports `sketch`, `claude-design`, `pretext`, `p5js`, `popular-web-designs`, `moon-ops`, and any "show me visually" / "screenshot it" / "prove it works" task on a web artifact.

## When NOT to use

- Static HTML/CSS with no WebGL, no ES modules, no animation loop — the default `computer_use` (`browser_navigate` + `browser_vision`) is faster and simpler.
- The user wants to *interact* with the page (click, type, scroll) — use `computer_use` for that, not Playwright.
- The page needs auth or state from the user's actual session — Playwright launches a fresh profile.

## Core workflow (6 steps)

### 1. Stand up a local HTTP server (loopback only)

WebGL/ES modules don't load from `file://` in Chromium. Use Python's stdlib server.

**Always `terminal(background=true)` — the smart-approval layer rejects `&` in foreground commands.**

```python
terminal(command="cd /path/to/proto && python3 -m http.server 8765 --bind 127.0.0.1",
         background=True, notify_on_complete=False)
```

Verify with `curl -sI http://127.0.0.1:8765/index.html` to confirm 200 before driving the browser.

### 2. Get a working Playwright + Chromium

The system Python's `playwright` is often broken on Kali/Debian (a stub `playwright/__init__.py` shadows the real package). `playwright install` also tends to time out downloading `chromium_headless_shell` while still completing the full `chromium` download. The reliable path:

```bash
python3 -m venv /tmp/pwenv
/tmp/pwenv/bin/pip install --quiet playwright
/tmp/pwenv/bin/python -m playwright install chromium   # may take 2-3 min
```

The download writes to `~/.cache/ms-playwright/chromium-<rev>/chrome-linux64/chrome`. **If only the full chromium (not `chromium_headless_shell`) finished, point Playwright at the full binary directly** — it works for `headless=True`:

```python
browser = p.chromium.launch(
    headless=True,
    executable_path="/home/meow/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome",
    args=["--no-sandbox", "--use-gl=swiftshader", "--enable-webgl",
          "--ignore-gpu-blocklist", "--enable-accelerated-2d-canvas",
          "--disable-dev-shm-usage"],
)
```

These flags are mandatory on a headless Linux box:

- `--no-sandbox` — no user namespace available
- `--use-gl=swiftshader` — software WebGL (no real GPU)
- `--ignore-gpu-blocklist` — needed for SwiftShader to be picked up
- `--disable-dev-shm-usage` — limited `/dev/shm`

### 3. Drive the page

```python
from playwright.sync_api import sync_playwright
import time

URL = "http://127.0.0.1:8765/index.html"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=..., args=[...])
    ctx = browser.new_context(viewport={"width": 1600, "height": 900},
                              device_scale_factor=1)
    page = ctx.new_page()
    page.on("console", lambda m: print(f"[console.{m.type}] {m.text}"))
    page.on("pageerror", lambda e: print(f"[pageerror] {e}"))
    page.goto(URL, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_selector("#your-root-element", timeout=10000)
    time.sleep(3.0)  # let animation loops settle
    page.screenshot(path="frame-01.png", full_page=False)
```

`page.wait_for_selector` on a known DOM element is the cheap way to wait for the scene to mount. The `time.sleep` after lets the first few animation frames render so particles/text aren't frozen at init.

**Don't use `page.wait_for_load_state("networkidle")`** for ES-module apps — importmap fetches from CDNs never fully go idle because of trailing keep-alive connections. Use `domcontentloaded` + `wait_for_selector` + sleep.

### 4. Capture a motion-diff to prove the loop is alive

```python
state1 = page.evaluate("""() => ({
  fps:  document.getElementById('fps').textContent,
  line: document.getElementById('thought').textContent,
})""")
time.sleep(3.0)
state2 = page.evaluate("""() => ({
  fps:  document.getElementById('fps').textContent,
  line: document.getElementById('thought').textContent,
})""")
assert state1 != state2, "page is static — animation loop not running"
```

For WebGL scenes, also assert the canvas exists and is non-zero:

```python
ok = page.evaluate("""() => {
  const c = document.querySelector('#canvas-container canvas');
  return c && c.width > 0 && c.height > 0;
}""")
```

### 5. Inspect the screenshot

Use `vision_analyze(image_url="/abs/path/to/frame.png", question="Describe what you see, including...")` to get an honest visual readout. Ask the model to verify the specific elements you care about (panels visible, scene rendering, no text overflow, layout intact). Don't trust pixel-level assertions — the user will look at the result.

### 6. Tear down

```python
browser.close()
```

Then `process(action='kill', session_id=<server-session-id>)` to stop the HTTP server. Don't leave it running.

## Pitfalls

- **`terminal(... & ...)` gets rejected** by the smart-approval layer. Always use `terminal(background=true)`. `notify_on_complete=true` is for bounded jobs (tests, builds); for servers/watchers leave it `false`.
- **System Python's `playwright` may be a stub** that imports but doesn't bind `_playwright`. Symptom: `AttributeError: 'PlaywrightContextManager' object has no attribute '_playwright'`. Fix: use a venv.
- **`playwright install` for `chromium_headless_shell` may hang or time out** while the full `chromium` download completes. Check `~/.cache/ms-playwright/` and use the full `chrome` binary via `executable_path` if the headless shell isn't there.
- **Favicon 404 in console** is harmless. Don't chase it.
- **FPS will look low (5-15)** in headless because SwiftShader is software WebGL. Not a real bug — explain it in the report so the user doesn't worry.
- **A 1MB black/white PNG is the canary** for "WebGL didn't initialize" — re-run with all the flags above.
- **Device pixel ratio on headless**: cap with `device_scale_factor=1` to keep screenshot file sizes sane. Headless Chromium otherwise renders at 2x.
- **Don't bind to a public interface.** `--bind 127.0.0.1` is loopback-only. Never use `0.0.0.0` on a prototype server.
- **Headless `--screenshot` captures the COLD state of a live-data UI.** Chromium's `--screenshot` (and `Page.captureScreenshot` at load) fires at the `load` event — BEFORE async work resolves: XHR/`fetch('/status')` calls, WebSocket status polls (5s+ cadence), Ollama/model cold-loads. So a dashboard whose panels are filled by a WS poll or an async fetch will render with **all-zero / placeholder values** in a headless screenshot even though the real browser populates within seconds and the backend is serving correct data. This is a CAPTURE-TIMING ARTIFACT, not a UI bug — do NOT burn turns "fixing" the 0% values or rewriting `apply()`. Symptoms: the 3D/canvas face renders fine (proving JS runs), only the data panels read 0%. Synchronous `XMLHttpRequest(...,false)` seed helps but can still be blocked/slow during load and is defeated by a cold backend (first `/status` that initializes the orchestrator can take 30s+). The robust verification is to prove the DATA PATH directly (see below), not to keep re-screenshotting.

## Verifying a live-data UI without trusting the screenshot

When the page is filled by an async WebSocket poll or fetch, a headless screenshot of the cold state is misleading. Confirm the backend is actually serving real values and feeding `apply()` correctly, independently of the render:

```bash
# 1. The HTTP status endpoint must return REAL (non-zero) data
curl -s --max-time 60 http://127.0.0.1:8777/status \
  | env -u PYTHONPATH .venv/bin/python -c "import sys,json;d=json.load(sys.stdin);print('agents',d.get('agents'),'cpu',d.get('system',{}).get('cpu'))"
# If this is slow on first call, the orchestrator is cold-initializing — warm it with one curl, then re-render.

# 2. The WebSocket path must deliver the same payload (proves the page's onmessage->apply works)
env -u PYTHONPATH .venv/bin/python - <<'PY'
import asyncio, json, websockets
async def t():
    async with websockets.connect("ws://127.0.0.1:8777/ws") as ws:
        await ws.send(json.dumps({"action":"status"}))
        m = json.loads(await asyncio.wait_for(ws.recv(), 5))
        if m.get("type") == "status":
            print("WS ok: agents=%s cpu=%s" % (m.get("agents"), m.get("system",{}).get("cpu")))
asyncio.run(t())
PY
```

If both return real data, the UI **will** populate in a live browser (which is what the user uses). Report the screenshot limitation honestly rather than chasing phantom 0% values.

**Headless capture that waits for live data:** if you must screenshot the populated state, do NOT rely on `--virtual-time-budget` (async XHR/fetch don't advance virtual time reliably). Use the CDP `Runtime.evaluate` loop (see `scripts/cdp_wait_screenshot.js`): open the page, poll a known populated element (e.g. `document.getElementById('envNodes').textContent !== '0'`) every 500ms, then `Page.captureScreenshot`. This is what works when the WS connects; if even that stays 0 after 60s, the sandbox headless browser is not opening the WebSocket (a sandbox quirk) — fall back to the curl+WS proof above.

See `references/headless-live-data-verification.md` for the full recipe and the gotchas that cost real turns this session.

## Verification before declaring done

Before you tell the user the prototype works, confirm:

1. The HTTP server returned 200 for the entry HTML.
2. The browser console had **zero** `[error]` lines (warnings from the GL driver are fine).
3. Both screenshots exist on disk and have non-trivial size.
4. `state1 != state2` proves the animation loop is alive (if the prototype has one).
5. `vision_analyze` confirms the expected elements are present and laid out correctly.

## See also

- `references/playwright-setup-troubleshooting.md` — the exact diagnostics when Playwright misbehaves on a fresh Kali box (which path to try first, which flags are required, why `networkidle` is a trap).
- `references/headless-live-data-verification.md` — how to verify a WebSocket/fetch-driven dashboard when headless screenshots show cold 0% values (the curl+WS proof, the CDP wait-loop, the sandbox-WS-quirk fallback). Born from a session that burned ~15 turns re-screenshotting phantom zeros.
- `scripts/render_prototype.py` — drop-in Playwright capture script. Edit the URL + output dir, run, get screenshots and a motion-diff verdict.
- `scripts/cdp_wait_screenshot.js` — headless capture that waits for a live-data element before screenshotting (when the WS actually connects).
- `templates/page-mock.html` — minimal HTML harness with importmap, canvas container, and HUD elements for Three.js / WebGL prototypes. Copy and modify.
