#!/usr/bin/env bash
# install_ollama_service.sh -- make MOON's model backend (Ollama) run anywhere.
#
# Idempotent, portable systemd installer for the Ollama service that powers MOON's
# local models. Safe to re-run: it creates the service user only if missing,
# writes/refreshes the unit, and enables+starts it. All privileged steps use
# `sudo` automatically when not already root, so `sudo ./install_ollama_service.sh`
# or `make install` works on any Debian/Ubuntu-like host with systemd.
#
# Behaviour:
#   * Creates a dedicated unprivileged `ollama` user (system account, no login).
#   * Adds the invoking user to the `ollama` group so they can use the socket.
#   * Detects an NVIDIA GPU (nvidia-smi) and exports CUDA_VISIBLE_DEVICES / the
#     OLLAMA_CUDA env so Ollama uses the GPU when present; falls back to CPU.
#   * Sets OLLAMA_DEBUG=1 (operator preference) and a stable OLLAMA_HOST.
#
# Env overrides:
#   MOON_OLLAMA_USER   service account name   (default: ollama)
#   OLLAMA_HOST        listen address         (default: 127.0.0.1:11434)
#   OLLAMA_INSTALL_DIR home for the user      (default: /usr/share/ollama)
#   SKIP_OLLAMA_USER   set to 1 to not manage the user/group
set -euo pipefail

OLLAMA_USER="${MOON_OLLAMA_USER:-ollama}"
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
INSTALL_DIR="${OLLAMA_INSTALL_DIR:-/usr/share/ollama}"
UNIT_PATH="/etc/systemd/system/ollama.service"

# Re-exec with sudo when not root (so the file can be run directly).
if [[ $EUID -ne 0 ]]; then
  echo "[install_ollama] not root -> re-running under sudo"
  exec sudo "$0" "$@"
fi

echo "[install_ollama] Ollama service installer"
echo "[install_ollama] user=$OLLAMA_USER host=$OLLAMA_HOST dir=$INSTALL_DIR"

# --- 1. Ensure the ollama binary exists ------------------------------------
if ! command -v ollama >/dev/null 2>&1; then
  echo "[install_ollama] ollama binary not found on PATH."
  echo "[install_ollama] Install it first, e.g.:"
  echo "    curl -fsSL https://ollama.com/install.sh | sh"
  exit 1
fi

# --- 2. Service user (idempotent) ------------------------------------------
if [[ "${SKIP_OLLAMA_USER:-0}" != "1" ]]; then
  if ! id "$OLLAMA_USER" >/dev/null 2>&1; then
    echo "[install_ollama] creating system user '$OLLAMA_USER'"
    useradd -r -s /bin/false -U -m -d "$INSTALL_DIR" "$OLLAMA_USER"
  else
    echo "[install_ollama] user '$OLLAMA_USER' already exists -- skipping"
  fi
  # Add the (non-root) invoking user to the ollama group for socket access.
  INVOKER="${SUDO_USER:-$USER}"
  if [[ -n "$INVOKER" && "$INVOKER" != "$OLLAMA_USER" ]]; then
    if id -nG "$INVOKER" | tr ' ' '\n' | grep -qx "$OLLAMA_USER"; then
      echo "[install_ollama] '$INVOKER' already in group '$OLLAMA_USER'"
    else
      echo "[install_ollama] adding '$INVOKER' to group '$OLLAMA_USER'"
      usermod -a -G "$OLLAMA_USER" "$INVOKER"
    fi
  fi
fi

# --- 3. GPU detection (CUDA) ------------------------------------------------
GPU_ENV=""
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  echo "[install_ollama] NVIDIA GPU detected -> enabling CUDA"
  GPU_ENV=$'Environment="CUDA_VISIBLE_DEVICES=all"\nEnvironment="OLLAMA_CUDA=1"'
else
  echo "[install_ollama] no NVIDIA GPU -> CPU mode"
fi

# --- 4. Write the unit (idempotent refresh) --------------------------------
echo "[install_ollama] writing $UNIT_PATH"
cat > "$UNIT_PATH" <<EOF
[Unit]
Description=Ollama Service (MOON model backend)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/ollama serve
User=$OLLAMA_USER
Group=$OLLAMA_USER
Restart=always
RestartSec=3
Environment="OLLAMA_HOST=$OLLAMA_HOST"
Environment="OLLAMA_DEBUG=1"
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/bin"
$GPU_ENV

[Install]
WantedBy=multi-user.target
EOF

# --- 5. Reload / enable / start (idempotent) -------------------------------
echo "[install_ollama] daemon-reload"
systemctl daemon-reload

echo "[install_ollama] enable"
systemctl enable ollama

echo "[install_ollama] restart (applies new unit)"
systemctl restart ollama

# Give it a moment, then report status.
sleep 2
systemctl is-active --quiet ollama && echo "[install_ollama] ollama ACTIVE" || echo "[install_ollama] WARNING: ollama not active"

echo "[install_ollama] done. MOON's model backend is up at $OLLAMA_HOST"
