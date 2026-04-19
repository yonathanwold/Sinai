#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/boot/firmware/sinai-emergency-demo.log"
if [ ! -d "/boot/firmware" ]; then
  LOG_FILE="/boot/sinai-emergency-demo.log"
fi

SSID="${SINAI_HOTSPOT_SSID:-Sinai-AI-Demo}"
PASSWORD="${SINAI_HOTSPOT_PASSWORD:-12345678}"
IFACE="${SINAI_HOTSPOT_IFACE:-wlan0}"
AP_IP="${SINAI_HOTSPOT_IP:-192.168.50.1}"
CHANNEL="${SINAI_HOTSPOT_CHANNEL:-11}"
APP_DIR="${SINAI_APP_DIR:-/home/pi/Sinai}"
MODEL="${SINAI_OLLAMA_MODEL:-llama3.2:1b}"

exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
  echo "[Sinai Emergency] $(date -Is) $*"
}

stop_old_stack() {
  log "Stopping conflicting services."
  systemctl stop sinai-hotspot sinai-web nginx apache2 caddy lighttpd NetworkManager wpa_supplicant dhcpcd dnsmasq hostapd >/dev/null 2>&1 || true
  pkill -f 'uvicorn app.local_web.server:app' >/dev/null 2>&1 || true
  pkill -x hostapd >/dev/null 2>&1 || true
  pkill -x dnsmasq >/dev/null 2>&1 || true
  rm -f /run/sinai-hostapd.pid /run/sinai-dnsmasq.pid /var/lib/misc/sinai-dnsmasq.leases
}

configure_wifi() {
  log "Configuring Wi-Fi access point ${SSID} on ${IFACE}."
  rfkill unblock all >/dev/null 2>&1 || true
  ip link set "${IFACE}" down >/dev/null 2>&1 || true
  ip addr flush dev "${IFACE}" >/dev/null 2>&1 || true
  ip addr add "${AP_IP}/24" dev "${IFACE}"
  ip link set "${IFACE}" up

  cat >/tmp/sinai-hostapd.conf <<EOF
country_code=US
interface=${IFACE}
driver=nl80211
ssid=${SSID}
hw_mode=g
channel=${CHANNEL}
wmm_enabled=0
ieee80211n=0
ieee80211d=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
ap_isolate=0
wpa=2
wpa_passphrase=${PASSWORD}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
rsn_pairwise=CCMP
ieee80211w=0
EOF

  local prefix="${AP_IP%.*}"
  cat >/tmp/sinai-dnsmasq.conf <<EOF
interface=${IFACE}
bind-dynamic
listen-address=${AP_IP}
port=53
dhcp-range=${prefix}.20,${prefix}.250,255.255.255.0,2h
dhcp-authoritative
dhcp-option=option:router,${AP_IP}
dhcp-option=option:dns-server,${AP_IP}
dhcp-option=114,http://${AP_IP}/client
dhcp-option=252,http://${AP_IP}/client
address=/#/${AP_IP}
no-resolv
cache-size=1000
log-dhcp
EOF
}

start_network() {
  log "Starting hostapd and dnsmasq."
  /usr/sbin/hostapd -B -P /run/sinai-hostapd.pid /tmp/sinai-hostapd.conf
  nohup /usr/sbin/dnsmasq --no-daemon --conf-file=/tmp/sinai-dnsmasq.conf --pid-file=/run/sinai-dnsmasq.pid --dhcp-leasefile=/var/lib/misc/sinai-dnsmasq.leases >>"${LOG_FILE}" 2>&1 &
  sleep 2
  ip addr show "${IFACE}" || true
}

start_app() {
  log "Starting Ollama and Sinai web app on port 80."
  systemctl enable --now ollama >/dev/null 2>&1 || true

  if [ ! -x "${APP_DIR}/.venv/bin/uvicorn" ]; then
    log "Missing ${APP_DIR}/.venv/bin/uvicorn. Cannot start app."
    exit 1
  fi

  cd "${APP_DIR}"
  nohup env \
    HOME=/home/pi \
    OLLAMA_HOST=http://127.0.0.1:11434 \
    OLLAMA_MODEL="${MODEL}" \
    SINAI_OLLAMA_HOST=http://127.0.0.1:11434 \
    SINAI_OLLAMA_MODEL="${MODEL}" \
    SINAI_OLLAMA_TIMEOUT=60 \
    SINAI_OLLAMA_MAX_TOKENS=80 \
    SINAI_OLLAMA_CONTEXT_WINDOW=1536 \
    SINAI_OLLAMA_KEEP_ALIVE=20m \
    "${APP_DIR}/.venv/bin/uvicorn" app.local_web.server:app --host 0.0.0.0 --port 80 >>"${LOG_FILE}" 2>&1 &

  for _ in $(seq 1 30); do
    if curl -fsS --max-time 2 "http://127.0.0.1/client" >/dev/null 2>&1; then
      log "Web app is live."
      return 0
    fi
    sleep 1
  done

  log "Web app did not answer yet. Last log lines follow."
  tail -80 "${LOG_FILE}" || true
  exit 1
}

open_monitor() {
  if command -v sudo >/dev/null 2>&1; then
    sudo -u pi DISPLAY=:0 XAUTHORITY=/home/pi/.Xauthority nohup chromium-browser \
      --kiosk http://127.0.0.1/monitor \
      --no-first-run \
      --no-default-browser-check \
      --password-store=basic \
      --use-mock-keychain >/dev/null 2>&1 || true
  fi
}

main() {
  stop_old_stack
  configure_wifi
  start_network
  start_app
  open_monitor
  log "READY: Wi-Fi=${SSID} password=${PASSWORD} phone=http://${AP_IP}/client monitor=http://${AP_IP}/monitor"
}

main "$@"
