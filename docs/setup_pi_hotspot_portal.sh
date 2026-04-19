#!/usr/bin/env bash
set -euo pipefail

# Configure Raspberry Pi as Sinai local hotspot with captive redirect.
#
# Usage:
#   sudo bash docs/setup_pi_hotspot_portal.sh [ssid] [passphrase] [ap_ip]
#
# Example:
#   sudo bash docs/setup_pi_hotspot_portal.sh Sinai-Node SinaiDemo2026 192.168.50.1

SSID="${1:-Sinai-Node}"
PASSPHRASE="${2:-SinaiDemo2026}"
AP_IP="${3:-192.168.50.1}"
WLAN_IFACE="${WLAN_IFACE:-wlan0}"
COUNTRY_CODE="${COUNTRY_CODE:-US}"
PROFILE_NAME="${PROFILE_NAME:-sinai-hotspot}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash $0 [ssid] [passphrase] [ap_ip]"
  exit 1
fi

if [[ "${#PASSPHRASE}" -lt 8 ]]; then
  echo "Passphrase must be at least 8 characters."
  exit 1
fi

log() {
  echo "[Sinai Hotspot] $*"
}

AP_NET_PREFIX="$(echo "${AP_IP}" | awk -F. '{print $1"."$2"."$3}')"
DHCP_START="${AP_NET_PREFIX}.20"
DHCP_END="${AP_NET_PREFIX}.250"
SINAI_URL="http://${AP_IP}:8501/"

configure_nginx_redirect() {
  log "Configuring captive redirect on port 80..."
  apt-get install -y nginx

  cat > /etc/nginx/sites-available/sinai-captive <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location = /generate_204 {
        return 302 ${SINAI_URL};
    }
    location = /hotspot-detect.html {
        return 302 ${SINAI_URL};
    }
    location = /ncsi.txt {
        return 302 ${SINAI_URL};
    }
    location / {
        return 302 ${SINAI_URL};
    }
}
EOF

  rm -f /etc/nginx/sites-enabled/default
  ln -sf /etc/nginx/sites-available/sinai-captive /etc/nginx/sites-enabled/sinai-captive
  nginx -t
  systemctl enable --now nginx
  systemctl restart nginx
}

configure_with_dhcpcd() {
  log "Using hostapd + dnsmasq path (dhcpcd detected)."
  apt-get update
  apt-get install -y hostapd dnsmasq nginx

  systemctl stop hostapd || true
  systemctl stop dnsmasq || true

  log "Configuring static IP for ${WLAN_IFACE} in /etc/dhcpcd.conf..."
  sed -i '/# >>> SINAI HOTSPOT >>>/,/# <<< SINAI HOTSPOT <<</d' /etc/dhcpcd.conf
  cat >> /etc/dhcpcd.conf <<EOF
# >>> SINAI HOTSPOT >>>
interface ${WLAN_IFACE}
static ip_address=${AP_IP}/24
nohook wpa_supplicant
# <<< SINAI HOTSPOT <<<
EOF

  log "Writing hostapd configuration..."
  cat > /etc/hostapd/hostapd.conf <<EOF
country_code=${COUNTRY_CODE}
interface=${WLAN_IFACE}
ssid=${SSID}
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=${PASSPHRASE}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF

  if grep -q '^DAEMON_CONF=' /etc/default/hostapd; then
    sed -i 's|^DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
  else
    echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' >> /etc/default/hostapd
  fi

  log "Writing dnsmasq DHCP + DNS override..."
  cat > /etc/dnsmasq.d/sinai-hotspot.conf <<EOF
interface=${WLAN_IFACE}
bind-interfaces
dhcp-range=${DHCP_START},${DHCP_END},255.255.255.0,24h
domain-needed
bogus-priv
address=/#/${AP_IP}
EOF

  configure_nginx_redirect

  log "Bringing up hotspot services..."
  rfkill unblock wlan || true
  systemctl unmask hostapd || true
  if systemctl list-unit-files | grep -q '^dhcpcd\.service'; then
    systemctl restart dhcpcd
  else
    ip link set "${WLAN_IFACE}" down || true
    ip addr flush dev "${WLAN_IFACE}" || true
    ip addr add "${AP_IP}/24" dev "${WLAN_IFACE}"
    ip link set "${WLAN_IFACE}" up
  fi
  systemctl enable --now hostapd
  systemctl enable --now dnsmasq
}

configure_with_nmcli() {
  log "Using NetworkManager hotspot path."
  apt-get update
  apt-get install -y network-manager nginx

  systemctl enable --now NetworkManager
  rfkill unblock wlan || true

  mkdir -p /etc/NetworkManager/dnsmasq-shared.d
  cat > /etc/NetworkManager/dnsmasq-shared.d/sinai-hotspot.conf <<EOF
address=/#/${AP_IP}
EOF

  nmcli connection delete "${PROFILE_NAME}" >/dev/null 2>&1 || true
  nmcli connection add \
    type wifi \
    ifname "${WLAN_IFACE}" \
    con-name "${PROFILE_NAME}" \
    autoconnect yes \
    ssid "${SSID}"

  nmcli connection modify "${PROFILE_NAME}" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    802-11-wireless-security.key-mgmt wpa-psk \
    802-11-wireless-security.psk "${PASSPHRASE}" \
    ipv4.method shared \
    ipv4.addresses "${AP_IP}/24" \
    ipv6.method ignore

  configure_nginx_redirect

  systemctl restart NetworkManager
  nmcli connection up "${PROFILE_NAME}"
}

if [[ -f /etc/dhcpcd.conf ]]; then
  configure_with_dhcpcd
elif command -v nmcli >/dev/null 2>&1; then
  configure_with_nmcli
else
  log "Neither dhcpcd nor nmcli path available. Install NetworkManager or dhcpcd."
  exit 1
fi

log "Completed."
echo "SSID: ${SSID}"
echo "Passphrase: ${PASSPHRASE}"
echo "Open Sinai on phones: ${SINAI_URL}"
echo "If captive portal does not auto-open, browse manually to: ${SINAI_URL}"
