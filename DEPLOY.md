# Deploy MOON Anywhere

MOON runs fully self-hosted: her brain is local (Ollama), her tools are local,
and her only optional egress is permission-gated. This guide gets her running
on any Debian/Ubuntu-like host with systemd in three commands.

## 1. One-time: install MOON's model backend (Ollama)

```bash
git clone git@github.com:crsuvo100-gif/MOON.git
cd MOON
sudo make install          # installs Ollama as a systemd service
```

`make install` runs `scripts/install_ollama.py`, which is **idempotent** and
cross-platform:
- creates the unprivileged `ollama` system user (skips if present),
- adds you to the `ollama` group for socket access,
- detects an NVIDIA GPU (`nvidia-smi`) and enables CUDA automatically; CPU otherwise,
- sets `OLLAMA_DEBUG=1` and a stable `OLLAMA_HOST` (default `127.0.0.1:11434`),
- writes `/etc/systemd/system/ollama.service`, then `daemon-reload` + `enable` + `restart`.

If you already have Ollama, just ensure it is serving on `OLLAMA_HOST` and skip this step.

## 2. Python environment

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3. Launch MOON

```bash
make start                # boots Ollama if needed, then MOON Terminal (:8777)
# or:
python3 scripts/moon_launcher.py dashboard   # Flask+SocketIO dashboard (:5000)
python3 scripts/moon_launcher.py run "hi Moon"  # one-shot task via main.py
```

`moon_launcher.py` checks Ollama is reachable and starts the service if it can
(needs root/`sudo` for the systemd step only), then boots MOON.

## 4. Pull MOON's models (first time)

```bash
make models              # pre-pulls each agent's preferred local model
# or let MOON pull them on demand via the capability/auto-acquire system.
```

## Notes

- **No GPU?** MOON runs fine on CPU with 3B-and-under models (the defaults).
- **Secrets:** `.env` is gitignored. Copy `.env.example` to `.env` and edit locally.
- **Self-hosted by design:** all cognition stays on your machine; external
  connections (other AI agents, services, the web) are gated by
  `app/connector/permission.py` and require operator confirmation by default.
- **Updating:** `python -m moon update` (safe `git pull --ff-only` + reinstall), or
  manually `git pull --ff-only && pip install -e .`. Never `git reset --hard`
  and never force-push; the canonical remote is `origin` (SSH
  `git@github.com:crsuvo100-gif/MOON.git`).

> **Note on the GitHub login prompt:** MOON itself has NO password or login
> screen. If you are asked for a `Username` / `Password` for `github.com`, that
> is **Git/GitHub's own credential prompt**, triggered only when you clone via
> the **HTTPS** URL (`https://github.com/...`). To avoid it entirely, clone with
> the **SSH** URL above (uses your SSH key — no password). If you must use HTTPS,
> supply a **GitHub Personal Access Token (PAT)** as the password (not your account
> password); GitHub disabled password auth for git in 2021.
