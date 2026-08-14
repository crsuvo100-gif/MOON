# MOON NEXUS — Future Interface

Start with:

```bash
python3 run_nexus.py
```

Then open:

`http://127.0.0.1:8787/`

The NEXUS UI connects to the existing MOON bridge at:

`ws://127.0.0.1:8765/moon`

## Design principles

- Existing MOON brain/functions are untouched.
- The UI is an additive presentation and terminal layer.
- MOON controls reasoning, memory, retrieval, planning and tool decisions.
- The UI renders avatar state, speech, emotion, terminal output and capability events.
- The avatar is renderer-neutral and ready for a true 3D/VRM/neural renderer.
- No external CDN is required for the UI.
- The original Tk dashboard and all previous project files remain intact.

## Browser interaction

The browser can:
- connect/reconnect to MOON
- display MOON capability events
- show live terminal output
- run/cancel terminal jobs through the existing policy
- display OS/shell/Python/CWD
- visualize avatar states
- show event history
