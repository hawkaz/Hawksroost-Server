#!/usr/bin/env bash
# Read-only look at the cabin laptop. Changes nothing. Safe to run any time.
#   bash /opt/hawksroost/scripts/inventory.sh
set -uo pipefail
say()  { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
ok()   { printf '  OK    %s\n' "$1"; }
warn() { printf '  CHECK %s\n' "$1"; }

say "System"
. /etc/os-release 2>/dev/null && echo "  $PRETTY_NAME"
echo "  Host: $(hostname)   Kernel: $(uname -r)"
echo "  CPU: $(nproc) cores   RAM: $(free -h | awk '/Mem:/{print $2" total, "$7" free"}')"
df -h / | awk 'NR==2{print "  Disk /: "$4" free of "$2" ("$5" used)"}'
if [ -d /opt/hawksroost ]; then df -h /opt/hawksroost | awk 'NR==2{print "  Disk for /opt/hawksroost: "$4" free"}'; fi

say "Battery (always-on laptop)"
for b in /sys/class/power_supply/BAT*; do
  [ -d "$b" ] || continue
  echo "  $(basename "$b"): $(cat "$b/capacity" 2>/dev/null)% $(cat "$b/status" 2>/dev/null)"
  for f in charge_control_start_threshold charge_control_end_threshold; do
    [ -f "$b/$f" ] && echo "  $f = $(cat "$b/$f")"
  done
done
[ -d /sys/class/power_supply/BAT0 ] || warn "No battery reported"

say "Docker"
if command -v docker >/dev/null; then
  docker --version
  docker compose version 2>/dev/null || warn "docker compose plugin missing"
  if docker ps >/dev/null 2>&1; then ok "This user can run docker without sudo"; else warn "docker needs sudo for this user"; fi
  echo; docker ps --format '  {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || sudo -n docker ps 2>/dev/null
else
  warn "Docker not installed"
fi

say "Ports in use"
ss -tlnH 2>/dev/null | awk '{print "  "$4}' | sort -u
for p in 80 443 8080; do
  if ss -tlnH "sport = :$p" 2>/dev/null | grep -q .; then warn "Port $p is in use"; else ok "Port $p is free"; fi
done

say "nginx on the host"
if command -v nginx >/dev/null; then
  warn "nginx installed on the host: $(nginx -v 2>&1)"; systemctl is-active nginx 2>/dev/null | sed 's/^/  service: /'
  ls /etc/nginx/sites-enabled 2>/dev/null | sed 's/^/  site: /'
else
  ok "No host nginx (the app brings its own in a container)"
fi

say "Network"
ip -4 -o addr show scope global | awk '{print "  "$2": "$4}'
echo "  Default route: $(ip route show default | head -1)"
if ping -c1 -W2 192.168.100.1 >/dev/null 2>&1; then ok "Starlink dish answers at 192.168.100.1"; else warn "No answer from the Starlink dish at 192.168.100.1"; fi
if timeout 3 bash -c '</dev/tcp/192.168.100.1/9200' 2>/dev/null; then ok "Starlink status port 9200 open"; else warn "Starlink port 9200 not reachable"; fi

say "Tempest (listening 70 seconds on UDP 50222)"
if command -v python3 >/dev/null; then
  python3 - <<'PY' || warn "Couldn't listen on UDP 50222 (is the collector already running? then this check isn't needed)"
import json, socket, time
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 50222)); s.settimeout(5)
end, seen = time.time() + 70, {}
while time.time() < end:
    try:
        data, addr = s.recvfrom(4096)
    except socket.timeout:
        continue
    m = json.loads(data); k = (m.get("serial_number"), m.get("type")); seen[k] = addr[0]
for (serial, kind), ip in sorted(seen.items(), key=str):
    print(f"  heard {kind} from {serial} ({ip})")
print("  OK    Tempest hub is on this network" if seen else "  CHECK Nothing heard from a Tempest hub")
PY
else
  warn "python3 not installed; skipping"
fi

say "RTL-SDR"
if lsusb 2>/dev/null | grep -qi 0bda:2838; then ok "$(lsusb | grep -i 0bda:2838)"; else warn "No RTL-SDR on USB"; fi
docker ps --format '{{.Names}} {{.Image}}' 2>/dev/null | grep -i -E 'owrx|openwebrx' | sed 's/^/  CHECK OpenWebRX running: /'

say "Watchtower"
docker ps --format '{{.Names}} {{.Image}}' 2>/dev/null | grep -i watchtower | sed 's/^/  /' || true

say "Existing copies of this repo"
find / -maxdepth 4 -type d -name '.git' -path '*awksroost*' 2>/dev/null | sed 's#/.git$##; s/^/  /'
echo; echo "Done. Copy everything above and paste it back to Claude."
