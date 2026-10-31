#!/usr/bin/env bash
# One-time prep of the cabin laptop (HAWKSROOST). Safe to re-run.
#   sudo bash /opt/hawksroost/scripts/server-prep.sh
#
# Sets cabin time zone, installs updates, nightly reboot window for kernel
# updates, clean shutdown on low battery, firewall rule for the Tempest hub,
# Docker log limits; removes old containers/data; turns off Wi-Fi and unused
# desktop services. Home Assistant and Watchtower are kept.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "FAIL  run it with sudo: sudo bash $0"; exit 1; }
OWNER="${SUDO_USER:-chris}"
HOME_DIR=$(getent passwd "$OWNER" | cut -d: -f6)
STACK_DIR="$HOME_DIR/Docker"           # Home Assistant + Watchtower compose
OLD_REPO="$HOME_DIR/hawksroost-server" # first SDR test (recordings)

step() { printf '\n== %s\n' "$1"; }
ok()   { echo "OK    $1"; }
note() { echo "NOTE  $1"; }

# --- 1. Time zone ----------------------------------------------------------------
step "Time zone"
timedatectl set-timezone America/Phoenix
ok "America/Phoenix (MST all year)"

# --- 2. Updates ------------------------------------------------------------------
step "Updates (a few minutes)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold full-upgrade
apt-get -y -q install upower
apt-get -y -q autoremove
ok "system up to date"

cat > /etc/apt/apt.conf.d/52hawksroost-reboot <<'EOF'
// Hawksroost: reboot at night when an update needs it (containers restart by themselves).
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF
ok "automatic security updates reboot at 4:00 am when needed"

# --- 3. Low battery -> clean shutdown ----------------------------------------------
step "Low-battery shutdown"
CONF=/etc/UPower/UPower.conf
set_key() {
  if grep -qE "^#?$1=" "$CONF"; then sed -i -E "s|^#?$1=.*|$1=$2|" "$CONF"; else echo "$1=$2" >> "$CONF"; fi
}
set_key UsePercentageForPolicy true
set_key PercentageLow 20.0
set_key PercentageCritical 10.0
set_key PercentageAction 7.0
set_key CriticalPowerAction PowerOff
# Debian only starts UPower when a desktop asks for it. This laptop has no
# desktop, so start it at every boot or the low-battery shutdown never happens.
cat > /etc/systemd/system/hawksroost-upower.service <<'UNIT'
[Unit]
Description=Keep UPower running for the low-battery shutdown (Hawksroost)
Wants=upower.service
After=upower.service

[Service]
Type=oneshot
ExecStart=/usr/bin/upower --enumerate
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable hawksroost-upower.service >/dev/null 2>&1
systemctl restart upower
systemctl restart hawksroost-upower.service
if upower -d | grep -q 'critical-action:.*PowerOff'; then
  ok "UPower starts at boot; shuts down cleanly at 7% battery (Wake on AC powers it back on)"
else
  echo "FAIL  UPower isn't reporting PowerOff — send this output to Claude"
  upower -d | grep -A12 'Daemon:' || true
fi

# --- 4. Firewall: Tempest broadcasts -----------------------------------------------
step "Firewall"
IFACE=$(ip route show default | awk '{print $5; exit}')
SUBNET=$(python3 -c "import ipaddress,sys; print(ipaddress.ip_interface(sys.argv[1]).network)" \
  "$(ip -o -4 addr show dev "$IFACE" | awk '{print $4; exit}')")
ufw allow from "$SUBNET" to any port 50222 proto udp comment 'Tempest weather hub' >/dev/null
ok "UDP 50222 allowed from $SUBNET (Tempest)"

# --- 5. Old containers and data ------------------------------------------------------
step "Old containers and data"
if docker rm -f hawksroost-airband >/dev/null 2>&1; then ok "removed old test recorder container"; else ok "old test recorder already gone"; fi
if [ -d "$OLD_REPO" ]; then
  rm -rf "$OLD_REPO"
  ok "removed $OLD_REPO (old NOAA test recordings)"
fi

if [ -f "$STACK_DIR/docker-compose.yml" ] && grep -q 'nginx-proxy-manager\|portainer\|owrx' "$STACK_DIR/docker-compose.yml"; then
  cp "$STACK_DIR/docker-compose.yml" "$STACK_DIR/docker-compose.yml.bak-$(date +%Y%m%d)"
  cat > "$STACK_DIR/docker-compose.yml" <<'EOF'
services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: homeassistant
    restart: always
    ports:
      - "8123:8123"
    volumes:
      - ./homeassistant/config:/config
      - /etc/localtime:/etc/localtime:ro

  watchtower:
    image: containrrr/watchtower
    container_name: watchtower
    restart: always
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --cleanup --schedule "0 0 3 * * *" --include-restarting
EOF
  ok "~/Docker/docker-compose.yml now has Home Assistant + Watchtower (backup saved beside it)"
fi
for c in owrx nginx-proxy-manager portainer; do
  if docker rm -f "$c" >/dev/null 2>&1; then ok "removed container $c"; fi
done
for v in docker_nginx_data docker_nginx_letsencrypt docker_portainer_data docker_openwebrx_settings portainer_data; do
  if docker volume rm "$v" >/dev/null 2>&1; then ok "removed volume $v"; fi
done
for d in OpenWebRX openwebrx sdrpp; do
  if [ -d "$STACK_DIR/$d" ]; then rm -rf "${STACK_DIR:?}/$d"; ok "removed ~/Docker/$d"; fi
done

# --- 6. Wi-Fi off (Ethernet only) ----------------------------------------------------
step "Wi-Fi"
WIFI_DEV=$(nmcli -t -f DEVICE,TYPE device | awk -F: '$2=="wifi"{print $1; exit}')
if [ -n "$WIFI_DEV" ]; then
  WIFI_IP=$(nmcli -g IP4.ADDRESS device show "$WIFI_DEV" | head -1 | cut -d/ -f1)
  if [ -n "$WIFI_IP" ] && ss -Htn state established '( sport = :22 )' | awk '{print $3}' | grep -q "^$WIFI_IP:"; then
    note "you're connected over Wi-Fi ($WIFI_IP) — skipped. Reconnect to the Ethernet address and run this again."
  else
    nmcli -t -f NAME,TYPE connection show | awk -F: '$2=="802-11-wireless"{print $1}' | while IFS= read -r con; do
      nmcli connection modify "$con" connection.autoconnect no
    done
    nmcli radio wifi off
    ok "Wi-Fi off and won't reconnect after reboot (Ethernet only)"
  fi
else
  ok "no Wi-Fi device"
fi

# --- 7. Unused desktop services ------------------------------------------------------
step "Unused services"
for u in cups-browsed.service cups.service cups.socket cups.path bluetooth.service ModemManager.service; do
  if systemctl list-unit-files "$u" --no-legend 2>/dev/null | grep -q .; then
    systemctl disable --now "$u" >/dev/null 2>&1 || true
    ok "turned off $u"
  fi
done

# --- 8. Docker log limits + clean up ------------------------------------------------
step "Docker"
if [ ! -f /etc/docker/daemon.json ]; then
  cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
  ok "log limits: 10 MB x 3 per container"
  LOGS_NEW=1
  systemctl restart docker
  ok "Docker restarted"
else
  note "/etc/docker/daemon.json already exists — left alone"
fi
if systemctl is-enabled --quiet docker; then ok "Docker starts at boot"; else systemctl enable docker containerd >/dev/null 2>&1; ok "Docker set to start at boot"; fi
# Recreate Home Assistant + Watchtower once, so they pick up the new log limits.
RECREATE=""; [ "${LOGS_NEW:-0}" = 1 ] && RECREATE="--force-recreate"
(cd "$STACK_DIR" && docker compose up -d $RECREATE --remove-orphans) >/dev/null 2>&1 \
  && ok "Home Assistant and Watchtower running" \
  || note "couldn't restart ~/Docker stack — check: cd ~/Docker && docker compose up -d"
docker image prune -af >/dev/null && docker volume prune -f >/dev/null && docker builder prune -af >/dev/null
ok "unused Docker images, volumes and build cache removed"

# --- Summary ---------------------------------------------------------------------
step "Done"
df -h / | awk 'NR==2{print "Disk: "$4" free"}'
docker ps --format '  {{.Names}}: {{.Status}}'
if [ -f /var/run/reboot-required ]; then
  echo "NOTE  an update needs a reboot — Claude will have you reboot next."
fi
echo "Still to do at the laptop: BIOS → Wake on AC."
