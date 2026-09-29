# MOON — Installation Guide

A self-hosted autonomous AI agent with its own "brain", connected per-agent brains, and continuous self-learning.

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Linux (Debian/Ubuntu/Kali) or macOS | Linux x86_64 |
| Python | 3.10+ | 3.11–3.14 |
| RAM | 2 GB free | 4 GB+ |
| Disk | 500 MB free | 2 GB+ |
| Network | Outbound HTTP/HTTPS | — |
| Browser | — | Chromium/Chrome (for HUD) |

---

## One-Command Install (Recommended)

```bash
git clone https://github.com/crsuvo100-gif/MOON.git
cd MOON
./install.sh --yes
```

This does everything: venv, dependencies, models, voice assets, launcher, systemd service, and a post-install health check.

---

## Manual Install (Step by Step)

### 1. Clone and enter the project

```bash
git clone https://github.com/crsuvo100-gif/MOON.git
cd MOON
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
pip install -r requirements-optional.txt   # best-effort; safe to skip
pip install -e .                            # makes `python -m moon` work
```

### 4. Run the setup wizard (first run only)

```bash
python setup_wizard.py          # interactive
python setup_wizard.py --yes    # non-interactive, uses defaults
```

This creates `.env` with your model backend, API keys, and safety boundary.

### 5. Install the launcher

The installer puts a `moon` script in `~/.local/bin/moon`. Make sure `~/.local/bin` is on your PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### 6. Start MOON

```bash
moon terminal          # opens the terminal HUD
# or:
./venv/bin/python main.py terminal
```

### 7. Verify it's running

```bash
curl -s http://127.0.0.1:8777/api/health
# Expected: {"status":"healthy",...}
```

---

## systemd Service (Auto-start + Self-heal)

The installer can set up a systemd user service so MOON starts on boot and restarts on failure:

```bash
# During install.sh: answer 'Y' to the systemd prompt
# Or manually:
cp deploy/moon-terminal.service ~/.config/systemd/user/moon-terminal.service
sed -i "s|__MOON_HOME__|$PWD|g" ~/.config/systemd/user/moon-terminal.service
systemctl --user daemon-reload
systemctl --user enable --now moon-terminal.service
```

The deep monitor runs every 15 minutes to verify MOON is actually responding:

```bash
cp deploy/moon-monitor.service ~/.config/systemd/user/
cp deploy/moon-monitor.timer ~/.config/systemd/user/
systemctl --user enable --now moon-monitor.timer
```

---

## Ollama (Model Backend)

MOON uses Ollama for local LLM inference. The Makefile target handles it:

```bash
make install          # installs Ollama systemd service
make start            # boots Ollama then MOON
```

Or manually:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:0.5b     # or any model you configure
```

---

## Voice (Optional)

MOON speaks with a female voice (espeak `f5` + SoX timbre chain):

```bash
make voice-install       # install espeak + sox
make voice-test          # generate a sample WAV
make voice               # companion loop: type -> MOON -> voice
```

For microphone dictation, set `VOSK_MODEL_DIR` and use `make voice -- --mic`.

---

## Uninstall

```bash
# Stop services
systemctl --user stop moon-terminal.service
systemctl --user disable moon-terminal.service
systemctl --user stop moon-monitor.timer
rm -rf ~/.config/systemd/user/moon-*.service ~/.config/systemd/user/moon-*.timer
rm -f ~/.local/bin/moon
rm -f ~/.local/share/applications/moon-terminal.desktop
rm -rf MOON/
```
