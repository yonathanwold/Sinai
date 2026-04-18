#!/usr/bin/env bash
set -euo pipefail

# Sinai Raspberry Pi bootstrap
# Usage:
#   bash docs/install_ollama_mini_pi.sh [model] [repo_dir]
# Example:
#   bash docs/install_ollama_mini_pi.sh llama3.2:1b /home/pi/Sinai

MODEL_NAME="${1:-llama3.2:1b}"
SINAI_DIR="${2:-$HOME/Sinai}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[Sinai] Starting Pi bootstrap for model '${MODEL_NAME}'"

if ! command -v curl >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y curl
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "[Sinai] Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
else
  echo "[Sinai] Ollama already installed"
fi

echo "[Sinai] Enabling Ollama service..."
sudo systemctl enable --now ollama

echo "[Sinai] Pulling local model '${MODEL_NAME}'..."
ollama pull "${MODEL_NAME}"

if [ ! -d "${SINAI_DIR}" ]; then
  echo "[Sinai] ERROR: Sinai repo not found at ${SINAI_DIR}"
  echo "Clone the repo first, then rerun this script."
  exit 1
fi

echo "[Sinai] Preparing Python environment..."
cd "${SINAI_DIR}"
${PYTHON_BIN} -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-hardware.txt || true

echo "[Sinai] Writing systemd service for dashboard..."
SERVICE_TMP="$(mktemp)"
cat > "${SERVICE_TMP}" <<EOF
[Unit]
Description=Sinai Streamlit Dashboard
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${SINAI_DIR}
Environment=OLLAMA_HOST=http://127.0.0.1:11434
Environment=OLLAMA_MODEL=${MODEL_NAME}
Environment=SINAI_FORCE_MOCK=false
ExecStart=${SINAI_DIR}/.venv/bin/streamlit run app/dashboard/streamlit_app.py --server.address 0.0.0.0 --server.port 8501
Restart=always
User=${USER}

[Install]
WantedBy=multi-user.target
EOF

sudo cp "${SERVICE_TMP}" /etc/systemd/system/sinai-dashboard.service
rm -f "${SERVICE_TMP}"

echo "[Sinai] Enabling dashboard service..."
sudo systemctl daemon-reload
sudo systemctl enable --now sinai-dashboard

echo "[Sinai] Completed."
echo "[Sinai] Check status:"
echo "  systemctl status ollama --no-pager"
echo "  systemctl status sinai-dashboard --no-pager"
echo
echo "[Sinai] Nearby users can open: http://<pi-local-ip>:8501"
