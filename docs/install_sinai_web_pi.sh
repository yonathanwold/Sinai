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
KIOSK_URL="${SINAI_KIOSK_URL:-http://127.0.0.1:8501}"

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

log "Configuring kiosk auto-launch on the Pi monitor..."
sudo -u "${SERVICE_USER}" mkdir -p "/home/${SERVICE_USER}/.local/bin"
sudo -u "${SERVICE_USER}" mkdir -p "/home/${SERVICE_USER}/.config/autostart"

cat > "/home/${SERVICE_USER}/.local/bin/sinai-kiosk.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail

URL="${KIOSK_URL}"
sleep 6

for _ in \$(seq 1 120); do
  if curl -fsS --max-time 2 "\${URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if pgrep -f "chromium.*127.0.0.1:8501" >/dev/null 2>&1; then
  exit 0
fi

exec /usr/bin/chromium \
  --kiosk \
  --app="\${URL}" \
  --noerrdialogs \
  --disable-session-crashed-bubble \
  --disable-infobars \
  --check-for-update-interval=31536000
EOF

cat > "/home/${SERVICE_USER}/.config/autostart/sinai-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Sinai Kiosk
Comment=Open Sinai local web UI on boot
Exec=/home/${SERVICE_USER}/.local/bin/sinai-kiosk.sh
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

chmod +x "/home/${SERVICE_USER}/.local/bin/sinai-kiosk.sh"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "/home/${SERVICE_USER}/.local" "/home/${SERVICE_USER}/.config/autostart"

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
