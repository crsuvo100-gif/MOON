#!/usr/bin/env bash
# =============================================================================
# MOON — portable installer
# -----------------------------------------------------------------------------
# One command to get MOON running on a fresh Linux/macOS machine:
#
#     git clone <moon-repo> && cd MOON && ./install.sh
#
# What it does (all additive / idempotent / non-destructive):
#   1. Checks Python >= 3.10
#   2. Creates ./venv (skips if present) and installs requirements.txt
#   3. Detects a browser for the HUD (google-chrome / chromium)
#   4. Installs a `moon` launcher into ~/.local/bin (on PATH)
#   5. Installs a `moon-terminal.desktop` entry (Linux)
#   6. OPTIONALLY installs a systemd *user* service (asked, default = no)
#      -- MOON auto-opens its HUD on MOON boot (not system login) via the
#         Settings -> autostart toggle, which is the intended behaviour.
#
# The installer never overwrites your settings, never touches system files
# outside ~/.local and ~/.config, and never runs as root unless you ask for
# the systemd service (which uses `systemctl --user`, no sudo).
# =============================================================================
set -euo pipefail

MOON_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$MOON_HOME"

# --- colours --------------------------------------------------------------
if [[ -t 1 ]]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[36m'; N=$'\033[0m'
else R=""; G=""; Y=""; B=""; N=""; fi
log(){ printf '%s[MOON]%s %s\n' "$B" "$N" "$1"; }
ok(){ printf '%s[OK]%s  %s\n' "$G" "$N" "$1"; }
warn(){ printf '%s[!!]%s  %s\n' "$Y" "$N" "$1"; }
err(){ printf '%s[XX]%s  %s\n' "$R" "$N" "$1"; }

# --- 1. Python check ------------------------------------------------------
PY_BIN="$(command -v python3 || true)"
if [[ -z "$PY_BIN" ]]; then err "python3 not found. Install Python >= 3.10 first."; exit 1; fi
PY_VER="$("$PY_BIN" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
if [[ "$(printf '%s\n' "$PY_VER" "3.10" | sort -V | head -1)" != "3.10" ]]; then
  err "Python $PY_VER found, but MOON needs >= 3.10."; exit 1
fi
ok "Python $PY_VER at $PY_BIN"

# --- 2. Virtualenv + deps -------------------------------------------------
if [[ ! -x "$MOON_HOME/.venv/bin/python" ]]; then
  log "Creating virtualenv in ./.venv ..."
  "$PY_BIN" -m venv .venv
  ok "venv created"
else
  log "venv already present, reusing it."
fi
VENVPY="$MOON_HOME/.venv/bin/python"
PIP="$MOON_HOME/.venv/bin/pip"

log "Upgrading pip ..."
"$PIP" install --quiet --upgrade pip wheel setuptools 2>&1 | tail -1 || true

REQ="$MOON_HOME/requirements.txt"
if [[ -f "$REQ" ]]; then
  log "Installing CORE dependencies from requirements.txt ..."
  if "$PIP" install --quiet -r "$REQ" 2>&1 | tail -5; then
    ok "core dependencies installed"
  else
    err "core dependency install failed — MOON cannot run without them."
    err "Check the output above and your network / Python version (>=3.10)."
    exit 1
  fi
else
  warn "requirements.txt not found; skipping dependency install."
fi

# Install the MOON package itself (editable) so `python -m moon` and the
# `moon` console script both work after a fresh clone. Additive: the root
# `main.py` entry point remains available too (the ~/.local/bin/moon launcher
# uses it). Skipping this would leave `python -m moon` unavailable.
log "Installing MOON package (editable) so 'python -m moon' works ..."
if "$VENVPY" -m pip install --quiet -e . 2>&1 | tail -5; then
  ok "moon package installed (python -m moon available)"
else
  warn "package install (-e .) failed; main.py entry still works via the launcher."
fi

# Optional deps are best-effort: a missing/unavailable package must NOT break
# the base install (e.g. TTS has no wheel for some Python versions).
OPT="$MOON_HOME/requirements-optional.txt"
if [[ -f "$OPT" ]]; then
  log "Installing OPTIONAL dependencies (best-effort) from requirements-optional.txt ..."
  if "$PIP" install --quiet -r "$OPT" 2>&1 | tail -5; then
    ok "optional dependencies installed"
  else
    warn "some optional dependencies were skipped (MOON still runs without them)."
  fi
fi

# --- 2b. Delegate the Python-stage bootstrap to install_moon.py (single source
#         of truth for .env creation, Ollama model pull, voice stack, smoke
#         import). It reuses the venv we just built (--no-venv) so dependency
#         install is never duplicated. This is additive: install_moon.py remains
#         fully runnable on its own; install.sh just orchestrates it.
if [[ -x "$VENVPY" ]]; then
  log "Delegating .env / models / voice / smoke-import to install_moon.py ..."
  if "$VENVPY" install_moon.py --no-venv 2>&1 | tail -8; then
    ok "Python-stage bootstrap complete (via install_moon.py)"
  else
    warn "install_moon.py reported issues (MOON may still run; review output above)."
  fi
else
  warn "venv python missing; skipping install_moon.py delegation."
fi

# --- 3. Browser detection -------------------------------------------------
CHROME="$(command -v google-chrome || command -v google-chrome-stable || command -v chromium || command -v chromium-browser || true)"
if [[ -n "$CHROME" ]]; then ok "browser found: $CHROME"; else warn "no Chrome/Chromium found — install one for the HUD (e.g. apt install chromium)"; fi

# --- 4. `moon` launcher in ~/.local/bin ----------------------------------
BIN_DIR="${HOME}/.local/bin"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/moon" <<EOF
#!/usr/bin/env bash
# MOON launcher — runs MOON from its install dir, clearing PYTHONPATH so the
# project venv is used unambiguously (avoids pydantic_core shadowing on systems
# where a different Python is on PYTHONPATH).
cd "$MOON_HOME" || exit 1
exec env -u PYTHONPATH "$MOON_HOME/.venv/bin/python" main.py "\$@"
EOF
chmod +x "$BIN_DIR/moon"
ok "launcher installed: $BIN_DIR/moon"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  warn "$BIN_DIR is not on your PATH. Add it:  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# --- 5. Desktop entry (Linux) --------------------------------------------
if [[ "$(uname)" == "Linux" ]]; then
  APPS="$HOME/.local/share/applications"
  mkdir -p "$APPS"
  cat > "$APPS/moon-terminal.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=MOON Neural Core
Comment=MOON sentient AI terminal HUD
Exec=$BIN_DIR/moon terminal
Icon=utilities-terminal
Terminal=false
Categories=Network;Utility;
EOF
  chmod +x "$APPS/moon-terminal.desktop"
  ok "desktop entry: $APPS/moon-terminal.desktop"
fi

# --- 6. Optional systemd user service ------------------------------------
read -r -p $'\033[33m[??]\033[0m Install a systemd *user* service so MOON auto-starts on login? [y/N] ' ANS || ANS="n"
if [[ "${ANS,,}" == "y" || "${ANS,,}" == "yes" ]]; then
  if command -v systemctl >/dev/null 2>&1; then
    SRC="$MOON_HOME/tools/install_terminal_service.sh"
    if [[ -x "$SRC" ]]; then bash "$SRC"; else warn "service installer missing: $SRC"; fi
  else warn "systemctl not available on this system; skipping service install."; fi
else
  log "Skipping systemd service (MOON still auto-opens its HUD on MOON boot via Settings -> autostart)."
fi

# --- done ----------------------------------------------------------------
echo
ok "MOON is installed at $MOON_HOME"
log "Launch the terminal HUD with:  moon terminal"
log "Or run directly:               ./venv/bin/python main.py terminal"
echo
