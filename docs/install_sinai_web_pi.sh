#!/usr/bin/env bash
set -euo pipefail

# Sinai Raspberry Pi bootstrap for the FastAPI local_web app.
# Usage:
#   bash docs/install_sinai_web_pi.sh [model] [repo_dir]
# Example:
#   bash docs/install_sinai_web_pi.sh llama3.2:1b /home/pi/Sinai

MODEL_NAME="${1:-llama3.2:1b}"
SINAI_DIR="${2:-$HOME/Sinai}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$USER}}"
REPO_URL="${SINAI_REPO_URL:-https://github.com/yonathanwold/Sinai.git}"

log() {
  echo "[Sinai Web] $*"
}

log "Starting Pi bootstrap for model '${MODEL_NAME}'"

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required for system setup."
  exit 1
fi

log "Installing system packages..."
sudo apt-get update
sudo apt-get install -y curl git "${PYTHON_BIN}" "${PYTHON_BIN}-venv"

if [ ! -d "${SINAI_DIR}" ]; then
  log "Cloning Sinai repo into ${SINAI_DIR}..."
  git clone "${REPO_URL}" "${SINAI_DIR}"
else
  log "Using existing Sinai directory at ${SINAI_DIR}"
fi

if ! command -v ollama >/dev/null 2>&1; then
  log "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
else
  log "Ollama already installed"
fi

log "Enabling Ollama service..."
sudo systemctl enable --now ollama

log "Pulling local model '${MODEL_NAME}'..."
ollama pull "${MODEL_NAME}"

log "Preparing Python environment..."
cd "${SINAI_DIR}"
"${PYTHON_BIN}" -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-hardware.txt || true

log "Disabling old dashboard service if present..."
if systemctl list-unit-files | grep -q '^sinai-dashboard.service'; then
  sudo systemctl disable --now sinai-dashboard || true
fi

log "Writing systemd service for Sinai local web app..."
SERVICE_TMP="$(mktemp)"
cat > "${SERVICE_TMP}" <<EOF
[Unit]
Description=Sinai Local Web (FastAPI)
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${SINAI_DIR}
Environment=OLLAMA_HOST=http://127.0.0.1:11434
Environment=OLLAMA_MODEL=${MODEL_NAME}
ExecStart=${SINAI_DIR}/.venv/bin/uvicorn app.local_web.server:app --host 0.0.0.0 --port 8501
Restart=always
User=${SERVICE_USER}

[Install]
WantedBy=multi-user.target
EOF

sudo cp "${SERVICE_TMP}" /etc/systemd/system/sinai-web.service
rm -f "${SERVICE_TMP}"

log "Enabling Sinai web service..."
sudo systemctl daemon-reload
sudo systemctl enable --now sinai-web

PI_IP="$(hostname -I | awk '{print $1}')"

log "Completed."
echo "Check status:"
echo "  systemctl status ollama --no-pager"
echo "  systemctl status sinai-web --no-pager"
echo
if [ -n "${PI_IP}" ]; then
  echo "Open from nearby devices: http://${PI_IP}:8501"
else
  echo "Open from nearby devices: http://<pi-ip>:8501"
fi
