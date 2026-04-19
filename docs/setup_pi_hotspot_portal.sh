#!/usr/bin/env bash
set -euo pipefail

# Configure Raspberry Pi as a local Sinai hotspot with captive redirect.
# This keeps all traffic local and redirects phone browser checks to Sinai.
#
# Usage:
#   sudo bash docs/setup_pi_hotspot_portal.sh [ssid] [passphrase] [ap_ip]
# Example:
#   sudo bash docs/setup_pi_hotspot_portal.sh Sinai-Node SinaiDemo2026 192.168.50.1

SSID="${1:-Sinai-Node}"
PASSPHRASE="${2:-SinaiDemo2026}"
AP_IP="${3:-192.168.50.1}"
WLAN_IFACE="${WLAN_IFACE:-wlan0}"
COUNTRY_CODE="${COUNTRY_CODE:-US}"

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

log "Installing hotspot and captive dependencies..."
apt-get update
apt-get install -y hostapd dnsmasq nginx

log "Stopping services before reconfiguration..."
systemctl stop hostapd || true
systemctl stop dnsmasq || true

log "Configuring static IP for ${WLAN_IFACE}..."
if [[ ! -f /etc/dhcpcd.conf ]]; then
  echo "/etc/dhcpcd.conf not found."
  exit 1
fi
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

log "Writing dnsmasq DHCP + local DNS override..."
cat > /etc/dnsmasq.d/sinai-hotspot.conf <<EOF
interface=${WLAN_IFACE}
bind-interfaces
dhcp-range=${DHCP_START},${DHCP_END},255.255.255.0,24h
domain-needed
bogus-priv
address=/#/${AP_IP}
EOF

log "Configuring captive redirect on port 80..."
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

log "Reloading network and starting services..."
rfkill unblock wlan || true
systemctl restart dhcpcd
systemctl enable --now hostapd
systemctl enable --now dnsmasq
systemctl restart nginx

log "Completed."
echo "SSID: ${SSID}"
echo "Passphrase: ${PASSPHRASE}"
echo "Open Sinai on phones: ${SINAI_URL}"
echo "If captive portal does not auto-open, browse manually to: ${SINAI_URL}"
