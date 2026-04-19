#!/usr/bin/env bash
set -euo pipefail

BOOT_DIR="/boot/firmware"
if [ ! -d "${BOOT_DIR}" ]; then
  BOOT_DIR="/boot"
fi

LOG_FILE="${BOOT_DIR}/sinai-demo-ready.log"
PROGRESS_FILE="${BOOT_DIR}/sinai-ollama-progress.json"
TARGET_DIR="/home/pi/Sinai"
MODEL_NAME="${SINAI_OLLAMA_MODEL:-llama3.2:1b}"
HOTSPOT_SSID="${SINAI_HOTSPOT_SSID:-Sinai-AI-Test}"
HOTSPOT_IP="${SINAI_HOTSPOT_IP:-192.168.50.1}"
HOTSPOT_IFACE="${SINAI_HOTSPOT_IFACE:-wlan0}"
HOTSPOT_CHANNEL="${SINAI_HOTSPOT_CHANNEL:-6}"

exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
  echo "[Sinai Demo Ready] $(date -Is) $*"
}

write_progress() {
  local phase="$1"
  local percent="$2"
  local message="$3"
  cat > "${PROGRESS_FILE}" <<JSON
{"phase":"${phase}","percent":${percent},"message":"${message}","updated_at":"$(date -Is)"}
JSON
}

cleanup_cmdline() {
  local cmdline="${BOOT_DIR}/cmdline.txt"
  if [ -f "${cmdline}" ]; then
    sed -i \
      -e 's# systemd.run=/boot/firmware/sinai-demo-ready.sh##g' \
      -e 's# systemd.run=/boot/sinai-demo-ready.sh##g' \
      -e 's# systemd.run_success_action=reboot##g' \
      -e 's# systemd.unit=kernel-command-line.target##g' \
      "${cmdline}" || true
  fi
}

configure_autologin_and_kiosk() {
  log "Configuring monitor auto-login and kiosk launch."

  mkdir -p /etc/systemd/system/getty@tty1.service.d
  cat >/etc/systemd/system/getty@tty1.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin pi --noclear %I $TERM
EOF

  if [ -d /etc/lightdm ] || command -v lightdm >/dev/null 2>&1; then
    mkdir -p /etc/lightdm/lightdm.conf.d
    cat >/etc/lightdm/lightdm.conf.d/50-sinai-autologin.conf <<'EOF'
[Seat:*]
autologin-user=pi
autologin-user-timeout=0
EOF
  fi

  mkdir -p /home/pi/.config/autostart /home/pi/.config/lxsession/LXDE-pi
  cat >/home/pi/.config/lxsession/LXDE-pi/autostart <<'EOF'
@xset s off
@xset -dpms
@xset s noblank
@/usr/local/bin/sinai-kiosk-launch.sh
EOF

  cat >/home/pi/.config/autostart/sinai-monitor.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Sinai Monitor
Comment=Open the Sinai shared assistant screen
Exec=/usr/local/bin/sinai-kiosk-launch.sh
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

  cat >/usr/local/bin/sinai-kiosk-launch.sh <<'EOF'
#!/usr/bin/env bash
set -uo pipefail

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/home/pi/.Xauthority}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/1000}"

URL="${SINAI_MONITOR_URL:-http://127.0.0.1:8501/monitor}"
PROFILE_DIR="/home/pi/.config/sinai-kiosk-chromium"
mkdir -p "${PROFILE_DIR}"
exec 9>/tmp/sinai-kiosk-launch.lock
flock -n 9 || exit 0

for _ in $(seq 1 90); do
  if curl -fsS --max-time 2 "${URL}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

pkill -f 'chrom.*127.0.0.1:8501/monitor' >/dev/null 2>&1 || true

for browser in chromium-browser chromium google-chrome; do
  if command -v "${browser}" >/dev/null 2>&1; then
    exec "${browser}" \
      --kiosk "${URL}" \
      --user-data-dir="${PROFILE_DIR}" \
      --no-first-run \
      --no-default-browser-check \
      --disable-infobars \
      --disable-session-crashed-bubble \
      --disable-restore-session-state \
      --disable-features=TranslateUI,MediaRouter \
      --password-store=basic \
      --use-mock-keychain \
      --check-for-update-interval=31536000
  fi
done

echo "No Chromium browser found for Sinai kiosk." >&2
exit 1
EOF
  chmod +x /usr/local/bin/sinai-kiosk-launch.sh
  chown -R pi:pi /home/pi/.config

  if command -v raspi-config >/dev/null 2>&1; then
    raspi-config nonint do_boot_behaviour B4 || true
  fi
}

configure_web_service() {
  log "Ensuring Sinai web service starts on boot."
  if [ -d "${TARGET_DIR}" ]; then
    cat >/etc/systemd/system/sinai-web.service <<EOF
[Unit]
Description=Sinai Local Web (FastAPI)
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
WorkingDirectory=${TARGET_DIR}
Environment=OLLAMA_HOST=http://127.0.0.1:11434
Environment=OLLAMA_MODEL=${MODEL_NAME}
Environment=SINAI_OLLAMA_HOST=http://127.0.0.1:11434
Environment=SINAI_OLLAMA_MODEL=${MODEL_NAME}
Environment=HOME=/home/pi
Environment=SINAI_OLLAMA_TIMEOUT=60
Environment=SINAI_OLLAMA_MAX_TOKENS=80
Environment=SINAI_OLLAMA_CONTEXT_WINDOW=1536
Environment=SINAI_OLLAMA_KEEP_ALIVE=20m
ExecStart=${TARGET_DIR}/.venv/bin/uvicorn app.local_web.server:app --host 0.0.0.0 --port 8501
Restart=always
RestartSec=3
User=pi

[Install]
WantedBy=multi-user.target
EOF
    systemctl enable sinai-web
    systemctl restart sinai-web || true
  else
    log "${TARGET_DIR} is missing; leaving existing web service in place."
  fi
}

configure_hotspot() {
  log "Configuring fast open hotspot using hostapd and dnsmasq."

  cat >/usr/local/sbin/sinai-hotspot-start.sh <<EOF
#!/usr/bin/env bash
set -uo pipefail

BOOT_DIR="/boot/firmware"
if [ ! -d "\${BOOT_DIR}" ]; then
  BOOT_DIR="/boot"
fi
LOG_FILE="\${BOOT_DIR}/sinai-hotspot.log"
exec >> "\${LOG_FILE}" 2>&1

SSID="\${SINAI_HOTSPOT_SSID:-${HOTSPOT_SSID}}"
AP_IP="\${SINAI_HOTSPOT_IP:-${HOTSPOT_IP}}"
IFACE="\${SINAI_HOTSPOT_IFACE:-${HOTSPOT_IFACE}}"
CHANNEL="\${SINAI_HOTSPOT_CHANNEL:-${HOTSPOT_CHANNEL}}"

log() {
  echo "[Sinai Hotspot] \$(date -Is) \$*"
}

apply_port_redirect() {
  if command -v iptables >/dev/null 2>&1; then
    iptables -t nat -D PREROUTING -i "\${IFACE}" -p tcp --dport 80 -j REDIRECT --to-ports 8501 2>/dev/null || true
    iptables -t nat -A PREROUTING -i "\${IFACE}" -p tcp --dport 80 -j REDIRECT --to-ports 8501 || true
  fi
}

wait_for_wifi() {
  for _ in \$(seq 1 45); do
    if [ -d "/sys/class/net/\${IFACE}" ]; then
      return 0
    fi
    sleep 1
  done
  log "Wi-Fi interface \${IFACE} did not appear."
  ip link show || true
  return 1
}

log "Starting open hotspot."
rfkill unblock all >/dev/null 2>&1 || true
wait_for_wifi || exit 1

systemctl stop NetworkManager wpa_supplicant >/dev/null 2>&1 || true
systemctl stop hostapd dnsmasq >/dev/null 2>&1 || true

ip link set "\${IFACE}" down >/dev/null 2>&1 || true
ip addr flush dev "\${IFACE}" >/dev/null 2>&1 || true
ip addr add "\${AP_IP}/24" dev "\${IFACE}" >/dev/null 2>&1 || true
ip link set "\${IFACE}" up >/dev/null 2>&1 || true

cat >/etc/hostapd/hostapd.conf <<HEOF
country_code=US
interface=\${IFACE}
ssid=\${SSID}
hw_mode=g
channel=\${CHANNEL}
wmm_enabled=1
ieee80211n=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
HEOF

mkdir -p /etc/dnsmasq.d
cat >/etc/dnsmasq.d/sinai-hotspot.conf <<DEOF
interface=\${IFACE}
bind-interfaces
dhcp-range=192.168.50.20,192.168.50.250,255.255.255.0,24h
dhcp-authoritative
dhcp-option=option:router,\${AP_IP}
dhcp-option=option:dns-server,\${AP_IP}
address=/#/\${AP_IP}
no-resolv
cache-size=1000
DEOF

grep -q 'sinai.local' /etc/hosts 2>/dev/null || echo "\${AP_IP} sinai.local sinai.test" >> /etc/hosts
sed -i 's|^#*DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd || true

systemctl unmask hostapd >/dev/null 2>&1 || true
systemctl enable hostapd dnsmasq >/dev/null 2>&1 || true
systemctl restart hostapd dnsmasq
sleep 2
apply_port_redirect
systemctl is-active --quiet hostapd && systemctl is-active --quiet dnsmasq
log "Ready. SSID=\${SSID} URL=http://\${AP_IP}/client"
EOF

  chmod +x /usr/local/sbin/sinai-hotspot-start.sh

  cat >/etc/systemd/system/sinai-hotspot.service <<'EOF'
[Unit]
Description=Sinai Open Phone Hotspot
After=multi-user.target sinai-web.service
Wants=sinai-web.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/sleep 8
ExecStart=/usr/local/sbin/sinai-hotspot-start.sh
Restart=on-failure
RestartSec=8
StartLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl disable --now sinai-iphone-wifi >/dev/null 2>&1 || true
  systemctl disable --now NetworkManager >/dev/null 2>&1 || true
  systemctl disable --now wpa_supplicant >/dev/null 2>&1 || true
  systemctl enable sinai-hotspot
  systemctl restart sinai-hotspot || true
}

verify_ollama() {
  log "Verifying local Ollama model ${MODEL_NAME}."
  export HOME=/home/pi
  export OLLAMA_HOST=http://127.0.0.1:11434

  systemctl enable --now ollama >/dev/null 2>&1 || true
  for _ in $(seq 1 30); do
    if command -v ollama >/dev/null 2>&1 && ollama list >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done

  if command -v ollama >/dev/null 2>&1 && ollama list 2>/dev/null | awk '{print $1}' | grep -qx "${MODEL_NAME}"; then
    log "Verified local model is installed: ${MODEL_NAME}."
    write_progress "ready" 100 "Local AI model is installed and ready."
    return 0
  fi

  log "Local model ${MODEL_NAME} was not found. The app will run, but answers may use fallback mode."
  write_progress "error" 0 "Local model was not found. Reconnect internet to install it."
  return 1
}

main() {
  log "Starting demo-ready configuration."
  cleanup_cmdline
  configure_autologin_and_kiosk
  configure_web_service
  verify_ollama || true
  configure_hotspot
  systemctl daemon-reload
  sync
  log "Demo-ready configuration complete."
}

main "$@"
