#!/usr/bin/env bash
# MOON -- Neural Brain Command Center
# One-command installer.
#
# Usage:
#   ./install.sh [--yes] [--no-venv] [--no-symlink] [--no-launch]
#
# What it does:
#   1. Checks prerequisites (git, python3 >= 3.10, pip, curl)
#   2. Creates a virtual environment (.venv)
#   3. Installs dependencies (requirements.txt, requirements-optional.txt)
#   4. Installs the package (pip install -e .)
#   5. Registers the `moon` / `moon-terminal` CLI entry points on PATH
#      - fixes the editable-install .pth so the project root (main.py) is importable
#      - symlinks the console scripts into ~/.local/bin
#   6. Runs first-run setup wizard (non-interactive if --yes)
#   7. Post-install health check (moon doctor)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

YES=0
NO_VENV=0
NO_SYMLINK=0
NO_LAUNCH=0

for arg in "$@"; do
    case "$arg" in
        --yes) YES=1 ;;
        --no-venv) NO_VENV=1 ;;
        --no-symlink) NO_SYMLINK=1 ;;
        --no-launch) NO_LAUNCH=1 ;;
        -h|--help)
            echo "Usage: $0 [--yes] [--no-venv] [--no-symlink] [--no-launch]"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            exit 1
            ;;
    esac
done

echo "=== MOON Installer ==="
echo "Project: $SCRIPT_DIR"

# --- Pre-flight ---
echo ""
echo "[1/7] Pre-flight checks..."
for cmd in git python3 pip3 curl; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd not found. Install it first."
        exit 1
    fi
done

PYTHON_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "  Python: $PYTHON_VER"
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
    echo "ERROR: Python 3.10+ required."
    exit 1
fi

# --- Create virtual environment ---
if [ "$NO_VENV" -eq 0 ]; then
    echo ""
    echo "[2/7] Creating virtual environment..."
    if [ -d .venv ]; then
        echo "  .venv already exists; reusing."
    else
        python3 -m venv .venv
    fi
    .venv/bin/python -m pip install --upgrade pip wheel setuptools
else
    echo ""
    echo "[2/7] (skipped venv creation, using existing python3 environment)"
fi

# --- Install dependencies ---
echo ""
echo "[3/7] Installing dependencies..."
.venv/bin/pip install --quiet --upgrade pip 2>/dev/null || true
.venv/bin/pip install --quiet -r requirements.txt
.venv/bin/pip install --quiet -r requirements-optional.txt 2>/dev/null || true

# --- Install the package (editable, so entry points persist) ---
echo ""
echo "[4/7] Installing package (editable)..."
.venv/bin/pip install --quiet -e . 2>&1 | tail -5

# --- Register CLI entry points on PATH ---
echo ""
echo "[5/7] Registering `moon` / `moon-terminal` CLI on PATH..."
# The editable install drops console scripts into .venv/bin.
# The editable .pth must also add the project root to sys.path, otherwise
# `from main import main` fails (main.py lives at the project root, not in site-packages).
_PTH=""
for _candidate in "$SCRIPT_DIR/.venv/lib/python3.14/site-packages/__editable__"*.pth; do
    if [ -f "$_candidate" ]; then
        _PTH="$_candidate"
        break
    fi
done
if [ -n "$_PTH" ]; then
    printf '\n# Add project root to sys.path so top-level modules (main) importable\nimport os,sys;_R=os.path.dirname(os.path.abspath(sys.prefix));sys.path.insert(0,_R)\n' >> "$_PTH"
    echo "  Fixed editable-install .pth: $_PTH"
else
    echo "  WARN: no editable-install .pth found; moon may not import from anywhere."
fi

# Symlink the console scripts into ~/.local/bin (already on PATH on most systems)
if [ "$NO_SYMLINK" -eq 0 ]; then
    mkdir -p "$HOME/.local/bin"
    ln -sfn "$SCRIPT_DIR/.venv/bin/moon" "$HOME/.local/bin/moon"
    ln -sfn "$SCRIPT_DIR/.venv/bin/moon-terminal" "$HOME/.local/bin/moon-terminal"
    echo "  Symlinks created: ~/.local/bin/moon      -> .venv/bin/moon"
    echo "  Symlinks created: ~/.local/bin/moon-terminal -> .venv/bin/moon-terminal"
    if ! echo "$PATH" | tr ':' '\n' | grep -qx "$HOME/.local/bin"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
        echo "  Added ~/.local/bin to PATH in ~/.bashrc"
    fi
fi

# --- First-run setup ---
if [ "$YES" -eq 1 ]; then
    echo ""
    echo "[6/7] Running first-run setup (non-interactive)..."
    if [ -f "setup_wizard.py" ]; then
        .venv/bin/python setup_wizard.py --yes 2>/dev/null || true
    fi
else
    echo ""
    echo "[6/7] First-run setup: run 'moon setup' or 'python setup_wizard.py' to configure .env"
fi

# --- Post-install health check ---
echo ""
echo "[7/7] Post-install health check..."
if [ "$NO_LAUNCH" -eq 0 ]; then
    echo "  Starting MOON backend in background..."
    nohup "$SCRIPT_DIR/.venv/bin/moon" status >/dev/null 2>&1 &
    sleep 4
    moon status 2>&1 | head -8
fi

echo ""
echo "=== MOON installation complete ==="
echo "  CLI:     moon / moon-terminal  (on PATH via ~/.local/bin)"
echo "  Web UI:  http://127.0.0.1:8777"
echo "  Terminal: moon terminal"
echo "  First run: moon setup / python setup_wizard.py"
echo ""
